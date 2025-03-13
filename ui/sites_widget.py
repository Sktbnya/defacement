#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль виджета управления сайтами для WDM_V12.
Содержит класс SitesWidget, который предоставляет интерфейс для управления списком мониторинга сайтов.
"""

import os
import datetime
from typing import Dict, List, Any, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView, 
    QDialog, QFormLayout, QLineEdit, QComboBox, QCheckBox, 
    QMessageBox, QFileDialog, QToolBar, QMenu, QSpinBox,
    QSplitter, QTextEdit, QDialogButtonBox, QGroupBox,
    QTabWidget, QScrollArea, QSizePolicy, QPlainTextEdit
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QCoreApplication
from PyQt6.QtGui import QIcon, QAction, QColor, QFont, QBrush
from PyQt6.QtWidgets import QDateTime

from utils.logger import get_module_logger, log_exception
from utils.common import format_timestamp, get_diff_color, get_status_color, handle_errors
from ui.table_utils import OptimizedTable, BatchDataLoader, get_ui_updater
from ui.table_converter import TableStyler, CommonTableSetup


class SiteDialog(QDialog):
    """Диалог для добавления/редактирования сайта"""
    
    def __init__(self, app_context, site_data=None, parent=None):
        """
        Инициализация диалога
        
        Args:
            app_context: Контекст приложения
            site_data: Данные сайта для редактирования (None для нового сайта)
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger('ui.sites_widget.site_dialog')
        self.app_context = app_context
        self.site_data = site_data or {}
        self.edit_mode = bool(site_data)
        
        # Настройка диалога
        self.setWindowTitle("Редактирование сайта" if self.edit_mode else "Добавление сайта")
        self.resize(700, 500)
        
        # Инициализация UI
        self._init_ui()
        
        # Если редактируем существующий сайт, заполняем поля
        if self.edit_mode:
            self._fill_fields()
        
        self.logger.debug(f"Диалог {'редактирования' if self.edit_mode else 'добавления'} сайта инициализирован")
    
    def _init_ui(self):
        """Инициализация элементов интерфейса"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        
        # Форма для ввода данных
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # Имя и URL сайта
        self.name_edit = QLineEdit()
        form_layout.addRow("Имя сайта*:", self.name_edit)
        
        # URL с кнопкой тестирования
        url_layout = QHBoxLayout()
        self.url_edit = QLineEdit()
        url_layout.addWidget(self.url_edit)
        
        self.test_url_button = QPushButton("Тест")
        self.test_url_button.setToolTip("Проверить доступность URL")
        self.test_url_button.clicked.connect(self._on_test_url)
        url_layout.addWidget(self.test_url_button)
        
        form_layout.addRow("URL сайта*:", url_layout)
        
        # Описание сайта
        self.description_edit = QPlainTextEdit()
        self.description_edit.setMaximumHeight(80)
        form_layout.addRow("Описание:", self.description_edit)
        
        # Группа
        self.group_combo = QComboBox()
        self.group_combo.addItem("Нет группы", None)
        groups = self.app_context.get_all_groups() or []
        for group in groups:
            self.group_combo.addItem(group['name'], group['id'])
        form_layout.addRow("Группа:", self.group_combo)
        
        # Метод проверки
        self.method_combo = QComboBox()
        self.method_combo.addItem("Статический (HTTP запрос)", "static")
        self.method_combo.addItem("Динамический (браузер)", "dynamic")
        self.method_combo.currentIndexChanged.connect(self._on_method_changed)
        form_layout.addRow("Метод проверки:", self.method_combo)
        
        # Интервал проверки
        interval_layout = QHBoxLayout()
        self.interval_spin = QSpinBox()
        self.interval_spin.setMinimum(1)
        self.interval_spin.setMaximum(1000)
        self.interval_spin.setValue(1)
        interval_layout.addWidget(self.interval_spin)
        
        self.interval_combo = QComboBox()
        self.interval_combo.addItem("минута", 60)
        self.interval_combo.addItem("час", 3600)
        self.interval_combo.addItem("день", 86400)
        self.interval_combo.setCurrentIndex(1)  # По умолчанию "час"
        interval_layout.addWidget(self.interval_combo)
        
        form_layout.addRow("Интервал проверки:", interval_layout)
        
        # Приоритет проверки
        self.priority_spin = QSpinBox()
        self.priority_spin.setMinimum(1)
        self.priority_spin.setMaximum(10)
        self.priority_spin.setValue(5)
        form_layout.addRow("Приоритет:", self.priority_spin)
        
        # Статус сайта
        self.status_combo = QComboBox()
        self.status_combo.addItem("Активный", "active")
        self.status_combo.addItem("Приостановлен", "paused")
        self.status_combo.addItem("Неактивный", "inactive")
        form_layout.addRow("Статус:", self.status_combo)
        
        # Уведомления об изменениях
        self.notify_check = QCheckBox("Уведомлять об изменениях")
        self.notify_check.setChecked(True)
        form_layout.addRow("", self.notify_check)
        
        # Добавляем основную форму
        main_layout.addLayout(form_layout)
        
        # Табы для дополнительных настроек
        self.tabs = QTabWidget()
        
        # Таб с расширенными настройками
        advanced_tab = QWidget()
        advanced_layout = QFormLayout(advanced_tab)
        
        # CSS селектор
        self.css_selector_edit = QLineEdit()
        advanced_layout.addRow("CSS селектор:", self.css_selector_edit)
        
        # XPath
        self.xpath_edit = QLineEdit()
        advanced_layout.addRow("XPath:", self.xpath_edit)
        
        # Регулярные выражения
        self.include_regex_edit = QLineEdit()
        advanced_layout.addRow("Включать содержимое, соответствующее:", self.include_regex_edit)
        
        self.exclude_regex_edit = QLineEdit()
        advanced_layout.addRow("Исключать содержимое, соответствующее:", self.exclude_regex_edit)
        
        self.tabs.addTab(advanced_tab, "Расширенные настройки")
        
        # Справка
        help_tab = QWidget()
        help_layout = QVBoxLayout(help_tab)
        
        help_text = QLabel()
        help_text.setText("""
        <h3>Справка по добавлению сайта</h3>
        <p><b>Основные настройки:</b></p>
        <ul>
        <li><b>Имя сайта</b> - название для идентификации сайта в системе</li>
        <li><b>URL сайта</b> - полный адрес страницы для мониторинга (с http:// или https://)</li>
        <li><b>Группа</b> - объединение сайтов по категориям для удобства управления</li>
        <li><b>Метод проверки</b> - способ получения содержимого страницы:
            <ul>
            <li><b>Статический</b> - простой HTTP запрос, быстрый и эффективный для большинства сайтов</li>
            <li><b>Динамический</b> - использует браузер для загрузки JavaScript, подходит для сложных сайтов</li>
            </ul>
        </li>
        <li><b>Интервал проверки</b> - периодичность проверки сайта на изменения</li>
        <li><b>Приоритет</b> - важность сайта при планировании проверок (выше значение = выше приоритет)</li>
        <li><b>Статус</b> - текущее состояние мониторинга сайта</li>
        </ul>
        
        <p><b>Расширенные настройки:</b></p>
        <ul>
        <li><b>CSS селектор</b> - указывает конкретный элемент на странице для отслеживания</li>
        <li><b>XPath</b> - альтернативный способ выбора элемента на странице</li>
        <li><b>Регулярные выражения</b> - дополнительная фильтрация содержимого</li>
        </ul>
        """)
        help_text.setWordWrap(True)
        help_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        help_scroll = QScrollArea()
        help_scroll.setWidget(help_text)
        help_scroll.setWidgetResizable(True)
        
        help_layout.addWidget(help_scroll)
        
        self.tabs.addTab(help_tab, "Справка")
        
        main_layout.addWidget(self.tabs)
        
        # Кнопки
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
        
        # Устанавливаем фокус на первое поле
        self.name_edit.setFocus()
    
    def _on_method_changed(self, index):
        """Обработка изменения метода проверки"""
        method = self.method_combo.currentData()
        self.logger.debug(f"Изменен метод проверки на: {method}")
        
        # Можно добавить дополнительную логику, например, показывать дополнительные поля
        # в зависимости от выбранного метода
    
    def _on_test_url(self):
        """Обработка нажатия на кнопку тестирования URL"""
        url = self.url_edit.text().strip()
        
        if not url:
            QMessageBox.warning(self, "Ошибка", "Введите URL для тестирования")
            return
        
        # Проверяем и исправляем URL при необходимости
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
            self.url_edit.setText(url)
        
        # Отключаем кнопку на время тестирования
        self.test_url_button.setEnabled(False)
        self.test_url_button.setText("Проверка...")
        
        # Запускаем проверку в отдельном потоке
        QCoreApplication.processEvents()
        try:
            # Проверяем доступность URL
            is_available, message = self.app_context.test_url(url)
            
            if is_available:
                QMessageBox.information(self, "Результат проверки", f"URL доступен.\n{message}")
            else:
                QMessageBox.warning(self, "Результат проверки", f"URL недоступен.\n{message}")
                
        except Exception as e:
            self.logger.error(f"Ошибка при тестировании URL: {e}")
            log_exception(self.logger, "Ошибка тестирования URL")
            QMessageBox.critical(self, "Ошибка", f"Не удалось выполнить проверку: {e}")
        
        finally:
            # Восстанавливаем кнопку
            self.test_url_button.setEnabled(True)
            self.test_url_button.setText("Тест")
    
    def _fill_fields(self):
        """Заполнение полей данными сайта при редактировании"""
        # Основные поля
        self.name_edit.setText(self.site_data.get('name', ''))
        self.url_edit.setText(self.site_data.get('url', ''))
        self.description_edit.setPlainText(self.site_data.get('description', ''))
        
        # Группа
        group_id = self.site_data.get('group_id')
        if group_id is not None:
            index = self.group_combo.findData(group_id)
            if index >= 0:
                self.group_combo.setCurrentIndex(index)
        
        # Метод проверки
        method = self.site_data.get('check_method', 'static')
        index = self.method_combo.findData(method)
        if index >= 0:
            self.method_combo.setCurrentIndex(index)
        
        # Интервал проверки
        interval = self.site_data.get('check_interval', 3600)
        
        # Выбираем наиболее подходящую единицу измерения
        if interval % 86400 == 0 and interval > 0:  # дни
            self.interval_combo.setCurrentIndex(2)
            self.interval_spin.setValue(interval // 3600)
        elif interval % 3600 == 0 and interval > 0:  # часы
            self.interval_combo.setCurrentIndex(1)
            self.interval_spin.setValue(interval // 3600)
        else:  # минуты
            self.interval_combo.setCurrentIndex(0)
            self.interval_spin.setValue(interval // 60)
        
        # Приоритет
        self.priority_spin.setValue(self.site_data.get('priority', 5))
        
        # Статус
        status = self.site_data.get('status', 'active')
        index = self.status_combo.findData(status)
        if index >= 0:
            self.status_combo.setCurrentIndex(index)
        
        # Уведомления
        self.notify_check.setChecked(bool(self.site_data.get('notify_on_change', True)))
        
        # Расширенные настройки
        self.css_selector_edit.setText(self.site_data.get('css_selector', ''))
        self.xpath_edit.setText(self.site_data.get('xpath', ''))
        self.include_regex_edit.setText(self.site_data.get('include_regex', ''))
        self.exclude_regex_edit.setText(self.site_data.get('exclude_regex', ''))
    
    def accept(self):
        """Обработка принятия диалога (нажатие OK)"""
        try:
            # Валидация обязательных полей
            name = self.name_edit.text().strip()
            url = self.url_edit.text().strip()
            
            if not name:
                QMessageBox.warning(self, "Ошибка", "Необходимо указать имя сайта")
                return
            
            if not url:
                QMessageBox.warning(self, "Ошибка", "Необходимо указать URL сайта")
                return
            
            if not url.startswith(('http://', 'https://')):
                QMessageBox.warning(self, "Ошибка", "URL должен начинаться с http:// или https://")
                return
            
            # Сбор данных
            site_data = {
                'name': name,
                'url': url,
                'description': self.description_edit.toPlainText().strip(),
                'check_method': self.method_combo.currentData(),
                'check_interval': self.interval_spin.value() * self.interval_combo.itemData(self.interval_combo.currentIndex()),
                'css_selector': self.css_selector_edit.text().strip(),
                'xpath': self.xpath_edit.text().strip(),
                'include_regex': self.include_regex_edit.text().strip(),
                'exclude_regex': self.exclude_regex_edit.text().strip(),
                'status': self.status_combo.currentData(),
                'priority': self.priority_spin.value(),
                'notify_on_change': self.notify_check.isChecked()
            }
            
            # Группа
            group_id = self.group_combo.currentData()
            if group_id is not None:
                site_data['group_id'] = group_id
            
            # Добавление или обновление сайта
            if self.edit_mode:
                # Обновление существующего сайта
                site_id = self.site_data['id']
                if self.app_context.update_site(site_id, site_data):
                    self.logger.info(f"Сайт {name} (ID: {site_id}) обновлен")
                    if hasattr(self.parent(), "update_data"):
                        QMessageBox.information(self, "Информация", f"Сайт '{name}' успешно обновлен")
                else:
                    self.logger.error(f"Не удалось обновить сайт {name} (ID: {site_id})")
                    QMessageBox.critical(self, "Ошибка", f"Не удалось обновить сайт '{name}'")
                    return
            else:
                # Добавление нового сайта
                site_id = self.app_context.add_site(site_data)
                if site_id:
                    self.logger.info(f"Добавлен новый сайт {name} (ID: {site_id})")
                    QMessageBox.information(self, "Информация", f"Сайт '{name}' успешно добавлен")
                else:
                    self.logger.error(f"Не удалось добавить сайт {name}")
                    QMessageBox.critical(self, "Ошибка", f"Не удалось добавить сайт '{name}'")
                    return
            
            # Закрываем диалог
            super().accept()
        
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении сайта: {e}")
            log_exception(self.logger, "Ошибка сохранения сайта")
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить сайт: {e}")


class SitesWidget(QWidget):
    """Виджет для управления сайтами"""
    
    def __init__(self, app_context, parent=None):
        """
        Инициализация виджета сайтов
        
        Args:
            app_context: Контекст приложения
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger('ui.sites_widget')
        self.logger.debug("Инициализация виджета сайтов")
        
        self.app_context = app_context
        self.parent = parent
        
        # Инициализация UI
        self._init_ui()
        
        # Создаем менеджер обновлений UI
        self.ui_updater = get_ui_updater()
        self.ui_updater.set_delay(200)  # 200 мс задержка для группировки обновлений
        
        # Регистрируем обработчик обновлений для таблицы сайтов
        self.ui_updater.register_handler("sites_table", self._update_sites_table)
        
        # Создаем загрузчик данных для таблицы
        self.data_loader = BatchDataLoader(self.sites_table)
        self.data_loader.batch_size = 50  # Загружаем по 50 сайтов за раз
        
        self.update_data()
        
        self.logger.debug("Виджет сайтов инициализирован")
    
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        # Основной макет
        layout = QVBoxLayout(self)
        
        # Панель инструментов
        toolbar_layout = QHBoxLayout()
        
        # Кнопка "Добавить сайт"
        self.btn_add_site = QPushButton("Добавить сайт")
        self.btn_add_site.setIcon(QIcon("resources/icons/add.png"))
        self.btn_add_site.clicked.connect(self.show_add_site_dialog)
        toolbar_layout.addWidget(self.btn_add_site)
        
        # Кнопка "Удалить выбранные"
        self.btn_delete_sites = QPushButton("Удалить выбранные")
        self.btn_delete_sites.setIcon(QIcon("resources/icons/delete.png"))
        self.btn_delete_sites.clicked.connect(self._delete_selected_sites)
        self.btn_delete_sites.setEnabled(False)  # По умолчанию отключена
        toolbar_layout.addWidget(self.btn_delete_sites)
        
        # Кнопка "Проверить выбранные"
        self.btn_check_sites = QPushButton("Проверить выбранные")
        self.btn_check_sites.setIcon(QIcon("resources/icons/check.png"))
        self.btn_check_sites.clicked.connect(self._check_selected_sites)
        self.btn_check_sites.setEnabled(False)  # По умолчанию отключена
        toolbar_layout.addWidget(self.btn_check_sites)
        
        # Кнопка "Обновить"
        self.btn_refresh = QPushButton("Обновить")
        self.btn_refresh.setIcon(QIcon("resources/icons/refresh.png"))
        self.btn_refresh.clicked.connect(self.update_data)
        toolbar_layout.addWidget(self.btn_refresh)
        
        # Кнопка "Импорт/Экспорт"
        self.btn_import_export = QPushButton("Импорт/Экспорт")
        self.btn_import_export.setIcon(QIcon("resources/icons/import_export.png"))
        
        # Создаем меню для кнопки
        import_export_menu = QMenu(self)
        
        import_action = QAction("Импорт сайтов из CSV", self)
        import_action.triggered.connect(self._import_sites)
        import_export_menu.addAction(import_action)
        
        export_action = QAction("Экспорт сайтов в CSV", self)
        export_action.triggered.connect(self._export_sites)
        import_export_menu.addAction(export_action)
        
        self.btn_import_export.setMenu(import_export_menu)
        toolbar_layout.addWidget(self.btn_import_export)
        
        toolbar_layout.addStretch()
        
        layout.addLayout(toolbar_layout)
        
        # Создаем оптимизированную таблицу вместо обычной
        self.sites_table = OptimizedTable(0, 0)
        self.sites_table.setObjectName("sites_table")
        
        # Настраиваем таблицу с помощью общего метода настройки
        CommonTableSetup.setup_site_table(
            self.sites_table,
            connect_signals=True,
            parent=self,
            double_click_handler=self.on_site_double_clicked
        )
        
        # Создаем индексы для ускорения поиска
        self.sites_table.create_index(0, True)  # ID (уникальный)
        self.sites_table.create_index(1, False)  # URL
        self.sites_table.create_index(4, False)  # Статус
        
        layout.addWidget(self.sites_table)
        
        # Панель статуса
        status_layout = QHBoxLayout()
        
        self.status_label = QLabel("Всего сайтов: 0")
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        
        layout.addLayout(status_layout)
    
    def update_data(self):
        """Обновляет данные в таблице."""
        # Блокируем обновления UI во время загрузки данных
        self.ui_updater.block_updates(True)
        
        try:
            # Получаем данные сайтов с учетом фильтров
            sites = self.get_filtered_sites()
            
            # Определяем маппинг полей на столбцы
            column_mapping = {
                "id": 0,
                "url": 1,
                "name": 2,
                "type": 3,
                "status": 4,
                "last_check": 5,
                "interval": 6,
                "tags": 7
            }
            
            # Создаем специальные обработчики для некоторых полей
            item_creators = {
                "status": lambda status: self._create_status_item(status),
                "last_check": lambda timestamp: self._create_timestamp_item(timestamp),
                "tags": lambda tags: self._create_tags_item(tags)
            }
            
            # Используем пакетную загрузку данных
            self.sites_table.set_loading(True)
            self.data_loader.load_data(sites, column_mapping, item_creators)
            self.sites_table.set_loading(False)
            
            # Обновляем статистику
            self.update_stats(sites)
        
        finally:
            # Разблокируем обновления UI
            self.ui_updater.block_updates(False)
    
    def _create_status_item(self, status):
        """
        Создает элемент для отображения статуса сайта.
        
        Args:
            status: Статус сайта
            
        Returns:
            QTableWidgetItem: Элемент для отображения статуса
        """
        item = QTableWidgetItem(status)
        
        # Применяем цветовое оформление в зависимости от статуса
        if status == "Active":
            item.setForeground(QBrush(QColor("#4CAF50")))
        elif status == "Error":
            item.setForeground(QBrush(QColor("#F44336")))
        elif status == "Warning":
            item.setForeground(QBrush(QColor("#FF9800")))
        
        return item
    
    def _create_timestamp_item(self, timestamp):
        """
        Создает элемент для отображения временной метки.
        
        Args:
            timestamp: Временная метка
            
        Returns:
            QTableWidgetItem: Элемент для отображения временной метки
        """
        if not timestamp:
            return QTableWidgetItem("Never")
            
        # Форматируем дату и время
        dt = QDateTime.fromSecsSinceEpoch(timestamp)
        formatted_date = dt.toString("yyyy-MM-dd HH:mm:ss")
        
        item = QTableWidgetItem(formatted_date)
        
        # Добавляем полные данные для сортировки
        item.setData(Qt.ItemDataRole.UserRole, timestamp)
        
        return item
    
    def _create_tags_item(self, tags):
        """
        Создает элемент для отображения тегов.
        
        Args:
            tags: Список тегов
            
        Returns:
            QTableWidgetItem: Элемент для отображения тегов
        """
        if not tags:
            return QTableWidgetItem("")
            
        # Объединяем теги в строку
        tags_text = ", ".join(tags)
        
        item = QTableWidgetItem(tags_text)
        
        # Добавляем полные данные для фильтрации
        item.setData(Qt.ItemDataRole.UserRole, tags)
        
        return item
    
    def _update_sites_table(self, properties):
        """
        Обработчик отложенных обновлений для таблицы сайтов.
        Вызывается через UIUpdater.
        
        Args:
            properties: Словарь обновляемых свойств
        """
        if "filter_changed" in properties:
            # Обновляем фильтр и затем данные
            self.current_filter = properties.get("filter", {})
            self.update_data()
        
        elif "site_changed" in properties:
            # Обновляем конкретный сайт
            site_id = properties.get("site_id")
            if site_id:
                self.update_site_row(site_id)
        
        elif "full_update" in properties:
            # Полное обновление данных
            self.update_data()
    
    def update_site_row(self, site_id):
        """
        Обновляет строку для конкретного сайта.
        
        Args:
            site_id: ID сайта для обновления
        """
        # Поиск строки по ID используя индекс
        row = self.sites_table.find_row(0, str(site_id))
        
        if row is not None:
            # Получаем актуальные данные сайта
            site_data = self.get_site_data(site_id)
            
            if site_data:
                # Обновляем данные в строке
                self.sites_table.set_loading(True)
                self.sites_table.setItem(row, 1, QTableWidgetItem(site_data["url"]))
                self.sites_table.setItem(row, 2, QTableWidgetItem(site_data["name"]))
                self.sites_table.setItem(row, 3, QTableWidgetItem(site_data["type"]))
                self.sites_table.setItem(row, 4, self._create_status_item(site_data["status"]))
                self.sites_table.setItem(row, 5, self._create_timestamp_item(site_data["last_check"]))
                self.sites_table.setItem(row, 6, QTableWidgetItem(str(site_data["interval"])))
                self.sites_table.setItem(row, 7, self._create_tags_item(site_data["tags"]))
                self.sites_table.set_loading(False)
    
    def on_site_double_clicked(self, row, column):
        """
        Обработчик двойного клика по сайту.
        
        Args:
            row: Индекс строки
            column: Индекс столбца
        """
        # Получаем ID сайта
        site_id = self.sites_table.item(row, 0).text()
        
        # Открываем форму редактирования сайта
        self.open_site_editor(site_id)
    
    def get_filtered_sites(self):
        """
        Получает отфильтрованный список сайтов.
        
        Returns:
            List[Dict]: Список словарей с данными сайтов
        """
        # ... existing code ...
    
    def get_site_data(self, site_id):
        """
        Получает данные конкретного сайта.
        
        Args:
            site_id: ID сайта
            
        Returns:
            Dict: Словарь с данными сайта
        """
        # ... existing code ...
    
    def update_stats(self, sites):
        """
        Обновляет статистику по сайтам.
        
        Args:
            sites: Список сайтов
        """
        # ... existing code ...
    
    def apply_filter(self, filter_data):
        """
        Применяет фильтр к списку сайтов.
        
        Args:
            filter_data: Данные фильтра
        """
        # Планируем отложенное обновление через UIUpdater
        self.ui_updater.schedule_update("sites_table", "filter_changed", True)
        self.ui_updater.schedule_update("sites_table", "filter", filter_data)
    
    def clear_filter(self):
        """Очищает текущий фильтр."""
        # Планируем отложенное обновление через UIUpdater
        self.ui_updater.schedule_update("sites_table", "filter_changed", True)
        self.ui_updater.schedule_update("sites_table", "filter", {})
    
    def open_site_editor(self, site_id=None):
        """
        Открывает редактор сайта.
        
        Args:
            site_id: ID сайта для редактирования (None для создания нового)
        """
        # ... existing code ...
    
    @handle_errors(error_msg="Ошибка при отображении диалога добавления сайта")
    def show_add_site_dialog(self):
        """Отображение диалога добавления сайта"""
        dialog = SiteDialog(self.app_context, None, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.update_data()
    
    @handle_errors(error_msg="Ошибка при отображении диалога редактирования сайта")
    def show_edit_site_dialog(self, site_data):
        """
        Отображение диалога редактирования сайта
        
        Args:
            site_data: Данные сайта для редактирования
        """
        dialog = SiteDialog(self.app_context, site_data, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.update_data()
    
    @handle_errors(error_msg="Ошибка при обновлении данных")
    def refresh(self):
        """Обновление данных"""
        self.update_data()
    
    def _delete_selected_sites(self):
        """Удаление выбранных сайтов"""
        try:
            # Получаем выбранные строки
            selected_rows = sorted({index.row() for index in self.sites_table.selectedIndexes()}, reverse=True)
            
            if not selected_rows:
                return
            
            # Запрашиваем подтверждение
            count = len(selected_rows)
            reply = QMessageBox.question(
                self,
                "Подтверждение удаления",
                f"Вы уверены, что хотите удалить {count} {'сайт' if count == 1 else 'сайта' if 1 < count < 5 else 'сайтов'}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            # Удаляем сайты
            deleted_count = 0
            for row in selected_rows:
                site_id = int(self.sites_table.item(row, 0).text())
                if self.app_context.delete_site(site_id):
                    deleted_count += 1
            
            # Обновляем таблицу
            self.update_data()
            
            # Выводим сообщение
            message = f"Удалено {deleted_count} из {count} {'сайт' if count == 1 else 'сайта' if 1 < count < 5 else 'сайтов'}"
            self.logger.info(message)
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Информация", message)
        
        except Exception as e:
            self.logger.error(f"Ошибка при удалении сайтов: {e}")
            log_exception(self.logger, "Ошибка удаления сайтов")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Ошибка", f"Не удалось удалить сайты: {e}", QMessageBox.Icon.Critical)
    
    def _check_selected_sites(self):
        """Проверка выбранных сайтов"""
        try:
            # Получаем выбранные строки
            selected_rows = {index.row() for index in self.sites_table.selectedIndexes()}
            
            if not selected_rows:
                return
            
            # Запрашиваем подтверждение
            count = len(selected_rows)
            reply = QMessageBox.question(
                self,
                "Подтверждение проверки",
                f"Вы уверены, что хотите проверить {count} {'сайт' if count == 1 else 'сайта' if 1 < count < 5 else 'сайтов'}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            # Проверяем сайты
            checked_count = 0
            for row in selected_rows:
                site_id = int(self.sites_table.item(row, 0).text())
                if self.app_context.check_site_now(site_id):
                    checked_count += 1
            
            # Обновляем таблицу через 2 секунды (дадим время на выполнение проверки)
            QTimer.singleShot(2000, self.update_data)
            
            # Выводим сообщение
            message = f"Запущена проверка {checked_count} из {count} {'сайт' if count == 1 else 'сайта' if 1 < count < 5 else 'сайтов'}"
            self.logger.info(message)
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Информация", message)
        
        except Exception as e:
            self.logger.error(f"Ошибка при проверке сайтов: {e}")
            log_exception(self.logger, "Ошибка проверки сайтов")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Ошибка", f"Не удалось проверить сайты: {e}", QMessageBox.Icon.Critical)
    
    def _import_sites(self):
        """Импорт списка сайтов из CSV-файла"""
        try:
            # Выбор файла
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Импорт сайтов из CSV",
                "",
                "CSV файлы (*.csv)"
            )
            
            if not file_path:
                return
            
            # Импорт из CSV
            import csv
            sites_to_import = []
            
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                # Проверка наличия обязательных полей
                fieldnames = reader.fieldnames or []
                if 'name' not in fieldnames or 'url' not in fieldnames:
                    self.logger.error("CSV-файл не содержит обязательных полей 'name' и 'url'")
                    if hasattr(self.parent, "show_message"):
                        self.parent.show_message(
                            "Ошибка", 
                            "CSV-файл должен содержать обязательные поля 'name' и 'url'", 
                            QMessageBox.Icon.Critical
                        )
                    return
                
                # Чтение данных
                for row in reader:
                    # Пропускаем строки с пустыми обязательными полями
                    if not row.get('name') or not row.get('url'):
                        continue
                    
                    # Стандартизация URL
                    url = row.get('url', '').strip()
                    if url and not url.startswith(('http://', 'https://')):
                        url = 'http://' + url
                    
                    # Формируем данные сайта
                    site_data = {
                        'name': row.get('name', '').strip(),
                        'url': url,
                        'description': row.get('description', '').strip(),
                        'check_method': row.get('check_method', 'static').strip(),
                        'css_selector': row.get('css_selector', '').strip(),
                        'xpath': row.get('xpath', '').strip(),
                        'include_regex': row.get('include_regex', '').strip(),
                        'exclude_regex': row.get('exclude_regex', '').strip(),
                        'status': row.get('status', 'active').strip()
                    }
                    
                    # Конвертация интервала проверки
                    try:
                        check_interval = int(row.get('check_interval', 3600))
                        site_data['check_interval'] = max(60, check_interval)  # Минимум 60 секунд
                    except (ValueError, TypeError):
                        site_data['check_interval'] = 3600  # По умолчанию 1 час
                    
                    # Добавляем сайт в список для импорта
                    sites_to_import.append(site_data)
            
            if not sites_to_import:
                self.logger.warning("CSV-файл не содержит данных сайтов для импорта")
                if hasattr(self.parent, "show_message"):
                    self.parent.show_message(
                        "Предупреждение", 
                        "CSV-файл не содержит данных сайтов для импорта", 
                        QMessageBox.Icon.Warning
                    )
                return
            
            # Запрос подтверждения
            count = len(sites_to_import)
            reply = QMessageBox.question(
                self,
                "Подтверждение импорта",
                f"Вы уверены, что хотите импортировать {count} {'сайт' if count == 1 else 'сайта' if 1 < count < 5 else 'сайтов'}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            # Импортируем сайты
            imported_count = 0
            for site_data in sites_to_import:
                try:
                    site_id = self.app_context.add_site(site_data)
                    if site_id:
                        imported_count += 1
                except Exception as e:
                    self.logger.error(f"Ошибка при импорте сайта {site_data.get('name')}: {e}")
            
            # Обновляем данные
            self.update_data()
            
            # Сообщение об успешном импорте
            message = f"Импортировано {imported_count} из {count} {'сайт' if count == 1 else 'сайта' if 1 < count < 5 else 'сайтов'}"
            self.logger.info(message)
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Информация", message)
        
        except Exception as e:
            self.logger.error(f"Ошибка при импорте сайтов: {e}")
            log_exception(self.logger, "Ошибка импорта сайтов")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Ошибка", f"Не удалось импортировать сайты: {e}", QMessageBox.Icon.Critical)
    
    def _export_sites(self):
        """Экспорт списка сайтов в CSV-файл"""
        try:
            # Выбор файла для сохранения
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Экспорт сайтов в CSV",
                "",
                "CSV файлы (*.csv)"
            )
            
            if not file_path:
                return
            
            # Если файл не имеет расширения .csv, добавляем его
            if not file_path.lower().endswith('.csv'):
                file_path += '.csv'
            
            # Получаем данные для экспорта
            sites = self.app_context.get_sites()
            
            if not sites:
                if hasattr(self.parent, "show_message"):
                    self.parent.show_message("Информация", "Нет сайтов для экспорта")
                return
            
            # Экспорт в CSV
            import csv
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                # Определяем поля для экспорта
                fieldnames = [
                    'name', 'url', 'description', 'check_method', 
                    'check_interval', 'css_selector', 'xpath', 
                    'include_regex', 'exclude_regex', 'status'
                ]
                
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                # Записываем только нужные поля
                for site in sites:
                    row = {field: site.get(field, '') for field in fieldnames}
                    writer.writerow(row)
            
            self.logger.info(f"Сайты экспортированы в {file_path}")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Информация", f"Сайты экспортированы в {file_path}")
        
        except Exception as e:
            self.logger.error(f"Ошибка при экспорте сайтов: {e}")
            log_exception(self.logger, "Ошибка экспорта сайтов")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Ошибка", f"Не удалось экспортировать сайты: {e}", QMessageBox.Icon.Critical) 