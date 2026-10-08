"""Bringing a list in: connecting an account comes first; importing by hand is the fallback,
and it says what you'd miss out on."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QMessageBox, QPushButton, QToolButton

from ..i18n import _, N_
from . import theme
from .common import card, hbox, label, vbox

if TYPE_CHECKING:
    from .window import MainWindow

SERVICES = [
    ("mal", "MyAnimeList", N_("Opens MyAnimeList in your browser. Approve Rinne and you're done.")),
    ("anilist", "AniList", N_("Opens AniList in your browser. Approve Rinne, then paste the code it shows.")),
]

MISSING_OUT = [
    N_("Episodes you tick, status changes and scores saved to your account automatically"),
    N_("Your list brought in again with one click: no export files or usernames"),
    N_("Private lists and private entries"),
]


def connected_name(win: MainWindow, service: str) -> str:
    s = win.state.settings
    if service == "mal":
        return (s.mal_user or _("your account")) if s.mal_token else ""
    return (s.anilist_user or _("your account")) if s.anilist_token else ""


def any_connected(win: MainWindow) -> bool:
    s = win.state.settings
    return bool(s.mal_token or s.anilist_token)


class ConnectDialog(QDialog):
    """Connect MyAnimeList or AniList (or re-import from a connected one)."""

    def __init__(self, win: MainWindow):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(_("Connect your list"))
        self.setModal(True)
        self.setMinimumWidth(theme.px(360 if theme.COMPACT else 620))
        lay = vbox(self, 14, 24)
        lay.addWidget(label(_("Connect your list"), "h1"))
        lay.addWidget(label(_("Sign in once: Rinne brings in your whole list, private entries included, and "
                            "keeps your account up to date as you watch."), "muted", wrap=True))
        row = (vbox if theme.COMPACT else hbox)(spacing=12)
        for key, name, how in SERVICES:
            frame, cl = card(margins=18, spacing=8)
            cl.addWidget(label(name, "h2"))
            user = connected_name(win, key)
            if user:
                cl.addWidget(label(_("✓ Connected as {user}").format(user=user), "small"))
                again = QPushButton(_("Bring in my list again"))
                again.setObjectName("ghost")
                again.clicked.connect(lambda _=False, k=key: self._pull(k))
                cl.addWidget(again)
            else:
                cl.addWidget(label(_(how), "small", wrap=True))
                go = QPushButton(_("Connect {name}").format(name=name))
                go.setObjectName("primary")
                go.setMinimumHeight(theme.px(40))
                go.clicked.connect(lambda _=False, k=key: self._connect(k))
                cl.addWidget(go)
            cl.addStretch()
            row.addWidget(frame, 1)
        lay.addLayout(row)
        line = QFrame()
        line.setObjectName("divider")
        lay.addWidget(line)
        manual = QToolButton(text=_("Don't want to connect? Import a file or username instead"))
        manual.setObjectName("linkButton")
        manual.setCursor(Qt.PointingHandCursor)
        manual.clicked.connect(self._manual)
        lay.addWidget(manual, alignment=Qt.AlignLeft)

    def _connect(self, key: str) -> None:
        self.accept()
        report = _report(self.win)
        (self.win.connect_mal if key == "mal" else self.win.connect_anilist)(report)

    def _pull(self, key: str) -> None:
        self.accept()
        self.win.pull_account(key)

    def _manual(self) -> None:
        self.accept()
        import_manually(self.win)


def _report(win: MainWindow):
    def result(msg) -> None:
        if msg:
            QMessageBox.warning(win, _("Couldn't connect"), msg)
    return result


def confirm_manual(win: MainWindow) -> bool:
    """Before a manual import: say what connecting would give. True = import anyway."""
    box = QMessageBox(win)
    box.setWindowTitle(_("Import without connecting?"))
    box.setIcon(QMessageBox.Information)
    box.setTextFormat(Qt.RichText)
    box.setText(_("<b>Importing works, but it's a one-off snapshot of your list.</b>"))
    box.setInformativeText(_("Without a connected account you'll miss out on:<ul>")
                           + "".join(f"<li>{_(m)}</li>" for m in MISSING_OUT)
                           + _("</ul>Connecting takes a few seconds and only touches your anime list."))
    connect = box.addButton(_("Connect instead"), QMessageBox.AcceptRole)
    anyway = box.addButton(_("Import anyway"), QMessageBox.DestructiveRole)
    box.addButton(QMessageBox.Cancel)
    box.setDefaultButton(connect)
    box.exec()
    if box.clickedButton() is connect:
        ConnectDialog(win).exec()
        return False
    return box.clickedButton() is anyway


def import_manually(win: MainWindow, kind: str = "") -> None:
    """Import from a MAL export file ("file"), a MAL username ("mal"), an AniList username
    ("anilist") or a Shikimori nickname ("shikimori"), asking which if `kind` is empty. Without a connected account, first says what
    connecting would give."""
    if not any_connected(win) and not confirm_manual(win):
        return
    if not kind:
        box = QMessageBox(win)
        box.setWindowTitle(_("Import your list"))
        box.setText(_("What do you want to import from?"))
        f = box.addButton(_("MAL export file…"), QMessageBox.ActionRole)
        m = box.addButton(_("MAL username…"), QMessageBox.ActionRole)
        a = box.addButton(_("AniList username…"), QMessageBox.ActionRole)
        sh = box.addButton(_("Shikimori nickname…"), QMessageBox.ActionRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        kind = {f: "file", m: "mal", a: "anilist", sh: "shikimori"}.get(box.clickedButton(), "")
    if kind == "file":
        win.import_file()
    elif kind == "mal":
        win.import_username()
    elif kind == "anilist":
        win.import_anilist()
    elif kind == "shikimori":
        win.import_shikimori()
