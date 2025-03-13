#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль общих утилитарных функций для WDM_V12.
"""

import datetime
from typing import Optional, Union, Tuple, Any, Dict
from functools import wraps
import logging
from PyQt6.QtGui import QColor

from utils.logger import get_module_logger, log_exception

# Константы для цветов
UI_COLORS = {
    'error': QColor(255, 0, 0),        # Красный
    'warning': QColor(255, 165, 0),    # Оранжевый
    'notice': QColor(255, 215, 0),     # Желтый
    'success': QColor(0, 128, 0),      # Зеленый
    'info': QColor(0, 0, 255),         # Синий
    'default': QColor(0, 0, 0)         # Черный
}

# Константы для статусов
STATUS_COLORS = {
    'unread': UI_COLORS['error'],
    'read': UI_COLORS['success'],
    'active': UI_COLORS['success'],
    'inactive': UI_COLORS['error'],
    'paused': UI_COLORS['warning']
}

def format_timestamp(timestamp: Union[str, datetime.datetime, None], 
                    format_str: str = "%d.%m.%Y %H:%M:%S") -> str:
    """
    Форматирование временной метки в строку
    
    Args:
        timestamp: Временная метка (строка, datetime или None)
        format_str: Строка формата для datetime.strftime
        
    Returns:
        str: Отформатированная строка с датой/временем
    """
    try:
        if isinstance(timestamp, str):
            try:
                dt = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return dt.strftime(format_str)
            except (ValueError, TypeError):
                return timestamp
        elif isinstance(timestamp, datetime.datetime):
            return timestamp.strftime(format_str)
        else:
            return str(timestamp) if timestamp is not None else ""
    except Exception as e:
        logger = get_module_logger('utils.common')
        logger.error(f"Ошибка при форматировании временной метки: {e}")
        return str(timestamp) if timestamp is not None else ""

def get_diff_color(diff_percent: float) -> QColor:
    """
    Получение цвета в зависимости от процента изменений
    
    Args:
        diff_percent: Процент изменений
        
    Returns:
        QColor: Цвет для отображения
    """
    if diff_percent > 50:
        return UI_COLORS['error']
    elif diff_percent > 20:
        return UI_COLORS['warning']
    elif diff_percent > 5:
        return UI_COLORS['notice']
    else:
        return UI_COLORS['success']

def get_status_color(status: str) -> QColor:
    """
    Получение цвета для статуса
    
    Args:
        status: Статус
        
    Returns:
        QColor: Цвет для отображения
    """
    return STATUS_COLORS.get(status, UI_COLORS['default'])

def handle_errors(logger: Optional[logging.Logger] = None, 
                 error_msg: str = "Произошла ошибка",
                 return_value: Any = None):
    """
    Декоратор для обработки ошибок
    
    Args:
        logger: Логгер для записи ошибок
        error_msg: Сообщение об ошибке
        return_value: Значение для возврата в случае ошибки
        
    Returns:
        Callable: Декорированная функция
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal logger
            if logger is None:
                logger = get_module_logger('utils.common')
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"{error_msg}: {e}")
                log_exception(logger, error_msg)
                return return_value
        return wrapper
    return decorator

def validate_data(data: Dict[str, Any], required_fields: list) -> Tuple[bool, str]:
    """
    Валидация данных на наличие обязательных полей
    
    Args:
        data: Словарь с данными
        required_fields: Список обязательных полей
        
    Returns:
        tuple: (bool, str) - результат валидации и сообщение об ошибке
    """
    if not isinstance(data, dict):
        return False, "Данные должны быть словарем"
        
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return False, f"Отсутствуют обязательные поля: {', '.join(missing_fields)}"
        
    return True, "" 