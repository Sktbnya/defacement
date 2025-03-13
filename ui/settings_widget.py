#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль виджета настроек для WDM_V12.
Предоставляет интерфейс для изменения настроек приложения.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget,
    QFormLayout, QLineEdit, QCheckBox, QSpinBox, QComboBox, QMessageBox,
    QGroupBox, QFileDialog, QDoubleSpinBox, QScrollArea
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QFont

# Внутренние импорты
from utils.logger import get_module_logger, log_exception
from core.settings import Settings
from core.notifications import NotificationManager
from utils.common import format_timestamp, get_diff_color, get_status_color, handle_errors


class SettingsWidget(QWidget):
    """
    Виджет настроек приложения.
    Обеспечивает интерфейс для изменения настроек мониторинга, уведомлений и т.д.
    """
    
    def __init__(self, app_context, parent=None):
        """
        Инициализация виджета настроек
        
        Args:
            app_context: Контекст приложения
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger('ui.settings_widget')
        self.logger.debug("Инициализация виджета настроек")
        
        self.app_context = app_context
        self.settings_manager = Settings()
        self.notification_manager = NotificationManager()
        
        # Создание UI
        self._init_ui()
        
        # Загрузка настроек
        self.load_settings()
        
        self.logger.debug("Виджет настроек инициализирован")
    
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        # Основной макет
        main_layout = QVBoxLayout(self)
        
        # Создание прокручиваемой области для вкладок
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        
        # Контейнер для вкладок
        tab_container = QWidget()
        tab_layout = QVBoxLayout(tab_container)
        
        # Создание вкладок для разных категорий настроек
        self.tabs = QTabWidget()
        tab_layout.addWidget(self.tabs)
        
        # Создание вкладок настроек
        self._create_general_tab()
        self._create_monitoring_tab()
        self._create_notification_tab()
        self._create_proxy_tab()
        self._create_logging_tab()
        
        # Установка контейнера в прокручиваемую область
        scroll_area.setWidget(tab_container)
        main_layout.addWidget(scroll_area)
        
        # Кнопки управления
        button_layout = QHBoxLayout()
        
        # Растягивающийся элемент для выравнивания кнопок вправо
        button_layout.addStretch()
        
        # Кнопка тестирования уведомлений
        self.test_notification_button = QPushButton("Тест уведомлений")
        self.test_notification_button.clicked.connect(self._on_test_notification)
        button_layout.addWidget(self.test_notification_button)
        
        # Кнопка применения настроек
        self.apply_button = QPushButton("Применить")
        self.apply_button.clicked.connect(self._on_apply_settings)
        button_layout.addWidget(self.apply_button)
        
        # Кнопка сохранения настроек
        self.save_button = QPushButton("Сохранить")
        self.save_button.clicked.connect(self._on_save_settings)
        button_layout.addWidget(self.save_button)
        
        # Кнопка сброса настроек
        self.reset_button = QPushButton("Сбросить")
        self.reset_button.clicked.connect(self._on_reset_settings)
        button_layout.addWidget(self.reset_button)
        
        main_layout.addLayout(button_layout)
    
    def _create_general_tab(self):
        """Создание вкладки общих настроек"""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # Группа основных настроек приложения
        app_group = QGroupBox("Основные настройки приложения")
        app_layout = QFormLayout(app_group)
        
        # Автоматический запуск мониторинга
        self.auto_start_monitoring = QCheckBox()
        self.auto_start_monitoring.setChecked(self.settings_manager.get('app', 'auto_start_monitoring', False))
        app_layout.addRow("Автоматически запускать мониторинг при старте:", self.auto_start_monitoring)
        
        # Проверка обновлений
        self.check_for_updates = QCheckBox()
        self.check_for_updates.setChecked(self.settings_manager.get('app', 'check_for_updates', True))
        app_layout.addRow("Проверять наличие обновлений при запуске:", self.check_for_updates)
        
        # Язык интерфейса
        self.language = QComboBox()
        self.language.addItems(["ru", "en"])
        self.language.setCurrentText(self.settings_manager.get('app', 'language', 'ru'))
        app_layout.addRow("Язык интерфейса:", self.language)
        
        # Тема оформления
        self.theme = QComboBox()
        self.theme.addItems(["system", "light", "dark"])
        self.theme.setCurrentText(self.settings_manager.get('app', 'theme', 'system'))
        app_layout.addRow("Тема оформления:", self.theme)
        
        layout.addRow(app_group)
        
        # Группа настроек резервного копирования
        backup_group = QGroupBox("Настройки резервного копирования")
        backup_layout = QFormLayout(backup_group)
        
        # Директория для резервных копий
        backup_dir_layout = QHBoxLayout()
        
        self.backup_dir = QLineEdit(self.settings_manager.get('app', 'backup_dir', 'backups'))
        backup_dir_layout.addWidget(self.backup_dir)
        
        self.select_backup_dir_button = QPushButton("...")
        self.select_backup_dir_button.setMaximumWidth(30)
        self.select_backup_dir_button.clicked.connect(self._on_select_backup_dir)
        backup_dir_layout.addWidget(self.select_backup_dir_button)
        
        backup_layout.addRow("Директория для резервных копий:", backup_dir_layout)
        
        # Максимальное количество резервных копий
        self.max_backups = QSpinBox()
        self.max_backups.setRange(1, 100)
        self.max_backups.setValue(self.settings_manager.get('app', 'max_backups', 10))
        backup_layout.addRow("Максимальное количество резервных копий:", self.max_backups)
        
        layout.addRow(backup_group)
        
        # Группа настроек базы данных
        db_group = QGroupBox("Настройки базы данных")
        db_layout = QFormLayout(db_group)
        
        # Путь к базе данных
        db_path_layout = QHBoxLayout()
        
        self.db_path = QLineEdit(self.settings_manager.get('database', 'path', 'data/wdm_database.db'))
        db_path_layout.addWidget(self.db_path)
        
        self.select_db_path_button = QPushButton("...")
        self.select_db_path_button.setMaximumWidth(30)
        self.select_db_path_button.clicked.connect(self._on_select_db_path)
        db_path_layout.addWidget(self.select_db_path_button)
        
        db_layout.addRow("Путь к базе данных:", db_path_layout)
        
        # Резервное копирование при запуске
        self.backup_on_start = QCheckBox()
        self.backup_on_start.setChecked(self.settings_manager.get('database', 'backup_on_start', True))
        db_layout.addRow("Резервное копирование БД при запуске:", self.backup_on_start)
        
        # Резервное копирование при выходе
        self.backup_on_exit = QCheckBox()
        self.backup_on_exit.setChecked(self.settings_manager.get('database', 'backup_on_exit', True))
        db_layout.addRow("Резервное копирование БД при выходе:", self.backup_on_exit)
        
        # Автоматическая очистка БД
        self.auto_vacuum = QCheckBox()
        self.auto_vacuum.setChecked(self.settings_manager.get('database', 'auto_vacuum', True))
        db_layout.addRow("Автоматическая оптимизация БД:", self.auto_vacuum)
        
        layout.addRow(db_group)
        
        self.tabs.addTab(tab, "Общие")
    
    def _create_monitoring_tab(self):
        """Создание вкладки настроек мониторинга"""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # Группа основных настроек мониторинга
        monitoring_group = QGroupBox("Основные настройки мониторинга")
        monitoring_layout = QFormLayout(monitoring_group)
        
        # Включен ли мониторинг
        self.monitoring_enabled = QCheckBox()
        self.monitoring_enabled.setChecked(self.settings_manager.get('monitoring', 'enabled', True))
        monitoring_layout.addRow("Мониторинг включен:", self.monitoring_enabled)
        
        # Интервал проверки
        check_interval_layout = QHBoxLayout()
        
        self.check_interval = QSpinBox()
        self.check_interval.setRange(1, 24 * 60 * 60)  # 1 секунда - 24 часа
        self.check_interval.setValue(self.settings_manager.get('monitoring', 'check_interval', 3600))
        check_interval_layout.addWidget(self.check_interval)
        
        self.check_interval_unit = QComboBox()
        self.check_interval_unit.addItem("секунд", 1)
        self.check_interval_unit.addItem("минут", 60)
        self.check_interval_unit.addItem("часов", 3600)
        
        # Установка правильной единицы измерения
        interval = self.settings_manager.get('monitoring', 'check_interval', 3600)
        if interval % 3600 == 0 and interval > 0:  # часы
            self.check_interval.setValue(interval // 3600)
            self.check_interval_unit.setCurrentIndex(2)
        elif interval % 60 == 0 and interval > 0:  # минуты
            self.check_interval.setValue(interval // 60)
            self.check_interval_unit.setCurrentIndex(1)
        else:  # секунды
            self.check_interval.setValue(interval)
            self.check_interval_unit.setCurrentIndex(0)
        
        check_interval_layout.addWidget(self.check_interval_unit)
        
        monitoring_layout.addRow("Интервал проверки:", check_interval_layout)
        
        # Количество параллельных проверок
        self.parallel_checks = QSpinBox()
        self.parallel_checks.setRange(1, 20)
        self.parallel_checks.setValue(self.settings_manager.get('monitoring', 'parallel_checks', 5))
        monitoring_layout.addRow("Количество параллельных проверок:", self.parallel_checks)
        
        # Количество попыток проверки при ошибке
        self.retry_count = QSpinBox()
        self.retry_count.setRange(0, 10)
        self.retry_count.setValue(self.settings_manager.get('monitoring', 'retry_count', 3))
        monitoring_layout.addRow("Количество повторных попыток при ошибке:", self.retry_count)
        
        # Задержка между попытками
        retry_delay_layout = QHBoxLayout()
        
        self.retry_delay = QSpinBox()
        self.retry_delay.setRange(1, 300)
        self.retry_delay.setValue(self.settings_manager.get('monitoring', 'retry_delay', 60))
        retry_delay_layout.addWidget(self.retry_delay)
        
        retry_delay_layout.addWidget(QLabel("секунд"))
        
        monitoring_layout.addRow("Задержка между попытками:", retry_delay_layout)
        
        layout.addRow(monitoring_group)
        
        # Группа настроек браузера
        browser_group = QGroupBox("Настройки браузера")
        browser_layout = QFormLayout(browser_group)
        
        # Использовать браузер для динамического контента
        self.use_browser = QCheckBox()
        self.use_browser.setChecked(self.settings_manager.get('monitoring', 'use_browser', True))
        browser_layout.addRow("Использовать браузер для динамического контента:", self.use_browser)
        
        # Таймаут загрузки страницы
        timeout_layout = QHBoxLayout()
        
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 300)
        self.timeout.setValue(self.settings_manager.get('monitoring', 'timeout', 30))
        timeout_layout.addWidget(self.timeout)
        
        timeout_layout.addWidget(QLabel("секунд"))
        
        browser_layout.addRow("Таймаут загрузки страницы:", timeout_layout)
        
        # User-Agent
        self.user_agent = QLineEdit(self.settings_manager.get('monitoring', 'user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'))
        browser_layout.addRow("User-Agent:", self.user_agent)
        
        # Время ожидания загрузки страницы в браузере
        browser_wait_layout = QHBoxLayout()
        
        self.browser_wait = QSpinBox()
        self.browser_wait.setRange(1, 60)
        self.browser_wait.setValue(self.settings_manager.get('monitoring', 'browser_wait', 5))
        browser_wait_layout.addWidget(self.browser_wait)
        
        browser_wait_layout.addWidget(QLabel("секунд"))
        
        browser_layout.addRow("Время ожидания загрузки в браузере:", browser_wait_layout)
        
        layout.addRow(browser_group)
        
        self.tabs.addTab(tab, "Мониторинг")
    
    def _create_notification_tab(self):
        """Создание вкладки настроек уведомлений"""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # Получаем текущие настройки уведомлений
        notification_settings = self.notification_manager.get_settings()
        
        # Общие настройки уведомлений
        general_group = QGroupBox("Общие настройки уведомлений")
        general_layout = QFormLayout(general_group)
        
        # Включить уведомления
        self.notifications_enabled = QCheckBox()
        self.notifications_enabled.setChecked(notification_settings.get('enabled', True))
        general_layout.addRow("Включить уведомления:", self.notifications_enabled)
        
        # Порог изменений для уведомлений
        threshold_layout = QHBoxLayout()
        
        self.notification_threshold = QDoubleSpinBox()
        self.notification_threshold.setRange(0.1, 100.0)
        self.notification_threshold.setSingleStep(0.1)
        self.notification_threshold.setDecimals(1)
        self.notification_threshold.setValue(notification_settings.get('notification_threshold', 5.0))
        threshold_layout.addWidget(self.notification_threshold)
        
        threshold_layout.addWidget(QLabel("%"))
        
        general_layout.addRow("Порог изменений для уведомлений:", threshold_layout)
        
        # Период охлаждения между уведомлениями
        cooldown_layout = QHBoxLayout()
        
        self.cooldown_period = QSpinBox()
        self.cooldown_period.setRange(1, 24 * 60 * 60)  # 1 секунда - 24 часа
        
        # Получаем текущий период охлаждения и устанавливаем подходящую единицу измерения
        cooldown = notification_settings.get('cooldown_period', 3600)
        
        self.cooldown_unit = QComboBox()
        self.cooldown_unit.addItem("секунд", 1)
        self.cooldown_unit.addItem("минут", 60)
        self.cooldown_unit.addItem("часов", 3600)
        
        if cooldown % 3600 == 0 and cooldown > 0:  # часы
            self.cooldown_period.setValue(cooldown // 3600)
            self.cooldown_unit.setCurrentIndex(2)
        elif cooldown % 60 == 0 and cooldown > 0:  # минуты
            self.cooldown_period.setValue(cooldown // 60)
            self.cooldown_unit.setCurrentIndex(1)
        else:  # секунды
            self.cooldown_period.setValue(cooldown)
            self.cooldown_unit.setCurrentIndex(0)
        
        cooldown_layout.addWidget(self.cooldown_period)
        cooldown_layout.addWidget(self.cooldown_unit)
        
        general_layout.addRow("Период охлаждения между уведомлениями:", cooldown_layout)
        
        layout.addRow(general_group)
        
        # Настройки уведомлений на рабочем столе
        desktop_group = QGroupBox("Уведомления на рабочем столе")
        desktop_layout = QFormLayout(desktop_group)
        
        # Включить уведомления на рабочем столе
        self.desktop_notifications = QCheckBox()
        self.desktop_notifications.setChecked(notification_settings.get('desktop_notifications', True))
        desktop_layout.addRow("Включить уведомления на рабочем столе:", self.desktop_notifications)
        
        # Кнопка для тестирования настольных уведомлений
        test_desktop_button = QPushButton("Тест уведомления")
        test_desktop_button.clicked.connect(self._on_test_desktop_notification)
        desktop_layout.addRow("", test_desktop_button)
        
        layout.addRow(desktop_group)
        
        # Настройки уведомлений по электронной почте
        email_group = QGroupBox("Уведомления по электронной почте")
        email_layout = QFormLayout(email_group)
        
        # Включить уведомления по email
        self.email_notifications = QCheckBox()
        self.email_notifications.setChecked(notification_settings.get('email_notifications', False))
        email_layout.addRow("Включить уведомления по email:", self.email_notifications)
        
        # Настройки SMTP сервера
        email_settings = notification_settings.get('email_settings', {})
        
        # SMTP сервер
        self.smtp_server = QLineEdit(email_settings.get('smtp_server', ''))
        email_layout.addRow("SMTP сервер:", self.smtp_server)
        
        # SMTP порт
        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setValue(email_settings.get('smtp_port', 587))
        email_layout.addRow("SMTP порт:", self.smtp_port)
        
        # SMTP имя пользователя
        self.smtp_username = QLineEdit(email_settings.get('smtp_username', ''))
        email_layout.addRow("SMTP имя пользователя:", self.smtp_username)
        
        # SMTP пароль
        self.smtp_password = QLineEdit(email_settings.get('smtp_password', ''))
        self.smtp_password.setEchoMode(QLineEdit.EchoMode.Password)
        email_layout.addRow("SMTP пароль:", self.smtp_password)
        
        # Адрес отправителя
        self.from_address = QLineEdit(email_settings.get('from_address', ''))
        email_layout.addRow("Адрес отправителя:", self.from_address)
        
        # Адрес получателя
        self.to_address = QLineEdit(email_settings.get('to_address', ''))
        email_layout.addRow("Адрес получателя:", self.to_address)
        
        # Кнопка для тестирования email уведомлений
        test_email_button = QPushButton("Тест email")
        test_email_button.clicked.connect(self._on_test_email_notification)
        email_layout.addRow("", test_email_button)
        
        layout.addRow(email_group)
        
        # Группа настроек Telegram-уведомлений
        telegram_group = QGroupBox("Уведомления через Telegram")
        telegram_group_layout = QVBoxLayout(telegram_group)
        
        # Включение/отключение Telegram-уведомлений
        self.telegram_notifications = QCheckBox("Включить уведомления через Telegram")
        self.telegram_notifications.setChecked(notification_settings.get('telegram_notifications', False))
        telegram_group_layout.addWidget(self.telegram_notifications)
        
        # Настройки Telegram
        telegram_form_layout = QFormLayout()
        
        # Токен бота
        self.telegram_bot_token = QLineEdit()
        telegram_form_layout.addRow("Токен бота:", self.telegram_bot_token)
        
        # ID чата
        self.telegram_chat_id = QLineEdit()
        telegram_form_layout.addRow("ID чата:", self.telegram_chat_id)
        
        # Информация о создании бота
        telegram_info = QLabel(
            "Для создания бота используйте @BotFather в Telegram.\n"
            "ID чата можно узнать через @userinfobot или @RawDataBot."
        )
        telegram_info.setWordWrap(True)
        
        telegram_group_layout.addLayout(telegram_form_layout)
        telegram_group_layout.addWidget(telegram_info)
        
        # Кнопка тестирования
        telegram_test_button = QPushButton("Протестировать Telegram-уведомления")
        telegram_test_button.clicked.connect(self._on_test_telegram_notification)
        telegram_group_layout.addWidget(telegram_test_button)
        
        # Добавляем группу в вкладку
        layout.addWidget(telegram_group)
        
        self.tabs.addTab(tab, "Уведомления")
    
    def _create_proxy_tab(self):
        """Создание вкладки настроек прокси"""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # Группа настроек прокси-сервера
        proxy_group = QGroupBox("Настройки прокси-сервера")
        proxy_layout = QFormLayout(proxy_group)
        
        # Включить использование прокси
        self.proxy_enabled = QCheckBox()
        self.proxy_enabled.setChecked(self.settings_manager.get('proxy', 'enabled', False))
        proxy_layout.addRow("Использовать прокси:", self.proxy_enabled)
        
        # Тип прокси
        self.proxy_type = QComboBox()
        self.proxy_type.addItems(["http", "socks5"])
        self.proxy_type.setCurrentText(self.settings_manager.get('proxy', 'type', 'http'))
        proxy_layout.addRow("Тип прокси:", self.proxy_type)
        
        # Хост прокси
        self.proxy_host = QLineEdit(self.settings_manager.get('proxy', 'host', ''))
        proxy_layout.addRow("Хост прокси:", self.proxy_host)
        
        # Порт прокси
        self.proxy_port = QSpinBox()
        self.proxy_port.setRange(1, 65535)
        self.proxy_port.setValue(self.settings_manager.get('proxy', 'port', 8080))
        proxy_layout.addRow("Порт прокси:", self.proxy_port)
        
        # Имя пользователя
        self.proxy_username = QLineEdit(self.settings_manager.get('proxy', 'username', ''))
        proxy_layout.addRow("Имя пользователя:", self.proxy_username)
        
        # Пароль
        self.proxy_password = QLineEdit(self.settings_manager.get('proxy', 'password', ''))
        self.proxy_password.setEchoMode(QLineEdit.EchoMode.Password)
        proxy_layout.addRow("Пароль:", self.proxy_password)
        
        layout.addRow(proxy_group)
        
        self.tabs.addTab(tab, "Прокси")
    
    def _create_logging_tab(self):
        """Создание вкладки настроек логирования"""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # Группа настроек логирования
        logging_group = QGroupBox("Настройки логирования")
        logging_layout = QFormLayout(logging_group)
        
        # Уровень логирования
        self.log_level = QComboBox()
        self.log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.log_level.setCurrentText(self.settings_manager.get('logging', 'level', 'INFO'))
        logging_layout.addRow("Уровень логирования:", self.log_level)
        
        # Максимальный размер файла лога
        file_size_layout = QHBoxLayout()
        
        self.max_file_size = QSpinBox()
        self.max_file_size.setRange(1, 100)
        self.max_file_size.setValue(self.settings_manager.get('logging', 'max_file_size', 10485760) // 1048576)  # Из байт в МБ
        file_size_layout.addWidget(self.max_file_size)
        
        file_size_layout.addWidget(QLabel("МБ"))
        
        logging_layout.addRow("Максимальный размер файла лога:", file_size_layout)
        
        # Максимальное количество файлов лога
        self.max_files = QSpinBox()
        self.max_files.setRange(1, 20)
        self.max_files.setValue(self.settings_manager.get('logging', 'max_files', 5))
        logging_layout.addRow("Максимальное количество файлов лога:", self.max_files)
        
        # Вывод лога в консоль
        self.log_to_console = QCheckBox()
        self.log_to_console.setChecked(self.settings_manager.get('logging', 'log_to_console', True))
        logging_layout.addRow("Выводить лог в консоль:", self.log_to_console)
        
        layout.addRow(logging_group)
        
        self.tabs.addTab(tab, "Логирование")
    
    def _on_select_backup_dir(self):
        """Обработчик выбора директории для резервных копий"""
        try:
            current_dir = self.backup_dir.text()
            dir_path = QFileDialog.getExistingDirectory(
                self,
                "Выбор директории для резервных копий",
                current_dir
            )
            
            if dir_path:
                self.backup_dir.setText(dir_path)
        
        except Exception as e:
            self.logger.error(f"Ошибка при выборе директории для резервных копий: {e}")
            log_exception(self.logger, "Ошибка выбора директории для резервных копий")
    
    def _on_select_db_path(self):
        """Обработчик выбора пути к базе данных"""
        try:
            current_path = self.db_path.text()
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Выбор или создание файла базы данных",
                current_path,
                "База данных SQLite (*.db);;Все файлы (*.*)"
            )
            
            if file_path:
                self.db_path.setText(file_path)
        
        except Exception as e:
            self.logger.error(f"Ошибка при выборе пути к базе данных: {e}")
            log_exception(self.logger, "Ошибка выбора пути к базе данных")
    
    def _on_test_desktop_notification(self):
        """Обработчик тестирования настольных уведомлений"""
        try:
            self.logger.debug("Тестирование настольных уведомлений")
            
            # Получаем актуальные настройки
            notification_settings = {
                'enabled': self.notifications_enabled.isChecked(),
                'desktop_notifications': self.desktop_notifications.isChecked()
            }
            
            # Временно устанавливаем настройки для теста
            self.notification_manager.update_settings(notification_settings)
            
            # Отправляем тестовое уведомление
            result = self.notification_manager.test_notification('desktop')
            
            if result:
                self.logger.info("Тестовое настольное уведомление отправлено успешно")
                QMessageBox.information(self, "Успех", "Тестовое настольное уведомление отправлено успешно")
            else:
                self.logger.warning("Не удалось отправить тестовое настольное уведомление")
                QMessageBox.warning(self, "Предупреждение", "Не удалось отправить тестовое настольное уведомление")
        
        except Exception as e:
            self.logger.error(f"Ошибка при тестировании настольных уведомлений: {e}")
            log_exception(self.logger, "Ошибка тестирования настольных уведомлений")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при тестировании настольных уведомлений: {e}")
    
    def _on_test_email_notification(self):
        """Обработчик тестирования email уведомлений"""
        try:
            self.logger.debug("Тестирование email уведомлений")
            
            # Получаем актуальные настройки
            notification_settings = {
                'enabled': self.notifications_enabled.isChecked(),
                'email_notifications': self.email_notifications.isChecked(),
                'email_settings': {
                    'smtp_server': self.smtp_server.text(),
                    'smtp_port': self.smtp_port.value(),
                    'smtp_username': self.smtp_username.text(),
                    'smtp_password': self.smtp_password.text(),
                    'from_address': self.from_address.text(),
                    'to_address': self.to_address.text()
                }
            }
            
            # Проверяем заполнение обязательных полей
            if not notification_settings['email_settings']['smtp_server']:
                QMessageBox.warning(self, "Предупреждение", "Не указан SMTP сервер")
                return
            
            if not notification_settings['email_settings']['from_address']:
                QMessageBox.warning(self, "Предупреждение", "Не указан адрес отправителя")
                return
            
            if not notification_settings['email_settings']['to_address']:
                QMessageBox.warning(self, "Предупреждение", "Не указан адрес получателя")
                return
            
            # Временно устанавливаем настройки для теста
            self.notification_manager.update_settings(notification_settings)
            
            # Отправляем тестовое уведомление
            result = self.notification_manager.test_notification('email')
            
            if result:
                self.logger.info("Тестовое email уведомление отправлено успешно")
                QMessageBox.information(self, "Успех", "Тестовое email уведомление отправлено успешно")
            else:
                self.logger.warning("Не удалось отправить тестовое email уведомление")
                QMessageBox.warning(self, "Предупреждение", "Не удалось отправить тестовое email уведомление")
        
        except Exception as e:
            self.logger.error(f"Ошибка при тестировании email уведомлений: {e}")
            log_exception(self.logger, "Ошибка тестирования email уведомлений")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при тестировании email уведомлений: {e}")

    def _on_save_settings(self):
        """Обработчик сохранения настроек"""
        try:
            self.logger.debug("Вызван метод сохранения настроек")
            
            # Сначала применяем настройки
            self._on_apply_settings()
            
            # Затем сохраняем их в файл
            self.settings_manager.save_settings()
            
            # Подтверждение
            QMessageBox.information(self, "Информация", "Настройки успешно сохранены")
            
            self.logger.info("Настройки успешно сохранены")
        
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении настроек: {e}")
            log_exception(self.logger, "Ошибка сохранения настроек")
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить настройки: {e}")
    
    def _on_reset_settings(self):
        """Обработчик сброса настроек"""
        try:
            self.logger.debug("Вызван метод сброса настроек")
            
            # Запрос подтверждения
            reply = QMessageBox.question(
                self,
                "Подтверждение сброса",
                "Вы уверены, что хотите сбросить все настройки к значениям по умолчанию?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            # Сброс настроек
            if self.settings_manager.reset_to_defaults():
                self.logger.info("Настройки сброшены к значениям по умолчанию")
                
                # Перезагрузка значений элементов управления
                self.load_settings()
                
                # Подтверждение
                QMessageBox.information(self, "Информация", "Настройки сброшены к значениям по умолчанию")
            else:
                raise Exception("Не удалось сбросить настройки")
        
        except Exception as e:
            self.logger.error(f"Ошибка при сбросе настроек: {e}")
            log_exception(self.logger, "Ошибка сброса настроек")
            QMessageBox.critical(self, "Ошибка", f"Не удалось сбросить настройки: {e}")
    
    def _on_test_notification(self):
        """Обработчик тестирования уведомлений"""
        try:
            self.logger.debug("Вызван метод тестирования уведомлений")
            
            # Обновляем настройки уведомлений из элементов управления
            self._update_notification_settings()
            
            # Формируем информационное сообщение
            message = "Для тестирования уведомлений используйте соответствующие кнопки на вкладке 'Уведомления'."
            
            self.logger.info("Отображение информации о тестировании уведомлений")
            QMessageBox.information(self, "Тестирование уведомлений", message)
        
        except Exception as e:
            self.logger.error(f"Ошибка при тестировании уведомлений: {e}")
            log_exception(self.logger, "Ошибка тестирования уведомлений")
            QMessageBox.critical(self, "Ошибка", f"Не удалось выполнить тестирование уведомлений: {e}")
    
    def _on_apply_settings(self):
        """Обработчик применения настроек"""
        try:
            self.logger.debug("Вызван метод применения настроек")
            
            # Обновление настроек приложения
            self._update_app_settings()
            
            # Обновление настроек базы данных
            self._update_database_settings()
            
            # Обновление настроек мониторинга
            self._update_monitoring_settings()
            
            # Обновление настроек уведомлений
            self._update_notification_settings()
            
            # Обновление настроек прокси
            self._update_proxy_settings()
            
            # Обновление настроек логирования
            self._update_logging_settings()
            
            self.logger.info("Настройки успешно применены")
            
            return True
        
        except Exception as e:
            self.logger.error(f"Ошибка при применении настроек: {e}")
            log_exception(self.logger, "Ошибка применения настроек")
            QMessageBox.critical(self, "Ошибка", f"Не удалось применить настройки: {e}")
            return False
    
    @handle_errors(error_msg="Ошибка при загрузке настроек")
    def load_settings(self):
        """Загрузка настроек из базы данных"""
        try:
            # Получаем настройки
            settings = self.app_context.get_settings()
            if not settings:
                self.logger.warning("Не удалось получить настройки")
                return
            
            # Проверяем и устанавливаем значения по умолчанию, если необходимо
            self._validate_and_set_defaults(settings)
            
            # Общие настройки
            general = settings.get('general', {})
            self.check_interval_spin.setValue(general.get('check_interval', 60))
            self.max_threads_spin.setValue(general.get('max_threads', 5))
            self.retry_count_spin.setValue(general.get('retry_count', 3))
            self.retry_delay_spin.setValue(general.get('retry_delay', 60))
            self.timeout_spin.setValue(general.get('timeout', 30))
            
            # Настройки уведомлений
            notifications = settings.get('notifications', {})
            self.email_notify_check.setChecked(notifications.get('email_enabled', False))
            self.desktop_notify_check.setChecked(notifications.get('desktop_enabled', True))
            self.sound_notify_check.setChecked(notifications.get('sound_enabled', False))
            
            # Email настройки
            email = settings.get('email', {})
            self.smtp_server_edit.setText(email.get('smtp_server', ''))
            self.smtp_port_spin.setValue(email.get('smtp_port', 587))
            self.smtp_user_edit.setText(email.get('smtp_user', ''))
            self.smtp_password_edit.setText(email.get('smtp_password', ''))
            self.smtp_ssl_check.setChecked(email.get('smtp_ssl', True))
            self.smtp_tls_check.setChecked(email.get('smtp_tls', True))
            
            # Настройки прокси
            proxy = settings.get('proxy', {})
            self.proxy_enabled_check.setChecked(proxy.get('enabled', False))
            self.proxy_type_combo.setCurrentText(proxy.get('type', 'http'))
            self.proxy_host_edit.setText(proxy.get('host', ''))
            self.proxy_port_spin.setValue(proxy.get('port', 8080))
            self.proxy_user_edit.setText(proxy.get('username', ''))
            self.proxy_password_edit.setText(proxy.get('password', ''))
            
            # Настройки логирования
            logging = settings.get('logging', {})
            self.log_level_combo.setCurrentText(logging.get('level', 'INFO'))
            self.log_file_edit.setText(logging.get('file', 'app.log'))
            self.log_max_size_spin.setValue(logging.get('max_size', 10))
            self.log_backup_count_spin.setValue(logging.get('backup_count', 5))
            
            # Настройки базы данных
            database = settings.get('database', {})
            self.db_backup_enabled_check.setChecked(database.get('backup_enabled', True))
            self.db_backup_interval_spin.setValue(database.get('backup_interval', 24))
            self.db_backup_count_spin.setValue(database.get('backup_count', 7))
            
            # Настройки очистки
            cleanup = settings.get('cleanup', {})
            self.cleanup_enabled_check.setChecked(cleanup.get('enabled', True))
            self.cleanup_interval_spin.setValue(cleanup.get('interval', 24))
            self.cleanup_age_spin.setValue(cleanup.get('max_age', 30))
            
            # Настройки безопасности
            security = settings.get('security', {})
            self.ssl_verify_check.setChecked(security.get('ssl_verify', True))
            self.user_agent_edit.setText(security.get('user_agent', ''))
            
            self.logger.info("Настройки успешно загружены")
            
        except Exception as e:
            self.logger.error(f"Ошибка при загрузке настроек: {e}")
            log_exception(self.logger, "Ошибка загрузки настроек")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Ошибка", f"Не удалось загрузить настройки: {e}", QMessageBox.Icon.Critical)
    
    def _validate_and_set_defaults(self, settings):
        """
        Проверка и установка значений по умолчанию для настроек
        
        Args:
            settings: Словарь с настройками
        """
        # Проверяем наличие всех необходимых разделов
        required_sections = ['general', 'notifications', 'email', 'proxy', 'logging', 'database', 'cleanup', 'security']
        for section in required_sections:
            if section not in settings:
                settings[section] = {}
        
        # Проверяем и устанавливаем значения по умолчанию для общих настроек
        general = settings['general']
        general.setdefault('check_interval', 60)
        general.setdefault('max_threads', 5)
        general.setdefault('retry_count', 3)
        general.setdefault('retry_delay', 60)
        general.setdefault('timeout', 30)
        
        # Проверяем и устанавливаем значения по умолчанию для уведомлений
        notifications = settings['notifications']
        notifications.setdefault('email_enabled', False)
        notifications.setdefault('desktop_enabled', True)
        notifications.setdefault('sound_enabled', False)
        
        # Проверяем и устанавливаем значения по умолчанию для email
        email = settings['email']
        email.setdefault('smtp_server', '')
        email.setdefault('smtp_port', 587)
        email.setdefault('smtp_user', '')
        email.setdefault('smtp_password', '')
        email.setdefault('smtp_ssl', True)
        email.setdefault('smtp_tls', True)
        
        # Проверяем и устанавливаем значения по умолчанию для прокси
        proxy = settings['proxy']
        proxy.setdefault('enabled', False)
        proxy.setdefault('type', 'http')
        proxy.setdefault('host', '')
        proxy.setdefault('port', 8080)
        proxy.setdefault('username', '')
        proxy.setdefault('password', '')
        
        # Проверяем и устанавливаем значения по умолчанию для логирования
        logging = settings['logging']
        logging.setdefault('level', 'INFO')
        logging.setdefault('file', 'app.log')
        logging.setdefault('max_size', 10)
        logging.setdefault('backup_count', 5)
        
        # Проверяем и устанавливаем значения по умолчанию для базы данных
        database = settings['database']
        database.setdefault('backup_enabled', True)
        database.setdefault('backup_interval', 24)
        database.setdefault('backup_count', 7)
        
        # Проверяем и устанавливаем значения по умолчанию для очистки
        cleanup = settings['cleanup']
        cleanup.setdefault('enabled', True)
        cleanup.setdefault('interval', 24)
        cleanup.setdefault('max_age', 30)
        
        # Проверяем и устанавливаем значения по умолчанию для безопасности
        security = settings['security']
        security.setdefault('ssl_verify', True)
        security.setdefault('user_agent', '')
    
    def _update_app_settings(self):
        """Обновление настроек приложения"""
        app_settings = {
            'auto_start_monitoring': self.auto_start_monitoring.isChecked(),
            'check_for_updates': self.check_for_updates.isChecked(),
            'language': self.language.currentText(),
            'theme': self.theme.currentText(),
            'backup_dir': self.backup_dir.text(),
            'max_backups': self.max_backups.value()
        }
        
        self.settings_manager.update_section('app', app_settings)
    
    def _update_database_settings(self):
        """Обновление настроек базы данных"""
        db_settings = {
            'path': self.db_path.text(),
            'backup_on_start': self.backup_on_start.isChecked(),
            'backup_on_exit': self.backup_on_exit.isChecked(),
            'auto_vacuum': self.auto_vacuum.isChecked()
        }
        
        self.settings_manager.update_section('database', db_settings)
    
    def _update_monitoring_settings(self):
        """Обновление настроек мониторинга"""
        # Рассчитываем интервал проверки в секундах
        check_interval = self.check_interval.value() * self.check_interval_unit.currentData()
        
        monitoring_settings = {
            'enabled': self.monitoring_enabled.isChecked(),
            'check_interval': check_interval,
            'parallel_checks': self.parallel_checks.value(),
            'retry_count': self.retry_count.value(),
            'retry_delay': self.retry_delay.value(),
            'use_browser': self.use_browser.isChecked(),
            'timeout': self.timeout.value(),
            'user_agent': self.user_agent.text(),
            'browser_wait': self.browser_wait.value()
        }
        
        self.settings_manager.update_section('monitoring', monitoring_settings)
    
    def _update_notification_settings(self):
        """Обновление настроек уведомлений из элементов управления"""
        self.logger.debug("Обновление настроек уведомлений из элементов управления")
        
        try:
            # Получаем настройки из элементов управления
            notification_settings = {
                'enabled': self.notifications_enabled.isChecked(),
                'desktop_notifications': self.desktop_notifications.isChecked(),
                'email_notifications': self.email_notifications.isChecked(),
                'email_settings': {
                    'smtp_server': self.smtp_server.text(),
                    'smtp_port': self.smtp_port.value(),
                    'smtp_username': self.smtp_username.text(),
                    'smtp_password': self.smtp_password.text(),
                    'from_address': self.from_address.text(),
                    'to_address': self.to_address.text()
                },
                'telegram_notifications': self.telegram_notifications.isChecked(),
                'telegram_settings': {
                    'bot_token': self.telegram_bot_token.text(),
                    'chat_id': self.telegram_chat_id.text()
                },
                'notification_threshold': self.notification_threshold.value(),
                'cooldown_period': self.cooldown_period.value() * 60  # Конвертируем минуты в секунды
            }
            
            # Обновляем настройки в менеджере уведомлений
            self.notification_manager.update_settings(notification_settings)
            
            # Обновляем настройки в менеджере настроек
            # Сначала обновляем словарь настроек
            self.settings_manager.settings['notifications'] = notification_settings
            # Затем сохраняем настройки
            self.settings_manager.save_settings()
            
            self.logger.info("Настройки уведомлений успешно обновлены")
            return True
        
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении настроек уведомлений: {e}")
            log_exception(self.logger, "Ошибка обновления настроек уведомлений")
            return False
    
    def _update_proxy_settings(self):
        """Обновление настроек прокси"""
        proxy_settings = {
            'enabled': self.proxy_enabled.isChecked(),
            'type': self.proxy_type.currentText(),
            'host': self.proxy_host.text(),
            'port': self.proxy_port.value(),
            'username': self.proxy_username.text(),
            'password': self.proxy_password.text()
        }
        
        self.settings_manager.update_section('proxy', proxy_settings)
    
    def _update_logging_settings(self):
        """Обновление настроек логирования"""
        # Пересчитываем размер файла из МБ в байты
        max_file_size = self.max_file_size.value() * 1048576  # 1 МБ = 1048576 байт
        
        logging_settings = {
            'level': self.log_level.currentText(),
            'max_file_size': max_file_size,
            'max_files': self.max_files.value(),
            'log_to_console': self.log_to_console.isChecked()
        }
        
        self.settings_manager.update_section('logging', logging_settings)
    
    def _on_test_telegram_notification(self):
        """Обработчик тестирования Telegram уведомлений"""
        try:
            self.logger.debug("Тестирование Telegram уведомлений")
            
            # Получаем актуальные настройки
            notification_settings = {
                'enabled': self.notifications_enabled.isChecked(),
                'telegram_notifications': self.telegram_notifications.isChecked(),
                'telegram_settings': {
                    'bot_token': self.telegram_bot_token.text(),
                    'chat_id': self.telegram_chat_id.text()
                }
            }
            
            # Проверяем заполнение обязательных полей
            if not notification_settings['telegram_settings']['bot_token']:
                QMessageBox.warning(self, "Предупреждение", "Не указан токен бота")
                return
            
            if not notification_settings['telegram_settings']['chat_id']:
                QMessageBox.warning(self, "Предупреждение", "Не указан ID чата")
                return
            
            # Временно устанавливаем настройки для теста
            self.notification_manager.update_settings(notification_settings)
            
            # Отправляем тестовое уведомление
            result = self.notification_manager.test_notification('telegram')
            
            if result:
                self.logger.info("Тестовое Telegram уведомление отправлено успешно")
                QMessageBox.information(self, "Успех", "Тестовое Telegram уведомление отправлено успешно")
            else:
                self.logger.warning("Не удалось отправить тестовое Telegram уведомление")
                QMessageBox.warning(self, "Предупреждение", "Не удалось отправить тестовое Telegram уведомление")
        
        except Exception as e:
            self.logger.error(f"Ошибка при тестировании Telegram уведомлений: {e}")
            log_exception(self.logger, "Ошибка тестирования Telegram уведомлений")
            QMessageBox.critical(self, "Ошибка", f"Ошибка при тестировании Telegram уведомлений: {e}") 