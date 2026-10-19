"""Build my Watching list: pick the settings, preview the new list, then apply it."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QPushButton, QScrollArea, QSpinBox, QWidget,
)

from .. import lineup, scheduler, seasonal
from ..i18n import _, _n
from ..models import ON_HOLD, WATCHING, Anime
from ..recommender import Suggestion
from . import theme
from .common import ElidedLabel, badge, clear, hbox, label, vbox
from .images import Cover


def _show_row(anime: Anime, tag: str, kind: str, reason: str = "") -> QWidget:
    row = QFrame()
    row.setObjectName("settingRow")
    lay = hbox(row, 12, 8)
    lay.addWidget(Cover(anime.image_url, anime.name, 36, 52, 6))
    text = vbox(spacing=2)
    title = ElidedLabel(anime.name)
    title.setObjectName("cardTitle")
    text.addWidget(title)
    if reason:
        text.addWidget(label(reason, "small", wrap=True))
    lay.addLayout(text, 1)
    side = vbox(spacing=4)
    side.addWidget(badge(tag, kind), alignment=Qt.AlignRight)
    if lineup.is_airing(anime):
        side.addWidget(badge(_("Airing"), "badge"), alignment=Qt.AlignRight)
    side.addStretch()
    lay.addLayout(side)
    return row


def _reason(s: Suggestion) -> str:
    good = [t for p, t in s.reasons if p > 0]
    return " · ".join(good[:2])


class LineupDialog(QDialog):
    def __init__(self, win, parent=None):
        super().__init__(parent or win)
        self.win = win
        s = win.state.settings
        self.setWindowTitle(_("Build my Watching list"))
        self.setMinimumWidth(theme.fit_width(620))
        self.resize(theme.fit_width(620), theme.px(720))
        root = vbox(self, 12, 24)
        root.addWidget(label(_("Build my Watching list"), "h1", wrap=True))
        root.addWidget(label(_("Rinne goes through your whole list and picks the shows to watch now. "
                               "Shows that don't make it move to On Hold; new ones come from Plan to Watch "
                               "and On Hold. Pinned shows always stay; paused ones are left as they are."),
                             "muted", wrap=True))

        controls = QWidget()
        grid = (vbox if theme.COMPACT else hbox)(controls, 14)
        self.size = QSpinBox(minimum=1, maximum=30, value=max(1, s.lineup_size))
        self.airing = QComboBox()
        self.airing.setMinimumWidth(theme.px(150))
        self.season = QCheckBox()
        self.season.setChecked(s.seasonal_picks)
        mood = _(seasonal.mood().name)
        self.season.setText(_("Seasonal picks ({mood})").format(mood=mood))
        self.season.setToolTip(_("Favour genres that fit the time of year, not the season a show aired."))
        for text, w in ((_("On Watching"), self.size), (_("Currently airing"), self.airing)):
            box = vbox(spacing=4)
            box.addWidget(label(text, "small"))
            box.addWidget(w)
            grid.addLayout(box)
        grid.addWidget(self.season, alignment=Qt.AlignBottom)
        grid.addStretch()
        root.addWidget(controls)
        self._fill_airing(s.lineup_airing)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        host = QWidget()
        host.setObjectName("page")
        self.list = vbox(host, 6)
        area.setWidget(host)
        root.addWidget(area, 1)

        self.note = label("", "faint", wrap=True)
        root.addWidget(self.note)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton(_("Cancel"))
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        self.ok = QPushButton()
        self.ok.setObjectName("primary")
        self.ok.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(self.ok)
        root.addLayout(buttons)

        self.size.valueChanged.connect(self._size_changed)
        self.airing.currentIndexChanged.connect(lambda _i: self.preview())
        self.season.toggled.connect(lambda _on: self.preview())
        self.preview()

    # ------------------------------------------------------------------ controls

    def _fill_airing(self, current: int) -> None:
        self.airing.blockSignals(True)
        self.airing.clear()
        n = self.size.value()
        auto_airing, _backlog = lineup.auto_split(n)
        self.airing.addItem(_("Automatic ({n})").format(n=auto_airing), lineup.AUTO)
        for k in range(n + 1):
            self.airing.addItem(str(k), k)
        idx = self.airing.findData(min(current, n) if current != lineup.AUTO else lineup.AUTO)
        self.airing.setCurrentIndex(max(0, idx))
        self.airing.blockSignals(False)

    def _size_changed(self) -> None:
        self._fill_airing(self.airing.currentData())
        self.preview()

    def _build(self) -> lineup.Lineup:
        st = self.win.state
        return lineup.build(st.library, self.size.value(), self.airing.currentData(), self.season.isChecked(),
                            exclude=scheduler.excluded_airing(st.library, st.settings.allow_airing))

    # ------------------------------------------------------------------ preview

    def preview(self) -> None:
        self.result = lu = self._build()
        clear(self.list)
        if not lu.picks:
            self.list.addWidget(label(_("There's nothing on your list to pick from yet. Add shows to "
                                        "Plan to Watch, or connect your account."), "muted", wrap=True))
        else:
            airing = sum(lineup.is_airing(s.anime) for s in lu.picks)
            self.list.addWidget(label(_("Your new Watching list"), "h2"))
            self.list.addWidget(label(_("{airing} airing, {backlog} from your backlog").format(
                airing=airing, backlog=len(lu.picks) - airing), "faint"))
            for sug in lu.picks:
                a = sug.anime
                if a.status == WATCHING:
                    tag, kind = _("Stays"), "badge"
                elif a.status == ON_HOLD:
                    tag, kind = _("From On Hold"), "badgeGreen"
                else:
                    tag, kind = _("New"), "badgeGreen"
                self.list.addWidget(_show_row(a, tag, kind, _reason(sug)))
        if lu.hold:
            self.list.addSpacing(theme.px(8))
            self.list.addWidget(label(_("Moves to On Hold"), "h2"))
            for a in lu.hold:
                self.list.addWidget(_show_row(a, _("On Hold"), "badgeAmber"))
        if lu.untouched:
            self.list.addSpacing(theme.px(8))
            self.list.addWidget(label(_n("{n} paused or finished show stays on Watching as it is.",
                                         "{n} paused or finished shows stay on Watching as they are.",
                                         len(lu.untouched)), "faint", wrap=True))
        self.list.addStretch()

        if len(lu.picks) < self.size.value() and lu.picks:
            self.note.setText(_n("Only {n} show could be picked.", "Only {n} shows could be picked.",
                                 len(lu.picks)) + " " + self._sync_note())
        else:
            self.note.setText(self._sync_note())
        self.ok.setText(_n("Apply {n} change", "Apply {n} changes", lu.changes) if lu.changes
                        else _("Nothing to change"))
        self.ok.setEnabled(bool(lu.changes))

    def _sync_note(self) -> str:
        s = self.win.state.settings
        connected = any([s.mal_token and s.sync_mal, s.anilist_token and s.sync_anilist,
                         s.shikimori_token and s.sync_shikimori])
        return _("Status changes are sent to your connected accounts.") if connected else ""

    # ------------------------------------------------------------------ apply

    def accept(self) -> None:
        s = self.win.state.settings
        s.lineup_size = self.size.value()
        s.lineup_airing = self.airing.currentData()
        s.seasonal_picks = self.season.isChecked()
        lineup.apply(self.result)
        super().accept()

