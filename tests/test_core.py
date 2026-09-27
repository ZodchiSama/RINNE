import gzip
import sys
from datetime import date, timedelta

import pytest

from rinne import mal, recommender, scheduler
from rinne.models import (
    COMPLETED, CURRENTLY_AIRING, FINISHED_AIRING, NOT_YET_AIRED, ON_HOLD, PLAN_TO_WATCH, WATCHING,
    Anime, Settings,
)
from rinne.storage import State, load_state, save_state

MONDAY = date(2026, 9, 21)

EXPORT = b"""<?xml version="1.0" encoding="UTF-8" ?>
<myanimelist>
  <myinfo><user_name>tester</user_name></myinfo>
  <anime>
    <series_animedb_id>5114</series_animedb_id>
    <series_title><![CDATA[Fullmetal Alchemist: Brotherhood]]></series_title>
    <series_type>TV</series_type><series_episodes>64</series_episodes>
    <my_watched_episodes>10</my_watched_episodes><my_score>10</my_score>
    <my_status>Watching</my_status><my_priority>HIGH</my_priority>
  </anime>
  <anime>
    <series_animedb_id>9253</series_animedb_id>
    <series_title><![CDATA[Steins;Gate]]></series_title>
    <series_type>TV</series_type><series_episodes>24</series_episodes>
    <my_watched_episodes>0</my_watched_episodes><my_score>0</my_score>
    <my_status>Plan to Watch</my_status><my_priority>LOW</my_priority>
  </anime>
</myanimelist>
"""


def show(mal_id, title=None, **kw):
    kw.setdefault("episodes_total", 12)
    kw.setdefault("airing_status", FINISHED_AIRING)
    kw.setdefault("enriched", True)
    return Anime(mal_id=mal_id, title=title or f"Show {mal_id}", **kw)


def make_state(*shows, **settings):
    return State(library={a.mal_id: a for a in shows}, settings=Settings(**settings))


# --------------------------------------------------------------------------- import


@pytest.mark.parametrize("compress", [False, True])
def test_parse_export(tmp_path, compress):
    p = tmp_path / "list.xml"
    p.write_bytes(gzip.compress(EXPORT) if compress else EXPORT)
    entries = {a.mal_id: a for a in mal.parse_mal_export(p)}
    fma = entries[5114]
    assert fma.title == "Fullmetal Alchemist: Brotherhood"
    assert (fma.status, fma.episodes_watched, fma.episodes_total, fma.priority) == (WATCHING, 10, 64, 2)
    assert entries[9253].status == PLAN_TO_WATCH


def test_parse_rejects_garbage(tmp_path):
    p = tmp_path / "x.xml"
    p.write_text("not xml")
    with pytest.raises(mal.ImportError_):
        mal.parse_mal_export(p)


def test_merge_keeps_local_progress_but_respects_on_hold():
    lib = {1: show(1, status=WATCHING, episodes_watched=8, genres=["Action"])}
    mal.merge_import(lib, [Anime(1, "Show 1", status=PLAN_TO_WATCH, episodes_watched=3)])
    assert (lib[1].status, lib[1].episodes_watched, lib[1].genres) == (WATCHING, 8, ["Action"])
    mal.merge_import(lib, [Anime(1, "Show 1", status=ON_HOLD, episodes_watched=3)])
    assert lib[1].status == ON_HOLD


def test_jikan_parsing():
    a = Anime(1, "x")
    mal._apply_jikan(a, {
        "score": 8.5, "episodes": 25, "duration": "1 hr 2 min", "status": "Currently Airing",
        "broadcast": {"day": "Saturdays"}, "aired": {"from": "2026-07-04T00:00:00+00:00"},
        "genres": [{"name": "Action"}], "themes": [{"name": "Military"}],
        "relations": [{"relation": "Sequel", "entry": [{"mal_id": 2, "type": "anime"},
                                                        {"mal_id": 3, "type": "manga"}]}],
    })
    assert a.episode_minutes == 62 and a.broadcast_day == 5 and a.airing_status == CURRENTLY_AIRING
    assert a.genres == ["Action", "Military"] and a.relations == {"sequel": [2]}


# --------------------------------------------------------------------------- recommender


def lib_of(*shows):
    return {a.mal_id: a for a in shows}


def test_follows_series_over_higher_rated_show():
    s1 = show(1, status=COMPLETED, genres=["Action"], relations={"sequel": [2]})
    s2 = show(2, genres=["Action"], relations={"prequel": [1]}, mean_score=7.5)
    other = show(3, genres=["Romance"], mean_score=9.1, priority=2)
    sug = recommender.pick_replacement(lib_of(s1, s2, other), s1, [])
    assert sug.anime is s2 and sug.kind == recommender.SERIES
    assert "Next in the series" in sug.headline


def test_series_skips_completed_seasons_and_resumes_on_hold():
    s1 = show(1, status=COMPLETED, relations={"sequel": [2]})
    s2 = show(2, status=COMPLETED, relations={"sequel": [3]})
    s3 = show(3, status=ON_HOLD, episodes_watched=4)
    sug = recommender.pick_replacement(lib_of(s1, s2, s3, show(9, mean_score=9.9)), s1, [])
    assert sug.anime is s3
    assert any("Show 2" in r for _, r in sug.reasons)
    assert any("episode 5" in r for _, r in sug.reasons)


def test_unlisted_sequel_becomes_placeholder_offline():
    s1 = show(1, status=COMPLETED, relations={"sequel": [50]}, relation_titles={"50": "S1 Season 2"})
    sug = recommender.pick_replacement(lib_of(s1, show(9)), s1, [])
    assert sug.kind == recommender.SERIES and sug.anime.title == "S1 Season 2"


def test_unaired_sequel_falls_back_with_explanation():
    s1 = show(1, status=COMPLETED, relations={"sequel": [2]})
    s2 = show(2, airing_status=NOT_YET_AIRED)
    s3 = show(3)
    sug = recommender.pick_replacement(lib_of(s1, s2, s3), s1, [])
    assert sug.anime is s3 and sug.kind == recommender.PICK
    assert "hasn't aired" in sug.headline


def test_unwatched_prequel_is_pushed_down():
    s1 = show(1, status=PLAN_TO_WATCH, mean_score=7.0)
    s2 = show(2, relations={"prequel": [1]}, mean_score=8.0)
    ranked = recommender.rank({1: s1, 2: s2}, active=[])
    assert [s.anime.mal_id for s in ranked] == [1, 2]


def test_taste_profile_and_exclusions():
    lib = {
        1: show(1, status=COMPLETED, user_score=10, genres=["Mystery"]),
        2: show(2, status=COMPLETED, user_score=10, genres=["Mystery"]),
        3: show(3, status=COMPLETED, user_score=4, genres=["Sports"]),
        4: show(4, genres=["Sports"], mean_score=8.0),
        5: show(5, genres=["Mystery"], mean_score=8.0),
        6: show(6, genres=["Mystery"], mean_score=9.9, excluded=True),
        7: show(7, genres=["Mystery"], mean_score=9.9, airing_status=NOT_YET_AIRED),
    }
    ranked = recommender.rank(lib, active=[])
    assert [s.anime.mal_id for s in ranked] == [5, 4]


# --------------------------------------------------------------------------- scheduler


def test_only_watching_shows_are_scheduled():
    st = make_state(show(1, status=WATCHING), show(2, status=PLAN_TO_WATCH, priority=2),
                    daily_episodes=[3] * 7)
    plan = scheduler.build_week(st, MONDAY)
    assert {i.mal_id for i in plan.items} == {1}


def test_episodes_per_day_mode_and_soft_cap():
    st = make_state(
        show(1, status=WATCHING, episodes_total=100), show(2, status=WATCHING, episodes_total=100),
        daily_episodes=[4, 0, 1, 1, 1, 6, 6], max_eps_per_show_per_day=2,
    )
    plan = scheduler.build_week(st, MONDAY)
    assert [len(plan.for_day(d)) for d in range(7)] == [4, 0, 1, 1, 1, 6, 6]
    monday = [i.mal_id for i in plan.for_day(0)]
    assert monday.count(1) == 2 and monday.count(2) == 2  # cap respected when possible
    assert st.library[1].episodes_watched == 0  # simulation doesn't touch real data


def test_minutes_mode_respects_budget():
    st = make_state(
        show(1, status=WATCHING, episodes_watched=2, episode_minutes=24),
        show(2, status=WATCHING, episode_minutes=45),
        plan_by="minutes", daily_minutes=[48, 48, 0, 70, 48, 96, 96],
    )
    plan = scheduler.build_week(st, MONDAY)
    assert not plan.for_day(2)
    for d in range(7):
        used = sum(st.library[i.mal_id].minutes_per_episode for i in plan.for_day(d))
        assert used <= st.settings.daily_minutes[d] or len(plan.for_day(d)) == 1
    eps = [i.episode for i in plan.items if i.mal_id == 1]
    assert eps == list(range(3, 3 + len(eps)))


def test_finale_is_labelled_with_next_season_but_not_scheduled():
    st = make_state(
        show(1, status=WATCHING, episodes_watched=10, relations={"sequel": [2]}),
        show(2, relations={"prequel": [1]}, title="Season 2"),
        daily_episodes=[2] * 7,
    )
    plan = scheduler.build_week(st, MONDAY)
    assert [(i.mal_id, i.episode) for i in plan.items] == [(1, 11), (1, 12)]
    assert plan.items[-1].note == "Finale — next up: Season 2"


def test_airing_show_paced_by_release():
    airing = show(1, status=WATCHING, episodes_total=12, episodes_watched=2,
                  airing_status=CURRENTLY_AIRING, aired_from="2026-09-03")  # a Thursday
    st = make_state(airing, daily_episodes=[3] * 7)
    plan = scheduler.build_week(st, MONDAY)
    by_day = {i.episode: i.day for i in plan.items}
    # Eps 1-3 aired by Sep 17; ep 4 on Thursday Sep 24.
    assert by_day == {3: 0, 4: 3}


def test_finishing_fetches_and_adds_unlisted_sequel():
    s1 = show(1, status=WATCHING, episodes_watched=11, relations={"sequel": [2]})
    st = make_state(s1, show(3, mean_score=9.9), daily_episodes=[2] * 7)
    scheduler.replan(st, MONDAY)
    finale = st.week.items[0]
    event = scheduler.toggle_item(st, finale, MONDAY)
    assert event.finished is s1 and s1.status == COMPLETED

    calls = []

    def fetch(mal_id):
        calls.append(mal_id)
        return show(mal_id, title="Season 2", episodes_total=12, relations={"prequel": [1]})

    sug, fetched = scheduler.find_replacement(st, s1, fetch, MONDAY)
    assert calls == [2] and sug.anime.title == "Season 2" and 2 not in st.library
    applied = scheduler.apply_replacement(st, sug, fetched, MONDAY)
    s2 = st.library[2]
    assert s2.status == WATCHING and s2.added_by_app and applied.added == [s2]
    scheduler.replan(st, MONDAY)
    assert any(i.mal_id == 2 for i in st.week.items)
    # Unchecking the finale reopens the first season.
    scheduler.toggle_item(st, finale, MONDAY)
    assert s1.status == WATCHING and s1.episodes_watched == 11


def test_refetch_keeps_list_status():
    s1 = show(1, status=COMPLETED, episodes_watched=12, relations={"sequel": [2]})
    s2 = show(2, status=COMPLETED, enriched=False)
    st = make_state(s1, s2, show(3, relations={"prequel": [2]}, enriched=False, status=ON_HOLD))

    def fetch(mal_id):
        rel = {2: {"sequel": [3]}, 3: {"prequel": [2]}}[mal_id]
        return show(mal_id, relations=rel)  # fetched copies default to Plan to Watch

    sug, fetched = scheduler.find_replacement(st, s1, fetch, MONDAY)
    assert sug.anime.mal_id == 3 and fetched[2].status == COMPLETED


def test_show_being_replaced_counts_as_finished_prequel():
    s1 = show(1, status=WATCHING, episodes_watched=10, genres=["Drama"])
    s2 = show(2, relations={"prequel": [1]}, genres=["Drama"])
    top = recommender.rank(lib_of(s1, s2), finished=s1, active=[s1])[0]
    assert top.anime is s2 and not any("first" in r for _, r in top.reasons)


def test_plan_starts_today_and_uses_that_weekdays_amount():
    thursday = date(2026, 9, 24)
    st = make_state(show(1, status=WATCHING, episodes_total=50),
                    daily_episodes=[1, 1, 1, 3, 1, 1, 1])  # Thursday = 3
    scheduler.replan(st, thursday)
    assert st.week.week_start == "2026-09-24"
    assert [len(st.week.for_day(d)) for d in range(7)] == [3, 1, 1, 1, 1, 1, 1]


def test_fresh_plan_discards_past_days():
    st = make_state(show(1, status=WATCHING, episodes_total=50), daily_episodes=[2] * 7)
    scheduler.replan(st, MONDAY)
    scheduler.toggle_item(st, st.week.items[0], MONDAY)
    wednesday = date(2026, 9, 23)
    scheduler.replan(st, wednesday)  # keeps Monday's history
    assert st.week.week_start == MONDAY.isoformat() and st.week.items[0].done
    scheduler.fresh_plan(st, wednesday)
    assert st.week.week_start == wednesday.isoformat()
    assert not any(i.done for i in st.week.items) and st.week.items[0].episode == 2


def test_expired_plan_rolls_over():
    st = make_state(show(1, status=WATCHING, episodes_total=50), daily_episodes=[1] * 7)
    scheduler.replan(st, MONDAY)
    later = date(2026, 9, 30)
    assert scheduler.plan_expired(st, later)
    scheduler.replan(st, later)
    assert st.week.week_start == later.isoformat()


def test_anilist_parsing_and_exact_airing():
    from rinne import anilist
    a = Anime(1, "#1")
    anilist.apply_media(a, {
        "id": 99, "idMal": 1, "title": {"romaji": "Ao no Hako", "english": "Blue Box", "native": "アオのハコ"},
        "format": "TV", "episodes": 25, "duration": 23, "status": "RELEASING", "averageScore": 82,
        "genres": ["Romance", "Sports"], "tags": [{"name": "Basketball", "rank": 90, "isMediaSpoiler": False},
                                                  {"name": "Twist", "rank": 95, "isMediaSpoiler": True}],
        "startDate": {"year": 2026, "month": 7, "day": 2},
        "nextAiringEpisode": {"episode": 13, "airingAt": 1790000000},
        "coverImage": {"extraLarge": "http://x/c.jpg", "color": "#e4a150"}, "bannerImage": "http://x/b.jpg",
        "relations": {"edges": [
            {"relationType": "SEQUEL", "node": {"idMal": 2, "type": "ANIME", "title": {"romaji": "S2"}}},
            {"relationType": "ADAPTATION", "node": {"idMal": 3, "type": "MANGA", "title": {"romaji": "M"}}}]},
    })
    assert a.title == "Ao no Hako" and a.title_english == "Blue Box" and a.mean_score == 8.2
    assert a.genres == ["Romance", "Sports", "Basketball"] and a.relations == {"sequel": [2]}
    assert a.relation_titles == {"2": "S2"} and a.airing_status == CURRENTLY_AIRING
    nxt = date.fromisoformat(a.next_airing[:10])
    assert a.episodes_available(nxt - timedelta(days=1)) == 12
    assert a.episodes_available(nxt) == 13
    assert a.episodes_available(nxt + timedelta(days=7)) == 14


def test_title_language():
    from rinne import models
    a = Anime(1, "Sousou no Frieren", title_english="Frieren: Beyond Journey's End",
              title_native="葬送のフリーレン")
    b = Anime(2, "Monster")
    try:
        models.title_language = models.ENGLISH
        assert a.name == "Frieren: Beyond Journey's End" and b.name == "Monster"
        models.title_language = models.NATIVE
        assert a.name == "葬送のフリーレン"
    finally:
        models.title_language = models.ROMAJI
    assert a.name == "Sousou no Frieren"


def test_replacement_records_why():
    s1 = show(1, status=WATCHING, episodes_watched=12, relations={"sequel": [2]}, title="Season 1")
    s2 = show(2, relations={"prequel": [1]})
    st = make_state(s1, s2)
    sug, fetched = scheduler.find_replacement(st, s1, None, MONDAY)
    scheduler.apply_replacement(st, sug, fetched, MONDAY, finished=s1)
    assert s2.origin["replaced"] == "Season 1" and s2.origin["kind"] == "series"
    assert any("Next in the series" in r for r in s2.origin["reasons"])


def test_state_roundtrip(tmp_path):
    st = make_state(show(1, status=WATCHING, relations={"sequel": [2]},
                        relation_titles={"2": "S2"}), zoom=1.3)
    scheduler.replan(st, MONDAY)
    save_state(st, tmp_path / "s.json")
    back = load_state(tmp_path / "s.json")
    assert back.library[1].relation_titles == {"2": "S2"}
    assert back.settings.zoom == 1.3 and back.week.to_dict() == st.week.to_dict()


def test_old_state_files_still_load():
    old = {"library": [], "settings": {"slots": 4, "daily_minutes": [30] * 7}, "week": None}
    st = State.from_dict(old)
    assert st.settings.daily_minutes == [30] * 7 and st.settings.plan_by == "episodes"


def test_explain_why_for_replacement_and_plan_to_watch():
    from rinne import explain
    s1 = show(1, status=WATCHING, episodes_watched=12, relations={"sequel": [2]}, title="Season 1")
    s2 = show(2, relations={"prequel": [1]}, title="Season 2")
    s3 = show(3, mean_score=8.5, title="Other")
    st = make_state(s1, s2, s3, daily_episodes=[2] * 7)
    sug, fetched = scheduler.find_replacement(st, s1, None, MONDAY)
    scheduler.apply_replacement(st, sug, fetched, MONDAY, finished=s1)
    scheduler.replan(st, MONDAY)
    lines = explain.why(st, s2, MONDAY)
    assert lines[0].startswith("Took over from Season 1") and "next season" in lines[0]
    assert any("next is episode 1, today" in line for line in lines)
    assert any("Ranked #1" in line for line in explain.why(st, s3, MONDAY))


def test_old_jikan_entries_get_refetched_once():
    old = show(1, relations={"sequel": [2]}, relation_titles={"2": "S2"})  # enriched, no AniList data
    assert old.needs_enrichment
    old.anilist_id = 5
    assert not old.needs_enrichment


def test_when_text_formats():
    pytest.importorskip("PySide6")
    from rinne.gui.profile import when_text
    today = date(2026, 9, 27)
    assert when_text({"startDate": {"year": 2026, "month": 10, "day": 2}}, today) == \
        "Starts Fri 02 October 2026 (in 5 days)"
    assert when_text({"startDate": {"year": 2027, "month": 10}}, today) == "Expected October 2027"
    assert when_text({"startDate": {"year": 2027}, "season": "FALL", "seasonYear": 2027}, today) == \
        "Expected Fall 2027"
    assert when_text({"startDate": {}}, today) == "Release date not announced yet"


def test_upcoming_walks_finished_sequels(monkeypatch):
    from rinne import anilist
    def node(i, status, **kw):
        return {"id": i, "idMal": i, "type": "ANIME", "status": status, "title": {"romaji": f"S{i}"}, **kw}
    graph = {
        1: {**node(1, "FINISHED"), "relations": {"edges": [
            {"relationType": "SEQUEL", "node": node(2, "FINISHED")},
            {"relationType": "SUMMARY", "node": node(9, "NOT_YET_RELEASED")}]}},
        2: {**node(2, "FINISHED"), "relations": {"edges": [
            {"relationType": "PREQUEL", "node": node(1, "FINISHED")},
            {"relationType": "SEQUEL", "node": node(3, "NOT_YET_RELEASED", startDate={"year": 2027})},
            {"relationType": "SIDE_STORY", "node": node(4, "RELEASING", startDate={"year": 2026})}]}},
    }
    monkeypatch.setattr(anilist, "_chain_media", lambda i: graph.get(i, {}))
    ups = anilist.upcoming(1)
    assert [(u["node"]["id"], u["relation"]) for u in ups] == [(4, "SIDE_STORY"), (3, "SEQUEL")]
    assert ups[1]["via"] == {"romaji": "S2"}


def test_artwork_parsing_and_cache(monkeypatch, tmp_path):
    import io, json as _json
    from rinne import artwork
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    calls = []
    payload = {"images": [
        {"coverType": "Banner", "url": "http://tvdb/banner.jpg"},
        {"coverType": "Fanart", "url": "http://tvdb/fanart1080.jpg"},
        {"coverType": "Clearlogo", "url": "http://tvdb/logo.png"}]}

    def fake_urlopen(req, timeout=0):
        calls.append(req.full_url)
        return io.BytesIO(_json.dumps(payload).encode())

    monkeypatch.setattr(artwork.net, "urlopen", fake_urlopen)
    a = Anime(1, "x", anilist_id=99)
    artwork.apply(a, artwork.fetch(a.anilist_id, a.mal_id))
    assert a.fanart_url.endswith("fanart1080.jpg") and a.logo_url.endswith("logo.png") and a.artwork_checked
    artwork.fetch(99)  # second call is served from the disk cache
    assert calls == ["https://api.ani.zip/mappings?anilist_id=99"]


def test_legacy_data_folder_is_migrated(monkeypatch, tmp_path):
    from rinne import storage
    old = tmp_path / "smart-watchlist"
    old.mkdir()
    (old / "state.json").write_text('{"library": [], "settings": {"slots": 4}}')
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert storage.data_dir() == tmp_path / "rinne"
    assert (tmp_path / "rinne" / "state.json").exists() and not old.exists()
    assert storage.load_state().settings.plan_by == "episodes"


def test_follow_extras_toggle_skips_movies():
    s1 = show(1, status=COMPLETED, relations={"sequel": [2]})
    movie = show(2, media_type="MOVIE", title="The Movie", relations={"sequel": [3]}, episodes_total=1)
    s2 = show(3, title="Season 2")
    lib = lib_of(s1, movie, s2)
    assert recommender.pick_replacement(lib, s1, []).anime is movie
    sug = recommender.pick_replacement(lib, s1, [], include_extras=False)
    assert sug.anime is s2 and any("The Movie (Movie)" in r for _, r in sug.reasons)


@pytest.mark.skipif(sys.platform == "win32", reason="uses a Unix socket; Windows uses named pipes")
def test_discord_rpc_handshake_and_activity(tmp_path, monkeypatch):
    import json as _json, socket, struct, threading
    from rinne import discord_rpc
    path = tmp_path / "discord-ipc-0"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)
    received = []

    def serve():
        conn, _ = server.accept()
        for _ in range(2):
            op, n = struct.unpack("<II", conn.recv(8))
            body = _json.loads(conn.recv(n))
            received.append((op, body))
            reply = _json.dumps({"cmd": "DISPATCH", "evt": "READY"} if op == 0
                                else {"cmd": "SET_ACTIVITY", "evt": None}).encode()
            conn.sendall(struct.pack("<II", 1, len(reply)) + reply)
        conn.close()

    threading.Thread(target=serve, daemon=True).start()
    monkeypatch.setattr(discord_rpc, "socket_paths", lambda: [path])
    rpc = discord_rpc.DiscordRPC("123456789")
    act = discord_rpc.build_activity("Frieren", "Frieren", "Episode 12", "https://x/c.jpg", 52991)
    assert rpc.set_activity(act)
    assert received[0] == (0, {"v": 1, "client_id": "123456789"})
    sent = received[1][1]["args"]["activity"]
    assert sent["type"] == 3 and sent["assets"]["large_image"] == "https://x/c.jpg"
    assert sent["buttons"][0]["url"].endswith("/52991")
    assert not discord_rpc.DiscordRPC("not-a-number").connect()


def test_discord_uses_builtin_app_by_default():
    from rinne import DISCORD_APP_ID
    s = Settings()
    assert s.discord_enabled and s.discord_client_id() == DISCORD_APP_ID
    s.discord_app_id = " 42 "
    assert s.discord_client_id() == "42"
    assert Settings.from_dict({"discord_app_id": DISCORD_APP_ID}).discord_app_id == ""


def test_onboarded_flag_roundtrip(tmp_path):
    st = State()
    assert not st.onboarded
    st.onboarded = True
    save_state(st, tmp_path / "s.json")
    assert load_state(tmp_path / "s.json").onboarded
    assert not State.from_dict({"library": []}).onboarded  # older files show the welcome once


def test_windows_uses_discord_named_pipes(monkeypatch):
    from rinne import discord_rpc
    monkeypatch.setattr(discord_rpc.sys, "platform", "win32")
    where = [w for w, _ in discord_rpc._transports()]
    assert where[0] == r"\\.\pipe\discord-ipc-0" and len(where) == 10


def test_windows_data_folders(monkeypatch, tmp_path):
    from rinne import storage
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(storage.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert storage.data_dir() == tmp_path / "Roaming" / "rinne"
    assert storage.cache_dir() == tmp_path / "Local" / "rinne"
