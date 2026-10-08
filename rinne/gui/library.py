"""Library: your whole list as a poster grid."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QModelIndex, QRect, QRectF, QSize, QSortFilterProxyModel, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QStandardItem, QStandardItemModel,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QFrame, QGridLayout, QLineEdit, QListView, QMenu, QPushButton,
    QScrollArea, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget,
)

from ..i18n import _, N_
from ..models import LIST_STATUSES, PLAN_TO_WATCH, Anime, status_label
from . import theme
from .common import elide_lines, hbox, label, page_margin, progress_text, set_margins, vbox
from .images import cache

if TYPE_CHECKING:
    from .window import MainWindow



ID_ROLE = Qt.UserRole + 1
STATUS_ROLE = Qt.UserRole + 2
SORT_ROLE = Qt.UserRole + 3
SEARCH_ROLE = Qt.UserRole + 4


class PosterDelegate(QStyledItemDelegate):
    def __init__(self, win: MainWindow, parent=None):
        super().__init__(parent)
        self.win = win

    cell: QSize | None = None  # set by LibraryPage (phones use a width-filling grid)

    def sizeHint(self, option, index) -> QSize:
        return self.cell or QSize(theme.px(172), theme.px(300))

    def paint(self, p: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        anime = self.win.state.library.get(index.data(ID_ROLE))
        if anime is None:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = option.rect.adjusted(theme.px(6), theme.px(6), -theme.px(6), -theme.px(6))
        hovered = option.state & QStyle.State_MouseOver
        selected = option.state & QStyle.State_Selected
        path = QPainterPath()
        path.addRoundedRect(QRectF(r), theme.px(12), theme.px(12))
        p.fillPath(path, QColor(theme.SURFACE_2 if hovered or selected else theme.SURFACE))
        if selected:
            p.setPen(QPen(QColor(theme.ACCENT), 2))
            p.drawPath(path)

        pad = theme.px(8)
        cw = r.width() - 2 * pad
        ch = round(cw * 1.42)
        dpr = p.device().devicePixelRatioF() if p.device() else 1.0
        pix = cache().cover(anime.image_url, anime.name, cw, ch, theme.px(9), dpr)
        p.drawPixmap(r.left() + pad, r.top() + pad, pix)
        if anime.excluded:
            p.fillRect(QRect(r.left() + pad, r.top() + pad, cw, ch), QColor(0, 0, 0, 140))

        # Status pill on the cover.
        color = QColor(theme.STATUS_COLORS.get(anime.status, theme.MUTED))
        f = QFont(option.font)
        f.setPixelSize(theme.px(11))
        f.setBold(True)
        p.setFont(f)
        text = status_label(anime.status)
        fm = QFontMetrics(f)
        pill = QRect(r.left() + pad + theme.px(6), r.top() + pad + theme.px(6),
                     fm.horizontalAdvance(text) + theme.px(14), fm.height() + theme.px(6))
        pp = QPainterPath()
        pp.addRoundedRect(QRectF(pill), pill.height() / 2, pill.height() / 2)
        p.fillPath(pp, theme.qcolor(theme.BG, 225))
        p.setPen(color)
        p.drawText(pill, Qt.AlignCenter, text)

        # Title and meta.
        y = r.top() + pad + ch + theme.px(8)
        f = QFont(option.font)
        f.setPixelSize(theme.px(13))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.TEXT))
        fm = QFontMetrics(f)
        title_rect = QRect(r.left() + pad, y, cw, fm.lineSpacing() * 2)
        elided = elide_lines(anime.name, fm, cw, 2)
        p.drawText(title_rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, elided)
        y += fm.lineSpacing() * 2 + theme.px(4)

        f.setBold(False)
        f.setPixelSize(theme.px(12))
        p.setFont(f)
        p.setPen(QColor(theme.MUTED))
        meta = progress_text(anime)
        if anime.mean_score:
            meta += f"   ★ {anime.mean_score:.2f}"
        p.drawText(QRect(r.left() + pad, y, cw, QFontMetrics(f).height()), Qt.AlignLeft, meta)
        p.restore()


class LibraryFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text, self.status = "", ""
        self.setSortRole(SORT_ROLE)

    def set_text(self, t: str) -> None:
        self.text = t.lower()
        self.invalidateFilter()

    def set_status(self, s: str) -> None:
        self.status = s
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent) -> bool:
        idx = self.sourceModel().index(row, 0, parent)
        if self.status and idx.data(STATUS_ROLE) != self.status:
            return False
        return self.text in (idx.data(SEARCH_ROLE) or "")


SORTS = [(N_("Title"), "title"), (N_("MAL score"), "score"), (N_("Progress"), "progress"), (N_("Recently started"), "started")]


class LibraryPage(QWidget):
    def __init__(self, win: MainWindow):
        super().__init__()
        self.win = win
        self.root = root = vbox(self, 14, 28)
        self.header = QWidget()
        self.head_grid = QGridLayout(self.header)
        self.head_grid.setContentsMargins(0, 0, 0, 0)
        self.head_grid.setHorizontalSpacing(theme.px(8))
        self.head_grid.setVerticalSpacing(theme.px(10))
        self.titles = QWidget()
        titles = vbox(self.titles, 2)
        titles.addWidget(label(_("Library"), "h1"))
        self.count = label("", "muted", wrap=True)
        titles.addWidget(self.count)
        self.search = QLineEdit(placeholderText=_("Search your list…"))
        self.sort = QComboBox()
        for text, key in SORTS:
            self.sort.addItem(_("Sort: {name}").format(name=_(text)), key)
        self.import_btn = QPushButton(_("Add your list"))
        self.import_btn.setObjectName("ghost")
        imenu = QMenu(self.import_btn)
        imenu.addAction(_("Connect MyAnimeList or AniList…"), win.open_connect)
        imenu.addAction(_("Import by hand (file or username)…"), win.import_manually)
        imenu.addSeparator()
        imenu.addAction(_("Refresh all show details"), lambda: win.run_enrich(force=True))
        self.import_btn.setMenu(imenu)
        self._head_compact: bool | None = None
        root.addWidget(self.header)

        chip_area = QScrollArea()  # scrolls sideways when the chips don't fit (phones)
        chip_area.setWidgetResizable(True)
        chip_area.setFrameShape(QFrame.NoFrame)
        chip_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chip_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chip_host = QWidget()
        chip_host.setObjectName("page")
        chips = hbox(chip_host, 8)
        self.group = QButtonGroup(self)
        for n, (text, key) in enumerate([(_("All"), "")] + [(status_label(s), s) for s in LIST_STATUSES]):
            b = QPushButton(text)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("status", key)
            self.group.addButton(b, n)
            chips.addWidget(b)
            if key == "":
                b.setChecked(True)
        chips.addStretch()
        chip_area.setWidget(chip_host)
        chip_area.setProperty("sideways", True)
        chip_area.setFixedHeight(chip_host.sizeHint().height() + theme.px(2))
        root.addWidget(chip_area)

        self.model = QStandardItemModel()
        self.proxy = LibraryFilter(self)
        self.proxy.setSourceModel(self.model)
        self.view = QListView()
        self.view.setModel(self.proxy)
        self.view.setViewMode(QListView.IconMode)
        self.view.setResizeMode(QListView.Adjust)
        self.view.setMovement(QListView.Static)
        self.view.setUniformItemSizes(True)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.setMouseTracking(True)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.view.setItemDelegate(PosterDelegate(win, self.view))
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._menu)
        self.view.clicked.connect(lambda idx: self._open(idx))
        self.view.viewport().installEventFilter(self)  # re-fit the grid when the view resizes
        root.addWidget(self.view, 1)
        self.hint = label("", "faint", wrap=True)
        root.addWidget(self.hint)

        self.search.textChanged.connect(self.proxy.set_text)
        self.group.buttonClicked.connect(lambda b: self.proxy.set_status(b.property("status")))
        self.sort.currentIndexChanged.connect(lambda _: self.refresh())
        cache().loaded.connect(lambda _: self.view.viewport().update())

    def _arrange_header(self) -> None:
        """Desktop: title left, controls right. Phone: title, then search, then sort + import."""
        if self._head_compact == theme.COMPACT:
            return
        self._head_compact = theme.COMPACT
        for w in (self.titles, self.search, self.sort, self.import_btn):
            self.head_grid.removeWidget(w)
        g = self.head_grid
        for c in range(4):
            g.setColumnStretch(c, 0)
        if theme.COMPACT:
            self.search.setMinimumWidth(0)
            g.addWidget(self.titles, 0, 0, 1, 2)
            g.addWidget(self.search, 1, 0, 1, 2)
            g.addWidget(self.sort, 2, 0)
            g.addWidget(self.import_btn, 2, 1)
            g.setColumnStretch(0, 1)
            self.hint.setText(_("Tap a show for its profile — status and progress are there"))
        else:
            self.search.setMinimumWidth(theme.px(260))
            g.addWidget(self.titles, 0, 0)
            g.addWidget(self.search, 0, 1)
            g.addWidget(self.sort, 0, 2)
            g.addWidget(self.import_btn, 0, 3)
            g.setColumnStretch(0, 1)
            self.hint.setText(_("Click a show for its profile · right-click to change status or progress"))
        set_margins(self.root, page_margin())

    def _update_grid(self) -> None:
        """Phones: as many columns as fit (at least 2), filling the width. Desktop: fixed cards."""
        delegate = self.view.itemDelegate()
        if theme.COMPACT:
            vw = max(1, self.view.viewport().width() - theme.px(4))
            cols = max(2, vw // theme.px(150))
            w = vw // cols
            size = QSize(w, round(w * 1.72))
        else:
            size = QSize(theme.px(172), theme.px(300))
        delegate.cell = size
        self.view.setGridSize(size)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_grid()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.view.viewport() and event.type() == event.Type.Resize:
            self._update_grid()
        return False

    def refresh(self) -> None:
        self._arrange_header()
        state = self.win.state
        key = self.sort.currentData()
        items = []
        for a in state.library.values():
            item = QStandardItem(a.name)
            item.setData(a.mal_id, ID_ROLE)
            item.setData(" ".join(a.all_titles()).lower(), SEARCH_ROLE)
            item.setData(a.status, STATUS_ROLE)
            item.setEditable(False)
            if key == "score":
                sort_val = -a.mean_score
            elif key == "progress":
                sort_val = -(a.episodes_watched / a.episodes_total if a.episodes_total else 0)
            elif key == "started":
                sort_val = "".join(chr(0x10FFFF - ord(c)) for c in a.started_on) or "\U0010ffff"
            else:
                sort_val = a.name.lower()
            item.setData(sort_val, SORT_ROLE)
            items.append(item)
        # One insert instead of thousands keeps big libraries fast (the proxy re-sorts per insert).
        self.model.clear()
        self.model.invisibleRootItem().appendRows(items)
        self.proxy.sort(0)
        counts = {s: 0 for s in LIST_STATUSES}
        for a in state.library.values():
            counts[a.status] = counts.get(a.status, 0) + 1
        self.count.setText(_("{n} shows · {watching} watching · {completed} completed · {value} plan to watch").format(n=len(state.library), watching=counts['watching'], completed=counts['completed'], value=counts[PLAN_TO_WATCH]))
        self._update_grid()

    def _selected(self) -> Anime | None:
        idx = self.view.currentIndex()
        return self.win.state.library.get(idx.data(ID_ROLE)) if idx.isValid() else None

    def _open(self, idx) -> None:
        anime = self.win.state.library.get(idx.data(ID_ROLE))
        if anime:
            self.win.open_profile(anime)

    def _menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu
        idx = self.view.indexAt(pos)
        if not idx.isValid():
            return
        self.view.setCurrentIndex(idx)
        anime = self._selected()
        menu = QMenu(self)
        status_menu = menu.addMenu(_("Set status"))
        for s in LIST_STATUSES:
            act = status_menu.addAction(status_label(s))
            act.setCheckable(True)
            act.setChecked(anime.status == s)
            act.triggered.connect(lambda _=False, s=s: self.win.set_status(anime, s))
        menu.addAction(_("Set episodes watched…"), self._edit_progress)
        if anime.status == "watching":
            menu.addAction(_("Resume") if anime.paused else _("Pause"),
                           lambda: self.win.set_show_option(anime, paused=not anime.paused))
            menu.addAction(_("Unpin") if anime.pinned else _("Pin (an episode every day)"),
                           lambda: self.win.set_show_option(anime, pinned=not anime.pinned))
        menu.addSeparator()
        excl = menu.addAction(_("Never suggest this"))
        excl.setCheckable(True)
        excl.setChecked(anime.excluded)
        excl.triggered.connect(lambda: self.win.toggle_excluded(anime))
        menu.addAction(_("Open on MyAnimeList"), lambda: self.win.open_mal(anime))
        menu.exec(self.view.viewport().mapToGlobal(pos))

    def _edit_progress(self) -> None:
        anime = self._selected()
        if anime:
            self.win.edit_progress(anime)
