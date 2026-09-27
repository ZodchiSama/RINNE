"""Cover art: async download, disk cache, and rounded/cropped rendering."""

from __future__ import annotations

import hashlib

from PySide6.QtCore import QByteArray, QObject, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QLabel, QWidget

from .. import USER_AGENT
from ..storage import cache_dir
from . import theme


class ImageCache(QObject):
    loaded = Signal(str)  # url

    def __init__(self, parent=None):
        super().__init__(parent)
        self.nam = QNetworkAccessManager(self)
        self.dir = cache_dir() / "images"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._raw: dict[str, QPixmap] = {}
        self._scaled: dict[tuple, QPixmap] = {}
        self._pending: set[str] = set()
        self._failed: set[str] = set()

    def _path(self, url: str):
        return self.dir / (hashlib.sha1(url.encode()).hexdigest() + ".img")

    def raw(self, url: str) -> QPixmap | None:
        if not url or url in self._failed:
            return None
        if url in self._raw:
            return self._raw[url]
        path = self._path(url)
        if path.exists():
            pix = QPixmap(str(path))
            if not pix.isNull():
                self._raw[url] = pix
                return pix
        if url not in self._pending:
            self._pending.add(url)
            req = QNetworkRequest(QUrl(url))
            req.setHeader(QNetworkRequest.UserAgentHeader, USER_AGENT)
            req.setAttribute(QNetworkRequest.RedirectPolicyAttribute,
                             QNetworkRequest.NoLessSafeRedirectPolicy)
            reply = self.nam.get(req)
            reply.finished.connect(lambda r=reply, u=url: self._done(u, r))
        return None

    def _done(self, url: str, reply: QNetworkReply) -> None:
        self._pending.discard(url)
        data: QByteArray = reply.readAll()
        ok = reply.error() == QNetworkReply.NoError
        reply.deleteLater()
        pix = QPixmap()
        if not ok or not pix.loadFromData(data):
            self._failed.add(url)
            return
        self._path(url).write_bytes(bytes(data))
        self._raw[url] = pix
        self.loaded.emit(url)

    def cover(self, url: str, title: str, w: int, h: int, radius: int, dpr: float = 1.0) -> QPixmap:
        """A w×h rounded cover, cropped to fill; a gradient placeholder until it loads."""
        raw = self.raw(url)
        key = (url if raw else "", title if not raw else "", w, h, radius, dpr)
        if key in self._scaled:
            return self._scaled[key]
        out = QPixmap(round(w * dpr), round(h * dpr))
        out.setDevicePixelRatio(dpr)
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
        p.setClipPath(path)
        if raw:
            scaled = raw.scaled(round(w * dpr), round(h * dpr),
                                Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            scaled.setDevicePixelRatio(dpr)
            sx = (scaled.width() / dpr - w) / 2
            sy = (scaled.height() / dpr - h) / 2
            p.drawPixmap(round(-sx), round(-sy), scaled)
        else:
            _placeholder(p, title, w, h)
        p.end()
        if len(self._scaled) > 1500:
            self._scaled.clear()
        self._scaled[key] = out
        return out


def _placeholder(p: QPainter, title: str, w: int, h: int) -> None:
    hue = int(hashlib.md5(title.encode()).hexdigest()[:4], 16) % 360
    grad = QLinearGradient(0, 0, w, h)
    grad.setColorAt(0, QColor.fromHsl(hue, 110, 70))
    grad.setColorAt(1, QColor.fromHsl((hue + 50) % 360, 120, 38))
    p.fillRect(0, 0, w, h, grad)
    letter = next((c for c in title if c.isalnum()), "?").upper()
    f = QFont()
    f.setPixelSize(max(8, int(min(w, h) * 0.42)))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255, 200))
    p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, letter)


_cache: ImageCache | None = None


def cache() -> ImageCache:
    global _cache
    if _cache is None:
        _cache = ImageCache()
    return _cache


class Cover(QLabel):
    """A fixed-size cover image that fills itself in when the download finishes."""

    def __init__(self, url: str, title: str, w: int, h: int, radius: int | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.url, self.title, self.w, self.h = url, title, theme.px(w), theme.px(h)
        self.radius = theme.px(radius if radius is not None else 10)
        self.setFixedSize(self.w, self.h)
        self._render()
        if url:
            cache().loaded.connect(self._on_loaded)

    def _render(self) -> None:
        dpr = self.devicePixelRatioF() or 1.0
        self.setPixmap(cache().cover(self.url, self.title, self.w, self.h, self.radius, dpr))

    def _on_loaded(self, url: str) -> None:
        if url == self.url:
            self._render()
