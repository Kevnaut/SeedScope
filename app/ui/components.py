from __future__ import annotations

from PySide6 import QtCore, QtWidgets, QtGui

from app.theme import theme


class StatusDot(QtWidgets.QWidget):
    def __init__(self, diameter: int = 10) -> None:
        super().__init__()
        self._color = QtGui.QColor(theme()["muted"])
        self._diameter = diameter
        self.setFixedSize(diameter, diameter)

    def set_status(self, status: str) -> None:
        if status == "connected":
            self._color = QtGui.QColor(theme()["accent"])
        elif status == "offline":
            self._color = QtGui.QColor(theme()["danger"])
        else:
            self._color = QtGui.QColor(theme()["muted"])
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QBrush(self._color))
        painter.drawEllipse(0, 0, self._diameter, self._diameter)


class StatCard(QtWidgets.QFrame):
    def __init__(self, title: str, value: str = "--") -> None:
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("accent", "true")
        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setObjectName("Muted")
        self.value_label = QtWidgets.QLabel(value)
        self.value_label.setStyleSheet("font-size: 18px; font-weight: 600;")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

        glow = QtWidgets.QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(20)
        glow.setOffset(0, 0)
        glow_color = QtGui.QColor(theme()["accent"])
        glow_color.setAlpha(40)
        glow.setColor(glow_color)
        self.setGraphicsEffect(glow)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class SectionHeader(QtWidgets.QWidget):
    def __init__(self, title: str, subtitle: str | None = None) -> None:
        super().__init__()
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(title_label)
        if subtitle:
            subtitle_label = QtWidgets.QLabel(subtitle)
            subtitle_label.setObjectName("Muted")
            layout.addWidget(subtitle_label)


class EmptyState(QtWidgets.QFrame):
    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self.setObjectName("Panel")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        body_label = QtWidgets.QLabel(body)
        body_label.setObjectName("Muted")
        body_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(body_label)
