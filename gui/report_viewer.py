# gui/report_viewer.py
from PyQt5.QtWidgets import (
    QMainWindow, QTextEdit, QVBoxLayout, QWidget,
    QPushButton, QFileDialog, QHBoxLayout
)
from monitor.diff_analyzer import export_pdf
import logging

class ReportViewer(QMainWindow):
    """
    Окно для отображения отчета с дифф-анализа и экспортом в PDF.
    """
    def __init__(self, report_html: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Отчет по изменениям")
        self.report_html = report_html
        self.init_ui(report_html)

    def init_ui(self, report_html: str):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setHtml(report_html)
        layout.addWidget(self.text_edit)
        button_layout = QHBoxLayout()
        self.export_pdf_button = QPushButton("Экспорт в PDF")
        self.export_pdf_button.clicked.connect(self.export_to_pdf)
        button_layout.addWidget(self.export_pdf_button)
        layout.addLayout(button_layout)

    def export_to_pdf(self):
        options = QFileDialog.Options()
        output_pdf, _ = QFileDialog.getSaveFileName(self, "Сохранить PDF", "", "PDF Files (*.pdf);;All Files (*)", options=options)
        if output_pdf:
            temp_html_file = "temp_report.html"
            try:
                with open(temp_html_file, "w", encoding="utf-8") as f:
                    f.write(self.report_html)
                export_pdf(temp_html_file, output_pdf)
            except Exception as e:
                logging.error(f"Ошибка экспорта в PDF: {e}")
