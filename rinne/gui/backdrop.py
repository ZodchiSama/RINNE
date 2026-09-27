"""A window background that slowly crossfades through art from today's shows."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from . import theme
from .images import cache

SLIDE_SECONDS = 9
FADE_MS = 1600


class Backdrop(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.enabled = False
        self.dim = 1
        self.urls: list[str] = []
        self.hd: set[str] = set()  # full-HD images are drawn sharp; the rest softened
        self.index = -1
        self.current: str | None = None
        self.previous: str | None = None
        self.t = 1.0
        self._prepared: dict[tuple[str, int, int], QPixmap] = {}
        self.timer = QTimer(self, interval=SLIDE_SECONDS * 1000, timeout=self.advance)
        self.anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=FADE_MS)
        self.anim.setEasingCurve(QEasingCurve.InOutSine)
        self.anim.valueChanged.connect(self._on_fade)
        cache().loaded.connect(self._on_loaded)

    def configure(self, seconds: int, dim: int) -> None:
        self.timer.setInterval(max(3, seconds) * 1000)
        self.dim = dim
        self.update()

    def set_enabled(self, on: bool) -> None:
        self.enabled = on
        if on and len(self.urls) > 1:
            self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def set_slides(self, slides: list[tuple[str, bool]]) -> None:
        """(url, is_hd) pairs, in display order."""
        urls = [u for u in dict.fromkeys(u for u, _ in slides) if u]
        self.hd = {u for u, hd in slides if hd}
        if urls == self.urls:
            return
        self.urls = urls
        for u in urls:
            cache().raw(u)  # start downloads
        self.index = -1
        self.current = self.previous = None
        self.advance(animate=False)
        self.set_enabled(self.enabled)

    def advance(self, animate: bool = True) -> None:
        if not self.urls:
            self.current = None
            self.update()
            return
        for step in range(1, len(self.urls) + 1):
            idx = (self.index + step) % len(self.urls)
            if cache().raw(self.urls[idx]) is not None:
                if idx == self.index and self.current is not None:
                    return
                self.index = idx
                self.previous, self.current = self.current, self.urls[idx]
                if animate and self.previous and self.enabled:
                    self.anim.stop()
                    self.anim.start()
                else:
                    self.t = 1.0
                    self.update()
                return

    def _on_loaded(self, url: str) -> None:
        if url in self.urls and self.current is None:
            self.advance(animate=False)

    def _on_fade(self, value) -> None:
        self.t = float(value)
        self.update()

    def resizeEvent(self, event) -> None:
        self._prepared.clear()
        super().resizeEvent(event)

    def _pixmap(self, url: str | None) -> QPixmap | None:
        if not url:
            return None
        size: QSize = self.size()
        key = (url, size.width(), size.height())
        if key in self._prepared:
            return self._prepared[key]
        raw = cache().raw(url)
        if raw is None or size.isEmpty():
            return None
        if url in self.hd:
            src = raw  # 1920×1080 fan art: keep it sharp
        else:
            # Low-res fallback would look blocky when stretched; soften it instead
            # (downscale then upscale smoothly — a cheap, pleasant blur).
            src = raw.scaled(max(1, raw.width() // 4), max(1, raw.height() // 4),
                             Qt.KeepAspectRatio, Qt.SmoothTransformation)
        dpr = self.devicePixelRatioF() or 1.0
        filled = src.scaled(size * dpr, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        filled.setDevicePixelRatio(dpr)
        if len(self._prepared) > 12:
            self._prepared.clear()
        self._prepared[key] = filled
        return filled

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = self.rect()
        p.fillRect(r, theme.qcolor(theme.BG))
        if not self.enabled:
            return
        for url, opacity in ((self.previous, 1.0 - self.t), (self.current, self.t)):
            pix = self._pixmap(url)
            if pix is None or opacity <= 0.01:
                continue
            p.setOpacity(opacity)
            w, h = pix.width() / pix.devicePixelRatio(), pix.height() / pix.devicePixelRatio()
            p.drawPixmap(round((r.width() - w) / 2), round((r.height() - h) / 3), pix)
        p.setOpacity(1.0)
        # Tint toward the theme background so text stays readable.
        tint = QLinearGradient(0, 0, 0, r.height())
        sharp = self.current in self.hd
        base = (125 if sharp else 150) if theme.DARK else (150 if sharp else 165)
        base = max(40, min(235, base + (self.dim - 1) * 40))
        tint.setColorAt(0.0, theme.qcolor(theme.BG, base))
        tint.setColorAt(1.0, theme.qcolor(theme.BG, min(255, base + 60)))
        p.fillRect(r, tint)
