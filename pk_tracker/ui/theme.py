"""Dark, minimal, slightly clinical theme.

A small restrained palette and a Qt stylesheet shared across the main window
and the floating widget. Readout numbers use a monospaced font so digits line
up and the dashboard reads like an instrument.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

# Core palette.
COLORS = {
    "bg": "#0e1116",
    "panel": "#161b22",
    "panel_alt": "#1b222b",
    "border": "#262e3a",
    "text": "#e6edf3",
    "subtext": "#8b98a5",
    "muted": "#5b6570",
    "accent": "#4aa3ff",
    "good": "#3fb950",
    "warn": "#d6a04a",
    "danger": "#e5534b",
    "grid": "#222a35",
    "future": "#3a4654",
}


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


def _stylesheet() -> str:
    c = COLORS
    return f"""
    QWidget {{
        background-color: {c['bg']};
        color: {c['text']};
        font-family: 'Segoe UI', 'Helvetica Neue', 'Cantarell', sans-serif;
        font-size: 13px;
    }}
    QFrame#Panel, QWidget#Panel {{
        background-color: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 10px;
    }}
    QLabel#H1 {{ font-size: 17px; font-weight: 600; }}
    QLabel#H2 {{ font-size: 13px; font-weight: 600; color: {c['subtext']}; }}
    QLabel#Sub {{ color: {c['subtext']}; font-size: 12px; }}
    QLabel#Muted {{ color: {c['muted']}; font-size: 11px; }}
    QLabel#Disclaimer {{ color: {c['muted']}; font-size: 11px; }}

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
        color: #06121f;
        font-weight: 600;
    }}
    QPushButton#Accent:hover {{ background-color: #6cb6ff; }}
    QPushButton#Ghost {{ background-color: transparent; border: 1px solid {c['border']}; }}

    QListWidget {{
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


def apply_theme(app: QApplication) -> None:
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
    pal.setColor(QPalette.HighlightedText, QColor("#06121f"))
    pal.setColor(QPalette.ToolTipBase, QColor(COLORS["panel"]))
    pal.setColor(QPalette.ToolTipText, QColor(COLORS["text"]))
    app.setPalette(pal)
    app.setStyleSheet(_stylesheet())
