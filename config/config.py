#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль конфигурации для WDM_V12.
Содержит настройки по умолчанию и функции для загрузки/сохранения конфигурации.
"""

import os
import json
import logging
from pathlib import Path
import time
import shutil

# Базовые директории
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
REPORTS_DIR = BASE_DIR / "reports_output"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
TEMPLATES_DIR = BASE_DIR / "resources" / "templates"

# Настройки по умолчанию
DEFAULT_CONFIG = {
    "database": {
        "path": str(DATA_DIR / "wdm_database.db"),
        "backup_dir": str(DATA_DIR / "backups"),
        "backup_interval_days": 7,
        "retention_days": 90,
        "backup_on_start": True,
        "backup_on_exit": True,
        "auto_vacuum": True,
        "log_queries": False,
        "slow_query_threshold": 1.0
    },
    "monitoring": {
        "check_interval_seconds": 3600,
        "timeout_seconds": 30,
        "retries": 3,
        "retry_delay_seconds": 5,
        "diff_threshold_percent": 5.0,
        "max_workers": 5,
        "use_headless_browser": True
    },
    "ui": {
        "theme": "light",
        "font_size": 10,
        "window_size": [1024, 768],
        "save_window_position": True,
        "show_system_tray": True,
        "minimize_to_tray": True
    },
    "report": {
        "default_format": "html",
        "available_formats": ["html", "csv", "xlsx", "pdf"],
        "max_items_per_page": 50,
        "include_screenshots": True,
        "include_diff_details": True
    },
    "notifications": {
        "enable_desktop": True,
        "enable_email": False,
        "email_recipients": [],
        "smtp_server": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": ""
    },
    "logging": {
        "level": "INFO",
        "max_file_size_mb": 10,
        "backup_count": 5,
        "console_output": True
    },
    "browser": {
        "executable_path": "",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "wait_time_seconds": 10,
        "proxy": None,
        "browser_type": "chrome",  # chrome, firefox, edge
        "use_webdriver_manager": True
    }
}

# Имя файла конфигурации
CONFIG_FILE = BASE_DIR / "config" / "settings.json"

# Инициализация логгера
logger = logging.getLogger('wdm.config')


def ensure_directories():
    """Создает необходимые директории, если они не существуют"""
    for directory in [DATA_DIR, LOGS_DIR, REPORTS_DIR, SCREENSHOTS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Проверена директория: {directory}")


def load_config():
    """Загружает конфигурацию из файла или возвращает настройки по умолчанию"""
    try:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config_data = f.read()
                    # Проверяем, что файл не пустой
                    if not config_data.strip():
                        logger.warning(f"Файл конфигурации {CONFIG_FILE} пуст, используются настройки по умолчанию")
                        save_config(DEFAULT_CONFIG)
                        return DEFAULT_CONFIG
                    
                    # Пытаемся загрузить JSON
                    config = json.loads(config_data)
                    
                    # Проверяем, что config - это словарь
                    if not isinstance(config, dict):
                        logger.warning(f"Файл конфигурации {CONFIG_FILE} имеет неверный формат, используются настройки по умолчанию")
                        save_config(DEFAULT_CONFIG)
                        return DEFAULT_CONFIG
                    
                    # Объединяем с настройками по умолчанию для добавления новых параметров
                    merged_config = DEFAULT_CONFIG.copy()
                    for section, values in config.items():
                        if section in merged_config and isinstance(values, dict):
                            merged_config[section].update(values)
                    
                    logger.info(f"Загружена конфигурация из {CONFIG_FILE}")
                    return merged_config
            except json.JSONDecodeError as json_error:
                logger.error(f"Ошибка декодирования JSON в файле конфигурации: {json_error}")
                # Создаем резервную копию поврежденного файла
                backup_file = str(CONFIG_FILE) + ".backup." + str(int(time.time()))
                try:
                    shutil.copy2(CONFIG_FILE, backup_file)
                    logger.info(f"Создана резервная копия поврежденного файла конфигурации: {backup_file}")
                except Exception as backup_error:
                    logger.warning(f"Не удалось создать резервную копию файла конфигурации: {backup_error}")
                
                # Пересоздаем файл конфигурации по умолчанию
                save_config(DEFAULT_CONFIG)
                return DEFAULT_CONFIG
            except Exception as read_error:
                logger.error(f"Ошибка чтения файла конфигурации: {read_error}")
                return DEFAULT_CONFIG
        else:
            save_config(DEFAULT_CONFIG)
            logger.info(f"Создан файл конфигурации по умолчанию {CONFIG_FILE}")
            return DEFAULT_CONFIG
    except Exception as e:
        logger.error(f"Ошибка загрузки конфигурации: {e}")
        # В случае критической ошибки всегда возвращаем настройки по умолчанию
        return DEFAULT_CONFIG


def save_config(config):
    """Сохраняет конфигурацию в файл"""
    try:
        # Убедимся, что директория существует
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        logger.info(f"Конфигурация сохранена в {CONFIG_FILE}")
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения конфигурации: {e}")
        return False


# Инициализация при импорте модуля
ensure_directories()
CURRENT_CONFIG = load_config()


def get_config():
    """Возвращает текущую конфигурацию"""
    return CURRENT_CONFIG


def update_config(section, key, value):
    """Обновляет и сохраняет один параметр конфигурации"""
    global CURRENT_CONFIG
    
    if section in CURRENT_CONFIG and key in CURRENT_CONFIG[section]:
        CURRENT_CONFIG[section][key] = value
        save_config(CURRENT_CONFIG)
        logger.debug(f"Обновлен параметр конфигурации {section}.{key} = {value}")
        return True
    else:
        logger.warning(f"Попытка обновить несуществующий параметр {section}.{key}")
        return False 