#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
WDM_V12 - Web Data Monitor, версия 12.
Система мониторинга веб-сайтов с возможностью отслеживания изменений,
генерации отчетов и интерактивного пользовательского интерфейса.
"""

import sys
import os
import logging
from PyQt6.QtWidgets import QApplication

# Настраиваем пути для импортов
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Импорты модулей приложения
from ui.main_window import MainWindow
from core.app_context import AppContext
from utils.logger import setup_logger


def main():
    """
    Главная функция запуска приложения
    """
    # Инициализируем логирование
    try:
        setup_logger()
        logger = logging.getLogger('wdm')
        logger.info("Запуск WDM_V12")
    except Exception as log_error:
        print(f"Критическая ошибка при инициализации логирования: {log_error}")
        return 1

    try:
        # Проверяем наличие необходимых директорий
        required_dirs = ['data', 'logs', 'config', 'screenshots', 'backups']
        for directory in required_dirs:
            os.makedirs(directory, exist_ok=True)
            logger.debug(f"Проверена директория: {directory}")
        
        # Проверяем доступность файла конфигурации
        config_file = os.path.join('config', 'settings.json')
        if not os.path.exists(config_file):
            logger.warning(f"Файл конфигурации {config_file} не найден, будут использованы настройки по умолчанию")
        
        # Инициализируем контекст приложения
        logger.info("Инициализация контекста приложения")
        app_context = AppContext()
        
        if not app_context._initialized:
            logger.error("Не удалось инициализировать контекст приложения")
            return 1
            
        init_result = app_context.initialize()
        if not init_result:
            logger.error("Инициализация приложения завершилась с ошибкой")
            return 1
        
        # Инициализируем приложение PyQt
        logger.info("Инициализация GUI")
        app = QApplication(sys.argv)
        app.setApplicationName("Web Data Monitor V12")
        
        # Создаем и показываем главное окно
        main_window = MainWindow(app_context)
        main_window.show()
        
        # Запускаем цикл событий приложения
        logger.info("Запуск главного цикла приложения")
        return app.exec()
    
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске приложения: {e}")
        # Добавляем полный стек вызовов
        import traceback
        logger.critical(f"Стек вызовов:\n{traceback.format_exc()}")
        return 1


if __name__ == "__main__":
    sys.exit(main()) 