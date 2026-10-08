"""Dialogs: a show finished, what's new after an update, and an update being available."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLayout, QPushButton, QWidget

from ..models import Anime
from ..recommender import SERIES, Suggestion
from . import theme
from .common import badge, label, vbox
from .images import Cover


class ReplacementDialog(QDialog):
    def __init__(self, finished: Anime, sug: Suggestion | None, added: list[Anime], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Show finished")
        self.setMinimumWidth(theme.fit_width(460))
        root = vbox(self, 16, 24)
        root.setSizeConstraint(QLayout.SetMinimumSize)
        root.addWidget(label(f"You finished {finished.name}!", "h1", wrap=True))

        row = QHBoxLayout()
        row.setSpacing(theme.px(18))
        row.addWidget(_poster_block(finished, "Finished"))
        if sug:
            arrow = label("→", "arrow")
            row.addWidget(arrow, alignment=Qt.AlignVCenter)
            is_series = sug.kind == SERIES
            row.addWidget(_poster_block(sug.anime, "Next season" if is_series else "Up next",
                                        "badgeGreen" if is_series else "badge"))
        row.addStretch()
        root.addLayout(row)

        if sug:
            root.addWidget(label(f"{sug.anime.name} is now on your Watching list and in this week's plan.",
                                 "muted", wrap=True))
            for _, text in sug.reasons[:4]:
                root.addWidget(label(f"•  {text}", "small", wrap=True))
            if any(a.mal_id == sug.anime.mal_id for a in added):
                root.addWidget(badge("Added — it wasn't on your list", "badgeAmber"),
                               alignment=Qt.AlignLeft)
        else:
            root.addWidget(label("There's no next season and nothing on your Plan to Watch list "
                                 "to take its place.", "muted", wrap=True))
        ok = QPushButton("Nice")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        root.addWidget(ok, alignment=Qt.AlignRight)

    def showEvent(self, event) -> None:
        # Qt's minimum height ignores word-wrapped labels; size from the real wrapped height.
        h = self.layout().totalHeightForWidth(self.width())
        if h > self.height():
            self.setMinimumHeight(h)
            self.resize(self.width(), h)
        super().showEvent(event)


def _poster_block(anime: Anime, caption: str, kind: str = "badge") -> QWidget:
    w = QWidget()
    lay = vbox(w, 8)
    lay.addWidget(Cover(anime.image_url, anime.name, 140, 200, 14))
    lay.addWidget(badge(caption, kind), alignment=Qt.AlignLeft)
    t = label(anime.name, "cardTitle", wrap=True)
    t.setMaximumWidth(theme.px(140))
    lay.addWidget(t)
    return w


class _FitHeight:
    """Size a fixed-width dialog to the height its wrapped text needs at that width
    (Qt's default size hint ignores word wrap)."""

    def showEvent(self, event) -> None:
        lay = self.layout()
        lay.activate()
        self.setFixedHeight(max(lay.totalHeightForWidth(self.width()), lay.totalMinimumSize().height()))
        super().showEvent(event)


class WhatsNewDialog(_FitHeight, QDialog):
    """Shown once after Rinne updates: this version's notes."""

    def __init__(self, parent=None):
        from .. import __version__
        from ..changelog import CHANGELOG
        super().__init__(parent)
        version, title, notes = next((c for c in CHANGELOG if c[0] == __version__), CHANGELOG[0])
        self.setWindowTitle("What's new in Rinne")
        # A fixed width lets the wrapped notes take the height they need.
        self.setFixedWidth(theme.fit_width(520))
        root = vbox(self, 12, 26)
        head = QHBoxLayout()
        head.setSpacing(theme.px(10))
        head.addWidget(badge(f"v{version}", "badgeGreen"))
        head.addWidget(label("What's new", "faint"))
        head.addStretch()
        root.addLayout(head)
        root.addWidget(label(title, "h1", wrap=True))
        for note in notes:
            root.addWidget(label(f"•  {note}", "", wrap=True))
        root.addSpacing(theme.px(4))
        root.addWidget(label("You can read these notes again any time in Settings → About.", "faint", wrap=True))
        ok = QPushButton("Got it")
        ok.setObjectName("primary")
        ok.setMinimumWidth(theme.px(120))
        ok.clicked.connect(self.accept)
        root.addWidget(ok, alignment=Qt.AlignRight)


class UpdateDialog(_FitHeight, QDialog):
    """A newer release is out: its notes, and a way to get it."""

    def __init__(self, release: dict, on_download, parent=None):
        from .. import __version__
        super().__init__(parent)
        self.setWindowTitle("Update available")
        # A fixed width lets the wrapped notes take the height they need.
        self.setFixedWidth(theme.fit_width(540))
        root = vbox(self, 12, 26)
        root.addWidget(label(f"Rinne {release['version']} is available", "h1", wrap=True))
        root.addWidget(label(f"You have v{__version__}." + (f" {release['name']}" if release.get("name") else ""),
                             "muted", wrap=True))
        notes = (release.get("notes") or "").strip()
        if notes:
            from PySide6.QtWidgets import QScrollArea
            body = label(notes, "small", wrap=True)
            body.setTextFormat(Qt.MarkdownText)
            body.setOpenExternalLinks(True)
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QScrollArea.NoFrame)
            area.setWidget(body)
            area.setMinimumHeight(theme.px(160))
            area.setMaximumHeight(theme.px(320))
            root.addWidget(area)
        root.addWidget(label("The Update button in the sidebar and Settings → About also take you there.",
                             "faint", wrap=True))
        later = QPushButton("Later")
        later.setObjectName("ghost")
        later.clicked.connect(self.reject)
        get = QPushButton("Download")
        get.setObjectName("primary")
        get.clicked.connect(lambda: (on_download(), self.accept()))
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(later)
        row.addWidget(get)
        root.addLayout(row)
