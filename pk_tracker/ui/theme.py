"""Dark + light themes: a small palette and a Qt stylesheet.

Two restrained palettes (dark default, optional light) share one stylesheet
built from the active palette. ``COLORS`` is a *mutable module dict* that
``apply_theme`` rewrites in place, so existing ``from .theme import COLORS``
references everywhere keep pointing at the live palette after a theme switch.
Readout numbers use a monospaced font so digits line up like an instrument.

On top of the two palettes sits a **per-substance accent**: ``set_accent``
replaces the accent family (accent, hover, on-accent text, and a soft tint) with
one derived from the active substance's own colour, so the whole UI reads amber
for caffeine, blue for methylphenidate, rose for alcohol. It is an override, not
a third palette: clearing it restores the palette's own accent.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout

# Two palettes with identical keys so every consumer is theme-agnostic.
DARK = {
    "bg": "#0e1116",
    "panel": "#161b22",
    "panel_alt": "#1b222b",
    "border": "#262e3a",
    "text": "#e6edf3",
    "subtext": "#8b98a5",
    "muted": "#5b6570",
    "accent": "#4aa3ff",
    "accent_text": "#06121f",   # text drawn on top of an accent fill
    "accent_hover": "#6cb6ff",
    "good": "#3fb950",
    "warn": "#d6a04a",
    "danger": "#e5534b",
    "grid": "#222a35",
    "future": "#3a4654",
    # The effect trace, deliberately *not* the accent: the level curve already
    # wears the substance's colour, so the two must never converge.
    "effect": "#4aa3ff",
}

LIGHT = {
    "bg": "#f4f6f9",
    "panel": "#ffffff",
    "panel_alt": "#eef1f6",
    "border": "#d6dce4",
    "text": "#1b2127",
    "subtext": "#586271",
    "muted": "#8a93a0",
    "accent": "#2f7fe0",
    "accent_text": "#ffffff",
    "accent_hover": "#5398e8",
    "good": "#2f9e44",
    "warn": "#b07d24",
    "danger": "#d63b34",
    "grid": "#e3e8ef",
    "future": "#aab3bf",
    "effect": "#2f7fe0",
}

THEMES = {"dark": DARK, "light": LIGHT}

# Live palette. Mutated in place by apply_theme so imported references stay valid.
COLORS = dict(DARK)
_mode = "dark"
# The active substance's colour, or None to use the palette's own accent.
_accent_override: str | None = None


def available_themes() -> list[str]:
    return ["dark", "light"]


def current_theme() -> str:
    return _mode


# ----- per-substance accent -------------------------------------------------
def _blend(a: QColor, b: QColor, t: float) -> QColor:
    """Mix ``a`` into ``b`` by fraction ``t`` (0 = all b, 1 = all a)."""
    return QColor(
        round(a.red() * t + b.red() * (1 - t)),
        round(a.green() * t + b.green() * (1 - t)),
        round(a.blue() * t + b.blue() * (1 - t)),
    )


def _luminance(c: QColor) -> float:
    """Perceived brightness (0..1), for choosing text drawn on top of a fill."""
    return 0.299 * c.redF() + 0.587 * c.greenF() + 0.114 * c.blueF()


def _refresh_accent() -> None:
    """Rewrite the accent family in COLORS from the override (or the palette)."""
    base = THEMES[_mode]
    if _accent_override:
        c = QColor(_accent_override)
        COLORS["accent"] = c.name()
        COLORS["accent_hover"] = c.lighter(124 if _mode == "dark" else 112).name()
        COLORS["accent_text"] = "#06121f" if _luminance(c) > 0.55 else "#ffffff"
    else:
        for key in ("accent", "accent_hover", "accent_text"):
            COLORS[key] = base[key]
    # A barely-there tint of the accent, for gauge tracks and tile chrome.
    COLORS["accent_soft"] = _blend(
        QColor(COLORS["accent"]), QColor(COLORS["panel"]), 0.22
    ).name()


def set_accent(color: str | None) -> bool:
    """Tint the UI to one substance's colour. True if anything actually changed.

    Only rewrites ``COLORS``; the caller re-applies the stylesheet (via
    ``apply_theme``) and repaints whatever caches colours at construction time.
    """
    global _accent_override
    c = QColor(color) if color else QColor()
    new = c.name() if c.isValid() else None
    if new == _accent_override:
        return False
    _accent_override = new
    _refresh_accent()
    return True


_refresh_accent()       # seed the derived keys before anyone reads COLORS


def mono_font(size: int = 11, weight: int = 400) -> QFont:
    """A monospaced font for numeric readouts, with sensible fallbacks."""
    qweight = QFont.Weight(int(weight))
    for family in ("JetBrains Mono", "DejaVu Sans Mono", "Menlo", "Consolas", "Monospace"):
        if family in QFontDatabase.families():
            f = QFont(family, size)
            f.setWeight(qweight)
            return f
    f = QFont()
    f.setStyleHint(QFont.Monospace)
    f.setFamily("monospace")
    f.setPointSize(size)
    f.setWeight(qweight)
    return f


# ----- chrome factories -----------------------------------------------------
# Small builders for the two repeated shapes of the design language, kept next
# to the stylesheet rules (#Card / #Tile) that give them their look.
def card_frame(title: str | None = None) -> QFrame:
    """A rounded sub-panel with an optional section title.

    Content goes into the frame's own ``layout()``, under the title if given.
    """
    frame = QFrame()
    frame.setObjectName("Card")
    v = QVBoxLayout(frame)
    v.setContentsMargins(14, 12, 14, 14)
    v.setSpacing(8)
    if title:
        label = QLabel(title)
        label.setObjectName("H2")
        v.addWidget(label)
    return frame


def stat_tile(caption: str, value: str = "—") -> tuple[QFrame, QLabel]:
    """An inset readout: a monospaced value over a small caption.

    Returns the tile and its value label, which the caller keeps to update.
    """
    frame = QFrame()
    frame.setObjectName("Tile")
    v = QVBoxLayout(frame)
    v.setContentsMargins(11, 9, 11, 9)
    v.setSpacing(2)
    val = QLabel(value)
    val.setObjectName("TileValue")
    val.setFont(mono_font(12, 600))
    cap = QLabel(caption)
    cap.setObjectName("TileLabel")
    cap.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    v.addWidget(val)
    v.addWidget(cap)
    return frame, val


def _stylesheet() -> str:
    c = COLORS
    return f"""
    QWidget {{
        background-color: {c['bg']};
        color: {c['text']};
        font-family: 'Segoe UI', 'Helvetica Neue', 'Cantarell', sans-serif;
        font-size: 13px;
    }}
    /* Labels sit on panels and cards, so they must not paint the window
       background as a strip behind their text. Id rules below still win. */
    QLabel {{ background: transparent; }}
    QFrame#Panel, QWidget#Panel {{
        background-color: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 10px;
    }}
    QFrame#Card, QWidget#Card {{
        background-color: {c['panel_alt']};
        border: 1px solid {c['border']};
        border-radius: 12px;
    }}
    QFrame#Tile, QWidget#Tile {{
        background-color: {c['bg']};
        border: 1px solid {c['border']};
        border-radius: 10px;
    }}
    QLabel#H1 {{ font-size: 17px; font-weight: 600; }}
    QLabel#H2 {{ font-size: 13px; font-weight: 600; color: {c['subtext']}; }}
    QLabel#Sub {{ color: {c['subtext']}; font-size: 12px; }}
    QLabel#Muted {{ color: {c['muted']}; font-size: 11px; }}
    QLabel#Disclaimer {{ color: {c['muted']}; font-size: 11px; }}
    QLabel#Ok {{ color: {c['good']}; font-size: 12px; font-weight: 600; }}
    QLabel#TileValue {{ color: {c['text']}; font-size: 13px; font-weight: 600; }}
    QLabel#TileLabel {{ color: {c['muted']}; font-size: 11px; }}
    QLabel#Accented {{ color: {c['accent']}; font-weight: 600; }}
    QLabel#Chip {{
        background-color: {c['accent_soft']};
        border: 1px solid {c['border']};
        border-radius: 9px;
        padding: 4px 10px;
        font-size: 12px;
        font-weight: 600;
    }}

    QPushButton {{
        background-color: {c['panel_alt']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        padding: 7px 12px;
        color: {c['text']};
    }}
    QPushButton:hover {{ border-color: {c['accent']}; }}
    QPushButton:pressed {{ background-color: {c['border']}; }}
    QPushButton#Accent {{
        background-color: {c['accent']};
        border: none;
        color: {c['accent_text']};
        font-weight: 600;
    }}
    QPushButton#Accent:hover {{ background-color: {c['accent_hover']}; }}
    QPushButton#Ghost {{ background-color: transparent; border: 1px solid {c['border']}; }}
    /* Segmented view switcher (Timeline / Insights). */
    QPushButton#Segment {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 7px;
        padding: 5px 14px;
        color: {c['subtext']};
        font-weight: 600;
    }}
    QPushButton#Segment:hover {{ color: {c['text']}; }}
    QPushButton#Segment:checked {{
        background-color: {c['accent_soft']};
        border-color: {c['accent']};
        color: {c['accent']};
    }}

    QToolButton#WidgetClose {{
        background: transparent; border: none; color: {c['muted']};
        font-size: 13px; font-weight: 700; padding: 0 2px;
    }}
    QToolButton#WidgetClose:hover {{ color: {c['danger']}; }}

    QListWidget, QTableWidget {{
        background-color: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        outline: none;
        padding: 4px;
    }}
    QListWidget::item {{ padding: 7px 8px; border-radius: 6px; }}
    QListWidget::item:selected {{ background-color: {c['panel_alt']}; color: {c['text']}; }}
    QListWidget::item:hover {{ background-color: {c['panel_alt']}; }}

    QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QTimeEdit, QDateTimeEdit {{
        background-color: {c['bg']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 5px 8px;
        selection-background-color: {c['accent']};
    }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{
        background-color: {c['panel']};
        border: 1px solid {c['border']};
        selection-background-color: {c['panel_alt']};
    }}

    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 24px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

    QToolTip {{
        background-color: {c['panel']};
        color: {c['text']};
        border: 1px solid {c['border']};
        padding: 4px;
    }}
    QMenu {{ background-color: {c['panel']}; border: 1px solid {c['border']}; padding: 4px; }}
    QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
    QMenu::item:selected {{ background-color: {c['panel_alt']}; }}
    QCheckBox {{ spacing: 8px; }}
    """


def _set_mode(mode: str) -> None:
    global _mode
    _mode = mode if mode in THEMES else "dark"
    COLORS.clear()
    COLORS.update(THEMES[_mode])
    _refresh_accent()       # the substance tint survives a theme switch


def apply_theme(app: QApplication, mode: str | None = None) -> None:
    """Apply (or re-apply) a theme to the whole application.

    Safe to call again at runtime to switch themes *or* to repaint after
    ``set_accent``: it rewrites COLORS in place, updates the pyqtgraph defaults,
    and re-sets the palette + stylesheet. Live plot widgets additionally expose
    ``apply_theme`` to refresh their chrome.
    """
    if mode is not None:
        _set_mode(mode)
    else:
        _refresh_accent()   # pick up a set_accent() since the last apply

    # Keep pyqtgraph's defaults in sync for any plot created afterwards.
    try:
        import pyqtgraph as pg

        pg.setConfigOption("background", COLORS["bg"])
        pg.setConfigOption("foreground", COLORS["subtext"])
    except Exception:
        pass

    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(COLORS["bg"]))
    pal.setColor(QPalette.Base, QColor(COLORS["bg"]))
    pal.setColor(QPalette.AlternateBase, QColor(COLORS["panel"]))
    pal.setColor(QPalette.Text, QColor(COLORS["text"]))
    pal.setColor(QPalette.WindowText, QColor(COLORS["text"]))
    pal.setColor(QPalette.Button, QColor(COLORS["panel_alt"]))
    pal.setColor(QPalette.ButtonText, QColor(COLORS["text"]))
    pal.setColor(QPalette.Highlight, QColor(COLORS["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor(COLORS["accent_text"]))
    pal.setColor(QPalette.ToolTipBase, QColor(COLORS["panel"]))
    pal.setColor(QPalette.ToolTipText, QColor(COLORS["text"]))
    app.setPalette(pal)
    app.setStyleSheet(_stylesheet())
