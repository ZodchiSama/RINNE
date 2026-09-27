"""The "show finished" dialog."""

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
                root.addWidget(badge("Added — it wasn't on your MAL list", "badgeAmber"),
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
