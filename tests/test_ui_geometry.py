from PySide6.QtCore import QRect, QSize

from source_doc_converter.ui_geometry import clamp_rect_to_available, initial_geometry_rect


def test_initial_geometry_uses_preferred_size_when_it_fits() -> None:
    rect = initial_geometry_rect(QSize(760, 680), QRect(0, 0, 1920, 1080))

    assert rect.width() == 760
    assert rect.height() == 680
    assert rect.x() >= 0
    assert rect.y() >= 0


def test_initial_geometry_caps_window_for_1024x768_available_area() -> None:
    rect = initial_geometry_rect(QSize(760, 680), QRect(0, 0, 1024, 768))

    assert rect.width() <= 760
    assert rect.height() <= 680
    assert QRect(0, 0, 1024, 768).contains(rect)


def test_clamp_rect_keeps_geometry_inside_available_bounds() -> None:
    clamped = clamp_rect_to_available(QRect(-100, -50, 1000, 900), QRect(10, 20, 700, 500))

    assert QRect(10, 20, 700, 500).contains(clamped)
