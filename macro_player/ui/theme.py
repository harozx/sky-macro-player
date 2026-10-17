"""Sky Instrument Console design tokens (see docs/UI_DESIGN.md)."""

from __future__ import annotations


class Tokens:
    CLOUD_INK = "#101722"
    DEEP_SLATE = "#192536"
    LIFTED_SLATE = "#24344A"
    MOON_MIST = "#E7EFF7"
    HUSHED_BLUE = "#91A5BA"
    SKY_BLUE = "#82CFFF"
    APRICOT = "#FFB287"
    DANGER = "#FF7A86"
    SUCCESS = "#8FE3B0"
    BORDER = "#34485F"
    DISABLED = "#5E7085"
    DISPLAY = "Bahnschrift SemiCondensed"
    BODY = "Segoe UI Variable"
    UTILITY = "Cascadia Mono"


STYLE = f"""
* {{ font-family: '{Tokens.BODY}', 'Segoe UI'; font-size: 13px; color: {Tokens.MOON_MIST}; }}
QMainWindow, QWidget#appRoot, QDialog {{ background: {Tokens.CLOUD_INK}; }}
QWidget#rail, QWidget#queuePanel, QFrame#playbackDock, QFrame#detailPanel,
QFrame#keyStrip {{ background: {Tokens.DEEP_SLATE}; }}
QFrame#detailPanel {{ border-radius: 10px; }}
QLabel#brand {{ font-family: '{Tokens.DISPLAY}'; font-size: 22px; font-weight: 600; }}
QLabel#eyebrow {{ color: {Tokens.SKY_BLUE}; font-family: '{Tokens.UTILITY}', 'Consolas'; font-size: 10px; }}
QLabel#pageTitle {{ font-family: '{Tokens.DISPLAY}'; font-size: 30px; font-weight: 600; }}
QLabel#sectionTitle {{ font-weight: 600; font-size: 14px; }}
QLabel#muted {{ color: {Tokens.HUSHED_BLUE}; }}
QLabel#mono {{ font-family: '{Tokens.UTILITY}', 'Consolas'; }}
QPushButton, QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 8px;
 padding: 8px 12px; text-align: left; }}
QPushButton:hover, QToolButton:hover {{ background: {Tokens.LIFTED_SLATE}; }}
QPushButton:focus, QToolButton:focus {{ border: 2px solid {Tokens.SKY_BLUE}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {Tokens.DISABLED}; }}
QPushButton:checked {{ background: {Tokens.LIFTED_SLATE}; color: {Tokens.SKY_BLUE}; }}
QPushButton[nav="true"]:checked {{ background: {Tokens.LIFTED_SLATE}; color: {Tokens.SKY_BLUE}; }}
QPushButton[primary="true"] {{ background: {Tokens.APRICOT}; color: {Tokens.CLOUD_INK};
 font-weight: 700; text-align: center; }}
QPushButton[primary="true"]:disabled {{ background: {Tokens.LIFTED_SLATE}; color: {Tokens.DISABLED}; }}
QPushButton[danger="true"] {{ color: {Tokens.DANGER}; border-color: #673846; text-align: center; }}
QPushButton[compact="true"] {{ padding: 6px 9px; text-align: center; }}
QPushButton[outline="true"] {{ border: 1px solid {Tokens.BORDER}; text-align: center; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{ background: {Tokens.DEEP_SLATE};
 border: 1px solid {Tokens.BORDER}; border-radius: 9px; padding: 8px 10px;
 selection-background-color: {Tokens.SKY_BLUE}; selection-color: {Tokens.CLOUD_INK}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{ border: 2px solid {Tokens.SKY_BLUE}; }}
QComboBox QAbstractItemView {{ background: {Tokens.DEEP_SLATE}; border: 1px solid {Tokens.BORDER};
 selection-background-color: {Tokens.LIFTED_SLATE}; }}
QListWidget, QTableWidget {{ background: transparent; border: 0; outline: 0; }}
QPlainTextEdit {{ font-family: '{Tokens.UTILITY}', 'Consolas'; }}
QListWidget::item {{ border-bottom: 1px solid #26384C; padding: 10px 8px; }}
QListWidget::item:hover {{ background: #1D2C3E; }}
QListWidget::item:selected {{ background: {Tokens.LIFTED_SLATE}; border-left: 3px solid {Tokens.SKY_BLUE}; }}
QListWidget:focus {{ border: 1px solid {Tokens.BORDER}; border-radius: 6px; }}
QHeaderView::section {{ background: {Tokens.DEEP_SLATE}; border: 0; padding: 6px; color: {Tokens.HUSHED_BLUE}; }}
QTableWidget::item {{ padding: 6px; border-bottom: 1px solid #26384C; }}
QCheckBox {{ spacing: 8px; padding: 4px 0; }}
QCheckBox:focus {{ color: {Tokens.SKY_BLUE}; }}
QScrollArea {{ background: transparent; border: 0; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QSlider::groove:horizontal {{ height: 4px; background: {Tokens.BORDER}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 14px; margin: -5px 0; background: {Tokens.SKY_BLUE}; border-radius: 7px; }}
QSlider::sub-page:horizontal {{ height: 4px; background: {Tokens.SKY_BLUE}; border-radius: 2px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {Tokens.BORDER}; border-radius: 4px; min-height: 28px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; height: 0; width: 0; }}
QMenu {{ background: {Tokens.DEEP_SLATE}; border: 1px solid {Tokens.BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {Tokens.LIFTED_SLATE}; }}
QToolTip {{ background: {Tokens.DEEP_SLATE}; color: {Tokens.MOON_MIST}; border: 1px solid {Tokens.BORDER}; }}
"""
