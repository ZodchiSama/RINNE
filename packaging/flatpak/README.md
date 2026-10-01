# Flatpak / Flathub

`io.github.zodchisama.rinne.yml` builds Rinne on the KDE 6.11 runtime with Flathub's
`io.qt.PySide.BaseApp`, so PySide6 isn't rebuilt. Rinne itself is pure Python and is copied in
with a small launcher (`rinne.sh`).

## Building locally

```sh
flatpak install flathub org.flatpak.Builder org.kde.Sdk//6.11 io.qt.PySide.BaseApp//6.11
cd packaging/flatpak
flatpak run org.flatpak.Builder --user --install --force-clean build-dir io.github.zodchisama.rinne.yml
flatpak run io.github.zodchisama.rinne
flatpak run --command=flatpak-builder-lint org.flatpak.Builder manifest io.github.zodchisama.rinne.yml
```

## Submitting to Flathub

The app ID `io.github.zodchisama.rinne` is tied to the GitHub account, and Flathub checks that
you own it. Steps, after `v1.0.0` is tagged:

1. In the manifest, replace the `type: dir` source with the commented-out `type: git` source.
   Fill in the tag and the full commit hash (`git rev-list -n 1 v1.0.0`).
2. Fork <https://github.com/flathub/flathub> and create a branch from `new-pr`.
3. Add `io.github.zodchisama.rinne.yml` to the branch root and open a pull request **against the
   `new-pr` branch** titled "Add io.github.zodchisama.rinne".
4. A reviewer comments; the bot builds it when someone writes `bot, build`. Once merged, you get
   a `flathub/io.github.zodchisama.rinne` repository for future updates.
5. After it's published, verify the app on <https://flathub.org> (log in with GitHub) to get
   the verified checkmark.

Flathub reviewers usually ask about permissions. Here is why each one is needed:

| Permission | Why |
|---|---|
| `--share=network` | AniList, MyAnimeList and artwork; the MAL sign-in redirects to localhost |
| `--socket=wayland`, `fallback-x11`, `--device=dri`, `--share=ipc` | The window |
| `--talk-name=org.kde.StatusNotifierWatcher` | Tray icon |
| `--talk-name=org.freedesktop.Notifications` | New-episode alerts and the daily reminder |
| `--filesystem=xdg-run/discord-ipc-0`, `xdg-run/app/com.discordapp.Discord:create` | Discord Rich Presence (native and Flatpak Discord) |

The screenshots in the metainfo point at `docs/screenshots/` on the `main` branch, so keep those
files in place. Copies installed through Flatpak don't show Rinne's in-app update button.
Updates come from Flathub.
