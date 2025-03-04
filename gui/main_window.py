# gui/main_window.py
from monitor.diff_analyzer import calculate_changes, generate_report
import sys
import threading
import asyncio
from datetime import datetime
from typing import List, Dict, Any
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStatusBar, QLabel,
    QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QMessageBox, QFileDialog, QCheckBox,
    QSplitter, QHeaderView, QTextBrowser
)
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot, QSettings, QTimer
import logging

from async_tasks.worker_thread import Worker
from monitor.fetcher import fetch_page
from monitor.parser import parse_html
from monitor.utils import CONFIG
# Если уведомления не нужны, можно удалить этот импорт
# from monitor.notifier import check_configuration  

def normalize_url(url: str) -> str:
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url.rstrip('/')

class ContentAnalyzer:
    def __init__(self):
        pass
    # Дополнительные методы анализа можно добавить здесь

class MainWindow(QMainWindow):
    # Сигнал для обновления таблицы при обновлении данных сайта
    site_updated = pyqtSignal(str, int, dict)  # url, row, changes

    def __init__(self):
        super().__init__()
        # Обновляем название окна на новую версию
        self.setWindowTitle("Web Deface Monitor V.10.0_ML")
        self.resize(1200, 600)
        self.settings = QSettings("At-Consulting", "WebDefaceMonitor")
        self.current_theme = self.settings.value("theme", "light")
        self.apply_theme(self.current_theme)
        
        # Внутренняя база: url -> {content, previous_content, baseline, row, last_modified, changes, status}
        self.sites_data: Dict[str, Dict[str, Any]] = {}
        self.data_lock = threading.Lock()
        self.analyzer = ContentAnalyzer()
        self.notifications_enabled = False
        
        self.worker = None
        self.worker_thread = None
        
        self.init_ui()
        self.load_default_sites()
        
        self.site_updated.connect(self._update_table_row)
        
    def init_ui(self):
        centralWidget = QWidget()
        self.setCentralWidget(centralWidget)
        mainLayout = QVBoxLayout(centralWidget)
        
        # Фиксированный заголовок с новой версией
        headerLabel = QLabel("Web Deface Monitor V.10.0_ML")
        headerLabel.setStyleSheet("background-color: #004080; color: white; font-size: 16pt; padding: 5px;")
        headerLabel.setAlignment(Qt.AlignCenter)
        headerLabel.setFixedHeight(50)
        mainLayout.addWidget(headerLabel)
        
        splitter = QSplitter(Qt.Horizontal)
        mainLayout.addWidget(splitter)
        
        # Левый блок: панель управления
        controlWidget = QWidget()
        controlLayout = QVBoxLayout(controlWidget)
        controlLayout.setContentsMargins(10,10,10,10)
        
        # Поле ввода URL и кнопка "Добавить"
        self.urlEdit = QLineEdit()
        self.urlEdit.setPlaceholderText("Введите URL сайта")
        controlLayout.addWidget(QLabel("URL сайта:"))
        controlLayout.addWidget(self.urlEdit)
        btnLayout = QHBoxLayout()
        self.btnAdd = QPushButton("Добавить")
        self.btnAdd.clicked.connect(self.add_site)
        self.btnDelete = QPushButton("Удалить")
        self.btnDelete.clicked.connect(self.delete_site)
        btnLayout.addWidget(self.btnAdd)
        btnLayout.addWidget(self.btnDelete)
        controlLayout.addLayout(btnLayout)
        
        # Кнопка "Сформировать отчёт"
        self.btnUpdate = QPushButton("Сформировать отчёт")
        self.btnUpdate.clicked.connect(self.on_generate_report)
        controlLayout.addWidget(self.btnUpdate)
        
        # Кнопка "Скачать отчет"
        self.btnDownload = QPushButton("Скачать отчет")
        self.btnDownload.clicked.connect(self.download_changes)
        controlLayout.addWidget(self.btnDownload)
        
        # Интервал мониторинга
        controlLayout.addWidget(QLabel("Интервал (мин):"))
        self.intervalEdit = QLineEdit(str(CONFIG.get('default_interval', 30)))
        self.intervalEdit.setFixedWidth(50)
        controlLayout.addWidget(self.intervalEdit)
        
        # Кнопки "Запуск" и "Остановка" фонового мониторинга
        btnLayout2 = QHBoxLayout()
        self.btnStart = QPushButton("Запуск")
        self.btnStart.clicked.connect(self.start_worker_monitoring)
        self.btnStop = QPushButton("Остановка")
        self.btnStop.clicked.connect(self.stop_monitoring)
        btnLayout2.addWidget(self.btnStart)
        btnLayout2.addWidget(self.btnStop)
        controlLayout.addLayout(btnLayout2)
        
        # Кнопка уведомлений
        self.notify_checkbox = QCheckBox("Уведомления в Telegram")
        self.notify_checkbox.setChecked(self.notifications_enabled)
        self.notify_checkbox.stateChanged.connect(lambda: self.toggle_notifications())
        controlLayout.addWidget(self.notify_checkbox)
        
        splitter.addWidget(controlWidget)
        
        # Правый блок: таблица сайтов
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Сайт", "Структура", "Контент", "Метаданные", "Итого", "Обновлено", "Статус"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(self.show_diff_window)
        splitter.addWidget(self.table)
        splitter.setSizes([300, 800])
        
        # Строка состояния
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Статус: Остановлен")
        self.statusBar.setStyleSheet("color: red;")
        footer = QLabel("All rights reserved©At-Consulting")
        footer.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        footer.setStyleSheet("color: green; font-size: 10pt;")
        self.statusBar.addPermanentWidget(footer)
        
        # QTimer для дополнительных обновлений (если требуется)
        self.monitorTimer = QTimer()
        self.monitorTimer.timeout.connect(self.monitor_loop)
        
    def apply_theme(self, theme: str):
        if theme == "dark":
            self.setStyleSheet("""
                QMainWindow { background-color: #2d2d30; color: #ffffff; }
                QLabel, QLineEdit, QTableWidget, QPushButton, QCheckBox { background-color: #3e3e42; color: #ffffff; }
                QHeaderView::section { background-color: #3e3e42; color: #ffffff; }
                QStatusBar { background-color: #3e3e42; color: #ffffff; }
            """)
        else:
            self.setStyleSheet("")

    def toggle_notifications(self):
        self.notifications_enabled = self.notify_checkbox.isChecked()

    def load_default_sites(self):
        # Реализуйте загрузку сайтов из конфигурационного файла, если необходимо
        pass

    def add_site(self):
        url = normalize_url(self.urlEdit.text().strip())
        if not url:
            QMessageBox.warning(self, "Ошибка", "Введите URL сайта")
            return
        with self.data_lock:
            if url in self.sites_data:
                QMessageBox.warning(self, "Ошибка", "Сайт уже добавлен")
                return
        self.add_site_to_table(url)
        self.urlEdit.clear()

    def add_site_to_table(self, url: str):
        with self.data_lock:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(url))
            for col in range(1, 7):
                item = QTableWidgetItem("0.00%")
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
            self.sites_data[url] = {
                "content": None,
                "previous_content": None,
                "baseline": None,
                "row": row,
                "last_modified": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "changes": {"visual_changes": {"structure": 0.0, "content": 0.0, "metadata": 0.0}},
                "status": "OK"
            }

    def delete_site(self):
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите сайт для удаления")
            return
        row = selected[0].row()
        url = self.table.item(row, 0).text()
        with self.data_lock:
            if url in self.sites_data:
                del self.sites_data[url]
        self.table.removeRow(row)

    def update_site(self):
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите сайт для обновления")
            return
        row = selected[0].row()
        url = self.table.item(row, 0).text()
        self.update_single_site(url)

    def update_single_site(self, url: str):
        target_row = None
        with self.data_lock:
            for row in range(self.table.rowCount()):
                if self.table.item(row, 0).text().strip() == url:
                    target_row = row
                    break
        if target_row is None:
            return

        statusItem = QTableWidgetItem("Обновление...")
        statusItem.setTextAlignment(Qt.AlignCenter)
        statusItem.setBackground(Qt.yellow)
        self.table.setItem(target_row, 6, statusItem)

        def fetch_and_update():
            try:
                html = fetch_page(url)
                if html is None:
                    raise Exception("Не удалось получить содержимое страницы")
                new_data = {"html": html, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                with self.data_lock:
                    old_data = self.sites_data[url]["content"] if self.sites_data[url]["content"] else {"html": ""}
                    changes = calculate_changes(old_data, new_data, self.analyzer)
                    self.sites_data[url].update({
                        "previous_content": old_data,
                        "content": new_data,
                        "last_modified": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "changes": changes,
                        "status": "OK"
                    })
                    local_row = None
                    for r in range(self.table.rowCount()):
                        if self.table.item(r, 0).text().strip() == url:
                            local_row = r
                            break
                    if local_row is not None:
                        self.site_updated.emit(url, local_row, changes)
            except Exception as e:
                with self.data_lock:
                    if url in self.sites_data:
                        self._update_error_status(url, target_row, str(e))
        threading.Thread(target=fetch_and_update, daemon=True).start()

    def _update_error_status(self, url: str, row: int, error_message: str):
        statusItem = QTableWidgetItem("Ошибка")
        statusItem.setTextAlignment(Qt.AlignCenter)
        statusItem.setBackground(Qt.red)
        statusItem.setToolTip(error_message)
        self.table.setItem(row, 6, statusItem)
        self.table.viewport().update()

    @pyqtSlot(str, int, dict)
    def _update_table_row(self, url: str, unused_row: int, changes: dict):
        if not changes or 'visual_changes' not in changes:
            return
        visual_changes = changes['visual_changes']
        target_row = None
        with self.data_lock:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item and item.text().strip() == url:
                    target_row = row
                    break
        if target_row is None:
            return
        updates = [
            (1, f"{visual_changes.get('structure', 0):.2f}%"),
            (2, f"{visual_changes.get('content', 0):.2f}%"),
            (3, f"{visual_changes.get('metadata', 0):.2f}%"),
            (4, f"{self.calculate_total_changes(changes):.2f}%"),
            (5, self.sites_data[url]["last_modified"])
        ]
        for col, value in updates:
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(target_row, col, item)
        statusItem = QTableWidgetItem("OK")
        statusItem.setTextAlignment(Qt.AlignCenter)
        statusItem.setBackground(Qt.green)
        self.table.setItem(target_row, 6, statusItem)
        self.table.viewport().update()

    def calculate_total_changes(self, changes: dict) -> float:
        try:
            weights = {'structure': 0.4, 'content': 0.4, 'metadata': 0.2}
            visual_changes = changes.get('visual_changes', {})
            total = sum(visual_changes.get(k, 0) * weights[k] for k in weights)
            return total
        except Exception:
            return 0.0

    def download_changes(self):
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите сайт для скачивания отчета")
            return
        row = selected[0].row()
        url = self.table.item(row, 0).text()
        with self.data_lock:
            if url not in self.sites_data:
                return
            site_data = self.sites_data[url]
            old_content = site_data.get("previous_content", {"html": ""})
            new_content = site_data.get("content", {"html": ""})
            changes = site_data.get("changes", {})
        report = generate_report(old_content, new_content, changes, url)
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить отчет", f"report_{url.replace('://','_').replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
            "HTML файлы (*.html);;Все файлы (*)"
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(report)
                QMessageBox.information(self, "Успех", "Отчет успешно сохранен")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить отчет:\n{str(e)}")

    def show_diff_window(self, row: int, column: int):
        url = self.table.item(row, 0).text()
        with self.data_lock:
            if url not in self.sites_data:
                QMessageBox.warning(self, "Предупреждение", "Сайт не найден в базе данных")
                return
            site_data = self.sites_data[url]
            if not site_data.get("previous_content") or not site_data.get("content"):
                QMessageBox.information(self, "Информация", "Недостаточно данных для сравнения")
                return
            old_content = site_data["previous_content"]
            new_content = site_data["content"]
        changes = calculate_changes(old_content, new_content, self.analyzer)
        report = generate_report(old_content, new_content, changes, url)
        from PyQt5.QtWidgets import QDialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Детали изменений: {url}")
        dialog.resize(1200, 800)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setHtml(report)
        layout.addWidget(browser)
        btnSave = QPushButton("Сохранить отчет")
        btnSave.clicked.connect(lambda: self.save_report_dialog(report))
        layout.addWidget(btnSave)
        dialog.exec_()

    def save_report_dialog(self, report: str):
        file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить отчет", "", "HTML файлы (*.html);;Все файлы (*)")
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(report)
                QMessageBox.information(self, "Успех", "Отчет успешно сохранен")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить отчет:\n{str(e)}")

    def monitor_loop(self):
        with self.data_lock:
            urls = list(self.sites_data.keys())
        for url in urls:
            self.update_single_site(url)
        try:
            interval = int(self.intervalEdit.text())
        except ValueError:
            interval = CONFIG.get('default_interval', 30)
        self.statusBar.showMessage(f"Статус: Активен (интервал: {interval} мин)", 5000)

    def start_worker_monitoring(self):
        # Единый механизм фонового мониторинга через QThread с Worker
        if self.worker_thread is not None:
            QMessageBox.information(self, "Информация", "Фоновый мониторинг уже запущен.")
            return
        self.statusBar.showMessage("Статус: Запущен")
        with self.data_lock:
            urls = list(self.sites_data.keys())
        try:
            interval_seconds = int(self.intervalEdit.text()) * 60
        except ValueError:
            interval_seconds = CONFIG.get('default_interval', 30) * 60
        from PyQt5.QtCore import QThread
        self.worker = Worker(urls, interval_seconds)
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.update_signal.connect(self.update_table)
        self.worker.finished_signal.connect(lambda: self.statusBar.showMessage("Статус: Остановлен"))
        self.worker_thread.start()

    def stop_monitoring(self):
        self.monitorTimer.stop()
        self.statusBar.showMessage("Статус: Остановлен")
        self.statusBar.setStyleSheet("color: red;")
        self.btnStart.setEnabled(True)
        self.btnStop.setEnabled(False)
        if self.worker is not None:
            self.worker.stop()
        if self.worker_thread is not None:
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.worker = None
            self.worker_thread = None

    @pyqtSlot(list)
    def update_table(self, results: List[Dict[str, Any]]):
        for res in results:
            url = res.get("url")
            if not url:
                continue
            target_row = None
            with self.data_lock:
                for row in range(self.table.rowCount()):
                    if self.table.item(row, 0).text().strip() == url:
                        target_row = row
                        break
            if target_row is not None:
                self.table.setItem(target_row, 1, QTableWidgetItem(str(res.get("structure", ""))))
                self.table.setItem(target_row, 2, QTableWidgetItem(str(res.get("content", ""))))
                self.table.setItem(target_row, 3, QTableWidgetItem(str(res.get("metadata", ""))))
                self.table.setItem(target_row, 4, QTableWidgetItem(str(res.get("overall", ""))))
                self.table.setItem(target_row, 5, QTableWidgetItem(res.get("updated", "")))
                self.table.setItem(target_row, 6, QTableWidgetItem(res.get("status", "")))

    def on_generate_report(self):
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QMessageBox.information(self, "Информация", "Выберите сайт в таблице для формирования отчёта.")
            return
        url_item = self.table.item(selected_row, 0)
        if not url_item:
            return
        url = url_item.text()
        threading.Thread(target=self.update_site_async, args=(url,), daemon=True).start()

    def update_site_async(self, url: str):
        try:
            from async_tasks.worker import process_site
            result = asyncio.run(process_site(url))
            target_row = None
            with self.data_lock:
                for row in range(self.table.rowCount()):
                    if self.table.item(row, 0).text().strip() == url:
                        target_row = row
                        break
                if target_row is None:
                    return
                self.sites_data[url].update({
                    "previous_content": self.sites_data[url]["content"] if self.sites_data[url]["content"] else {"html": ""},
                    "content": {"html": result.get("html", ""), "timestamp": result.get("timestamp", "")},
                    "last_modified": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "changes": result.get("changes", {}),
                    "status": result.get("status", "OK")
                })
            self.site_updated.emit(url, target_row, result.get("changes", {}))
            QTimer.singleShot(0, lambda: QMessageBox.information(self, "Отчет", f"Отчет по сайту '{url}' сформирован и данные обновлены."))
        except Exception as e:
            QTimer.singleShot(0, lambda: QMessageBox.critical(self, "Ошибка", f"Ошибка при формировании отчета для {url}:\n{str(e)}"))

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
