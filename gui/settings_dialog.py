# gui/settings_dialog.py
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton

class SettingsDialog(QDialog):
    """
    Диалоговое окно для настройки параметров мониторинга.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Введите URL сайта:"))
        self.url_input = QLineEdit()
        layout.addWidget(self.url_input)
        self.save_button = QPushButton("Сохранить")
        self.save_button.clicked.connect(self.save_settings)
        layout.addWidget(self.save_button)

    def save_settings(self):
        url = self.url_input.text().strip()
        if url:
            print(f"Настройка сохранена: {url}")
            self.accept()
        else:
            self.reject()
