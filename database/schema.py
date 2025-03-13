#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль схемы базы данных для WDM_V12.
Содержит SQL-запросы для создания таблиц и необходимых индексов.
"""

import logging
from typing import List, Dict, Any, Optional
import os

from utils.logger import get_module_logger

# SQL-запросы для создания таблиц
CREATE_TABLES_SQL = [
    # Таблица сайтов
    """
    CREATE TABLE IF NOT EXISTS sites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        url TEXT NOT NULL,
        description TEXT,
        check_method TEXT DEFAULT 'dynamic',
        check_interval INTEGER DEFAULT 3600,
        css_selector TEXT,
        xpath TEXT,
        include_regex TEXT,
        exclude_regex TEXT,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_check TIMESTAMP,
        last_change TIMESTAMP,
        group_id INTEGER,
        priority INTEGER DEFAULT 0,
        notify_on_change BOOLEAN DEFAULT 1,
        FOREIGN KEY (group_id) REFERENCES groups(id)
    )
    """,
    
    # Таблица групп сайтов
    """
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    
    # Таблица пользователей
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        email TEXT,
        full_name TEXT,
        role_id INTEGER NOT NULL,
        is_active BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP,
        FOREIGN KEY (role_id) REFERENCES roles(id)
    )
    """,
    
    # Таблица ролей
    """
    CREATE TABLE IF NOT EXISTS roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    
    # Таблица разрешений
    """
    CREATE TABLE IF NOT EXISTS permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    
    # Таблица связи ролей и разрешений
    """
    CREATE TABLE IF NOT EXISTS role_permissions (
        role_id INTEGER NOT NULL,
        permission_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (role_id, permission_id),
        FOREIGN KEY (role_id) REFERENCES roles(id),
        FOREIGN KEY (permission_id) REFERENCES permissions(id)
    )
    """,
    
    # Таблица снимков сайтов
    """
    CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id INTEGER NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        content_hash TEXT,
        content_path TEXT,
        screenshot_path TEXT,
        content_size INTEGER,
        content_type TEXT,
        diff_percent REAL,
        status TEXT DEFAULT 'success',
        error_message TEXT,
        FOREIGN KEY (site_id) REFERENCES sites(id)
    )
    """,
    
    # Таблица изменений
    """
    CREATE TABLE IF NOT EXISTS changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id INTEGER NOT NULL,
        old_snapshot_id INTEGER,
        new_snapshot_id INTEGER NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        diff_percent REAL,
        diff_details TEXT,
        status TEXT DEFAULT 'unread',
        reviewed_at TIMESTAMP,
        reviewed_by TEXT,
        notes TEXT,
        FOREIGN KEY (site_id) REFERENCES sites(id),
        FOREIGN KEY (old_snapshot_id) REFERENCES snapshots(id),
        FOREIGN KEY (new_snapshot_id) REFERENCES snapshots(id)
    )
    """,
    
    # Таблица журнала событий
    """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        site_id INTEGER,
        snapshot_id INTEGER,
        change_id INTEGER,
        details TEXT,
        FOREIGN KEY (site_id) REFERENCES sites(id),
        FOREIGN KEY (snapshot_id) REFERENCES snapshots(id),
        FOREIGN KEY (change_id) REFERENCES changes(id)
    )
    """,
    
    # Таблица настроек
    """
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE NOT NULL,
        value TEXT,
        description TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
]

# SQL-запросы для создания индексов
CREATE_INDEXES_SQL = [
    # Индексы для таблицы сайтов
    "CREATE INDEX IF NOT EXISTS idx_sites_status ON sites(status)",
    "CREATE INDEX IF NOT EXISTS idx_sites_group_id ON sites(group_id)",
    "CREATE INDEX IF NOT EXISTS idx_sites_last_check ON sites(last_check)",
    "CREATE INDEX IF NOT EXISTS idx_sites_last_change ON sites(last_change)",
    
    # Индексы для таблицы снимков
    "CREATE INDEX IF NOT EXISTS idx_snapshots_site_id ON snapshots(site_id)",
    "CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON snapshots(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_snapshots_content_hash ON snapshots(content_hash)",
    "CREATE INDEX IF NOT EXISTS idx_snapshots_status ON snapshots(status)",
    
    # Индексы для таблицы изменений
    "CREATE INDEX IF NOT EXISTS idx_changes_site_id ON changes(site_id)",
    "CREATE INDEX IF NOT EXISTS idx_changes_timestamp ON changes(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_changes_status ON changes(status)",
    "CREATE INDEX IF NOT EXISTS idx_changes_new_snapshot_id ON changes(new_snapshot_id)",
    
    # Индексы для таблицы событий
    "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type)",
    "CREATE INDEX IF NOT EXISTS idx_events_site_id ON events(site_id)"
]

# Перечень необходимых начальных настроек для таблицы settings
DEFAULT_SETTINGS = [
    {
        'key': 'monitoring_enabled',
        'value': '1',
        'description': 'Включить автоматический мониторинг (0 - выключено, 1 - включено)'
    },
    {
        'key': 'default_check_interval',
        'value': '3600',
        'description': 'Интервал проверки сайтов по умолчанию (в секундах)'
    },
    {
        'key': 'max_workers',
        'value': '5',
        'description': 'Максимальное количество параллельных потоков мониторинга'
    },
    {
        'key': 'diff_threshold_percent',
        'value': '5.0',
        'description': 'Порог изменений для уведомления (в процентах)'
    },
    {
        'key': 'user_agent',
        'value': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'description': 'User-Agent для запросов'
    },
    {
        'key': 'notifications_enabled',
        'value': '1',
        'description': 'Включить уведомления (0 - выключено, 1 - включено)'
    },
    {
        'key': 'database_version',
        'value': '1',
        'description': 'Версия схемы базы данных'
    }
]

# Предустановленные роли пользователей
DEFAULT_ROLES = [
    {
        'id': 1,
        'name': 'admin',
        'description': 'Администратор системы с полными правами доступа'
    },
    {
        'id': 2,
        'name': 'manager',
        'description': 'Менеджер с правами управления сайтами и просмотра отчетов'
    },
    {
        'id': 3,
        'name': 'viewer',
        'description': 'Наблюдатель с правами только на просмотр информации'
    }
]

# Предустановленные разрешения
DEFAULT_PERMISSIONS = [
    {
        'id': 1,
        'name': 'view_dashboard',
        'description': 'Просмотр панели мониторинга'
    },
    {
        'id': 2,
        'name': 'view_sites',
        'description': 'Просмотр списка сайтов'
    },
    {
        'id': 3,
        'name': 'add_sites',
        'description': 'Добавление новых сайтов'
    },
    {
        'id': 4,
        'name': 'edit_sites',
        'description': 'Редактирование сайтов'
    },
    {
        'id': 5,
        'name': 'delete_sites',
        'description': 'Удаление сайтов'
    },
    {
        'id': 6,
        'name': 'view_changes',
        'description': 'Просмотр изменений на сайтах'
    },
    {
        'id': 7,
        'name': 'view_reports',
        'description': 'Просмотр отчетов'
    },
    {
        'id': 8,
        'name': 'generate_reports',
        'description': 'Генерация отчетов'
    },
    {
        'id': 9,
        'name': 'export_reports',
        'description': 'Экспорт отчетов'
    },
    {
        'id': 10,
        'name': 'manage_settings',
        'description': 'Управление настройками системы'
    },
    {
        'id': 11,
        'name': 'manage_users',
        'description': 'Управление пользователями'
    },
    {
        'id': 12,
        'name': 'manage_roles',
        'description': 'Управление ролями и разрешениями'
    }
]

# Связь ролей с разрешениями
DEFAULT_ROLE_PERMISSIONS = {
    'admin': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    'manager': [1, 2, 3, 4, 6, 7, 8, 9],
    'viewer': [1, 2, 6, 7]
}

# Предустановленный пользователь-администратор (пароль: admin)
DEFAULT_USERS = [
    {
        'id': 1,
        'username': 'admin',
        'password_hash': 'pbkdf2:sha256:150000$u1cM1Iuh$80a90b8cea5c793efafff9e7e11aad9c9325cd9b51fc971d9cda97fdf98e56aa',  # 'admin'
        'email': 'admin@example.com',
        'full_name': 'Administrator',
        'role_id': 1,
        'is_active': 1
    }
]

# Примеры сайтов для начального заполнения таблицы sites
DEFAULT_SITES = [
    {
        'name': 'Пример: Google',
        'url': 'https://www.google.com',
        'description': 'Главная страница Google (пример)',
        'check_method': 'static',
        'check_interval': 3600,
        'css_selector': 'body',
        'status': 'active'
    },
    {
        'name': 'Пример: GitHub',
        'url': 'https://github.com',
        'description': 'Главная страница GitHub (пример)',
        'check_method': 'dynamic',
        'check_interval': 7200,
        'css_selector': 'body',
        'status': 'active'
    },
    {
        'name': 'Пример: Hacker News',
        'url': 'https://news.ycombinator.com',
        'description': 'Главная страница Hacker News (пример)',
        'check_method': 'static',
        'check_interval': 1800,
        'css_selector': 'table.itemlist',
        'status': 'active'
    }
]

# Примеры групп для начального заполнения таблицы groups
DEFAULT_GROUPS = [
    {
        'name': 'Поисковые системы',
        'description': 'Группа поисковых систем'
    },
    {
        'name': 'Разработка',
        'description': 'Сайты, связанные с разработкой программного обеспечения'
    },
    {
        'name': 'Новости',
        'description': 'Новостные сайты и агрегаторы'
    }
]


class DatabaseSchema:
    """
    Класс для управления схемой базы данных.
    Отвечает за создание и обновление таблиц и индексов.
    """
    
    def __init__(self, app_context):
        """
        Инициализация схемы базы данных
        
        Args:
            app_context: Контекст приложения с доступом к БД
        """
        self.logger = get_module_logger('database.schema')
        self.app_context = app_context
    
    def initialize(self):
        """
        Инициализация базы данных.
        Создает все необходимые таблицы и добавляет начальные данные.
        """
        try:
            self.logger.debug("Начало инициализации базы данных")
            
            # Проверяем существование файла базы данных
            if not os.path.exists(self.app_context.db_path):
                self.logger.debug(f"Создание новой базы данных: {self.app_context.db_path}")
                try:
                    # Создаем директорию для базы данных, если она не существует
                    os.makedirs(os.path.dirname(self.app_context.db_path), exist_ok=True)
                    
                    # Создаем пустой файл базы данных
                    with open(self.app_context.db_path, 'w') as f:
                        pass
                    
                    self.logger.debug("Файл базы данных успешно создан")
                except Exception as e:
                    self.logger.error(f"Ошибка при создании файла базы данных: {e}")
                    from utils.logger import log_exception
                    log_exception(self.logger, "Ошибка создания файла базы данных")
                    raise
            
            # Проверяем права доступа к файлу базы данных
            if not os.access(self.app_context.db_path, os.R_OK | os.W_OK):
                self.logger.error(f"Нет прав доступа к файлу базы данных: {self.app_context.db_path}")
                raise PermissionError(f"Нет прав доступа к файлу базы данных: {self.app_context.db_path}")
            
            # Создаем таблицы
            self._create_tables()
            
            # Создаем индексы
            for sql in CREATE_INDEXES_SQL:
                try:
                    self.app_context.db_manager.execute_query(sql)
                    self.logger.debug(f"Индекс успешно создан: {sql.split()[2]}")
                except Exception as e:
                    self.logger.error(f"Ошибка при создании индекса: {e}")
                    from utils.logger import log_exception
                    log_exception(self.logger, "Ошибка создания индекса")
                    raise
            
            # Инициализируем настройки
            self._initialize_settings()
            
            # Инициализируем роли
            self._initialize_roles()
            
            # Инициализируем разрешения
            self._initialize_permissions()
            
            # Инициализируем связи ролей и разрешений
            self._initialize_role_permissions()
            
            # Инициализируем пользователя-администратора
            self._initialize_admin_user()
            
            # Проверяем целостность базы данных
            try:
                self.app_context.db_manager.execute_query("PRAGMA integrity_check")
                self.logger.debug("Целостность базы данных проверена")
            except Exception as e:
                self.logger.error(f"Ошибка при проверке целостности базы данных: {e}")
                from utils.logger import log_exception
                log_exception(self.logger, "Ошибка проверки целостности")
                raise
                
            self.logger.info("База данных успешно инициализирована")
            
        except Exception as e:
            self.logger.error(f"Критическая ошибка при инициализации базы данных: {e}")
            from utils.logger import log_exception
            log_exception(self.logger, "Критическая ошибка инициализации")
            raise
    
    def check_update_needed(self) -> bool:
        """
        Проверяет, требуется ли обновление схемы базы данных
        
        Returns:
            bool: True, если требуется обновление
        """
        try:
            # Проверяем наличие всех необходимых таблиц
            check_tables_query = """
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN ('settings', 'sites', 'groups', 'users', 'roles', 'permissions', 'role_permissions', 'snapshots', 'changes', 'events')
            """
            result = self.app_context.execute_db_query(check_tables_query)
            
            if not result or len(result) < 10:  # Должно быть 10 таблиц
                self.logger.info("Отсутствуют необходимые таблицы, требуется обновление")
                return True
            
            # Проверяем версию базы данных
            version_query = """
            SELECT value FROM settings 
            WHERE key = 'database_version'
            """
            result = self.app_context.execute_db_query(version_query)
            
            if not result:
                self.logger.info("Отсутствует запись о версии базы данных")
                return True
            
            current_version = int(result[0]['value'])
            latest_version = 1  # Текущая версия схемы
            
            if current_version < latest_version:
                self.logger.info(f"Требуется обновление с версии {current_version} до {latest_version}")
                return True
            
            self.logger.debug("Обновление схемы базы данных не требуется")
            return False
        
        except Exception as e:
            self.logger.error(f"Ошибка при проверке необходимости обновления базы данных: {e}")
            from utils.logger import log_exception
            log_exception(self.logger, "Ошибка проверки необходимости обновления")
            return True  # В случае ошибки лучше обновить
    
    def update_database(self) -> bool:
        """
        Обновляет схему базы данных до последней версии
        
        Returns:
            bool: Результат обновления
        """
        try:
            self.logger.info("Обновление схемы базы данных")
            
            # Проверяем наличие таблицы settings
            check_table_query = """
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='settings'
            """
            result = self.app_context.execute_db_query(check_table_query)
            
            if not result:
                self.logger.info("Таблица settings не найдена, инициализируем базу данных")
                return self.initialize()
            
            # Проверяем текущую версию
            version_query = """
            SELECT value FROM settings 
            WHERE key = 'database_version'
            """
            result = self.app_context.execute_db_query(version_query)
            
            if not result:
                self.logger.info("Запись о версии не найдена, инициализируем базу данных")
                return self.initialize()
            
            current_version = int(result[0]['value'])
            latest_version = 1  # Текущая версия схемы
            
            if current_version < latest_version:
                self.logger.info(f"Обновление с версии {current_version} до {latest_version}")
                self._update_to_version_1()
                
                # Обновляем версию в базе данных
                update_version_query = """
                UPDATE settings 
                SET value = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE key = 'database_version'
                """
                self.app_context.execute_db_query(update_version_query, (str(latest_version),))
            
            self.logger.info("Схема базы данных обновлена успешно")
            return True
        
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении схемы базы данных: {e}")
            from utils.logger import log_exception
            log_exception(self.logger, "Ошибка обновления схемы базы данных")
            return False
    
    def _create_tables(self):
        """
        Создание всех необходимых таблиц в базе данных.
        Включает создание таблиц и индексов.
        """
        try:
            self.logger.debug("Начало создания таблиц в базе данных")
            
            # Создаем таблицы
            for sql in CREATE_TABLES_SQL:
                try:
                    self.app_context.execute_db_query(sql)
                    self.logger.debug(f"Таблица успешно создана: {sql.split()[2]}")
                except Exception as e:
                    self.logger.error(f"Ошибка при создании таблицы: {e}")
                    from utils.logger import log_exception
                    log_exception(self.logger, "Ошибка создания таблицы")
                    raise
            
            # Создаем индексы
            for sql in CREATE_INDEXES_SQL:
                try:
                    self.app_context.execute_db_query(sql)
                    self.logger.debug(f"Индекс успешно создан: {sql.split()[2]}")
                except Exception as e:
                    self.logger.error(f"Ошибка при создании индекса: {e}")
                    from utils.logger import log_exception
                    log_exception(self.logger, "Ошибка создания индекса")
                    raise
            
            # Проверяем, что все таблицы созданы
            for table in ['sites', 'groups', 'users', 'roles', 'permissions', 
                         'role_permissions', 'snapshots', 'changes', 'events', 'settings']:
                if not self.app_context.db_manager.table_exists(table):
                    self.logger.error(f"Таблица {table} не была создана")
                    raise RuntimeError(f"Таблица {table} не была создана")
            
            self.logger.info("Все таблицы и индексы успешно созданы")
            
        except Exception as e:
            self.logger.error(f"Критическая ошибка при создании таблиц: {e}")
            from utils.logger import log_exception
            log_exception(self.logger, "Критическая ошибка создания таблиц")
            raise
    
    def _initialize_settings(self):
        """
        Инициализация настроек по умолчанию в базе данных.
        Добавляет настройки только если они отсутствуют.
        """
        try:
            self.logger.debug("Начало инициализации настроек")
            
            # Проверяем существование таблицы settings
            if not self.app_context.db_manager.table_exists('settings'):
                self.logger.error("Таблица settings не существует")
                raise RuntimeError("Таблица settings не существует")
            
            # Получаем текущие настройки
            current_settings = self.app_context.db_manager.get_all_records('settings')
            current_keys = {setting['key'] for setting in current_settings}
            
            # Добавляем отсутствующие настройки
            for setting in DEFAULT_SETTINGS:
                if setting['key'] not in current_keys:
                    try:
                        self.app_context.db_manager.insert_record('settings', setting)
                        self.logger.debug(f"Добавлена настройка: {setting['key']}")
                    except Exception as e:
                        self.logger.error(f"Ошибка при добавлении настройки {setting['key']}: {e}")
                        from utils.logger import log_exception
                        log_exception(self.logger, "Ошибка добавления настройки")
                        raise
            
            # Проверяем, что все настройки добавлены
            final_settings = self.app_context.db_manager.get_all_records('settings')
            final_keys = {setting['key'] for setting in final_settings}
            
            missing_settings = set(setting['key'] for setting in DEFAULT_SETTINGS) - final_keys
            if missing_settings:
                self.logger.error(f"Отсутствуют настройки: {missing_settings}")
                raise RuntimeError(f"Отсутствуют настройки: {missing_settings}")
            
            self.logger.info("Все настройки успешно инициализированы")
        
        except Exception as e:
            self.logger.error(f"Критическая ошибка при инициализации настроек: {e}")
            from utils.logger import log_exception
            log_exception(self.logger, "Критическая ошибка инициализации настроек")
            raise
    
    def _add_default_data(self):
        """
        Добавление предустановленных данных в базу данных (настройки, группы, сайты)
        """
        try:
            self.logger.debug("Начало добавления предустановленных данных")
            
            # Добавляем группы
            self.logger.debug("Добавление групп")
            for group in DEFAULT_GROUPS:
                try:
                    query = "INSERT OR IGNORE INTO groups (id, name, description) VALUES (?, ?, ?)"
                    params = (group['id'], group['name'], group['description'])
                    self.app_context.db_manager.execute_query(query, params)
                    self.logger.debug(f"Добавлена группа: {group['name']}")
                except Exception as e:
                    self.logger.error(f"Ошибка при добавлении группы {group['name']}: {e}")
                    from utils.logger import log_exception
                    log_exception(self.logger, f"Ошибка добавления группы: {group['name']}")
                    raise
            
            # Добавляем сайты
            self.logger.debug("Добавление сайтов")
            for site in DEFAULT_SITES:
                try:
                    query = """
                    INSERT OR IGNORE INTO sites 
                    (id, name, url, description, check_method, check_interval, status, group_id) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    params = (
                        site['id'], 
                        site['name'], 
                        site['url'], 
                        site['description'], 
                        site['check_method'], 
                        site['check_interval'], 
                        site['status'], 
                        site['group_id']
                    )
                    self.app_context.db_manager.execute_query(query, params)
                    self.logger.debug(f"Добавлен сайт: {site['name']}")
                except Exception as e:
                    self.logger.error(f"Ошибка при добавлении сайта {site['name']}: {e}")
                    from utils.logger import log_exception
                    log_exception(self.logger, f"Ошибка добавления сайта: {site['name']}")
                    raise
            
            # Добавляем настройки
            self.logger.debug("Добавление настроек")
            for setting in DEFAULT_SETTINGS:
                try:
                    query = "INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)"
                    params = (setting['key'], setting['value'], setting['description'])
                    self.app_context.db_manager.execute_query(query, params)
                    self.logger.debug(f"Добавлена настройка: {setting['key']}")
                except Exception as e:
                    self.logger.error(f"Ошибка при добавлении настройки {setting['key']}: {e}")
                    from utils.logger import log_exception
                    log_exception(self.logger, f"Ошибка добавления настройки: {setting['key']}")
                    raise
            
            # Добавляем роли
            self.logger.debug("Добавление ролей")
            for role in DEFAULT_ROLES:
                try:
                    query = "INSERT OR IGNORE INTO roles (id, name, description) VALUES (?, ?, ?)"
                    params = (role['id'], role['name'], role['description'])
                    self.app_context.db_manager.execute_query(query, params)
                    self.logger.debug(f"Добавлена роль: {role['name']}")
                except Exception as e:
                    self.logger.error(f"Ошибка при добавлении роли {role['name']}: {e}")
                    from utils.logger import log_exception
                    log_exception(self.logger, f"Ошибка добавления роли: {role['name']}")
                    raise
            
            # Добавляем разрешения
            self.logger.debug("Добавление разрешений")
            for permission in DEFAULT_PERMISSIONS:
                try:
                    query = "INSERT OR IGNORE INTO permissions (id, name, description) VALUES (?, ?, ?)"
                    params = (permission['id'], permission['name'], permission['description'])
                    self.app_context.db_manager.execute_query(query, params)
                    self.logger.debug(f"Добавлено разрешение: {permission['name']}")
                except Exception as e:
                    self.logger.error(f"Ошибка при добавлении разрешения {permission['name']}: {e}")
                    from utils.logger import log_exception
                    log_exception(self.logger, f"Ошибка добавления разрешения: {permission['name']}")
                    raise
            
            # Добавляем связи ролей и разрешений
            self.logger.debug("Добавление связей ролей и разрешений")
            self._initialize_role_permissions()
            
            # Добавляем пользователей
            self.logger.debug("Добавление пользователей")
            for user in DEFAULT_USERS:
                try:
                    query = """
                    INSERT OR IGNORE INTO users 
                    (id, username, password_hash, email, full_name, role_id, is_active) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """
                    params = (
                        user['id'],
                        user['username'],
                        user['password_hash'],
                        user['email'],
                        user['full_name'],
                        user['role_id'],
                        user['is_active']
                    )
                    self.app_context.db_manager.execute_query(query, params)
                    self.logger.debug(f"Добавлен пользователь: {user['username']}")
                except Exception as e:
                    self.logger.error(f"Ошибка при добавлении пользователя {user['username']}: {e}")
                    from utils.logger import log_exception
                    log_exception(self.logger, f"Ошибка добавления пользователя: {user['username']}")
                    raise
            
            self.logger.info("Предустановленные данные успешно добавлены в базу данных")
            return True
        
        except Exception as e:
            self.logger.error(f"Критическая ошибка при добавлении предустановленных данных: {e}")
            from utils.logger import log_exception
            log_exception(self.logger, "Критическая ошибка добавления предустановленных данных")
            raise
    
    def _update_to_version_1(self):
        """
        Обновление базы данных до версии 1.
        Добавляет новые таблицы и индексы, если они отсутствуют.
        """
        try:
            self.logger.debug("Начало обновления базы данных до версии 1")
            
            # Проверяем текущую версию
            current_version = self.app_context.db_manager.get_setting('database_version')
            if current_version and int(current_version) >= 1:
                self.logger.debug("База данных уже обновлена до версии 1")
                return
            
            # Создаем отсутствующие таблицы
            for sql in CREATE_TABLES_SQL:
                try:
                    table_name = sql.split()[2]
                    if not self.app_context.db_manager.table_exists(table_name):
                        self.app_context.db_manager.execute_query(sql)
                        self.logger.debug(f"Создана таблица: {table_name}")
                except Exception as e:
                    self.logger.error(f"Ошибка при создании таблицы {table_name}: {e}")
                    from utils.logger import log_exception
                    log_exception(self.logger, "Ошибка создания таблицы")
                    raise
            
            # Создаем отсутствующие индексы
            for sql in CREATE_INDEXES_SQL:
                try:
                    index_name = sql.split()[2]
                    if not self.app_context.db_manager.index_exists(index_name):
                        self.app_context.db_manager.execute_query(sql)
                        self.logger.debug(f"Создан индекс: {index_name}")
                except Exception as e:
                    self.logger.error(f"Ошибка при создании индекса {index_name}: {e}")
                    from utils.logger import log_exception
                    log_exception(self.logger, "Ошибка создания индекса")
                    raise
            
            # Проверяем целостность базы данных
            try:
                self.app_context.db_manager.execute_query("PRAGMA integrity_check")
                self.logger.debug("Целостность базы данных проверена")
            except Exception as e:
                self.logger.error(f"Ошибка при проверке целостности базы данных: {e}")
                from utils.logger import log_exception
                log_exception(self.logger, "Ошибка проверки целостности")
                raise
            
            # Обновляем версию базы данных
            try:
                self.app_context.db_manager.update_setting('database_version', '1')
                self.logger.debug("Версия базы данных обновлена до 1")
            except Exception as e:
                self.logger.error(f"Ошибка при обновлении версии базы данных: {e}")
                from utils.logger import log_exception
                log_exception(self.logger, "Ошибка обновления версии")
                raise
            
            self.logger.info("База данных успешно обновлена до версии 1")
            
        except Exception as e:
            self.logger.error(f"Критическая ошибка при обновлении базы данных: {e}")
            from utils.logger import log_exception
            log_exception(self.logger, "Критическая ошибка обновления")
            raise

    def _initialize_role_permissions(self):
        """
        Инициализация связей между ролями и разрешениями по умолчанию.
        Добавляет связи только если они отсутствуют.
        """
        try:
            self.logger.debug("Начало инициализации связей ролей и разрешений")
            
            # Проверяем существование таблицы role_permissions
            if not self.app_context.db_manager.table_exists('role_permissions'):
                self.logger.error("Таблица role_permissions не существует")
                raise RuntimeError("Таблица role_permissions не существует")
            
            # Получаем текущие связи
            current_links = self.app_context.db_manager.get_all_records('role_permissions')
            # Проверяем существование таблицы roles
            if not self.app_context.db_manager.table_exists('roles'):
                self.logger.error("Таблица roles не существует")
                raise RuntimeError("Таблица roles не существует")
            
            # Получаем текущие роли
            current_roles = self.app_context.db_manager.get_all_records('roles')
            current_names = {role['name'] for role in current_roles}
            
            # Добавляем отсутствующие роли
            for role in DEFAULT_ROLES:
                if role['name'] not in current_names:
                    try:
                        self.app_context.db_manager.insert_record('roles', role)
                        self.logger.debug(f"Добавлена роль: {role['name']}")
                    except Exception as e:
                        self.logger.error(f"Ошибка при добавлении роли {role['name']}: {e}")
                        from utils.logger import log_exception
                        log_exception(self.logger, "Ошибка добавления роли")
                        raise
            
            # Проверяем, что все роли добавлены
            final_roles = self.app_context.db_manager.get_all_records('roles')
            final_names = {role['name'] for role in final_roles}
            
            missing_roles = set(role['name'] for role in DEFAULT_ROLES) - final_names
            if missing_roles:
                self.logger.error(f"Отсутствуют роли: {missing_roles}")
                raise RuntimeError(f"Отсутствуют роли: {missing_roles}")
            
            self.logger.info("Все роли пользователей успешно инициализированы")
            
        except Exception as e:
            self.logger.error(f"Критическая ошибка при инициализации ролей: {e}")
            from utils.logger import log_exception
            log_exception(self.logger, "Критическая ошибка инициализации ролей")
            raise

    def _initialize_permissions(self):
        """
        Инициализация разрешений по умолчанию.
        Добавляет разрешения только если они отсутствуют.
        """
        try:
            self.logger.debug("Начало инициализации разрешений")
            
            # Проверяем существование таблицы permissions
            if not self.app_context.db_manager.table_exists('permissions'):
                self.logger.error("Таблица permissions не существует")
                raise RuntimeError("Таблица permissions не существует")
            
            # Получаем текущие разрешения
            current_permissions = self.app_context.db_manager.get_all_records('permissions')
            current_names = {permission['name'] for permission in current_permissions}
            
            # Добавляем отсутствующие разрешения
            for permission in DEFAULT_PERMISSIONS:
                if permission['name'] not in current_names:
                    try:
                        self.app_context.db_manager.insert_record('permissions', permission)
                        self.logger.debug(f"Добавлено разрешение: {permission['name']}")
                    except Exception as e:
                        self.logger.error(f"Ошибка при добавлении разрешения {permission['name']}: {e}")
                        from utils.logger import log_exception
                        log_exception(self.logger, "Ошибка добавления разрешения")
                        raise
            
            # Проверяем, что все разрешения добавлены
            final_permissions = self.app_context.db_manager.get_all_records('permissions')
            final_names = {permission['name'] for permission in final_permissions}
            
            missing_permissions = set(permission['name'] for permission in DEFAULT_PERMISSIONS) - final_names
            if missing_permissions:
                self.logger.error(f"Отсутствуют разрешения: {missing_permissions}")
                raise RuntimeError(f"Отсутствуют разрешения: {missing_permissions}")
            
            self.logger.info("Все разрешения успешно инициализированы")
            
        except Exception as e:
            self.logger.error(f"Критическая ошибка при инициализации разрешений: {e}")
            from utils.logger import log_exception
            log_exception(self.logger, "Критическая ошибка инициализации разрешений")
            raise

    def _initialize_roles(self):
        """
        Инициализация ролей по умолчанию.
        Добавляет роли только если они отсутствуют.
        """
        try:
            self.logger.debug("Начало инициализации ролей")
            
            # Проверяем существование таблицы roles
            if not self.app_context.db_manager.table_exists('roles'):
                self.logger.error("Таблица roles не существует")
                raise RuntimeError("Таблица roles не существует")
            
            # Получаем текущие роли
            current_roles = self.app_context.db_manager.get_all_records('roles')
            current_names = {role['name'] for role in current_roles}
            
            # Добавляем отсутствующие роли
            for role in DEFAULT_ROLES:
                if role['name'] not in current_names:
                    try:
                        self.app_context.db_manager.insert_record('roles', role)
                        self.logger.debug(f"Добавлена роль: {role['name']}")
                    except Exception as e:
                        self.logger.error(f"Ошибка при добавлении роли {role['name']}: {e}")
                        from utils.logger import log_exception
                        log_exception(self.logger, "Ошибка добавления роли")
                        raise
            
            # Проверяем, что все роли добавлены
            final_roles = self.app_context.db_manager.get_all_records('roles')
            final_names = {role['name'] for role in final_roles}
            
            missing_roles = set(role['name'] for role in DEFAULT_ROLES) - final_names
            if missing_roles:
                self.logger.error(f"Отсутствуют роли: {missing_roles}")
                raise RuntimeError(f"Отсутствуют роли: {missing_roles}")
            
            self.logger.info("Все роли успешно инициализированы")
        
        except Exception as e:
            self.logger.error(f"Критическая ошибка при инициализации ролей: {e}")
            from utils.logger import log_exception
            log_exception(self.logger, "Критическая ошибка инициализации ролей")
            raise

    def _initialize_admin_user(self):
        """
        Инициализация пользователя-администратора.
        Добавляет администратора только если он отсутствует.
        """
        try:
            self.logger.debug("Начало инициализации пользователя-администратора")
            
            # Проверяем существование таблицы users
            if not self.app_context.db_manager.table_exists('users'):
                self.logger.error("Таблица users не существует")
                raise RuntimeError("Таблица users не существует")
            
            # Проверяем существование таблицы roles
            if not self.app_context.db_manager.table_exists('roles'):
                self.logger.error("Таблица roles не существует")
                raise RuntimeError("Таблица roles не существует")
            
            # Получаем роль администратора
            admin_role_query = "SELECT id FROM roles WHERE name = 'admin'"
            admin_role = self.app_context.db_manager.execute_query(admin_role_query, fetch_all=False)
            
            if not admin_role:
                self.logger.error("Роль администратора не найдена")
                raise RuntimeError("Роль администратора не найдена")
            
            # Проверяем существование администратора
            admin_query = "SELECT id FROM users WHERE username = 'admin'"
            admin = self.app_context.db_manager.execute_query(admin_query, fetch_all=False)
            
            if not admin:
                # Создаем администратора
                admin_data = {
                    'username': 'admin',
                    'password_hash': 'pbkdf2:sha256:260000$YOUR_SALT$YOUR_HASH',  # Замените на реальный хеш
                    'email': 'admin@example.com',
                    'full_name': 'System Administrator',
                    'role_id': admin_role['id'],
                    'is_active': True
                }
                
                try:
                    self.app_context.db_manager.insert_record('users', admin_data)
                    self.logger.info("Пользователь-администратор успешно создан")
                except Exception as e:
                    self.logger.error(f"Ошибка при создании пользователя-администратора: {e}")
                    from utils.logger import log_exception
                    log_exception(self.logger, "Ошибка создания администратора")
                    raise
            else:
                self.logger.debug("Пользователь-администратор уже существует")
        
        except Exception as e:
            self.logger.error(f"Критическая ошибка при инициализации пользователя-администратора: {e}")
            from utils.logger import log_exception
            log_exception(self.logger, "Критическая ошибка инициализации администратора")
            raise 