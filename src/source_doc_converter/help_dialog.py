from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QDialog, QTextBrowser, QVBoxLayout

from source_doc_converter import ui_geometry
from source_doc_converter.help_content import HelpSection


class HelpDialog(QDialog):
    def __init__(self, section: HelpSection, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(section.title)
        layout = QVBoxLayout(self)
        self.content = QTextBrowser()
        self.content.setReadOnly(True)
        self.content.setOpenExternalLinks(True)
        self.content.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content.setText(section.body)
        layout.addWidget(self.content)
        ui_geometry.apply_initial_geometry(self, QSize(760, 520))

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        ui_geometry.clamp_widget_to_available_screen(self)
