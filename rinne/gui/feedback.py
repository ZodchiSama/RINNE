"""Feedback dialog and system-info helpers for bug reports."""

from __future__ import annotations

import os
import platform
import urllib.parse

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import Qt, QUrl, qVersion
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QFrame, QLineEdit, QPlainTextEdit, QPushButton,
)

from .. import CONTACT_EMAIL, DISPLAY_NAME, ISSUES_URL, __version__
from . import theme
from .common import hbox, label, vbox
from ..i18n import _


def system_info(state=None) -> list[tuple[str, str]]:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "unknown"
    session = os.environ.get("XDG_SESSION_TYPE", "unknown")
    try:
        distro = platform.freedesktop_os_release().get("PRETTY_NAME", "")
    except OSError:
        distro = ""
    info = [
        (DISPLAY_NAME, __version__),
        ("Python", platform.python_version()),
        ("Qt / PySide6", f"{qVersion()} / {pyside_version}"),
        ("System", distro or f"{platform.system()} {platform.release()}"),
        ("Kernel", platform.release()),
        ("Desktop", f"{desktop} ({session})"),
    ]
    if state is not None:
        s = state.settings
        info += [("Library", f"{len(state.library)} shows"),
                 ("Theme", f"{s.theme}{' + slideshow' if s.backdrop else ''}"),
                 ("Plan by", s.plan_by)]
    return info


def system_info_text(state=None) -> str:
    return "\n".join(f"{k}: {v}" for k, v in system_info(state))


class FeedbackDialog(QDialog):
    KINDS = [("bug", "Bug report"), ("idea", "Feature idea"), ("other", "Other feedback")]

    def __init__(self, state, kind: str = "bug", parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle(_("Send feedback — {DISPLAY_NAME}").format(DISPLAY_NAME=DISPLAY_NAME))
        self.setMinimumWidth(theme.fit_width(560))
        root = vbox(self, 12, 22)
        root.addWidget(label(_("Send feedback"), "h1"))
        root.addWidget(label(_("Found a bug or have an idea? Write it here — Rinne formats it into a report "
                             "you can send in one click."), "muted", wrap=True))

        seg_box = QFrame()
        seg_box.setObjectName("segBox")
        seg = hbox(seg_box, 2, 3)
        self.group = QButtonGroup(self)
        for key, text in self.KINDS:
            b = QPushButton(text)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setChecked(key == kind)
            b.setProperty("kind", key)
            self.group.addButton(b)
            seg.addWidget(b)
        root.addWidget(seg_box, alignment=Qt.AlignLeft)

        self.summary = QLineEdit()
        self.summary.setPlaceholderText(_("Short summary"))
        root.addWidget(self.summary)
        self.details = QPlainTextEdit()
        self.details.setPlaceholderText(_("What happened? What did you expect? Steps to reproduce help a lot."))
        self.details.setMinimumHeight(theme.px(160))
        root.addWidget(self.details)
        self.include = QCheckBox(_("Include system info (version, OS, Qt — no personal data)"))
        self.include.setChecked(True)
        root.addWidget(self.include)
        self.include_log = QCheckBox(_("Include the recent log (helps find crashes; contains no account details)"))
        self.include_log.setChecked(kind == "bug")
        root.addWidget(self.include_log)

        self.status = label("", "small", wrap=True)
        root.addWidget(self.status)
        row = hbox(spacing=8)
        row.addStretch()
        copy = QPushButton(_("Copy report"))
        copy.setObjectName("ghost")
        copy.clicked.connect(self.copy)
        row.addWidget(copy)
        if CONTACT_EMAIL:
            mail = QPushButton(_("Email it"))
            mail.setObjectName("ghost")
            mail.clicked.connect(self.email)
            row.addWidget(mail)
        if ISSUES_URL:
            send = QPushButton(_("Open issue tracker"))
            send.setObjectName("primary")
            send.clicked.connect(self.open_issue)
            row.addWidget(send)
        close = QPushButton(_("Close"))
        close.setObjectName("ghost")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        root.addLayout(row)

    def _kind(self) -> str:
        b = self.group.checkedButton()
        return b.property("kind") if b else "other"

    def title(self) -> str:
        prefix = {"bug": "[Bug]", "idea": "[Idea]", "other": "[Feedback]"}[self._kind()]
        return f"{prefix} {self.summary.text().strip() or 'No summary'}"

    def body(self) -> str:
        parts = [self.details.toPlainText().strip() or "(no details)"]
        if self.include.isChecked():
            parts.append("---\n" + system_info_text(self.state))
        if self.include_log.isChecked():
            from ..logs import tail
            recent = tail(60)
            if recent:
                parts.append("--- recent log ---\n" + recent)
        return "\n\n".join(parts)

    def copy(self) -> None:
        QGuiApplication.clipboard().setText(f"{self.title()}\n\n{self.body()}")
        self.status.setText(_("Copied to the clipboard."))

    def email(self) -> None:
        q = urllib.parse.urlencode({"subject": self.title(), "body": self.body()}, quote_via=urllib.parse.quote)
        QDesktopServices.openUrl(QUrl(f"mailto:{CONTACT_EMAIL}?{q}"))

    def open_issue(self) -> None:
        q = urllib.parse.urlencode({"title": self.title(), "body": self.body()})
        sep = "&" if "?" in ISSUES_URL else "?"
        url = ISSUES_URL.rstrip("/")
        if "github.com" in url and not url.endswith("/new"):
            url += "/new"
        QDesktopServices.openUrl(QUrl(f"{url}{sep}{q}"))
        self.status.setText(_("Opened in your browser — review and submit it there."))

