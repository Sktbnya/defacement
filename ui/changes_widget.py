#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль виджета изменений для WDM_V12.
Содержит класс ChangesWidget, который отображает информацию об изменениях сайтов.
"""

import os
import datetime
import json
import difflib  # Добавляем импорт difflib для сравнения контента
from typing import Dict, List, Any, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QScrollArea, QSizePolicy, QGridLayout, QTableWidget, 
    QTableWidgetItem, QHeaderView, QSplitter, QTabWidget,
    QSpacerItem, QTextEdit, QFileDialog, QDialog, QFormLayout,
    QLineEdit, QComboBox, QCheckBox, QMessageBox
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QFont, QColor, QPalette, QAction

from utils.logger import get_module_logger, log_exception
from utils.common import format_timestamp, get_diff_color, get_status_color, handle_errors


class ChangeDetailsDialog(QDialog):
    """Диалог для отображения деталей изменения"""
    
    def __init__(self, app_context, change_id, parent=None):
        """
        Инициализация диалога
        
        Args:
            app_context: Контекст приложения
            change_id: ID изменения
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger('ui.changes_widget.detail_dialog')
        self.app_context = app_context
        self.change_id = change_id
        
        # Получение данных об изменении
        self.change_data = self.app_context.get_change(change_id)
        
        # Настройка диалога
        self.setWindowTitle("Детали изменения")
        self.resize(900, 700)  # Увеличиваем размер для лучшего отображения diff
        
        # Инициализация UI
        self._init_ui()
        
        self.logger.debug(f"Диалог деталей изменения ID={change_id} создан")
    
    @handle_errors(error_msg="Ошибка при инициализации интерфейса диалога")
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        # Основной макет
        layout = QVBoxLayout(self)
        
        # Заголовок
        if self.change_data:
            site_name = self.change_data.get('site_name', 'Неизвестный сайт')
            site_url = self.change_data.get('site_url', '')
            
            header_text = f"<h2>Изменение сайта: {site_name}</h2>"
            header_text += f"<p>URL: <a href='{site_url}'>{site_url}</a></p>"
            header_text += f"<p>Дата: {format_timestamp(self.change_data.get('timestamp'))}</p>"
            
            diff_percent = self.change_data.get('diff_percent')
            if diff_percent is None:
                diff_percent = 0.0
            
            header_text += f"<p>Процент изменений: <b>{diff_percent:.2f}%</b></p>"
            
            status = self.change_data.get('status', '')
            status_map = {
                'unread': "Не прочитано",
                'read': "Прочитано"
            }
            status_text = status_map.get(status, status)
            header_text += f"<p>Статус: <b>{status_text}</b></p>"
            
            header = QLabel(header_text)
            header.setTextFormat(Qt.TextFormat.RichText)
            header.setOpenExternalLinks(True)
            header.setWordWrap(True)
            layout.addWidget(header)
            
            # Кнопка для открытия сайта
            btn_open_site = QPushButton("Открыть сайт в браузере")
            btn_open_site.setIcon(QIcon("resources/icons/web.png"))
            btn_open_site.clicked.connect(lambda: self._open_url(site_url))
            layout.addWidget(btn_open_site)
            
            # Горизонтальный разделитель
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFrameShadow(QFrame.Shadow.Sunken)
            layout.addWidget(separator)
            
            # Создание вкладок
            tab_widget = QTabWidget()
            
            # Вкладка с деталями изменений
            changes_tab = QWidget()
            changes_layout = QVBoxLayout(changes_tab)
            
            # Получение данных о различиях
            diff_details = self.change_data.get('diff_details', {})
            
            if diff_details:
                # Общая информация о изменениях
                info_text = "<h3>Информация о изменениях</h3>"
                
                added_lines = diff_details.get('added_lines', 0)
                removed_lines = diff_details.get('removed_lines', 0)
                total_changes = diff_details.get('total_changes', 0)
                total_lines = diff_details.get('total_lines', 0)
                
                info_text += f"<p>Добавлено строк: <b>{added_lines}</b></p>"
                info_text += f"<p>Удалено строк: <b>{removed_lines}</b></p>"
                info_text += f"<p>Общее количество изменений: <b>{total_changes}</b></p>"
                info_text += f"<p>Общее количество строк: <b>{total_lines}</b></p>"
                
                if total_lines > 0:
                    diff_percent = (total_changes / total_lines) * 100
                    info_text += f"<p>Процент изменений: <b>{diff_percent:.2f}%</b></p>"
                
                info_label = QLabel(info_text)
                info_label.setTextFormat(Qt.TextFormat.RichText)
                info_label.setWordWrap(True)
                changes_layout.addWidget(info_label)
                
                # Примеры изменений
                examples = diff_details.get('examples', {})
                
                if examples:
                    # Добавленные строки
                    added_examples = examples.get('added', [])
                    if added_examples:
                        added_text = "<h3>Примеры добавленных строк</h3><pre>"
                        for i, line in enumerate(added_examples):
                            if i >= 5:  # Ограничиваем количество примеров
                                added_text += "...\n"
                                break
                            added_text += f"+ {line}\n"
                        added_text += "</pre>"
                        
                        added_label = QLabel(added_text)
                        added_label.setTextFormat(Qt.TextFormat.RichText)
                        added_label.setWordWrap(True)
                        changes_layout.addWidget(added_label)
                    
                    # Удаленные строки
                    removed_examples = examples.get('removed', [])
                    if removed_examples:
                        removed_text = "<h3>Примеры удаленных строк</h3><pre>"
                        for i, line in enumerate(removed_examples):
                            if i >= 5:  # Ограничиваем количество примеров
                                removed_text += "...\n"
                                break
                            removed_text += f"- {line}\n"
                        removed_text += "</pre>"
                        
                        removed_label = QLabel(removed_text)
                        removed_label.setTextFormat(Qt.TextFormat.RichText)
                        removed_label.setWordWrap(True)
                        changes_layout.addWidget(removed_label)
            else:
                info_label = QLabel("<h3>Нет детальной информации об изменениях</h3>")
                info_label.setTextFormat(Qt.TextFormat.RichText)
                changes_layout.addWidget(info_label)
            
            changes_layout.addStretch()
            tab_widget.addTab(changes_tab, "Детали изменений")
            
            # Вкладка с контентом
            content_tab = QWidget()
            content_layout = QVBoxLayout(content_tab)
            
            # Информация о снимках
            old_content_path = self.change_data.get('old_content_path')
            new_content_path = self.change_data.get('new_content_path')
            
            # Кнопки для открытия файлов
            btn_layout = QHBoxLayout()
            
            if old_content_path and os.path.exists(old_content_path):
                btn_open_old = QPushButton("Открыть старый контент")
                btn_open_old.setIcon(QIcon("resources/icons/file.png"))
                btn_open_old.clicked.connect(lambda: self._open_file(old_content_path))
                btn_layout.addWidget(btn_open_old)
            
            if new_content_path and os.path.exists(new_content_path):
                btn_open_new = QPushButton("Открыть новый контент")
                btn_open_new.setIcon(QIcon("resources/icons/file.png"))
                btn_open_new.clicked.connect(lambda: self._open_file(new_content_path))
                btn_layout.addWidget(btn_open_new)
            
            content_layout.addLayout(btn_layout)
            
            # Разделитель для контента
            content_splitter = QSplitter(Qt.Orientation.Vertical)
            
            # Старый контент
            old_content_group = QWidget()
            old_content_layout = QVBoxLayout(old_content_group)
            old_content_layout.addWidget(QLabel("<h3>Старый контент</h3>"))
            
            old_content_edit = QTextEdit()
            old_content_edit.setReadOnly(True)
            
            if old_content_path and os.path.exists(old_content_path):
                try:
                    with open(old_content_path, 'r', encoding='utf-8') as f:
                        old_content = f.read()
                        old_content_edit.setPlainText(old_content)
                except Exception as e:
                    old_content_edit.setPlainText(f"Ошибка при чтении файла: {e}")
            else:
                old_content_edit.setPlainText("Файл не найден или недоступен")
            
            old_content_layout.addWidget(old_content_edit)
            content_splitter.addWidget(old_content_group)
            
            # Новый контент
            new_content_group = QWidget()
            new_content_layout = QVBoxLayout(new_content_group)
            new_content_layout.addWidget(QLabel("<h3>Новый контент</h3>"))
            
            new_content_edit = QTextEdit()
            new_content_edit.setReadOnly(True)
            
            if new_content_path and os.path.exists(new_content_path):
                try:
                    with open(new_content_path, 'r', encoding='utf-8') as f:
                        new_content = f.read()
                        new_content_edit.setPlainText(new_content)
                except Exception as e:
                    new_content_edit.setPlainText(f"Ошибка при чтении файла: {e}")
            else:
                new_content_edit.setPlainText("Файл не найден или недоступен")
            
            new_content_layout.addWidget(new_content_edit)
            content_splitter.addWidget(new_content_group)
            
            content_layout.addWidget(content_splitter)
            tab_widget.addTab(content_tab, "Контент")
            
            # Создаем вкладку с визуальным сравнением (HTML diff)
            visual_diff_tab = QWidget()
            visual_diff_layout = QVBoxLayout(visual_diff_tab)
            
            # Получаем пути к файлам со снимками содержимого
            old_content_path = self.change_data.get('old_content_path', '')
            new_content_path = self.change_data.get('new_content_path', '')
            
            if old_content_path and new_content_path and os.path.exists(old_content_path) and os.path.exists(new_content_path):
                try:
                    # Загружаем содержимое файлов
                    with open(old_content_path, 'r', encoding='utf-8') as f:
                        old_content = f.read()
                    
                    with open(new_content_path, 'r', encoding='utf-8') as f:
                        new_content = f.read()
                    
                    # Создаем HTML diff
                    html_diff = self._generate_html_diff(old_content, new_content)
                    
                    # Создаем просмотрщик для HTML diff
                    diff_viewer = QTextEdit()
                    diff_viewer.setReadOnly(True)
                    diff_viewer.setHtml(html_diff)
                    
                    visual_diff_layout.addWidget(diff_viewer)
                except Exception as e:
                    self.logger.error(f"Ошибка при загрузке содержимого файлов: {e}")
                    log_exception(self.logger, "Ошибка загрузки содержимого файлов")
                    
                    error_label = QLabel(f"Не удалось загрузить содержимое файлов: {e}")
                    error_label.setWordWrap(True)
                    visual_diff_layout.addWidget(error_label)
            else:
                not_available_label = QLabel("Файлы со снимками содержимого не найдены")
                not_available_label.setWordWrap(True)
                visual_diff_layout.addWidget(not_available_label)
            
            # Добавляем вкладку в таб-виджет
            tab_widget.addTab(visual_diff_tab, "Визуальное сравнение")
            
            # Вкладка с семантическим анализом
            semantic_tab = QWidget()
            semantic_layout = QVBoxLayout(semantic_tab)
            
            semantic_analysis = self._analyze_changes_semantically(diff_details)
            
            semantic_text = QTextEdit()
            semantic_text.setReadOnly(True)
            semantic_text.setHtml(semantic_analysis)
            
            semantic_layout.addWidget(semantic_text)
            
            # Добавляем вкладку в таб-виджет
            tab_widget.addTab(semantic_tab, "Семантический анализ")
            
            # Добавляем вкладку в основной макет
            layout.addWidget(tab_widget)
            
            # Кнопки
            btn_layout = QHBoxLayout()
            
            # Кнопка "Отметить как прочитанное"
            if status != 'read':
                btn_mark_read = QPushButton("Отметить как прочитанное")
                btn_mark_read.setIcon(QIcon("resources/icons/check.png"))
                btn_mark_read.clicked.connect(self._mark_as_read)
                btn_layout.addWidget(btn_mark_read)
            
            # Кнопка "Закрыть"
            btn_close = QPushButton("Закрыть")
            btn_close.setIcon(QIcon("resources/icons/close.png"))
            btn_close.clicked.connect(self.close)
            btn_layout.addWidget(btn_close)
            
            layout.addLayout(btn_layout)
        else:
            # Если данные об изменении не найдены
            error_label = QLabel("<h3>Ошибка: Данные об изменении не найдены</h3>")
            error_label.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(error_label)
            
            # Кнопка "Закрыть"
            btn_close = QPushButton("Закрыть")
            btn_close.setIcon(QIcon("resources/icons/close.png"))
            btn_close.clicked.connect(self.close)
            layout.addWidget(btn_close)
    
    @handle_errors(error_msg="Ошибка при открытии URL")
    def _open_url(self, url):
        """
        Открытие URL в браузере
        
        Args:
            url: URL для открытия
        """
        import webbrowser
        webbrowser.open(url)
    
    @handle_errors(error_msg="Ошибка при открытии файла")
    def _open_file(self, file_path):
        """
        Открытие файла в ассоциированной программе
        
        Args:
            file_path: Путь к файлу
        """
        import os
        import platform
        
        if platform.system() == 'Windows':
            os.startfile(file_path)
        elif platform.system() == 'Darwin':  # macOS
            os.system(f'open "{file_path}"')
        else:  # Linux
            os.system(f'xdg-open "{file_path}"')
    
    @handle_errors(error_msg="Ошибка при отметке изменения как прочитанного")
    def _mark_as_read(self):
        """Отметка изменения как прочитанного"""
        if self.app_context.mark_change_as_read(self.change_id):
            self.logger.info(f"Изменение ID={self.change_id} отмечено как прочитанное")
            QMessageBox.information(self, "Информация", "Изменение отмечено как прочитанное")
            
            # Обновляем данные
            self.change_data = self.app_context.get_change(self.change_id)
            
            # Перезагружаем UI
            self.close()
            # Если нужно обновить родительский виджет
            if hasattr(self.parent(), "update_data"):
                self.parent().update_data()
        else:
            self.logger.error(f"Не удалось отметить изменение ID={self.change_id} как прочитанное")
            QMessageBox.critical(self, "Ошибка", "Не удалось отметить изменение как прочитанное")
    
    @handle_errors(error_msg="Ошибка при создании HTML diff")
    def _generate_html_diff(self, old_content, new_content):
        """
        Создает HTML-представление разницы между старым и новым содержимым
        
        Args:
            old_content: Старое содержимое
            new_content: Новое содержимое
            
        Returns:
            str: HTML-код с выделенными изменениями
        """
        # Разбиваем контент на строки
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()
        
        # Создаем HTML diff
        differ = difflib.HtmlDiff(tabsize=4, wrapcolumn=80)
        html_diff = differ.make_table(
            old_lines,
            new_lines,
            fromdesc="Предыдущая версия",
            todesc="Текущая версия",
            context=True,
            numlines=3
        )
        
        # Добавляем стили для лучшего отображения
        css_styles = """
        <style>
            .diff_header {background-color: #e0e0e0; font-weight: bold; padding: 3px;}
            .diff_next {background-color: #c0c0c0; font-weight: bold; padding: 3px;}
            .diff_add {background-color: #aaffaa; padding: 3px;}
            .diff_chg {background-color: #ffff77; padding: 3px;}
            .diff_sub {background-color: #ffaaaa; padding: 3px;}
            table.diff {border-collapse: collapse; width: 100%;}
            table.diff td {padding: 3px; vertical-align: top; font-family: monospace;}
            table.diff th {background-color: #e0e0e0; padding: 3px;}
        </style>
        """
        
        # Добавляем CSS-стили к HTML-дифу
        html_diff = css_styles + html_diff
        
        return html_diff
    
    @handle_errors(error_msg="Ошибка при семантическом анализе изменений")
    def _analyze_changes_semantically(self, diff_details):
        """
        Проводит семантический анализ изменений и выдает результат в виде HTML
        
        Args:
            diff_details: Детали изменений
            
        Returns:
            str: HTML-код с результатами семантического анализа
        """
        added_lines = diff_details.get('added_lines', 0)
        removed_lines = diff_details.get('removed_lines', 0)
        total_changes = diff_details.get('total_changes', 0)
        total_lines = diff_details.get('total_lines', 0)
        examples = diff_details.get('examples', {})
        
        added_examples = examples.get('added', [])
        removed_examples = examples.get('removed', [])
        
        # Анализируем тип изменений
        change_type = "Неопределенный"
        if added_lines > 0 and removed_lines == 0:
            change_type = "Добавление контента"
        elif added_lines == 0 and removed_lines > 0:
            change_type = "Удаление контента"
        elif added_lines > 0 and removed_lines > 0:
            if added_lines > removed_lines * 2:
                change_type = "Преимущественно добавление контента"
            elif removed_lines > added_lines * 2:
                change_type = "Преимущественно удаление контента"
            else:
                change_type = "Модификация контента"
        
        # Анализируем значимость изменений
        significance = "Низкая"
        diff_percent = 0
        if total_lines > 0:
            diff_percent = (total_changes / total_lines) * 100
            if diff_percent > 50:
                significance = "Высокая"
            elif diff_percent > 20:
                significance = "Средняя"
        
        # Получаем цвет для значимости
        significance_color = get_diff_color(diff_percent).name()
        
        # Формируем HTML-результат
        html_result = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1, h2, h3 {{ color: #333366; }}
                .significance {{ font-weight: bold; color: {significance_color}; }}
                .changes {{ margin-top: 20px; }}
                .examples {{ margin-top: 20px; }}
                .examples pre {{ background-color: #f5f5f5; padding: 10px; border-radius: 5px; }}
                .added {{ background-color: #e6ffe6; }}
                .removed {{ background-color: #ffe6e6; }}
            </style>
        </head>
        <body>
            <h1>Семантический анализ изменений</h1>
            
            <div class="changes">
                <h2>Тип изменений</h2>
                <p><b>{change_type}</b></p>
                
                <h2>Значимость изменений</h2>
                <p class="significance">
                    {significance} ({diff_percent:.2f}%)
                </p>
                
                <h2>Статистика</h2>
                <ul>
                    <li>Добавлено строк: {added_lines}</li>
                    <li>Удалено строк: {removed_lines}</li>
                    <li>Всего изменений: {total_changes}</li>
                    <li>Всего строк: {total_lines}</li>
                </ul>
            </div>
            
            <div class="examples">
                <h2>Примеры изменений</h2>
        """
        
        if added_examples:
            html_result += """
                <h3>Добавленные элементы</h3>
                <div class="added">
                    <pre>
            """
            for example in added_examples[:5]:  # Первые 5 примеров
                html_result += f"{example}\n"
            html_result += """
                    </pre>
                </div>
            """
        
        if removed_examples:
            html_result += """
                <h3>Удаленные элементы</h3>
                <div class="removed">
                    <pre>
            """
            for example in removed_examples[:5]:  # Первые 5 примеров
                html_result += f"{example}\n"
            html_result += """
                    </pre>
                </div>
            """
        
        html_result += """
            </div>
        </body>
        </html>
        """
        
        return html_result


class ChangesWidget(QWidget):
    """Виджет для отображения изменений сайтов"""
    
    def __init__(self, app_context, parent=None):
        """
        Инициализация виджета изменений
        
        Args:
            app_context: Контекст приложения
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger('ui.changes_widget')
        self.app_context = app_context
        self.parent = parent
        
        # Инициализация UI
        self._init_ui()
        
        # Обновление данных
        self.update_data()
        
        self.logger.debug("Виджет изменений инициализирован")
    
    @handle_errors(error_msg="Ошибка при инициализации интерфейса виджета изменений")
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        # Основной макет
        layout = QVBoxLayout(self)
        
        # Панель инструментов
        toolbar_layout = QHBoxLayout()
        
        # Кнопка "Обновить"
        self.btn_refresh = QPushButton("Обновить")
        self.btn_refresh.setIcon(QIcon("resources/icons/refresh.png"))
        self.btn_refresh.clicked.connect(self.update_data)
        toolbar_layout.addWidget(self.btn_refresh)
        
        # Кнопка "Отметить все как прочитанные"
        self.btn_mark_all_read = QPushButton("Отметить все как прочитанные")
        self.btn_mark_all_read.setIcon(QIcon("resources/icons/check_all.png"))
        self.btn_mark_all_read.clicked.connect(self._mark_all_as_read)
        toolbar_layout.addWidget(self.btn_mark_all_read)
        
        # Кнопка "Экспорт"
        self.btn_export = QPushButton("Экспорт")
        self.btn_export.setIcon(QIcon("resources/icons/export.png"))
        self.btn_export.clicked.connect(self._export_changes)
        toolbar_layout.addWidget(self.btn_export)
        
        toolbar_layout.addStretch()
        
        layout.addLayout(toolbar_layout)
        
        # Таблица с изменениями
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ID", "Сайт", "URL", "Дата", "Отличия", "Статус"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        
        # Подключение сигнала по двойному клику
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        
        layout.addWidget(self.table)
        
        # Панель статуса
        status_layout = QHBoxLayout()
        
        self.status_label = QLabel("Всего изменений: 0")
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        
        layout.addLayout(status_layout)
    
    @handle_errors(error_msg="Ошибка при обновлении данных в таблице изменений")
    def update_data(self):
        """Обновление данных в таблице"""
        # Получаем список изменений
        changes = self.app_context.get_changes()
        
        # Очищаем таблицу
        self.table.setRowCount(0)
        
        if not changes:
            self.status_label.setText("Всего изменений: 0")
            return
        
        # Заполняем таблицу
        for i, change in enumerate(changes):
            self.table.insertRow(i)
            
            # ID
            self.table.setItem(i, 0, QTableWidgetItem(str(change.get('id', ''))))
            
            # Сайт
            self.table.setItem(i, 1, QTableWidgetItem(change.get('site_name', '')))
            
            # URL
            self.table.setItem(i, 2, QTableWidgetItem(change.get('site_url', '')))
            
            # Дата
            date_str = format_timestamp(change.get('timestamp'), "%d.%m.%Y %H:%M")
            self.table.setItem(i, 3, QTableWidgetItem(date_str))
            
            # Отличия
            diff_percent = change.get('diff_percent')
            if diff_percent is None:
                diff_percent = 0.0
            
            diff_item = QTableWidgetItem(f"{diff_percent:.2f}%")
            diff_item.setForeground(get_diff_color(diff_percent))
            self.table.setItem(i, 4, diff_item)
            
            # Статус
            status = change.get('status', '')
            status_map = {
                'unread': "Не прочитано",
                'read': "Прочитано"
            }
            status_text = status_map.get(status, status)
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(get_status_color(status))
            self.table.setItem(i, 5, status_item)
        
        # Обновляем панель статуса
        self.status_label.setText(f"Всего изменений: {len(changes)}")
        
        # Обновляем активность кнопки "Отметить все как прочитанные"
        unread_count = sum(1 for change in changes if change.get('status') == 'unread')
        self.btn_mark_all_read.setEnabled(unread_count > 0)
    
    @handle_errors(error_msg="Ошибка при обработке двойного клика по ячейке")
    def _on_cell_double_clicked(self, row, column):
        """
        Обработка двойного клика по ячейке таблицы
        
        Args:
            row: Индекс строки
            column: Индекс столбца
        """
        # Получаем ID изменения
        change_id = int(self.table.item(row, 0).text())
        
        # Открываем диалог с деталями изменения
        self.open_change(change_id)
    
    @handle_errors(error_msg="Ошибка при открытии диалога с деталями изменения")
    def open_change(self, change_id):
        """
        Открытие диалога с деталями изменения
        
        Args:
            change_id: ID изменения
        """
        # Создаем и открываем диалог
        dialog = ChangeDetailsDialog(self.app_context, change_id, self)
        dialog.exec()
        
        # После закрытия диалога обновляем данные
        self.update_data()
    
    @handle_errors(error_msg="Ошибка при отметке всех изменений как прочитанных")
    def _mark_all_as_read(self):
        """Отметка всех изменений как прочитанные"""
        # Запрашиваем подтверждение
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Вы уверены, что хотите отметить все изменения как прочитанные?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Получаем список непрочитанных изменений
            unread_changes = []
            for row in range(self.table.rowCount()):
                change_id = int(self.table.item(row, 0).text())
                status = self.table.item(row, 5).text()
                if status == "Не прочитано":
                    unread_changes.append(change_id)
            
            if not unread_changes:
                self.logger.info("Нет непрочитанных изменений")
                if hasattr(self.parent, "show_message"):
                    self.parent.show_message("Информация", "Нет непрочитанных изменений")
                return
            
            # Отмечаем все непрочитанные изменения как прочитанные
            success_count = 0
            for change_id in unread_changes:
                if self.app_context.mark_change_as_read(change_id):
                    success_count += 1
            
            self.logger.info(f"Отмечено {success_count} из {len(unread_changes)} изменений как прочитанные")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Информация", f"Отмечено {success_count} из {len(unread_changes)} изменений как прочитанные")
            
            # Обновляем данные
            self.update_data()
    
    @handle_errors(error_msg="Ошибка при экспорте изменений")
    def _export_changes(self):
        """Экспорт изменений в CSV файл"""
        # Выбор файла для сохранения
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт изменений",
            "",
            "CSV файлы (*.csv)"
        )
        
        if not file_path:
            return
        
        # Если файл не имеет расширения .csv, добавляем его
        if not file_path.lower().endswith('.csv'):
            file_path += '.csv'
        
        # Получаем данные для экспорта
        data = []
        for row in range(self.table.rowCount()):
            row_data = []
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                row_data.append(item.text() if item else "")
            data.append(row_data)
        
        # Заголовки столбцов
        headers = ["ID", "Сайт", "URL", "Дата", "Отличия", "Статус"]
        
        # Экспорт в CSV
        import csv
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(data)
        
        self.logger.info(f"Изменения экспортированы в {file_path}")
        if hasattr(self.parent, "show_message"):
            self.parent.show_message("Информация", f"Изменения экспортированы в {file_path}") 