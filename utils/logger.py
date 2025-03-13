#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль настройки логирования для WDM_V12.
Настраивает систему логирования с выводом в файл и консоль.
"""

import os
import logging
import logging.handlers
import sys
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


def setup_logger(log_level=None, console_output=True):
    """
    Настраивает логирование с указанным уровнем и опцией вывода в консоль
    
    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        console_output: Флаг вывода логов в консоль
    """
    # Если директория логов не существует, создаем её
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR)
        
    # Получаем уровень логирования из конфигурации
    if log_level is None:
        try:
            # Импорт конфигурации здесь, чтобы избежать циклического импорта
            from config.config import get_config
            config = get_config()
            log_level = config['logging']['level']
            console_output = config['logging']['console_output']
            max_file_size = config['logging']['max_file_size_mb'] * 1024 * 1024  # в байтах
            backup_count = config['logging']['backup_count']
        except (ImportError, KeyError):
            log_level = 'INFO'
            console_output = True
            max_file_size = 10 * 1024 * 1024  # 10 МБ
            backup_count = 5
    
    # Преобразуем строковый уровень в константу logging
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Настраиваем корневой логгер
    root_logger = logging.getLogger('wdm')
    root_logger.setLevel(numeric_level)
    
    # Удаляем существующие обработчики, если они есть
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Создаем форматтер для файла
    file_formatter = logging.Formatter(FILE_LOG_FORMAT)
    
    # Создаем обработчик для файла с ротацией
    log_file = os.path.join(LOGS_DIR, 'wdm.log')
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=max_file_size, backupCount=backup_count, encoding='utf-8'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # Если нужен вывод в консоль, добавляем соответствующий обработчик
    if console_output:
        # Создаем цветной форматтер для консоли
        console_formatter = colorlog.ColoredFormatter(
            CONSOLE_LOG_FORMAT,
            log_colors=LOG_COLORS
        )
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # Логируем информацию о начале логирования
    root_logger.debug(f"Логирование настроено. Уровень: {log_level}, "
                     f"файл: {log_file}, вывод в консоль: {console_output}")
    
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