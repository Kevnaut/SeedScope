from __future__ import annotations

from PySide6 import QtGui

def _arrow_data_uri(color: str) -> str:
    hex_color = color.lstrip("#")
    hex_color = f"%23{hex_color}"
    return (
        "data:image/svg+xml;utf8,"
        f"<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'>"
        f"<path fill='{hex_color}' d='M1 0l4 4 4-4 1 1-5 5-5-5z'/>"
        "</svg>"
    )


DARK_THEME = {
    "bg_grad_start": "#0b0f14",
    "bg_grad_end": "#0f1722",
    "panel": "#121823",
    "card": "#121a26",
    "accent": "#23e0d0",
    "accent_soft": "#1db8c8",
    "text": "#e6f1ff",
    "muted": "#8aa1b1",
    "border": "#1b2a36",
    "danger": "#ff5d73",
    "button_bg": "#0f1621",
    "input_bg": "#0d141d",
    "table_bg": "#0e141d",
    "header_bg": "#0f1722",
    "scroll_bg": "#0c121b",
    "scroll_handle": "#1b2a36",
}

LIGHT_THEME = {
    "bg_grad_start": "#f5f8fb",
    "bg_grad_end": "#e9f0f6",
    "panel": "#ffffff",
    "card": "#ffffff",
    "accent": "#1bbfc0",
    "accent_soft": "#28b7c6",
    "text": "#0a1219",
    "muted": "#5b6b7a",
    "border": "#d7e0e8",
    "danger": "#d94a5a",
    "button_bg": "#f1f5f9",
    "input_bg": "#f3f6f9",
    "table_bg": "#f6f9fc",
    "header_bg": "#eef3f8",
    "scroll_bg": "#e6edf4",
    "scroll_handle": "#c7d3df",
}

CURRENT_THEME = DARK_THEME


def set_theme(mode: str) -> None:
    global CURRENT_THEME
    CURRENT_THEME = LIGHT_THEME if str(mode).lower() == "light" else DARK_THEME


def theme() -> dict:
    return CURRENT_THEME


def qss(theme_map: dict) -> str:
    arrow_uri = _arrow_data_uri(theme_map["muted"])
    return f"""
    QMainWindow {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {theme_map['bg_grad_start']}, stop:1 {theme_map['bg_grad_end']});
        color: {theme_map['text']};
        font-family: 'Bahnschrift', 'Segoe UI', sans-serif;
        font-size: 12px;
    }}

    QLabel {{
        color: {theme_map['text']};
    }}

    QLabel#Muted {{
        color: {theme_map['muted']};
    }}

    QFrame#Panel {{
        background: {theme_map['panel']};
        border: 1px solid {theme_map['border']};
        border-radius: 12px;
    }}

    QFrame#Card {{
        background: {theme_map['card']};
        border: 1px solid {theme_map['border']};
        border-radius: 14px;
    }}

    QFrame#Card[accent="true"] {{
        border: 1px solid {theme_map['accent_soft']};
    }}

    QPushButton {{
        background: {theme_map['button_bg']};
        border: 1px solid {theme_map['border']};
        border-radius: 10px;
        padding: 8px 14px;
        color: {theme_map['text']};
    }}

    QPushButton:hover {{
        border: 1px solid rgba(35, 224, 208, 0.6);
    }}

    QPushButton:checked {{
        background: rgba(35, 224, 208, 0.08);
        border: 1px solid {theme_map['accent']};
        color: {theme_map['accent']};
    }}

    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {theme_map['input_bg']};
        border: 1px solid {theme_map['border']};
        border-radius: 8px;
        padding: 6px 10px;
        color: {theme_map['text']};
    }}

    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
        border: 1px solid rgba(35, 224, 208, 0.8);
    }}

    QCheckBox {{
        color: {theme_map['text']};
        spacing: 8px;
    }}

    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {theme_map['border']};
        background: {theme_map['input_bg']};
    }}

    QCheckBox::indicator:checked {{
        border: 1px solid {theme_map['accent']};
        background: rgba(35, 224, 208, 0.25);
    }}

    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 28px;
        border-left: 1px solid {theme_map['border']};
    }}

    QComboBox::down-arrow {{
        image: url("{arrow_uri}");
        width: 10px;
        height: 6px;
    }}

    QComboBox QAbstractItemView {{
        background: {theme_map['panel']};
        border: 1px solid {theme_map['border']};
        selection-background-color: rgba(35, 224, 208, 0.2);
        color: {theme_map['text']};
    }}

    QTableWidget {{
        background: {theme_map['table_bg']};
        border: 1px solid {theme_map['border']};
        gridline-color: {theme_map['border']};
    }}

    QTableView::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {theme_map['border']};
        background: {theme_map['input_bg']};
    }}

    QTableView::indicator:checked {{
        border: 1px solid {theme_map['accent']};
        background: rgba(35, 224, 208, 0.25);
    }}

    QHeaderView::section {{
        background: {theme_map['header_bg']};
        color: {theme_map['muted']};
        padding: 6px 8px;
        border: 1px solid {theme_map['border']};
    }}

    QScrollBar:vertical {{
        background: {theme_map['scroll_bg']};
        width: 10px;
        margin: 0px;
    }}

    QScrollBar::handle:vertical {{
        background: {theme_map['scroll_handle']};
        border-radius: 5px;
        min-height: 20px;
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QTabWidget::pane {{
        border: 1px solid {theme_map['border']};
        background: {theme_map['panel']};
        border-radius: 12px;
    }}

    QTabBar::tab {{
        background: {theme_map['button_bg']};
        padding: 8px 14px;
        border: 1px solid {theme_map['border']};
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        margin-right: 4px;
        color: {theme_map['muted']};
    }}

    QTabBar::tab:selected {{
        color: {theme_map['accent']};
        border: 1px solid {theme_map['accent']};
    }}
    """


def apply_theme(app, mode: str = "dark") -> None:
    set_theme(mode)
    font = QtGui.QFont("Bahnschrift")
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(qss(CURRENT_THEME))
