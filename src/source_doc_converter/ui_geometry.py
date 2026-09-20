from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtWidgets import QWidget

_MIN_WIDTH = 360
_MIN_HEIGHT = 300


def available_geometry_for_widget(widget: QWidget) -> QRect:
    screen = _screen_for_widget(widget)
    if screen is None:
        return QRect(0, 0, 1024, 768)
    return screen.availableGeometry()


def _screen_for_widget(widget: QWidget) -> QScreen | None:
    handle = widget.windowHandle()
    if handle is not None and handle.screen() is not None:
        return handle.screen()
    if widget.screen() is not None:
        return widget.screen()
    return QGuiApplication.primaryScreen()


def initial_geometry_rect(
    preferred_size: QSize,
    available: QRect,
    *,
    margin: int = 24,
    max_fraction: float = 0.92,
) -> QRect:
    max_width = max(_MIN_WIDTH, min(int(available.width() * max_fraction), available.width() - (margin * 2)))
    max_height = max(
        _MIN_HEIGHT,
        min(int(available.height() * max_fraction), available.height() - (margin * 2)),
    )
    width = min(preferred_size.width(), max_width)
    height = min(preferred_size.height(), max_height)
    x = available.x() + max(0, (available.width() - width) // 2)
    y = available.y() + max(0, (available.height() - height) // 2)
    return QRect(x, y, width, height)


def clamp_rect_to_available(rect: QRect, available: QRect, *, margin: int = 8) -> QRect:
    max_width = max(_MIN_WIDTH, available.width() - (margin * 2))
    max_height = max(_MIN_HEIGHT, available.height() - (margin * 2))
    width = min(rect.width(), max_width)
    height = min(rect.height(), max_height)
    min_x = available.x() + margin
    min_y = available.y() + margin
    max_x = available.x() + available.width() - margin - width
    max_y = available.y() + available.height() - margin - height
    x = min(max(rect.x(), min_x), max_x)
    y = min(max(rect.y(), min_y), max_y)
    return QRect(x, y, width, height)


def apply_initial_geometry(
    widget: QWidget,
    preferred_size: QSize,
    *,
    margin: int = 24,
    max_fraction: float = 0.92,
) -> None:
    available = available_geometry_for_widget(widget)
    widget.setGeometry(
        initial_geometry_rect(
            preferred_size,
            available,
            margin=margin,
            max_fraction=max_fraction,
        )
    )


def clamp_widget_to_available_screen(widget: QWidget, *, margin: int = 8) -> None:
    available = available_geometry_for_widget(widget)
    widget.setGeometry(clamp_rect_to_available(widget.geometry(), available, margin=margin))
