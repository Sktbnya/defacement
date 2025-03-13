#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль настройки логирования для WDM_V12.
Настраивает систему логирования с выводом в файл и консоль.
Поддерживает разные уровни логирования для разных сред исполнения.
"""

import os
import logging
import logging.handlers
import sys
import json
from pathlib import Path
import colorlog

# Определение директории логов
from pathlib import Path
BASE_DIR = Path(__file__).parent.parent
LOGS_DIR = BASE_DIR / "logs"

# Форматы логов
FILE_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
CONSOLE_LOG_FORMAT = '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s%(reset)s'

# Цвета для уровней логирования
LOG_COLORS = {
    'DEBUG': 'cyan',
    'INFO': 'green',
    'WARNING': 'yellow',
    'ERROR': 'red',
    'CRITICAL': 'red,bg_white',
}

# Настройки логирования для разных сред
ENVIRONMENT_SETTINGS = {
    'development': {
        'log_level': 'DEBUG',
        'console_output': True,
        'file_output': True,
        'log_rotation': True,
        'max_file_size_mb': 10,
        'backup_count': 5,
        'detailed_tracebacks': True
    },
    'testing': {
        'log_level': 'INFO',
        'console_output': True,
        'file_output': True,
        'log_rotation': True,
        'max_file_size_mb': 5,
        'backup_count': 3,
        'detailed_tracebacks': True
    },
    'production': {
        'log_level': 'WARNING',
        'console_output': False,
        'file_output': True,
        'log_rotation': True,
        'max_file_size_mb': 20,
        'backup_count': 10,
        'detailed_tracebacks': False
    }
}

# Текущая среда исполнения (по умолчанию - development)
CURRENT_ENVIRONMENT = os.environ.get('WDM_ENVIRONMENT', 'development')


def get_environment_settings():
    """
    Получение настроек логирования для текущей среды
    
    Returns:
        dict: Настройки логирования
    """
    # Проверяем наличие файла с настройками
    settings_file = BASE_DIR / "config" / "logging_settings.json"
    
    if settings_file.exists():
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                custom_settings = json.load(f)
                
            if CURRENT_ENVIRONMENT in custom_settings:
                return custom_settings[CURRENT_ENVIRONMENT]
        except Exception as e:
            print(f"Ошибка при чтении настроек логирования: {e}")
    
    # Если файла нет или произошла ошибка, используем стандартные настройки
    return ENVIRONMENT_SETTINGS.get(CURRENT_ENVIRONMENT, ENVIRONMENT_SETTINGS['development'])


def setup_logger(log_level=None, console_output=None, environment=None):
    """
    Настраивает логирование с указанным уровнем и опциями в зависимости от среды
    
    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        console_output: Флаг вывода логов в консоль
        environment: Среда исполнения (development, testing, production)
    """
    # Если директория логов не существует, создаем её
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR)
    
    # Определяем текущую среду и её настройки
    global CURRENT_ENVIRONMENT
    if environment:
        CURRENT_ENVIRONMENT = environment
        
    settings = get_environment_settings()
    
    # Используем параметры из настроек, если не указаны явно
    if log_level is None:
        log_level = settings['log_level']
    if console_output is None:
        console_output = settings['console_output']
    
    # Преобразуем строковый уровень логирования в константу
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    
    # Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Очищаем существующие обработчики
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    
    # Настройка обработчика для записи в файл
    if settings['file_output']:
        log_file = os.path.join(LOGS_DIR, "wdm_v12.log")
        
        if settings['log_rotation']:
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=settings['max_file_size_mb'] * 1024 * 1024,
                backupCount=settings['backup_count'],
                encoding='utf-8'
            )
        else:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
        
        file_formatter = logging.Formatter(FILE_LOG_FORMAT)
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(numeric_level)
        root_logger.addHandler(file_handler)
    
    # Настройка обработчика для вывода в консоль
    if console_output:
        console_handler = logging.StreamHandler()
        console_formatter = colorlog.ColoredFormatter(
            CONSOLE_LOG_FORMAT,
            log_colors=LOG_COLORS
        )
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(numeric_level)
        root_logger.addHandler(console_handler)
    
    # Установка перехватчика необработанных исключений
    sys.excepthook = handle_uncaught_exception
    
    # Создаем логгер для этого модуля
    logger = logging.getLogger(__name__)
    logger.debug(f"Логирование настроено для среды {CURRENT_ENVIRONMENT} с уровнем {log_level}")
    
    return root_logger


# Функция для создания логгера для конкретного модуля
def get_module_logger(module_name):
    """
    Возвращает логгер для указанного модуля
    
    Args:
        module_name: Имя модуля
        
    Returns:
        logging.Logger: Настроенный объект логгера
    """
    return logging.getLogger(f'wdm.{module_name}')


# Функция для логирования исключений
def log_exception(logger, message="Перехвачено исключение", exc_info=None):
    """
    Логирует информацию об исключении
    
    Args:
        logger: Объект логгера
        message: Сообщение для логирования
        exc_info: Информация об исключении (по умолчанию sys.exc_info())
    """
    if exc_info is None:
        exc_info = sys.exc_info()
    
    logger.error(f"{message}: {exc_info[1]}", exc_info=exc_info)


# Устанавливаем перехватчик неперехваченных исключений
def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
    """Обработчик неперехваченных исключений"""
    if issubclass(exc_type, KeyboardInterrupt):
        # Не перехватываем нажатие Ctrl+C
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logger = logging.getLogger('wdm')
    logger.critical("Неперехваченное исключение", 
                   exc_info=(exc_type, exc_value, exc_traceback))


# Устанавливаем перехватчик
sys.excepthook = handle_uncaught_exception 