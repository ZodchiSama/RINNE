"""Themes, sizes and the application stylesheet. Everything scales with the zoom level.

Colours are module attributes (theme.ACCENT, theme.SURFACE, …) so painting code always reads
the active palette; `apply()` swaps them and rebuilds the stylesheet.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

PALETTES: dict[str, dict] = {
    "midnight": dict(
        label="Midnight", dark=True,
        BG="#0e1016", SIDEBAR="#12151d", SURFACE="#181c26", SURFACE_2="#202532", SURFACE_3="#2a3040",
        BORDER="#262c3a", TEXT="#e9ebf2", BODY="#cfd3de", MUTED="#8c93a8", FAINT="#5c6376",
        ACCENT="#8b5cf6", ACCENT_2="#ec4899", ACCENT_HOVER="#9d74f8", ACCENT_2_HOVER="#f062a8",
        ACCENT_SOFT="#2b2346", SOFT_TEXT="#d8c8ff", ON_ACCENT="#ffffff", H1="#e9ebf2",
        SUCCESS="#34d399", DANGER="#fb7185", WARN="#fbbf24",
        GREEN_BG="#143329", AMBER_BG="#3a2e12", TODAY_BG="#1a1a2b", ACCENT_CARD="#1b1830",
        CHIP="rgba(255,255,255,0.08)", SCROLL_HOVER="#3a4256",
        STATUS={"watching": "#34d399", "completed": "#60a5fa", "on_hold": "#fbbf24",
                "dropped": "#fb7185", "plan_to_watch": "#a78bfa"},
    ),
    "dark": dict(
        label="Dark", dark=True,
        BG="#0f0f10", SIDEBAR="#151516", SURFACE="#1b1b1d", SURFACE_2="#242427", SURFACE_3="#303034",
        BORDER="#2a2a2e", TEXT="#ececee", BODY="#d0d0d4", MUTED="#9a9aa2", FAINT="#64646c",
        ACCENT="#3b82f6", ACCENT_2="#06b6d4", ACCENT_HOVER="#5a97f8", ACCENT_2_HOVER="#22c7e2",
        ACCENT_SOFT="#1c2a45", SOFT_TEXT="#bcd4ff", ON_ACCENT="#ffffff", H1="#ececee",
        SUCCESS="#4ade80", DANGER="#f87171", WARN="#facc15",
        GREEN_BG="#15301f", AMBER_BG="#34300f", TODAY_BG="#16202e", ACCENT_CARD="#151d2b",
        CHIP="rgba(255,255,255,0.07)", SCROLL_HOVER="#44444a",
        STATUS={"watching": "#4ade80", "completed": "#60a5fa", "on_hold": "#facc15",
                "dropped": "#f87171", "plan_to_watch": "#a5b4fc"},
    ),
    "light": dict(
        label="Light", dark=False,
        BG="#f4f5f9", SIDEBAR="#ffffff", SURFACE="#ffffff", SURFACE_2="#f0f2f7", SURFACE_3="#dfe3ec",
        BORDER="#e2e5ed", TEXT="#1b1e27", BODY="#343a48", MUTED="#5f6577", FAINT="#9197a6",
        ACCENT="#7c3aed", ACCENT_2="#db2777", ACCENT_HOVER="#8b50f0", ACCENT_2_HOVER="#e2468c",
        ACCENT_SOFT="#ede6fe", SOFT_TEXT="#5b21b6", ON_ACCENT="#ffffff", H1="#1b1e27",
        SUCCESS="#059669", DANGER="#e11d48", WARN="#b45309",
        GREEN_BG="#d7f5e8", AMBER_BG="#fdeccc", TODAY_BG="#f6f1ff", ACCENT_CARD="#f7f3ff",
        CHIP="rgba(0,0,0,0.06)", SCROLL_HOVER="#c5cad6",
        STATUS={"watching": "#059669", "completed": "#2563eb", "on_hold": "#b45309",
                "dropped": "#e11d48", "plan_to_watch": "#7c3aed"},
    ),
    # 4chan's classic "Yotsuba": cream page, peach posts, maroon text, red subjects, green names.
    "yotsuba": dict(
        label="Yotsuba", dark=False,
        BG="#ffffee", SIDEBAR="#f0e0d6", SURFACE="#f0e0d6", SURFACE_2="#ead3c6", SURFACE_3="#d9bfb7",
        BORDER="#d9bfb7", TEXT="#800000", BODY="#800000", MUTED="#9c4b3e", FAINT="#b98b80",
        ACCENT="#117743", ACCENT_2="#cc1105", ACCENT_HOVER="#169152", ACCENT_2_HOVER="#e0200f",
        ACCENT_SOFT="#dcebd2", SOFT_TEXT="#0e5a32", ON_ACCENT="#ffffff", H1="#cc1105",
        SUCCESS="#117743", DANGER="#cc1105", WARN="#9a6700",
        GREEN_BG="#dcebd2", AMBER_BG="#f6e4b8", TODAY_BG="#f7e9df", ACCENT_CARD="#f4e6dc",
        CHIP="rgba(128,0,0,0.08)", SCROLL_HOVER="#c9a79c",
        STATUS={"watching": "#117743", "completed": "#0f0c5d", "on_hold": "#9a6700",
                "dropped": "#cc1105", "plan_to_watch": "#8a3a8a"},
    ),
}
THEMES = list(PALETTES)

# Active palette values (overwritten by _load()).
BG = SIDEBAR = SURFACE = SURFACE_2 = SURFACE_3 = BORDER = TEXT = BODY = MUTED = FAINT = ""
ACCENT = ACCENT_2 = ACCENT_HOVER = ACCENT_2_HOVER = ACCENT_SOFT = SOFT_TEXT = ON_ACCENT = H1 = ""
SUCCESS = DANGER = WARN = GREEN_BG = AMBER_BG = TODAY_BG = ACCENT_CARD = CHIP = SCROLL_HOVER = ""
STATUS_COLORS: dict[str, str] = {}
DARK = True
BACKDROP = False
COMPACT = False  # phone / narrow-window layout, set by the main window
current = "midnight"

MIN_ZOOM, MAX_ZOOM = 0.7, 2.0
_zoom = 1.0


def _load(name: str) -> None:
    global STATUS_COLORS, DARK, current
    current = name if name in PALETTES else "midnight"
    pal = PALETTES[current]
    g = globals()
    for key, value in pal.items():
        if key.isupper() and key != "STATUS":
            g[key] = value
    STATUS_COLORS = dict(pal["STATUS"])
    DARK = pal["dark"]


_load("midnight")


def zoom() -> float:
    return _zoom


def px(n: float) -> int:
    """A length in design pixels, scaled by the current zoom."""
    return max(1, round(n * _zoom))


def fit_width(preferred: float) -> int:
    """A dialog/popup width that fits on small screens (phones)."""
    from PySide6.QtGui import QGuiApplication
    screen = QGuiApplication.primaryScreen()
    avail = screen.availableGeometry().width() if screen else 10_000
    return max(px(240), min(px(preferred), avail - px(24)))


def rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha:.2f})"


def qcolor(hex_color: str, alpha: int = 255) -> QColor:
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c


def _font_family() -> str:
    families = set(QFontDatabase.families())
    wanted = ("Arial", "Liberation Sans", "Helvetica") if current == "yotsuba" else ()
    for name in wanted + ("Inter", "Inter Variable", "Segoe UI Variable Text", "Segoe UI", "Noto Sans",
                          "Cantarell", "Roboto"):
        if name in families:
            return name
    return QApplication.font().family()


def apply(app: QApplication, z: float, name: str | None = None, backdrop: bool | None = None) -> None:
    global _zoom, BACKDROP
    _zoom = min(MAX_ZOOM, max(MIN_ZOOM, z))
    if name is not None:
        _load(name)
    if backdrop is not None:
        BACKDROP = backdrop
    font = QFont(_font_family())
    font.setPixelSize(px(14))
    app.setFont(font)

    pal = QPalette()
    for role, color in [
        (QPalette.Window, BG), (QPalette.Base, SURFACE), (QPalette.AlternateBase, SURFACE_2),
        (QPalette.Text, TEXT), (QPalette.WindowText, TEXT), (QPalette.ButtonText, TEXT),
        (QPalette.Button, SURFACE_2), (QPalette.Highlight, ACCENT),
        (QPalette.HighlightedText, ON_ACCENT), (QPalette.ToolTipBase, SURFACE_3),
        (QPalette.ToolTipText, TEXT), (QPalette.PlaceholderText, FAINT), (QPalette.Link, ACCENT),
    ]:
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    try:  # Qt 6.8+: tells the OS the colour scheme, e.g. a dark title bar on Windows
        from PySide6.QtCore import Qt
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark if DARK else Qt.ColorScheme.Light)
    except AttributeError:
        pass
    app.setStyleSheet(stylesheet())


def stylesheet() -> str:
    r = px(12)
    # With the slideshow backdrop, pages are see-through and cards are frosted glass.
    glass = BACKDROP
    page_bg = "transparent" if glass else BG
    a = 0.80 if DARK else 0.86
    surface = rgba(SURFACE, a) if glass else SURFACE
    surface_2 = rgba(SURFACE_2, min(1, a + 0.08)) if glass else SURFACE_2
    sidebar = rgba(SIDEBAR, 0.82 if DARK else 0.9) if glass else SIDEBAR
    today_bg = rgba(TODAY_BG, 0.86) if glass else TODAY_BG
    accent_card = rgba(ACCENT_CARD, 0.88) if glass else ACCENT_CARD
    grad = f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_2})"
    grad_hover = f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_HOVER}, stop:1 {ACCENT_2_HOVER})"
    small_badge = (f"border-radius: {px(6)}px; padding: {px(1)}px {px(6)}px; "
                   f"font-size: {px(11)}px; font-weight: 700;")
    return f"""
    * {{ outline: none; }}
    QMainWindow, QDialog {{ background: {BG}; }}
    #page {{ background: {page_bg}; }}
    QWidget {{ color: {TEXT}; }}
    QToolTip {{ background: {SURFACE_3}; color: {TEXT}; border: 1px solid {BORDER};
                padding: {px(6)}px {px(8)}px; border-radius: {px(6)}px; }}

    /* ---- sidebar ---- */
    #sidebar {{ background: {sidebar}; border-right: 1px solid {BORDER}; }}
    #brand {{ font-size: {px(19)}px; font-weight: 800; padding: {px(4)}px {px(8)}px; color: {H1}; }}
    #brandSub {{ color: {MUTED}; font-size: {px(12)}px; padding: 0 {px(8)}px; }}
    #credit {{ color: {ACCENT}; font-size: {px(13)}px; font-weight: 700; letter-spacing: 1px; }}
    QPushButton#nav {{
        text-align: left; padding: {px(10)}px {px(14)}px; border: none; border-radius: {px(10)}px;
        background: transparent; color: {MUTED}; font-size: {px(14)}px; font-weight: 600;
    }}
    QPushButton#nav:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
    QPushButton#nav:checked {{ background: {ACCENT_SOFT}; color: {SOFT_TEXT};
                               border-left: {px(3)}px solid {ACCENT}; padding-left: {px(11)}px; }}
    #navBadge {{ background: {ACCENT}; color: {ON_ACCENT}; border-radius: {px(10)}px;
                 min-width: {px(20)}px; max-height: {px(20)}px; min-height: {px(20)}px;
                 padding: 0 {px(5)}px; font-size: {px(11)}px; font-weight: 800; qproperty-alignment: AlignCenter; }}
    #bottomBar {{ background: {sidebar}; border-top: 1px solid {BORDER}; }}
    QToolButton#bnav {{ background: transparent; border: none; border-radius: {px(12)}px; color: {MUTED};
                        padding: {px(6)}px {px(4)}px; font-size: {px(11)}px; font-weight: 700; }}
    QToolButton#bnav:checked {{ color: {SOFT_TEXT}; background: {ACCENT_SOFT}; }}
    QPushButton#updateChip {{ background: {GREEN_BG}; color: {SUCCESS}; border: 1px solid {SUCCESS};
                              border-radius: {px(9)}px; padding: {px(6)}px; font-weight: 700; }}
    QPushButton#watch {{ background: {ACCENT_SOFT}; color: {SOFT_TEXT}; border: none;
                         border-radius: {px(8)}px; padding: {px(5)}px {px(10)}px; font-size: {px(12)}px; }}
    QPushButton#watch:hover {{ background: {ACCENT}; color: {ON_ACCENT}; }}
    #upNextCard {{ background: {surface_2}; border: 1px solid {BORDER}; border-radius: {px(12)}px; }}
    #upNextCard:hover {{ border: 1px solid {ACCENT}; }}
    #sideSection {{ color: {FAINT}; font-size: {px(11)}px; font-weight: 700;
                    letter-spacing: 1px; padding: {px(10)}px {px(14)}px {px(2)}px; }}

    /* ---- typography ---- */
    #h1 {{ font-size: {px(28)}px; font-weight: 800; color: {H1}; }}
    #h2 {{ font-size: {px(17)}px; font-weight: 700; }}
    #muted {{ color: {MUTED}; }}
    #faint {{ color: {FAINT}; font-size: {px(12)}px; }}
    #small {{ font-size: {px(12)}px; color: {MUTED}; }}
    #cardTitle {{ font-weight: 700; font-size: {px(14)}px; }}
    #bigTitle {{ font-weight: 800; font-size: {px(20)}px; }}
    #body {{ font-size: {px(14)}px; color: {BODY}; }}
    #vaName {{ font-weight: 700; font-size: {px(14)}px; color: {SOFT_TEXT if DARK else ACCENT}; }}
    #epTitle {{ font-size: {px(12)}px; color: {TEXT}; font-weight: 600; }}
    #knownRole {{ font-size: {px(12)}px; color: {SUCCESS}; }}

    /* ---- buttons ---- */
    QPushButton {{
        background: {surface_2}; border: 1px solid {BORDER}; border-radius: {px(9)}px;
        padding: {px(8)}px {px(14)}px; font-weight: 600;
    }}
    QPushButton:hover {{ background: {SURFACE_3}; }}
    QPushButton:disabled {{ color: {FAINT}; }}
    QPushButton#primary {{ background: {grad}; border: none; color: {ON_ACCENT}; }}
    QPushButton#primary:hover {{ background: {grad_hover}; }}
    QPushButton#ghost {{ background: {rgba(SURFACE, 0.5) if glass else "transparent"};
                         border: 1px solid {BORDER}; }}
    QPushButton#ghost:hover {{ background: {surface_2}; }}
    QPushButton#chip {{
        background: {surface}; border: 1px solid {BORDER}; border-radius: {px(15)}px;
        padding: {px(6)}px {px(14)}px; color: {MUTED};
    }}
    QPushButton#chip:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT}; color: {SOFT_TEXT}; }}
    QPushButton#seg {{ background: transparent; border: none; border-radius: {px(7)}px; color: {MUTED};
                       padding: {px(5)}px {px(6)}px; font-size: {px(12)}px; }}
    QPushButton#seg:checked {{ background: {ACCENT_SOFT}; color: {SOFT_TEXT}; }}
    #segBox {{ background: {surface}; border: 1px solid {BORDER}; border-radius: {px(9)}px; }}
    QPushButton::menu-indicator {{ width: 0; }}
    QToolButton#check {{
        border: 2px solid {SURFACE_3}; border-radius: {px(12)}px; background: transparent;
        min-width: {px(20)}px; max-width: {px(20)}px; min-height: {px(20)}px; max-height: {px(20)}px;
        color: {BG}; font-weight: 900; font-size: {px(12)}px;
    }}
    QToolButton#check:hover {{ border-color: {ACCENT}; }}
    QToolButton#check:checked {{ background: {SUCCESS}; border-color: {SUCCESS}; }}
    QToolButton#stepper {{
        background: {surface_2}; border: none; border-radius: {px(7)}px; font-weight: 800;
        min-width: {px(22)}px; min-height: {px(22)}px; color: {MUTED};
    }}
    QToolButton#stepper:hover {{ background: {ACCENT_SOFT}; color: {SOFT_TEXT}; }}

    /* ---- cards ---- */
    #card, #day, #stat {{ background: {surface}; border: 1px solid {BORDER}; border-radius: {r}px; }}
    #day[today="true"] {{ border: 2px solid {ACCENT}; background: {today_bg}; }}
    #day[past="true"] {{ background: {sidebar}; }}
    #day[dropTarget="true"] {{ border: 2px dashed {ACCENT}; background: {ACCENT_CARD}; }}
    #toast {{ background: {SURFACE_3}; border: 1px solid {BORDER}; border-radius: {px(12)}px; }}
    #toast QLabel {{ color: {TEXT}; }}
    QPushButton#toastAction {{ background: transparent; border: none; color: {SOFT_TEXT}; font-weight: 800;
                               padding: {px(4)}px {px(10)}px; }}
    QPushButton#toastAction:hover {{ color: {TEXT}; }}
    #dayDone {{ background: {surface}; border: 1px solid {BORDER}; border-left: {px(4)}px solid {SUCCESS};
                border-radius: {r}px; }}
    #doneCheck {{ background: {SUCCESS}; color: {SURFACE}; border-radius: {px(15)}px;
                  font-size: {px(15)}px; font-weight: 900; }}
    QToolButton#linkButton {{ background: transparent; border: none; color: {MUTED}; font-size: {px(12)}px;
                              text-decoration: underline; padding: 0; }}
    QToolButton#linkButton:hover {{ color: {TEXT}; }}
    #weekDay {{ background: {surface}; border: 1px solid {BORDER}; border-radius: {px(12)}px; }}
    #weekDay[state="done"] {{ background: {GREEN_BG}; border-color: {SUCCESS}; }}
    #weekDay[state="unfinished"] {{ background: {AMBER_BG}; border-color: {WARN}; }}
    #weekDay[state="today"] {{ border: 2px solid {ACCENT}; background: {today_bg}; }}
    #weekDay[state="off"] {{ background: transparent; }}
    #weekDayName {{ color: {MUTED}; font-size: {px(11)}px; font-weight: 700; letter-spacing: 1px; }}
    #weekDayMark {{ font-size: {px(16)}px; font-weight: 800; }}
    #weekDay[state="done"] #weekDayMark {{ color: {SUCCESS}; }}
    #weekDay[state="unfinished"] #weekDayMark {{ color: {WARN}; }}
    #weekDay[state="off"] #weekDayMark, #weekDay[state="off"] #weekDayName {{ color: {FAINT}; }}
    #episode {{ background: {surface_2}; border-radius: {px(10)}px; border: 1px solid transparent; }}
    #episode:hover, #card[clickable="true"]:hover {{ border: 1px solid {ACCENT}; }}
    #episode[missed="true"] {{ border-left: {px(3)}px solid {DANGER}; }}
    #episode[finale="true"] {{ border: 1px solid {ACCENT}; }}
    #card[accent="true"] {{ border: 1px solid {ACCENT}; background: {accent_card}; }}
    #cast {{ background: {surface_2}; border-radius: {px(12)}px; border: 1px solid transparent; }}
    #cast:hover {{ border: 1px solid {SURFACE_3}; }}
    #divider {{ background: {BORDER}; max-height: 1px; min-height: 1px; border: none; }}
    #badge {{ background: {ACCENT_SOFT}; color: {SOFT_TEXT}; {small_badge} }}
    #badgeGreen {{ background: {GREEN_BG}; color: {SUCCESS}; {small_badge} }}
    #badgeAmber {{ background: {AMBER_BG}; color: {WARN}; {small_badge} }}
    #chipLabel {{ background: {CHIP}; color: {TEXT}; border-radius: {px(7)}px;
                  padding: {px(3)}px {px(9)}px; font-size: {px(12)}px; font-weight: 600; }}
    #statValue {{ font-size: {px(22)}px; font-weight: 800; }}
    #statLabel {{ color: {MUTED}; font-size: {px(12)}px; }}
    #arrow {{ color: {ACCENT}; font-size: {px(26)}px; font-weight: 800; }}
    #welcomeTitle {{ font-size: {px(30)}px; font-weight: 800; color: {H1}; }}
    #heroName {{ font-size: {px(56)}px; font-weight: 900; letter-spacing: {px(6)}px; color: {H1}; }}
    #heroSub {{ font-size: {px(15)}px; color: {ACCENT}; font-weight: 700; letter-spacing: 1px; }}
    QPushButton#link {{ background: transparent; border: none; color: {MUTED}; padding: {px(4)}px; }}
    QPushButton#link:hover {{ color: {TEXT}; text-decoration: underline; }}
    #tourBubble {{ background: {SURFACE}; border: 1px solid {ACCENT}; border-radius: {px(14)}px; }}
    #tourCounter {{ color: {ACCENT}; font-size: {px(11)}px; font-weight: 800; letter-spacing: 1px; }}
    #settingRow {{ background: {surface}; border: 1px solid {BORDER}; border-radius: {px(10)}px; }}
    #settingTitle {{ font-weight: 700; font-size: {px(14)}px; }}
    QPushButton#subnav {{
        text-align: left; padding: {px(9)}px {px(14)}px; border: none; border-radius: {px(9)}px;
        background: transparent; color: {MUTED}; font-weight: 600;
    }}
    QPushButton#subnav:hover {{ background: {surface_2}; color: {TEXT}; }}
    QPushButton#subnav:checked {{ background: {ACCENT_SOFT}; color: {SOFT_TEXT}; }}
    #themeCard {{ border: 2px solid {BORDER}; border-radius: {px(12)}px; background: {surface}; }}
    #themeCard[selected="true"] {{ border: 2px solid {ACCENT}; }}
    #themeCard:hover {{ border: 2px solid {SCROLL_HOVER}; }}
    QSlider::groove:horizontal {{ height: {px(6)}px; background: {SURFACE_3}; border-radius: {px(3)}px; }}
    QSlider::sub-page:horizontal {{ background: {grad}; border-radius: {px(3)}px; }}
    QSlider::handle:horizontal {{ background: #ffffff; width: {px(16)}px; height: {px(16)}px;
                                  margin: -{px(5)}px 0; border-radius: {px(8)}px; }}
    QTimeEdit {{ background: {surface}; border: 1px solid {BORDER}; border-radius: {px(9)}px;
                 padding: {px(6)}px {px(10)}px; }}
    QTimeEdit::up-button, QTimeEdit::down-button {{ width: 0; border: none; }}
    #mini {{ border-radius: {px(10)}px; padding: {px(4)}px; }}
    #mini:hover {{ background: {surface_2}; }}

    /* ---- progress ---- */
    QProgressBar {{ background: {SURFACE_3}; border: none; border-radius: {px(3)}px;
                    max-height: {px(6)}px; min-height: {px(6)}px; }}
    QProgressBar::chunk {{ border-radius: {px(3)}px; background: {grad}; }}
    QProgressBar#busy {{ max-height: {px(4)}px; min-height: {px(4)}px; }}

    /* ---- inputs ---- */
    QLineEdit, QSpinBox, QComboBox {{
        background: {surface}; border: 1px solid {BORDER}; border-radius: {px(9)}px;
        padding: {px(7)}px {px(10)}px; selection-background-color: {ACCENT};
        selection-color: {ON_ACCENT};
    }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
    QPlainTextEdit {{ background: {surface}; border: 1px solid {BORDER}; border-radius: {px(9)}px;
                      padding: {px(6)}px; selection-background-color: {ACCENT}; }}
    QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
    QComboBox::drop-down {{ border: none; width: {px(24)}px; }}
    QComboBox QAbstractItemView {{ background: {SURFACE_2}; border: 1px solid {BORDER};
                                   selection-background-color: {ACCENT_SOFT};
                                   selection-color: {SOFT_TEXT}; }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
    QCheckBox, QRadioButton {{ spacing: {px(8)}px; }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: {px(18)}px; height: {px(18)}px; border: 2px solid {SURFACE_3};
        border-radius: {px(5)}px; background: {SURFACE};
    }}
    QRadioButton::indicator {{ border-radius: {px(10)}px; }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background: {ACCENT}; border-color: {ACCENT};
    }}

    /* ---- lists, menus, scrollbars ---- */
    QListView {{ background: transparent; border: none; }}
    QMenu {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: {px(8)}px;
             padding: {px(6)}px; }}
    QMenu::item {{ padding: {px(7)}px {px(18)}px; border-radius: {px(6)}px; }}
    QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {SOFT_TEXT}; }}
    QMenu::separator {{ height: 1px; background: {BORDER}; margin: {px(4)}px {px(8)}px; }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QWidget#qt_scrollarea_viewport {{ background: transparent; }}
    QStackedWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: {px(10)}px; margin: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: {px(10)}px; margin: 0; }}
    QScrollBar::handle {{ background: {SURFACE_3}; border-radius: {px(5)}px; min-height: {px(30)}px;
                          min-width: {px(30)}px; }}
    QScrollBar::handle:hover {{ background: {SCROLL_HOVER}; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
        background: none; border: none; width: 0; height: 0; }}
    QStatusBar {{ background: {SIDEBAR}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
    QStatusBar::item {{ border: none; }}
    QMessageBox QLabel {{ min-width: {px(320)}px; }}
    """
