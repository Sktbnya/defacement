#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль контекста приложения для WDM_V12.
Содержит класс AppContext, который предоставляет доступ к ресурсам приложения.
"""

import os
import time
import logging
import threading
import json
from typing import Dict, List, Any, Optional, Union
import datetime
import sys

from config.config import get_config, save_config
from utils.logger import get_module_logger, log_exception
from database.db_manager import DBManager
from database.schema import DatabaseSchema
from core.settings import Settings
from utils.http_client import get_http_client


class AppContext:
    """
    Класс контекста приложения.
    Предоставляет доступ к ресурсам приложения: конфигурации, логгеру, базе данных и т.д.
    """
    
    # Единственный экземпляр класса (шаблон Singleton)
    _instance = None
    
    # Блокировка для обеспечения потокобезопасности
    _lock = threading.RLock()
    
    def __new__(cls):
        """
        Реализация шаблона Singleton для класса AppContext
        
        Returns:
            AppContext: Единственный экземпляр класса
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AppContext, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        """
        Инициализация контекста приложения
        """
        if self._initialized:
            return
            
        self.logger = get_module_logger('core.app_context')
        self.logger.debug("Инициализация контекста приложения")
        
        # Загружаем конфигурацию
        self.config = get_config()
        
        # Инициализируем пути
        self.db_path = self.config.get('database', {}).get('path')
        if not self.db_path:
            raise ValueError("Путь к базе данных не найден в конфигурации")
            
        self.backup_dir = self.config.get('database', {}).get('backup_dir', 'backups')
        
        # Инициализируем менеджеры
        self.db_manager = DBManager(self.db_path)
        self.settings_manager = Settings()
        self.monitor_manager = None  # Инициализируем как None, будет создан при необходимости
        
        # Инициализируем схему базы данных
        self.schema = DatabaseSchema(self)
        
        # Инициализируем базу данных
        self.schema.initialize()
        
        # Состояние приложения
        self._status = {
            'is_ready': False,
            'sites_count': 0,
            'last_check': None,
            'errors': [],
            'monitoring_active': False,
            'active_workers': 0,
            'changed_sites_count': 0
        }
        
        self._initialized = True
        self.logger.debug("Контекст приложения инициализирован")
    
    def _initialize_database(self):
        """
        Инициализация менеджера базы данных и схемы базы данных
        
        Returns:
            bool: True, если инициализация прошла успешно
        """
        try:
            self.logger.debug("Инициализация базы данных")
            
            # Создаем менеджер базы данных
            self.db_manager = DBManager()
            
            # Инициализируем схему базы данных
            schema = DatabaseSchema(self)
            
            # Проверяем, требуется ли обновление схемы
            if schema.check_update_needed():
                self.logger.info("Требуется обновление схемы базы данных")
                if not schema.update_database():
                    self.logger.error("Не удалось обновить схему базы данных")
                    return False
            
            # Проверяем целостность базы данных
            try:
                self.db_manager.execute_query("PRAGMA integrity_check")
                self.logger.debug("Целостность базы данных проверена")
            except Exception as e:
                self.logger.error(f"Ошибка при проверке целостности базы данных: {e}")
                log_exception(self.logger, "Ошибка проверки целостности")
                return False
            
            # Получаем статистику по базе данных
            db_stats = self.db_manager.get_database_stats()
            sites_count = db_stats.get('tables', {}).get('sites', {}).get('row_count', 0)
            
            # Обновляем статус приложения
            self.update_status(
                is_ready=True,
                sites_count=sites_count
            )
            
            self.logger.debug("База данных инициализирована успешно")
            return True
        
        except Exception as e:
            self.logger.error(f"Ошибка при инициализации базы данных: {e}")
            log_exception(self.logger, "Ошибка инициализации базы данных")
            
            # Обновляем статус приложения
            self.update_status(is_ready=False)
            return False
    
    def start_monitoring(self):
        """
        Запуск системы мониторинга
        
        Returns:
            bool: Результат запуска
        """
        start_id = f"start_mon_{int(time.time())}"
        start_time = time.time()
        
        try:
            self.logger.info(f"Запуск системы мониторинга [{start_id}]")
            
            # Проверяем, что база данных инициализирована
            if not self.db_manager:
                self.logger.error(f"Не удалось запустить мониторинг [{start_id}]: менеджер БД не создан")
                return False
                
            if not self._status['is_ready']:
                self.logger.error(f"Не удалось запустить мониторинг [{start_id}]: база данных не инициализирована")
                return False
            
            # Если менеджер мониторинга еще не создан, создаем его
            if not self.monitor_manager:
                self.logger.debug(f"Создание менеджера мониторинга [{start_id}]")
                try:
                    from workers.monitor_manager import MonitorManager
                    self.monitor_manager = MonitorManager(self)
                    self.logger.debug(f"Менеджер мониторинга успешно создан [{start_id}]")
                except Exception as manager_error:
                    self.logger.error(f"Ошибка при создании менеджера мониторинга [{start_id}]: {manager_error}")
                    log_exception(self.logger, f"Ошибка создания менеджера мониторинга [{start_id}]")
                    return False
            
            # Запускаем мониторинг
            start_result = self.monitor_manager.start()
            if not start_result:
                self.logger.error(f"Менеджер мониторинга не удалось запустить [{start_id}]")
                return False
                
            execution_time = time.time() - start_time
            self.logger.info(f"Система мониторинга запущена успешно [{start_id}] за {execution_time:.3f} сек")
            return True
        
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Ошибка при запуске системы мониторинга [{start_id}] (время: {execution_time:.3f} сек): {e}")
            log_exception(self.logger, f"Ошибка запуска системы мониторинга [{start_id}]")
            return False
    
    def stop_monitoring(self):
        """
        Остановка системы мониторинга
        
        Returns:
            bool: Результат остановки
        """
        try:
            self.logger.info("Остановка системы мониторинга")
            
            # Проверяем, что менеджер мониторинга инициализирован
            if not self.monitor_manager:
                self.logger.warning("Система мониторинга не была запущена")
                return True
            
            # Останавливаем мониторинг
            self.monitor_manager.stop()
            
            self.logger.info("Система мониторинга остановлена успешно")
            return True
        
        except Exception as e:
            self.logger.error(f"Ошибка при остановке системы мониторинга: {e}")
            log_exception(self.logger, "Ошибка остановки системы мониторинга")
            return False
    
    def check_site_now(self, site_id):
        """
        Запрос на немедленную проверку сайта
        
        Args:
            site_id: ID сайта для проверки
            
        Returns:
            bool: Результат выполнения запроса
        """
        try:
            self.logger.info(f"Запрос на немедленную проверку сайта ID={site_id}")
            
            # Проверяем, что менеджер мониторинга инициализирован и активен
            if not self.monitor_manager or not self.monitor_manager.is_active:
                self.logger.warning("Система мониторинга не активна")
                return False
            
            # Выполняем запрос на проверку
            return self.monitor_manager.check_now(site_id)
        
        except Exception as e:
            self.logger.error(f"Ошибка при запросе проверки сайта ID={site_id}: {e}")
            log_exception(self.logger, "Ошибка запроса проверки сайта")
            return False
    
    def check_all_sites_now(self):
        """
        Запрос на немедленную проверку всех сайтов
        
        Returns:
            bool: Результат выполнения запроса
        """
        try:
            self.logger.info("Запрос на немедленную проверку всех сайтов")
            
            # Проверяем, что менеджер мониторинга инициализирован и активен
            if not self.monitor_manager or not self.monitor_manager.is_active:
                self.logger.warning("Система мониторинга не активна")
                return False
            
            # Выполняем запрос на проверку
            return self.monitor_manager.check_now()
        
        except Exception as e:
            self.logger.error(f"Ошибка при запросе проверки всех сайтов: {e}")
            log_exception(self.logger, "Ошибка запроса проверки всех сайтов")
            return False
    
    def get_status(self):
        """
        Получение текущего статуса приложения
        
        Returns:
            Dict[str, Any]: Статус приложения
        """
        with self._lock:
            # Обновляем время последнего обновления
            self._status['last_update'] = time.time()
            return self._status.copy()
    
    def update_status(self, **kwargs):
        """
        Обновление статуса приложения
        
        Args:
            **kwargs: Ключи и значения для обновления
        """
        with self._lock:
            for key, value in kwargs.items():
                if key in self._status:
                    self._status[key] = value
            
            # Обновляем время последнего обновления
            self._status['last_update'] = time.time()
    
    def get_settings(self):
        """
        Получение всех настроек приложения
        
        Returns:
            Dict[str, Any]: Словарь со всеми настройками
        """
        try:
            return self.settings_manager.get_settings()
        except Exception as e:
            self.logger.error(f"Ошибка при получении настроек приложения: {e}")
            log_exception(self.logger, "Ошибка получения настроек приложения")
            return {}
    
    def update_setting(self, key, value):
        """
        Обновление настройки приложения в базе данных
        
        Args:
            key: Ключ настройки
            value: Новое значение
            
        Returns:
            bool: Результат обновления
        """
        try:
            # Выполняем запрос к базе данных
            query = """
            UPDATE settings 
            SET value = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE key = ?
            """
            
            self.db_manager.execute_query(query, (value, key))
            
            # Обновляем конфигурацию, если настройка влияет на неё
            if key in self.config.get('settings', {}):
                self.config['settings'][key] = value
                save_config(self.config)
            
            return True
        
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении настройки {key}: {e}")
            log_exception(self.logger, "Ошибка обновления настройки")
            return False
    
    def execute_db_query(self, query, params=None, fetch_all=True):
        """
        Выполнение запроса к базе данных
        
        Args:
            query: SQL-запрос
            params: Параметры запроса (кортеж или словарь)
            fetch_all: Возвращать ли все результаты
            
        Returns:
            Результаты запроса
        """
        try:
            # Проверка на наличие менеджера БД
            if not self.db_manager:
                self.logger.error("Менеджер базы данных не инициализирован")
                raise RuntimeError("Менеджер базы данных не инициализирован")
                
            # Проверка на SQL-инъекции в запросе (базовая)
            dangerous_keywords = ["DROP", "TRUNCATE", "ALTER", ";", "--"]
            query_upper = query.upper()
            
            # Для действительно опасных операций требуется специальный флаг
            if any(kw in query_upper for kw in dangerous_keywords) and "PRAGMA" not in query_upper:
                is_allowed = False
                if query_upper.startswith("SELECT") or query.startswith("INSERT") or query.startswith("UPDATE") or query.startswith("DELETE"):
                    is_allowed = True
                    
                if not is_allowed:
                    self.logger.warning(f"Потенциально опасный SQL-запрос: {query}")
                    raise ValueError(f"Потенциально опасный SQL-запрос: {query}")
            
            # Проверка параметров
            if params is not None and not isinstance(params, (tuple, list, dict)):
                self.logger.warning(f"Неверный тип параметров: {type(params)}")
                params = (params,)  # Преобразуем скалярный параметр в кортеж
                
            # Выполнение запроса с логированием
            self.logger.debug(f"Выполнение SQL: {query}")
            return self.db_manager.execute_query(query, params, fetch_all)
        except Exception as e:
            # Конкретизация типов ошибок для улучшения отладки
            if "UNIQUE constraint failed" in str(e):
                error_msg = "Ошибка: нарушение уникальности данных"
            elif "FOREIGN KEY constraint failed" in str(e):
                error_msg = "Ошибка: нарушение внешнего ключа"
            elif "no such table" in str(e):
                error_msg = "Ошибка: таблица не существует"
            elif "database is locked" in str(e):
                error_msg = "Ошибка: база данных заблокирована"
            else:
                error_msg = f"Ошибка при выполнении запроса к базе данных: {e}"
                
            self.logger.error(error_msg)
            log_exception(self.logger, "Ошибка выполнения запроса к базе данных")
            raise
    
    def shutdown(self):
        """Завершение работы приложения и освобождение ресурсов"""
        try:
            self.logger.info("Завершение работы приложения")
            
            # Устанавливаем флаг остановки
            self.is_stopping = True
            
            # Останавливаем мониторинг, если он активен
            if self.monitor_manager and self.monitor_manager.is_active:
                self.stop_monitoring()
            
            # Закрываем соединение с базой данных
            if self.db_manager:
                self.db_manager.close()
            
            self.logger.info("Приложение успешно завершило работу")
        
        except Exception as e:
            self.logger.error(f"Ошибка при завершении работы приложения: {e}")
            log_exception(self.logger, "Ошибка завершения работы приложения")
    
    def get_sites(self, condition=None, params=None, limit=None, offset=None):
        """
        Получение списка сайтов из базы данных
        
        Args:
            condition: Условие WHERE (опционально)
            params: Параметры условия (опционально)
            limit: Ограничение количества результатов (опционально)
            offset: Смещение (опционально)
            
        Returns:
            List[Dict[str, Any]]: Список сайтов
        """
        try:
            # Базовый запрос для получения сайтов вместе с информацией о группе
            query = """
            SELECT s.*, g.name as group_name 
            FROM sites s 
            LEFT JOIN groups g ON s.group_id = g.id
            """
            
            # Добавляем условие, если оно указано
            if condition:
                query += f" WHERE {condition}"
            
            # Добавляем сортировку
            query += " ORDER BY s.name"
            
            # Добавляем ограничение количества результатов, если оно указано
            if limit:
                query += f" LIMIT {limit}"
            
            # Добавляем смещение, если оно указано
            if offset:
                query += f" OFFSET {offset}"
            
            return self.execute_db_query(query, params)
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка сайтов: {e}")
            log_exception(self.logger, "Ошибка получения списка сайтов")
            return []
    
    def get_site(self, site_id):
        """
        Получение информации о сайте по ID
        
        Args:
            site_id: ID сайта
            
        Returns:
            Dict[str, Any]: Информация о сайте или None, если сайт не найден
        """
        try:
            query = """
            SELECT s.*, g.name as group_name 
            FROM sites s 
            LEFT JOIN groups g ON s.group_id = g.id 
            WHERE s.id = ?
            """
            
            result = self.execute_db_query(query, (site_id,), fetch_all=False)
            return result
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении информации о сайте ID={site_id}: {e}")
            log_exception(self.logger, "Ошибка получения информации о сайте")
            return None
    
    def validate_site_data(self, site_data):
        """
        Валидация данных сайта перед добавлением или обновлением
        
        Args:
            site_data: Данные сайта для валидации
            
        Returns:
            tuple: (bool, str) - результат валидации и сообщение об ошибке
        """
        try:
            # Проверка типа входных данных
            if not isinstance(site_data, dict):
                return False, "Данные сайта должны быть словарем"
                
            # Проверка наличия обязательных полей
            if 'name' not in site_data or not site_data['name']:
                return False, "Имя сайта является обязательным"
                
            if 'url' not in site_data or not site_data['url']:
                return False, "URL сайта является обязательным"
            
            # Проверка типов данных
            if not isinstance(site_data.get('name', ''), str):
                return False, "Имя сайта должно быть строкой"
                
            if not isinstance(site_data.get('url', ''), str):
                return False, "URL должен быть строкой"
            
            # Проверка длины имени
            if len(site_data['name']) > 100:
                return False, "Имя сайта не должно превышать 100 символов"
            
            # Валидация URL
            try:
                from urllib.parse import urlparse
                result = urlparse(site_data['url'])
                if not all([result.scheme, result.netloc]):
                    return False, "Некорректный URL"
                
                # Проверка поддерживаемых схем
                if result.scheme not in ['http', 'https']:
                    return False, "URL должен начинаться с http:// или https://"
            except Exception as e:
                self.logger.error(f"Ошибка при разборе URL: {e}")
                return False, f"Ошибка обработки URL: {e}"
            
            # Проверка интервала проверки
            check_interval = site_data.get('check_interval', 3600)
            if not isinstance(check_interval, int):
                try:
                    check_interval = int(check_interval)
                except (ValueError, TypeError):
                    return False, "Интервал проверки должен быть числом"
            
            if check_interval < 60:
                return False, "Минимальный интервал проверки - 60 секунд"
                
            if check_interval > 86400 * 30:  # 30 дней
                return False, "Максимальный интервал проверки - 30 дней"
            
            # Проверка метода проверки
            check_method = site_data.get('check_method', 'static')
            if check_method not in ['static', 'dynamic']:
                return False, "Метод проверки должен быть 'static' или 'dynamic'"
            
            # Проверка статуса
            status = site_data.get('status', 'active')
            if status not in ['active', 'paused', 'inactive']:
                return False, "Статус должен быть 'active', 'paused' или 'inactive'"
            
            # Проверка приоритета
            priority = site_data.get('priority', 5)
            try:
                priority = int(priority)
                if priority < 1 or priority > 10:
                    return False, "Приоритет должен быть числом от 1 до 10"
            except (ValueError, TypeError):
                return False, "Приоритет должен быть числом"
            
            # Проверка группы, если она указана
            if 'group_id' in site_data and site_data['group_id'] is not None:
                try:
                    group_id = int(site_data['group_id'])
                    group = self.execute_db_query(
                        "SELECT id FROM groups WHERE id = ?", 
                        (group_id,),
                        fetch_all=False
                    )
                    if not group:
                        return False, "Указанная группа не существует"
                except (ValueError, TypeError):
                    return False, "ID группы должен быть числом"
            
            # Проверка дубликатов URL
            exists_query = "SELECT id FROM sites WHERE url = ?"
            params = [site_data['url']]
            
            # Если это обновление, исключаем текущий сайт из проверки
            if 'id' in site_data:
                exists_query += " AND id != ?"
                params.append(site_data['id'])
                
            exists = self.execute_db_query(exists_query, tuple(params))
            if exists:
                return False, "Сайт с таким URL уже существует"
            
            return True, ""
            
        except Exception as e:
            self.logger.error(f"Ошибка при валидации данных сайта: {e}")
            log_exception(self.logger, "Ошибка валидации данных сайта")
            return False, f"Ошибка валидации: {e}"
    
    def test_url(self, url):
        """
        Проверка доступности URL
        
        Args:
            url: URL для проверки
            
        Returns:
            tuple: (bool, str) - результат проверки и сообщение об ошибке (если есть)
        """
        try:
            import requests
            from urllib.parse import urlparse
            
            # Базовая проверка формата URL
            result = urlparse(url)
            if not all([result.scheme, result.netloc]):
                return False, "Некорректный формат URL"
                
            # Получаем настройки мониторинга
            settings = self.get_settings()
            monitoring_settings = settings.get('monitoring', {})
            
            # Настройка заголовков запроса
            headers = {
                'User-Agent': monitoring_settings.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Connection': 'keep-alive'
            }
            
            # Выполнение запроса с учетом таймаута
            timeout = monitoring_settings.get('timeout', 30)
            
            self.logger.debug(f"Тестирование доступности URL: {url}")
            
            # Проверка прокси
            proxy_settings = settings.get('proxy', {})
            proxies = None
            if proxy_settings.get('enabled', False):
                proxy_type = proxy_settings.get('type', 'http')
                proxy_host = proxy_settings.get('host', '')
                proxy_port = proxy_settings.get('port', 8080)
                proxy_username = proxy_settings.get('username', '')
                proxy_password = proxy_settings.get('password', '')
                
                # Формируем строку прокси
                proxy_url = f"{proxy_type}://"
                if proxy_username and proxy_password:
                    proxy_url += f"{proxy_username}:{proxy_password}@"
                proxy_url += f"{proxy_host}:{proxy_port}"
                
                proxies = {
                    'http': proxy_url,
                    'https': proxy_url
                }
            
            response = requests.head(url, 
                                    headers=headers, 
                                    timeout=timeout, 
                                    proxies=proxies, 
                                    allow_redirects=True)
            
            # Проверка успешности запроса (коды 200-399 считаются успешными)
            if 200 <= response.status_code < 400:
                return True, f"URL доступен (код ответа: {response.status_code})"
            else:
                return False, f"URL недоступен. Код ответа: {response.status_code}"
        
        except requests.exceptions.Timeout:
            self.logger.warning(f"Таймаут при проверке URL: {url}")
            return False, "Превышено время ожидания ответа от сервера"
            
        except requests.exceptions.ConnectionError:
            self.logger.warning(f"Ошибка соединения при проверке URL: {url}")
            return False, "Не удалось установить соединение с сервером"
            
        except requests.exceptions.TooManyRedirects:
            self.logger.warning(f"Слишком много перенаправлений при проверке URL: {url}")
            return False, "Слишком много перенаправлений"
            
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Ошибка запроса при проверке URL {url}: {e}")
            return False, f"Ошибка запроса: {e}"
            
        except Exception as e:
            self.logger.error(f"Неизвестная ошибка при проверке URL {url}: {e}")
            log_exception(self.logger, "Ошибка проверки URL")
            return False, f"Неизвестная ошибка: {e}"
    
    def add_site(self, site_data):
        """
        Добавление нового сайта в базу данных
        
        Args:
            site_data: Данные сайта
            
        Returns:
            int: ID добавленного сайта или None в случае ошибки
        """
        try:
            # Валидация данных сайта
            is_valid, error_message = self.validate_site_data(site_data)
            if not is_valid:
                self.logger.error(f"Ошибка валидации данных сайта: {error_message}")
                return None
                
            # Начинаем транзакцию
            conn = self.db_manager._get_connection()
            
            try:
                # Формируем список полей и значений
                fields = ', '.join(site_data.keys())
                placeholders = ', '.join(['?' for _ in site_data])
                
                query = f"INSERT INTO sites ({fields}) VALUES ({placeholders})"
                
                # Выполняем запрос и получаем ID добавленного сайта
                cursor = conn.execute(query, tuple(site_data.values()))
                site_id = cursor.lastrowid
                
                # Создаем начальный снимок сайта, если необходимо
                # Это может быть полезно для отслеживания изменений с момента добавления
                if site_data.get('create_initial_snapshot', False):
                    current_time = datetime.datetime.now()
                    snapshot_query = """
                    INSERT INTO snapshots (site_id, status, timestamp, content_hash, content_size)
                    VALUES (?, 'pending', ?, '', 0)
                    """
                    conn.execute(snapshot_query, (site_id, current_time))
                
                # Фиксируем транзакцию
                conn.commit()
                
                # Обновляем статус приложения
                sites_count = self.db_manager.get_row_count('sites')
                self.update_status(sites_count=sites_count)
                
                self.logger.info(f"Сайт успешно добавлен: {site_data.get('name')} (ID: {site_id})")
                return site_id
                
            except Exception as e:
                # Откатываем транзакцию в случае ошибки
                conn.rollback()
                raise
        
        except Exception as e:
            self.logger.error(f"Ошибка при добавлении сайта: {e}")
            log_exception(self.logger, "Ошибка добавления сайта")
            return None
    
    def update_site(self, site_id, site_data):
        """
        Обновление информации о сайте
        
        Args:
            site_id: ID сайта
            site_data: Новые данные сайта
            
        Returns:
            bool: Результат обновления
        """
        try:
            # Добавляем ID в данные для валидации
            validation_data = site_data.copy()
            validation_data['id'] = site_id
            
            # Валидация данных сайта
            is_valid, error_message = self.validate_site_data(validation_data)
            if not is_valid:
                self.logger.error(f"Ошибка валидации данных сайта (ID: {site_id}): {error_message}")
                return False
                
            # Начинаем транзакцию
            conn = self.db_manager._get_connection()
            
            try:
                # Формируем список полей и значений для обновления
                set_clause = ', '.join([f"{key} = ?" for key in site_data.keys()])
                
                query = f"UPDATE sites SET {set_clause} WHERE id = ?"
                
                # Добавляем ID сайта в конец списка параметров
                params = list(site_data.values())
                params.append(site_id)
                
                # Выполняем запрос
                conn.execute(query, tuple(params))
                
                # Фиксируем транзакцию
                conn.commit()
                
                self.logger.info(f"Сайт успешно обновлен: {site_data.get('name')} (ID: {site_id})")
                return True
                
            except Exception as e:
                # Откатываем транзакцию в случае ошибки
                conn.rollback()
                raise
        
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении сайта ID={site_id}: {e}")
            log_exception(self.logger, "Ошибка обновления сайта")
            return False
    
    def delete_site(self, site_id):
        """
        Удаление сайта из базы данных
        
        Args:
            site_id: ID сайта
            
        Returns:
            bool: Результат удаления
        """
        try:
            # Проверяем существование сайта
            site = self.get_site(site_id)
            if not site:
                self.logger.error(f"Не удалось найти сайт с ID={site_id} для удаления")
                return False
                
            # Начинаем транзакцию
            conn = self.db_manager._get_connection()
            
            try:
                # Удаляем связанные записи из таблицы snapshots
                query_snapshots = "DELETE FROM snapshots WHERE site_id = ?"
                conn.execute(query_snapshots, (site_id,))
                
                # Удаляем связанные записи из таблицы changes
                query_changes = "DELETE FROM changes WHERE site_id = ?"
                conn.execute(query_changes, (site_id,))
                
                # Удаляем связанные записи из таблицы events
                query_events = "DELETE FROM events WHERE site_id = ?"
                conn.execute(query_events, (site_id,))
                
                # Удаляем сайт
                query = "DELETE FROM sites WHERE id = ?"
                conn.execute(query, (site_id,))
                
                # Фиксируем транзакцию
                conn.commit()
                
                # Обновляем статус приложения
                sites_count = self.db_manager.get_row_count('sites')
                self.update_status(sites_count=sites_count)
                
                self.logger.info(f"Сайт успешно удален: {site.get('name')} (ID: {site_id})")
                return True
                
            except Exception as e:
                # Откатываем транзакцию в случае ошибки
                conn.rollback()
                raise
            
        except Exception as e:
            self.logger.error(f"Ошибка при удалении сайта ID={site_id}: {e}")
            log_exception(self.logger, "Ошибка удаления сайта")
            return False
    
    def get_groups(self):
        """
        Получение списка групп сайтов
        
        Returns:
            List[Dict[str, Any]]: Список групп
        """
        try:
            query = "SELECT * FROM groups ORDER BY name"
            return self.execute_db_query(query)
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка групп: {e}")
            log_exception(self.logger, "Ошибка получения списка групп")
            return []
    
    def get_all_groups(self):
        """
        Алиас для метода get_groups для совместимости с кодом,
        использующим данный метод
        
        Returns:
            List[Dict[str, Any]]: Список всех групп
        """
        return self.get_groups()
    
    def add_group(self, group_data):
        """
        Добавление новой группы сайтов
        
        Args:
            group_data: Данные группы
            
        Returns:
            int: ID добавленной группы или None в случае ошибки
        """
        try:
            # Валидация данных группы
            if not isinstance(group_data, dict):
                self.logger.error("Данные группы должны быть словарем")
                return None
                
            if 'name' not in group_data or not group_data['name']:
                self.logger.error("Имя группы является обязательным")
                return None
                
            # Проверка на дубликаты
            exists_query = "SELECT id FROM groups WHERE name = ?"
            exists = self.execute_db_query(exists_query, (group_data['name'],))
            if exists:
                self.logger.error(f"Группа с именем '{group_data['name']}' уже существует")
                return None
                
            # Начинаем транзакцию
            conn = self.db_manager._get_connection()
            
            try:
                # Формируем список полей и значений
                fields = ', '.join(group_data.keys())
                placeholders = ', '.join(['?' for _ in group_data])
                
                query = f"INSERT INTO groups ({fields}) VALUES ({placeholders})"
                
                # Выполняем запрос
                conn.execute(query, tuple(group_data.values()))
                
                # Получаем ID добавленной группы
                group_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                
                # Фиксируем транзакцию
                conn.commit()
                
                self.logger.info(f"Добавлена новая группа: {group_data['name']} (ID: {group_id})")
                return group_id
                
            except Exception as e:
                # Откатываем транзакцию в случае ошибки
                conn.rollback()
                raise
        
        except Exception as e:
            self.logger.error(f"Ошибка при добавлении группы: {e}")
            log_exception(self.logger, "Ошибка добавления группы")
            return None
    
    def update_group(self, group_id, group_data):
        """
        Обновление информации о группе
        
        Args:
            group_id: ID группы
            group_data: Новые данные группы
            
        Returns:
            bool: Результат обновления
        """
        try:
            # Валидация данных группы
            if not isinstance(group_data, dict):
                self.logger.error("Данные группы должны быть словарем")
                return False
                
            if 'name' in group_data and not group_data['name']:
                self.logger.error("Имя группы не может быть пустым")
                return False
                
            # Проверка на существование группы
            group = self.execute_db_query("SELECT * FROM groups WHERE id = ?", (group_id,), fetch_all=False)
            if not group:
                self.logger.error(f"Группа с ID={group_id} не найдена")
                return False
                
            # Проверка на дубликаты имени
            if 'name' in group_data:
                exists_query = "SELECT id FROM groups WHERE name = ? AND id != ?"
                exists = self.execute_db_query(exists_query, (group_data['name'], group_id))
                if exists:
                    self.logger.error(f"Группа с именем '{group_data['name']}' уже существует")
                    return False
                    
            # Начинаем транзакцию
            conn = self.db_manager._get_connection()
            
            try:
                # Формируем список полей и значений для обновления
                set_clause = ', '.join([f"{key} = ?" for key in group_data.keys()])
                
                query = f"UPDATE groups SET {set_clause} WHERE id = ?"
                
                # Добавляем ID группы в конец списка параметров
                params = list(group_data.values())
                params.append(group_id)
                
                # Выполняем запрос
                conn.execute(query, tuple(params))
                
                # Фиксируем транзакцию
                conn.commit()
                
                self.logger.info(f"Группа успешно обновлена: ID={group_id}")
                return True
                
            except Exception as e:
                # Откатываем транзакцию в случае ошибки
                conn.rollback()
                raise
        
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении группы ID={group_id}: {e}")
            log_exception(self.logger, "Ошибка обновления группы")
            return False
    
    def delete_group(self, group_id):
        """
        Удаление группы сайтов
        
        Args:
            group_id: ID группы
            
        Returns:
            bool: Результат удаления
        """
        try:
            # Проверка на существование группы
            group = self.execute_db_query("SELECT * FROM groups WHERE id = ?", (group_id,), fetch_all=False)
            if not group:
                self.logger.error(f"Группа с ID={group_id} не найдена")
                return False
                
            # Начинаем транзакцию
            conn = self.db_manager._get_connection()
            
            try:
                # Обновляем сайты, принадлежащие к данной группе
                update_sites_query = "UPDATE sites SET group_id = NULL WHERE group_id = ?"
                conn.execute(update_sites_query, (group_id,))
                
                # Удаляем группу
                delete_query = "DELETE FROM groups WHERE id = ?"
                conn.execute(delete_query, (group_id,))
                
                # Фиксируем транзакцию
                conn.commit()
                
                self.logger.info(f"Группа успешно удалена: {group.get('name')} (ID: {group_id})")
                return True
                
            except Exception as e:
                # Откатываем транзакцию в случае ошибки
                conn.rollback()
                raise
        
        except Exception as e:
            self.logger.error(f"Ошибка при удалении группы ID={group_id}: {e}")
            log_exception(self.logger, "Ошибка удаления группы")
            return False
    
    def get_changes(self, condition=None, params=None, limit=None, offset=None):
        """
        Получение списка изменений сайтов
        
        Args:
            condition: Условие WHERE (опционально)
            params: Параметры условия (опционально)
            limit: Ограничение количества результатов (опционально)
            offset: Смещение (опционально)
            
        Returns:
            List[Dict[str, Any]]: Список изменений
        """
        try:
            # Базовый запрос для получения изменений вместе с информацией о сайте
            query = """
            SELECT c.*, s.name as site_name, s.url as site_url 
            FROM changes c 
            JOIN sites s ON c.site_id = s.id
            """
            
            # Добавляем условие, если оно указано
            if condition:
                query += f" WHERE {condition}"
            
            # Добавляем сортировку
            query += " ORDER BY c.timestamp DESC"
            
            # Добавляем ограничение количества результатов, если оно указано
            if limit:
                query += f" LIMIT {limit}"
            
            # Добавляем смещение, если оно указано
            if offset:
                query += f" OFFSET {offset}"
            
            return self.execute_db_query(query, params)
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка изменений: {e}")
            log_exception(self.logger, "Ошибка получения списка изменений")
            return []
    
    def get_change(self, change_id):
        """
        Получение информации об изменении по ID
        
        Args:
            change_id: ID изменения
            
        Returns:
            Dict[str, Any]: Информация об изменении или None, если изменение не найдено
        """
        try:
            query = """
            SELECT c.*, s.name as site_name, s.url as site_url,
                   old.content_path as old_content_path, old.content_hash as old_content_hash, old.screenshot_path as old_screenshot_path,
                   new.content_path as new_content_path, new.content_hash as new_content_hash, new.screenshot_path as new_screenshot_path
            FROM changes c 
            JOIN sites s ON c.site_id = s.id
            LEFT JOIN snapshots old ON c.old_snapshot_id = old.id
            JOIN snapshots new ON c.new_snapshot_id = new.id
            WHERE c.id = ?
            """
            
            result = self.execute_db_query(query, (change_id,), fetch_all=False)
            
            # Если есть результат и есть данные о различиях в формате JSON, преобразуем их
            if result and result.get('diff_details'):
                try:
                    result['diff_details'] = json.loads(result['diff_details'])
                except json.JSONDecodeError:
                    pass
            
            return result
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении информации об изменении ID={change_id}: {e}")
            log_exception(self.logger, "Ошибка получения информации об изменении")
            return None
    
    def mark_change_as_read(self, change_id, user=None):
        """
        Отметка изменения как прочитанного
        
        Args:
            change_id: ID изменения
            user: Имя пользователя (опционально)
            
        Returns:
            bool: Результат обновления
        """
        try:
            query = """
            UPDATE changes 
            SET status = 'read', reviewed_at = CURRENT_TIMESTAMP, reviewed_by = ? 
            WHERE id = ?
            """
            
            self.execute_db_query(query, (user, change_id))
            
            # Обновляем счетчик непрочитанных изменений
            unread_count = self.db_manager.get_row_count('changes', "status = 'unread'")
            self.update_status(changed_sites_count=unread_count)
            
            return True
        
        except Exception as e:
            self.logger.error(f"Ошибка при отметке изменения ID={change_id} как прочитанного: {e}")
            log_exception(self.logger, "Ошибка отметки изменения как прочитанного")
            return False
    
    def get_snapshots(self, site_id, limit=None, offset=None):
        """
        Получение истории снимков сайта
        
        Args:
            site_id: ID сайта
            limit: Ограничение количества результатов (опционально)
            offset: Смещение (опционально)
            
        Returns:
            List[Dict[str, Any]]: Список снимков
        """
        try:
            query = """
            SELECT * FROM snapshots 
            WHERE site_id = ? 
            ORDER BY timestamp DESC
            """
            
            # Добавляем ограничение количества результатов, если оно указано
            if limit:
                query += f" LIMIT {limit}"
            
            # Добавляем смещение, если оно указано
            if offset:
                query += f" OFFSET {offset}"
            
            return self.execute_db_query(query, (site_id,))
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении истории снимков сайта ID={site_id}: {e}")
            log_exception(self.logger, "Ошибка получения истории снимков сайта")
            return []
    
    def get_snapshot(self, snapshot_id):
        """
        Получение информации о снимке по ID
        
        Args:
            snapshot_id: ID снимка
            
        Returns:
            Dict[str, Any]: Информация о снимке или None, если снимок не найден
        """
        try:
            query = "SELECT * FROM snapshots WHERE id = ?"
            return self.execute_db_query(query, (snapshot_id,), fetch_all=False)
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении информации о снимке ID={snapshot_id}: {e}")
            log_exception(self.logger, "Ошибка получения информации о снимке")
            return None
    
    def get_dashboard_data(self):
        """
        Получение данных для дашборда
        
        Returns:
            Dict[str, Any]: Данные для дашборда
        """
        try:
            # Получаем статус приложения
            status = self.get_status()
            
            # Получаем количество сайтов по статусам
            sites_by_status_query = """
            SELECT status, COUNT(*) as count 
            FROM sites 
            GROUP BY status
            """
            sites_by_status = self.execute_db_query(sites_by_status_query)
            
            # Получаем количество сайтов по группам
            sites_by_group_query = """
            SELECT g.name as group_name, COUNT(s.id) as count 
            FROM sites s 
            LEFT JOIN groups g ON s.group_id = g.id 
            GROUP BY s.group_id
            """
            sites_by_group = self.execute_db_query(sites_by_group_query)
            
            # Получаем последние изменения
            recent_changes_query = """
            SELECT c.id, c.timestamp, c.diff_percent, c.status,
                   s.id as site_id, s.name as site_name, s.url as site_url
            FROM changes c 
            JOIN sites s ON c.site_id = s.id
            ORDER BY c.timestamp DESC
            LIMIT 10
            """
            recent_changes = self.execute_db_query(recent_changes_query)
            
            # Получаем последние ошибки
            recent_errors_query = """
            SELECT id, site_id, timestamp, error_message 
            FROM snapshots 
            WHERE status = 'error' 
            ORDER BY timestamp DESC 
            LIMIT 10
            """
            recent_errors = self.execute_db_query(recent_errors_query)
            
            # Объединяем все данные
            dashboard_data = {
                'status': status,
                'sites_by_status': sites_by_status,
                'sites_by_group': sites_by_group,
                'recent_changes': recent_changes,
                'recent_errors': recent_errors
            }
            
            return dashboard_data
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении данных для дашборда: {e}")
            log_exception(self.logger, "Ошибка получения данных для дашборда")
            return {
                'status': self.get_status(),
                'error': str(e)
            }
    
    def initialize(self):
        """
        Инициализация приложения - проверка базы данных и готовности всех компонентов
        
        Returns:
            bool: True, если инициализация успешна
        """
        init_id = f"init_{int(time.time())}"
        self.logger.info(f"Начало инициализации приложения [{init_id}]")
        start_time = time.time()
        
        try:
            # Проверяем, создан ли менеджер базы данных
            if not self.db_manager:
                self.logger.error(f"Инициализация [{init_id}] остановлена: менеджер БД не создан")
                return False
                
            # Проверяем инициализацию базы данных
            if not self._initialize_database():
                execution_time = time.time() - start_time
                self.logger.error(f"Инициализация [{init_id}] не удалась: ошибка инициализации БД (время: {execution_time:.3f} сек)")
                return False
            
            execution_time = time.time() - start_time
            self.logger.info(f"Инициализация приложения [{init_id}] успешно завершена за {execution_time:.3f} сек")
            return True
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Критическая ошибка при инициализации приложения [{init_id}] (время: {execution_time:.3f} сек): {e}")
            log_exception(self.logger, f"Критическая ошибка инициализации [{init_id}]")
            
            # Обновляем статус приложения
            self.update_status(is_ready=False, errors=[str(e)])
            return False
    
    def check_for_updates(self) -> dict:
        """
        Проверяет наличие обновлений программы на сервере.
        
        Returns:
            dict: Информация об обновлении или пустой словарь, если обновлений нет
        """
        try:
            self.logger.debug("Проверка наличия обновлений")
            
            # Получаем текущую версию программы
            current_version = self.app_version
            
            # URL сервера обновлений (замените на фактический URL)
            update_server_url = self.config.get('update_server_url', 'https://example.com/updates/api/check')
            
            # Параметры запроса
            params = {
                'version': current_version,
                'platform': sys.platform,
                'app_id': 'wdm_v12'
            }
            
            # Получаем HTTP-клиент
            http_client = get_http_client()
            
            # Выполняем запрос к серверу обновлений
            response = http_client.get(
                url=update_server_url,
                params=params,
                timeout=10,
                retries=2
            )
            
            # Проверяем ответ
            if response.status_code == 200:
                update_info = response.json()
                
                # Проверяем, есть ли доступное обновление
                if update_info.get('update_available', False):
                    self.logger.info(f"Доступно обновление: {update_info.get('version')}")
                    return update_info
                else:
                    self.logger.debug("Обновлений не найдено")
                    return {}
            else:
                self.logger.warning(f"Ошибка при проверке обновлений. Код: {response.status_code}")
                return {}
                
        except Exception as e:
            self.logger.error(f"Ошибка при проверке обновлений: {e}")
            log_exception(self.logger, "Ошибка проверки обновлений")
            return {}
    
    def download_update(self, update_info: dict) -> bool:
        """
        Скачивает обновление программы.
        
        Args:
            update_info: Информация об обновлении
            
        Returns:
            bool: True, если обновление успешно скачано
        """
        try:
            self.logger.info(f"Начало загрузки обновления версии {update_info.get('version')}")
            
            # URL для скачивания обновления
            download_url = update_info.get('download_url')
            if not download_url:
                self.logger.error("URL для скачивания обновления не указан")
                return False
            
            # Путь для сохранения файла обновления
            update_dir = os.path.join(self.app_dir, 'updates')
            os.makedirs(update_dir, exist_ok=True)
            
            file_name = f"update_v{update_info.get('version')}.zip"
            download_path = os.path.join(update_dir, file_name)
            
            # Получаем HTTP-клиент
            http_client = get_http_client()
            
            # Скачиваем файл обновления
            success = http_client.download_file(
                url=download_url,
                destination=download_path,
                timeout=120,  # Увеличенный тайм-аут для скачивания
                retries=3
            )
            
            if success:
                self.logger.info(f"Обновление успешно скачано: {download_path}")
                
                # Сохраняем информацию об обновлении
                self.update_info = {
                    'version': update_info.get('version'),
                    'file_path': download_path,
                    'release_notes': update_info.get('release_notes'),
                    'download_time': time.time()
                }
                
                return True
            else:
                self.logger.error("Не удалось скачать обновление")
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка при скачивании обновления: {e}")
            log_exception(self.logger, "Ошибка загрузки обновления")
            return False 