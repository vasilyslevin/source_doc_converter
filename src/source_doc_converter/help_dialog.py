from PySide6.QtWidgets import QDialog, QTextBrowser, QVBoxLayout

from source_doc_converter.help_content import HelpSection


class HelpDialog(QDialog):
    def __init__(self, section: HelpSection, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(section.title)
        self.resize(760, 520)
        layout = QVBoxLayout(self)
        self.content = QTextBrowser()
        self.content.setReadOnly(True)
        self.content.setOpenExternalLinks(True)
        self.content.setText(section.body)
        layout.addWidget(self.content)
