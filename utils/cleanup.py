#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Утилита для очистки старых логов и временных файлов
"""

import os
import time
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
import shutil

from utils.logger import get_module_logger
from config.config import get_config


class CleanupManager:
    """Менеджер очистки старых файлов"""
    
    def __init__(self):
        """Инициализация менеджера очистки"""
        self.logger = get_module_logger('utils.cleanup')
        self.config = get_config()
        
        # Загружаем настройки
        self.log_dir = 'logs'
        self.max_log_age = self.config.get('logging', {}).get('max_age_days', 30)
        self.max_log_files = self.config.get('logging', {}).get('max_files', 5)
        
    def cleanup_logs(self):
        """
        Очистка старых лог-файлов
        
        Returns:
            int: Количество удаленных файлов
        """
        try:
            self.logger.info("Начало очистки старых лог-файлов")
            deleted_count = 0
            
            # Проверяем существование директории
            if not os.path.exists(self.log_dir):
                self.logger.warning(f"Директория логов не найдена: {self.log_dir}")
                return 0
            
            # Получаем список лог-файлов
            log_files = []
            for file in Path(self.log_dir).glob('*.log*'):
                if file.is_file():
                    log_files.append({
                        'path': file,
                        'mtime': file.stat().st_mtime,
                        'size': file.stat().st_size
                    })
            
            if not log_files:
                self.logger.info("Лог-файлы не найдены")
                return 0
            
            # Сортируем файлы по времени изменения
            log_files.sort(key=lambda x: x['mtime'], reverse=True)
            
            # Удаляем старые файлы
            current_time = time.time()
            for idx, file_info in enumerate(log_files):
                try:
                    # Проверяем возраст файла
                    file_age_days = (current_time - file_info['mtime']) / (24 * 3600)
                    
                    # Удаляем если файл старый или превышен лимит
                    if idx >= self.max_log_files or file_age_days > self.max_log_age:
                        file_info['path'].unlink()
                        deleted_count += 1
                        self.logger.debug(f"Удален старый лог-файл: {file_info['path']}")
                
                except Exception as e:
                    self.logger.error(f"Ошибка при удалении файла {file_info['path']}: {e}")
            
            self.logger.info(f"Очистка завершена. Удалено файлов: {deleted_count}")
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Ошибка при очистке лог-файлов: {e}")
            return 0
    
    def cleanup_temp_files(self, temp_dir='temp', max_age_hours=24):
        """
        Очистка временных файлов
        
        Args:
            temp_dir: Директория с временными файлами
            max_age_hours: Максимальный возраст файлов в часах
            
        Returns:
            int: Количество удаленных файлов
        """
        try:
            self.logger.info("Начало очистки временных файлов")
            deleted_count = 0
            
            # Проверяем существование директории
            if not os.path.exists(temp_dir):
                self.logger.warning(f"Директория не найдена: {temp_dir}")
                return 0
            
            # Получаем список файлов
            current_time = time.time()
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    try:
                        file_path = os.path.join(root, file)
                        file_mtime = os.path.getmtime(file_path)
                        
                        # Проверяем возраст файла
                        file_age_hours = (current_time - file_mtime) / 3600
                        
                        if file_age_hours > max_age_hours:
                            os.remove(file_path)
                            deleted_count += 1
                            self.logger.debug(f"Удален временный файл: {file_path}")
                    
                    except Exception as e:
                        self.logger.error(f"Ошибка при удалении файла {file}: {e}")
            
            # Удаляем пустые директории
            for root, dirs, files in os.walk(temp_dir, topdown=False):
                for dir_name in dirs:
                    try:
                        dir_path = os.path.join(root, dir_name)
                        if not os.listdir(dir_path):
                            os.rmdir(dir_path)
                            self.logger.debug(f"Удалена пустая директория: {dir_path}")
                    except Exception as e:
                        self.logger.error(f"Ошибка при удалении директории {dir_name}: {e}")
            
            self.logger.info(f"Очистка завершена. Удалено файлов: {deleted_count}")
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Ошибка при очистке временных файлов: {e}")
            return 0
    
    def run_cleanup(self):
        """
        Запуск полной очистки
        
        Returns:
            dict: Результаты очистки
        """
        results = {
            'logs_deleted': 0,
            'temp_deleted': 0
        }
        
        # Очистка логов
        results['logs_deleted'] = self.cleanup_logs()
        
        # Очистка временных файлов
        results['temp_deleted'] = self.cleanup_temp_files()
        
        return results


if __name__ == '__main__':
    # Создаем и запускаем менеджер очистки
    cleanup_manager = CleanupManager()
    results = cleanup_manager.run_cleanup()
    
    print("Очистка завершена:")
    print(f"- Удалено лог-файлов: {results['logs_deleted']}")
    print(f"- Удалено временных файлов: {results['temp_deleted']}") 