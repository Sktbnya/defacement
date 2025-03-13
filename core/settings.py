#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль настроек для WDM_V12.
Отвечает за хранение, загрузку и сохранение настроек приложения.
"""

import os
import json
import logging
import datetime
import threading
from typing import Dict, Any, Optional

from utils.logger import get_module_logger, log_exception
from database.db_manager import DBManager


class Settings:
    """
    Класс для управления настройками приложения.
    Реализует шаблон Singleton для обеспечения единой точки доступа к настройкам.
    """
    
    # Единственный экземпляр класса (шаблон Singleton)
    _instance = None
    
    # Блокировка для обеспечения потокобезопасности
    _lock = threading.RLock()
    
    # Имя файла настроек по умолчанию
    DEFAULT_SETTINGS_FILE = "settings.json"
    
    def __new__(cls, settings_file=None):
        """Реализация шаблона Singleton"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Settings, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self, settings_file=None):
        """
        Инициализация объекта настроек
        
        Args:
            settings_file: Путь к файлу настроек (опционально)
        """
        with self._lock:
            if self._initialized:
                return
            
            self.logger = get_module_logger('core.settings')
            self.logger.debug("Инициализация менеджера настроек")
            
            # Устанавливаем файл настроек
            self.settings_file = settings_file or self.DEFAULT_SETTINGS_FILE
            
            # Настройки по умолчанию
            self._default_settings = {
                # Общие настройки приложения
                'app': {
                    'title': 'WDM v12 - Система мониторинга веб-сайтов',
                    'version': '12.0.0',
                    'auto_start_monitoring': False,
                    'check_for_updates': True,
                    'language': 'ru',
                    'theme': 'system',  # system, light, dark
                    'backup_dir': 'backups',
                    'max_backups': 10,
                    'last_backup': None
                },
                
                # Настройки мониторинга
                'monitoring': {
                    'enabled': True,
                    'check_interval': 3600,  # в секундах
                    'parallel_checks': 5,     # количество параллельных проверок
                    'retry_count': 3,         # количество попыток проверки при ошибке
                    'retry_delay': 60,        # задержка между попытками в секундах
                    'use_browser': True,      # использовать браузер для динамического контента
                    'timeout': 30,            # таймаут загрузки страницы в секундах
                    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'browser_wait': 5,        # время ожидания загрузки страницы в браузере (сек)
                    'browser_args': [
                        '--headless',
                        '--disable-gpu',
                        '--no-sandbox',
                        '--disable-dev-shm-usage'
                    ]
                },
                
                # Настройки БД
                'database': {
                    'path': 'data/wdm_database.db',
                    'backup_on_start': True,
                    'backup_on_exit': True,
                    'auto_vacuum': True
                },
                
                # Настройки уведомлений
                'notifications': {
                    'enabled': True,
                    'desktop_notifications': True,
                    'email_notifications': False,
                    'email_settings': {
                        'smtp_server': '',
                        'smtp_port': 587,
                        'smtp_username': '',
                        'smtp_password': '',
                        'from_address': '',
                        'to_address': ''
                    },
                    'notification_threshold': 5.0,  # Минимальный процент изменений для уведомления
                    'cooldown_period': 3600,       # Период охлаждения между уведомлениями (в секундах)
                },
                
                # Настройки прокси
                'proxy': {
                    'enabled': False,
                    'type': 'http',  # http, socks5
                    'host': '',
                    'port': 8080,
                    'username': '',
                    'password': ''
                },
                
                # Настройки логирования
                'logging': {
                    'level': 'INFO',  # DEBUG, INFO, WARNING, ERROR, CRITICAL
                    'max_file_size': 10485760,  # 10 MB
                    'max_files': 5,
                    'log_to_console': True
                }
            }
            
            # Текущие настройки приложения
            self._settings = {}
            
            # Загружаем настройки из файла или используем настройки по умолчанию
            self.load_settings()
            
            # Флаг инициализации
            self._initialized = True
            
            self.logger.debug("Менеджер настроек инициализирован")
    
    def get(self, section, key=None, default=None):
        """
        Получение значения настройки
        
        Args:
            section: Раздел настроек
            key: Ключ настройки (если None, возвращается весь раздел)
            default: Значение по умолчанию, если настройка не найдена
            
        Returns:
            Any: Значение настройки или раздел целиком
        """
        with self._lock:
            try:
                if section not in self._settings:
                    if section in self._default_settings:
                        return self._default_settings[section] if key is None else \
                               self._default_settings[section].get(key, default)
                    return default if key is None else default
                
                if key is None:
                    return self._settings[section]
                
                return self._settings[section].get(key, default)
            
            except Exception as e:
                self.logger.error(f"Ошибка при получении настройки {section}.{key}: {e}")
                return default
    
    def set(self, section, key, value):
        """
        Установка значения настройки
        
        Args:
            section: Раздел настроек
            key: Ключ настройки
            value: Значение настройки
            
        Returns:
            bool: Результат установки
        """
        with self._lock:
            try:
                if section not in self._settings:
                    self._settings[section] = {}
                
                self._settings[section][key] = value
                return True
            
            except Exception as e:
                self.logger.error(f"Ошибка при установке настройки {section}.{key}: {e}")
                return False
    
    def update_section(self, section, values):
        """
        Обновление раздела настроек
        
        Args:
            section: Раздел настроек
            values: Словарь с новыми значениями
            
        Returns:
            bool: Результат обновления
        """
        with self._lock:
            try:
                if section not in self._settings:
                    self._settings[section] = {}
                
                self._settings[section].update(values)
                return True
            
            except Exception as e:
                self.logger.error(f"Ошибка при обновлении раздела настроек {section}: {e}")
                return False
    
    def load_settings(self):
        """
        Загрузка настроек из файла и базы данных
        
        Returns:
            bool: Результат загрузки
        """
        with self._lock:
            try:
                # Проверяем, существует ли файл настроек
                if not os.path.isfile(self.settings_file):
                    self.logger.warning(f"Файл настроек {self.settings_file} не найден, используются настройки по умолчанию")
                    self._settings = self._default_settings.copy()
                else:
                    # Открываем файл и загружаем настройки
                    with open(self.settings_file, 'r', encoding='utf-8') as f:
                        loaded_settings = json.load(f)
                    
                    # Проверяем и дополняем отсутствующие настройки значениями по умолчанию
                    self._settings = self._merge_settings(self._default_settings, loaded_settings)
                
                # Загружаем настройки из базы данных
                self.load_from_db()
                
                self.logger.info("Настройки успешно загружены")
                return True
            
            except Exception as e:
                self.logger.error(f"Ошибка при загрузке настроек: {e}")
                log_exception(self.logger, "Ошибка загрузки настроек")
                return False
    
    def save_settings(self):
        """
        Сохранение настроек в файл и базу данных
        
        Returns:
            bool: Результат сохранения
        """
        with self._lock:
            try:
                # Создаем директорию для файла настроек, если она не существует
                settings_dir = os.path.dirname(self.settings_file)
                if settings_dir and not os.path.exists(settings_dir):
                    os.makedirs(settings_dir)
                
                # Сохраняем настройки в файл
                with open(self.settings_file, 'w', encoding='utf-8') as f:
                    json.dump(self._settings, f, indent=4, ensure_ascii=False)
                
                # Сохраняем настройки в базу данных
                self.save_to_db()
                
                self.logger.info("Настройки успешно сохранены")
                return True
            
            except Exception as e:
                self.logger.error(f"Ошибка при сохранении настроек: {e}")
                log_exception(self.logger, "Ошибка сохранения настроек")
                return False
    
    def reset_to_defaults(self):
        """
        Сброс настроек к значениям по умолчанию
        
        Returns:
            bool: Результат сброса
        """
        with self._lock:
            try:
                self._settings = self._default_settings.copy()
                self.logger.info("Настройки сброшены к значениям по умолчанию")
                return True
            
            except Exception as e:
                self.logger.error(f"Ошибка при сбросе настроек: {e}")
                return False
    
    def create_backup(self):
        """
        Создание резервной копии файла настроек
        
        Returns:
            str: Путь к файлу резервной копии или None в случае ошибки
        """
        with self._lock:
            try:
                # Проверяем, существует ли файл настроек
                if not os.path.isfile(self.settings_file):
                    self.logger.warning(f"Файл настроек {self.settings_file} не найден, резервная копия не создана")
                    return None
                
                # Формируем имя файла резервной копии
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_dir = self.get('app', 'backup_dir', 'backups')
                
                # Создаем директорию для резервных копий, если она не существует
                if not os.path.exists(backup_dir):
                    os.makedirs(backup_dir)
                
                # Формируем путь к файлу резервной копии
                backup_file = os.path.join(backup_dir, f"settings_{timestamp}.json")
                
                # Копируем файл настроек
                with open(self.settings_file, 'r', encoding='utf-8') as src, \
                     open(backup_file, 'w', encoding='utf-8') as dst:
                    dst.write(src.read())
                
                # Обновляем информацию о последней резервной копии
                self.set('app', 'last_backup', datetime.datetime.now().isoformat())
                
                # Проверяем и удаляем старые резервные копии
                self._cleanup_backups()
                
                self.logger.info(f"Резервная копия настроек создана: {backup_file}")
                return backup_file
            
            except Exception as e:
                self.logger.error(f"Ошибка при создании резервной копии настроек: {e}")
                log_exception(self.logger, "Ошибка создания резервной копии настроек")
                return None
    
    def _cleanup_backups(self):
        """
        Удаление старых резервных копий
        """
        try:
            backup_dir = self.get('app', 'backup_dir', 'backups')
            max_backups = self.get('app', 'max_backups', 10)
            
            # Проверяем, существует ли директория резервных копий
            if not os.path.exists(backup_dir):
                return
            
            # Получаем список файлов резервных копий
            backup_files = [os.path.join(backup_dir, f) for f in os.listdir(backup_dir) 
                           if f.startswith("settings_") and f.endswith(".json")]
            
            # Сортируем файлы по времени изменения (от старых к новым)
            backup_files.sort(key=lambda x: os.path.getmtime(x))
            
            # Удаляем старые резервные копии, если их больше максимального количества
            if len(backup_files) > max_backups:
                for file_to_remove in backup_files[:-max_backups]:
                    os.remove(file_to_remove)
                    self.logger.debug(f"Удалена старая резервная копия: {file_to_remove}")
        
        except Exception as e:
            self.logger.error(f"Ошибка при очистке старых резервных копий: {e}")
    
    def restore_from_backup(self, backup_file):
        """
        Восстановление настроек из резервной копии
        
        Args:
            backup_file: Путь к файлу резервной копии
            
        Returns:
            bool: Результат восстановления
        """
        with self._lock:
            try:
                # Проверяем, существует ли файл резервной копии
                if not os.path.isfile(backup_file):
                    self.logger.error(f"Файл резервной копии {backup_file} не найден")
                    return False
                
                # Загружаем настройки из резервной копии
                with open(backup_file, 'r', encoding='utf-8') as f:
                    backup_settings = json.load(f)
                
                # Проверяем и дополняем отсутствующие настройки значениями по умолчанию
                self._settings = self._merge_settings(self._default_settings, backup_settings)
                
                # Сохраняем восстановленные настройки
                self.save_settings()
                
                self.logger.info(f"Настройки успешно восстановлены из резервной копии {backup_file}")
                return True
            
            except json.JSONDecodeError as e:
                self.logger.error(f"Ошибка формата JSON в файле резервной копии {backup_file}: {e}")
                return False
            
            except Exception as e:
                self.logger.error(f"Ошибка при восстановлении настроек из резервной копии {backup_file}: {e}")
                log_exception(self.logger, "Ошибка восстановления настроек")
                return False
    
    def _merge_settings(self, default_settings, user_settings):
        """
        Объединение настроек по умолчанию и пользовательских настроек
        
        Args:
            default_settings: Настройки по умолчанию
            user_settings: Пользовательские настройки
            
        Returns:
            dict: Объединенные настройки
        """
        result = default_settings.copy()
        
        for section, values in user_settings.items():
            if section in result and isinstance(result[section], dict) and isinstance(values, dict):
                # Рекурсивно объединяем вложенные словари
                result[section] = self._merge_settings(result[section], values)
            else:
                # Заменяем значение целиком
                result[section] = values
        
        return result
    
    def get_settings(self):
        """
        Получение всех настроек приложения
        
        Returns:
            Dict[str, Any]: Словарь со всеми настройками
        """
        with self._lock:
            return self._settings.copy()
    
    def save_to_db(self):
        """
        Сохранение настроек в базу данных
        
        Returns:
            bool: Результат сохранения
        """
        with self._lock:
            try:
                # Получаем соединение с базой данных
                db_manager = DBManager()
                
                # Сначала удаляем все старые настройки
                db_manager.execute_query("DELETE FROM settings")
                
                # Сохраняем каждую настройку
                for section, settings in self._settings.items():
                    for key, value in settings.items():
                        db_key = f"{section}.{key}"
                        db_value = json.dumps(value) if value is not None else ''
                        
                        # Добавляем новую настройку
                        query = """
                        INSERT INTO settings (key, value, updated_at) 
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                        """
                        db_manager.execute_query(query, (db_key, db_value))
                
                self.logger.info("Настройки успешно сохранены в базу данных")
                return True
            
            except Exception as e:
                self.logger.error(f"Ошибка при сохранении настроек в базу данных: {e}")
                log_exception(self.logger, "Ошибка сохранения настроек в базу данных")
                return False
    
    def load_from_db(self):
        """
        Загрузка настроек из базы данных
        
        Returns:
            bool: Результат загрузки
        """
        with self._lock:
            try:
                # Получаем соединение с базой данных
                db_manager = DBManager()
                
                # Получаем все настройки
                settings = db_manager.get_all_settings()
                
                # Преобразуем настройки в словарь
                for key, value in settings.items():
                    try:
                        # Разбиваем ключ на секцию и имя
                        section, name = key.split('.', 1)
                        
                        # Создаем секцию, если её нет
                        if section not in self._settings:
                            self._settings[section] = {}
                        
                        # Преобразуем значение из JSON
                        try:
                            self._settings[section][name] = json.loads(value)
                        except json.JSONDecodeError:
                            # Если не удалось преобразовать как JSON, используем как есть
                            self._settings[section][name] = value
                    except ValueError:
                        # Если ключ не содержит точку, пропускаем его
                        continue
                
                self.logger.info("Настройки успешно загружены из базы данных")
                return True
            
            except Exception as e:
                self.logger.error(f"Ошибка при загрузке настроек из базы данных: {e}")
                log_exception(self.logger, "Ошибка загрузки настроек из базы данных")
                return False 