#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Скрипт для очистки базы данных - удаляет все сайты и связанные данные,
сохраняя структуру БД и основные настройки.
"""

import os
import sys
import logging
import sqlite3
import time

# Настраиваем пути для импортов
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Импорты модулей приложения
from core.app_context import AppContext
from utils.logger import setup_logger


def clean_database(app_context):
    """
    Очистка базы данных от сайтов и связанных данных
    
    Args:
        app_context: Контекст приложения
    
    Returns:
        bool: Результат очистки
    """
    logger = logging.getLogger('wdm.clean_db')
    logger.info("Начало очистки базы данных")
    
    # Получаем соединение с базой данных
    try:
        connection = app_context.db_manager._get_connection()
        cursor = connection.cursor()
        
        # Начинаем транзакцию
        connection.execute("BEGIN TRANSACTION")
        
        # Получаем список таблиц для очистки (в правильном порядке из-за внешних ключей)
        tables_to_clean = [
            'changes',
            'snapshots',
            'events',
            'sites'
        ]
        
        # Очищаем каждую таблицу
        for table in tables_to_clean:
            try:
                query = f"DELETE FROM {table}"
                cursor.execute(query)
                deleted_count = cursor.rowcount
                logger.info(f"Удалено {deleted_count} записей из таблицы {table}")
            except Exception as e:
                logger.error(f"Ошибка при очистке таблицы {table}: {e}")
                connection.execute("ROLLBACK")
                return False
        
        # Сбрасываем автоинкремент для таблицы sites
        try:
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='sites'")
            logger.info("Сброшен автоинкремент для таблицы sites")
        except Exception as e:
            logger.warning(f"Не удалось сбросить автоинкремент: {e}")
        
        # Фиксируем транзакцию
        connection.execute("COMMIT")
        
        # Выполняем VACUUM для оптимизации базы данных
        try:
            cursor.execute("VACUUM")
            logger.info("База данных оптимизирована (VACUUM)")
        except Exception as e:
            logger.warning(f"Не удалось выполнить VACUUM: {e}")
        
        logger.info("База данных успешно очищена")
        return True
    
    except Exception as e:
        logger.error(f"Критическая ошибка при очистке базы данных: {e}")
        # Если транзакция была начата, откатываем её
        try:
            connection.execute("ROLLBACK")
        except:
            pass
        return False


if __name__ == "__main__":
    # Инициализируем логирование
    setup_logger()
    logger = logging.getLogger('wdm')
    logger.info("Запуск скрипта очистки базы данных")
    
    try:
        # Инициализируем контекст приложения
        app_context = AppContext()
        
        # Проверяем, инициализирован ли контекст
        if not app_context._initialized:
            logger.error("Не удалось инициализировать контекст приложения")
            sys.exit(1)
        
        # Инициализируем приложение
        if not app_context.initialize():
            logger.error("Инициализация приложения завершилась с ошибкой")
            sys.exit(1)
        
        # Очищаем базу данных
        result = clean_database(app_context)
        
        if result:
            logger.info("Очистка базы данных завершена успешно")
            sys.exit(0)
        else:
            logger.error("Очистка базы данных завершена с ошибками")
            sys.exit(1)
    
    except Exception as e:
        logger.critical(f"Критическая ошибка при выполнении скрипта: {e}")
        import traceback
        logger.critical(f"Стек вызовов:\n{traceback.format_exc()}")
        sys.exit(1) 