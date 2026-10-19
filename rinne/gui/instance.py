"""One Rinne at a time. A second launch (e.g. from the app menu while Rinne sits in the tray)
brings the running window forward and exits, instead of starting a second copy that would save
over the first one's changes."""

from __future__ import annotations

import hashlib

from PySide6.QtNetwork import QLocalServer, QLocalSocket

from ..storage import data_dir


def server_name() -> str:
    """Per data folder, so separate profiles (and tests) never meet."""
    return "rinne-" + hashlib.sha1(str(data_dir()).encode()).hexdigest()[:12]


def claim(on_activate) -> QLocalServer | None:
    """Become the running instance and return its server (keep a reference to it), or return None
    after asking the one already running to show itself."""
    name = server_name()
    sock = QLocalSocket()
    sock.connectToServer(name)
    if sock.waitForConnected(500):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
        return None
    QLocalServer.removeServer(name)  # a socket left behind by a crash
    server = QLocalServer()
    server.listen(name)

    def accept() -> None:
        while server.hasPendingConnections():
            conn = server.nextPendingConnection()
            conn.disconnected.connect(conn.deleteLater)
        on_activate()

    server.newConnection.connect(accept)
    return server
