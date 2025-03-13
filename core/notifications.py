#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль системы уведомлений для WDM_V12.
Отвечает за отправку уведомлений пользователю о изменениях на веб-сайтах.
"""

import os
import sys
import platform
import logging
import datetime
import threading
import json
import webbrowser
from typing import Dict, List, Any, Optional, Union

from utils.logger import get_module_logger, log_exception
from config.config import get_config
from utils.http_client import get_http_client


class NotificationManager:
    """
    Класс для управления уведомлениями.
    Поддерживает различные типы уведомлений: desktop, системный лоток, email.
    """
    
    # Единственный экземпляр класса (шаблон Singleton)
    _instance = None
    
    # Блокировка для обеспечения потокобезопасности
    _lock = threading.RLock()
    
    def __new__(cls):
        """Реализация шаблона Singleton"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(NotificationManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        """Инициализация менеджера уведомлений"""
        with self._lock:
            if self._initialized:
                return
            
            self.logger = get_module_logger('core.notifications')
            self.logger.debug("Инициализация менеджера уведомлений")
            
            # Настройки по умолчанию
            self.settings = {
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
                'telegram_notifications': False,
                'telegram_settings': {
                    'bot_token': '',
                    'chat_id': ''
                },
                'notification_threshold': 5.0,  # Минимальный процент изменений для уведомления
                'cooldown_period': 3600,  # Период охлаждения между уведомлениями (в секундах)
                'last_notification_times': {}  # Время последнего уведомления для каждого сайта
            }
            
            # Флаг инициализации
            self._initialized = True
            
            self.logger.debug("Менеджер уведомлений инициализирован")
    
    def update_settings(self, new_settings):
        """
        Обновление настроек уведомлений
        
        Args:
            new_settings: Новые настройки
            
        Returns:
            bool: Результат обновления
        """
        try:
            with self._lock:
                # Обновляем настройки
                self.settings.update(new_settings)
                
                self.logger.debug("Настройки уведомлений обновлены")
                return True
        
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении настроек уведомлений: {e}")
            log_exception(self.logger, "Ошибка обновления настроек уведомлений")
            return False
    
    def get_settings(self):
        """
        Получение текущих настроек уведомлений
        
        Returns:
            Dict: Текущие настройки
        """
        with self._lock:
            return self.settings.copy()
    
    def send_change_notification(self, site_id, site_name, site_url, diff_percent, change_id=None):
        """
        Отправка уведомления о изменении сайта
        
        Args:
            site_id: ID сайта
            site_name: Имя сайта
            site_url: URL сайта
            diff_percent: Процент изменений
            change_id: ID изменения (опционально)
            
        Returns:
            bool: Результат отправки
        """
        try:
            with self._lock:
                # Проверяем, включены ли уведомления
                if not self.settings['enabled']:
                    return False
                
                # Проверяем порог уведомлений
                if diff_percent < self.settings['notification_threshold']:
                    self.logger.debug(f"Изменение меньше порога уведомлений: {diff_percent:.2f}% < {self.settings['notification_threshold']}%")
                    return False
                
                # Проверяем период охлаждения
                site_id_str = str(site_id)
                now = datetime.datetime.now().timestamp()
                last_notification = self.settings['last_notification_times'].get(site_id_str, 0)
                
                if now - last_notification < self.settings['cooldown_period']:
                    self.logger.debug(f"Период охлаждения для сайта {site_name} еще не истек")
                    return False
                
                # Обновляем время последнего уведомления
                self.settings['last_notification_times'][site_id_str] = now
                
                # Формируем заголовок и текст уведомления
                title = f"Изменение на сайте: {site_name}"
                message = f"Обнаружено изменение на сайте {site_name} ({diff_percent:.2f}%)."
                
                # Отправляем уведомления
                success = False
                
                if self.settings['desktop_notifications']:
                    desktop_result = self._send_desktop_notification(title, message, site_url, change_id)
                    success = success or desktop_result
                
                if self.settings['email_notifications']:
                    email_result = self._send_email_notification(title, message, site_url, change_id)
                    success = success or email_result
                
                if self.settings['telegram_notifications']:
                    telegram_result = self._send_telegram_notification(title, message, site_url, change_id)
                    success = success or telegram_result
                
                if success:
                    self.logger.info(f"Уведомление о изменении сайта {site_name} отправлено")
                else:
                    self.logger.warning(f"Не удалось отправить уведомление о изменении сайта {site_name}")
                
                return success
        
        except Exception as e:
            self.logger.error(f"Ошибка при отправке уведомления: {e}")
            log_exception(self.logger, "Ошибка отправки уведомления")
            return False
    
    def _send_desktop_notification(self, title, message, site_url=None, change_id=None):
        """
        Отправка уведомления на рабочий стол
        
        Args:
            title: Заголовок уведомления
            message: Текст уведомления
            site_url: URL сайта (опционально)
            change_id: ID изменения (опционально)
            
        Returns:
            bool: Результат отправки
        """
        try:
            # Определяем операционную систему
            os_name = platform.system()
            
            if os_name == 'Windows':
                # Уведомление для Windows
                try:
                    from win10toast import ToastNotifier
                    toaster = ToastNotifier()
                    
                    # Подготовка callback для открытия URL при клике
                    callback_func = None
                    if site_url:
                        callback_func = lambda: webbrowser.open(site_url)
                    
                    # Отправка уведомления
                    toaster.show_toast(
                        title,
                        message,
                        icon_path=None,
                        duration=5,
                        threaded=True,
                        callback_on_click=callback_func
                    )
                    return True
                
                except ImportError:
                    self.logger.warning("win10toast не установлен, невозможно отправить уведомление на рабочий стол Windows")
                    return False
            
            elif os_name == 'Darwin':  # macOS
                try:
                    # Уведомление для macOS
                    import subprocess
                    cmd = [
                        'osascript', '-e',
                        f'display notification "{message}" with title "{title}"'
                    ]
                    subprocess.Popen(cmd)
                    return True
                
                except Exception as e:
                    self.logger.warning(f"Ошибка при отправке уведомления на macOS: {e}")
                    return False
            
            elif os_name == 'Linux':
                try:
                    # Уведомление для Linux
                    import subprocess
                    cmd = [
                        'notify-send',
                        title,
                        message
                    ]
                    subprocess.Popen(cmd)
                    return True
                
                except Exception as e:
                    self.logger.warning(f"Ошибка при отправке уведомления на Linux: {e}")
                    return False
            
            else:
                self.logger.warning(f"Не поддерживаемая операционная система для настольных уведомлений: {os_name}")
                return False
        
        except Exception as e:
            self.logger.error(f"Ошибка при отправке уведомления на рабочий стол: {e}")
            log_exception(self.logger, "Ошибка отправки уведомления на рабочий стол")
            return False
    
    def _send_email_notification(self, title, message, site_url=None, change_id=None):
        """
        Отправка уведомления по электронной почте
        
        Args:
            title: Заголовок уведомления
            message: Текст уведомления
            site_url: URL сайта (опционально)
            change_id: ID изменения (опционально)
            
        Returns:
            bool: Результат отправки
        """
        try:
            # Проверяем настройки электронной почты
            email_settings = self.settings['email_settings']
            
            if not email_settings['smtp_server'] or not email_settings['from_address'] or not email_settings['to_address']:
                self.logger.warning("Не настроены параметры SMTP для отправки уведомлений по электронной почте")
                return False
            
            # Импортируем модули для работы с электронной почтой
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            # Создаем сообщение
            msg = MIMEMultipart()
            msg['From'] = email_settings['from_address']
            msg['To'] = email_settings['to_address']
            msg['Subject'] = title
            
            # Формируем тело письма
            body = message
            
            if site_url:
                body += f"\n\nURL сайта: {site_url}"
            
            if change_id:
                body += f"\n\nID изменения: {change_id}"
            
            body += "\n\nС уважением,\nСистема мониторинга WDM v12"
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Отправляем сообщение
            server = smtplib.SMTP(email_settings['smtp_server'], email_settings['smtp_port'])
            server.starttls()
            
            # Авторизация на сервере, если указаны учетные данные
            if email_settings['smtp_username'] and email_settings['smtp_password']:
                server.login(email_settings['smtp_username'], email_settings['smtp_password'])
            
            # Отправка сообщения
            server.send_message(msg)
            server.quit()
            
            self.logger.info(f"Уведомление по электронной почте отправлено на {email_settings['to_address']}")
            return True
        
        except Exception as e:
            self.logger.error(f"Ошибка при отправке уведомления по электронной почте: {e}")
            log_exception(self.logger, "Ошибка отправки уведомления по электронной почте")
            return False
    
    def _send_telegram_notification(self, title, message, site_url=None, change_id=None):
        """
        Отправляет уведомление через Telegram.
        
        Args:
            title: Заголовок уведомления
            message: Текст уведомления
            site_url: URL сайта (опционально)
            change_id: ID изменения (опционально)
            
        Returns:
            bool: True, если уведомление отправлено успешно
        """
        try:
            # Получаем настройки Telegram
            telegram_settings = self.settings['telegram_settings']
            
            # Проверяем, включены ли Telegram-уведомления
            if not telegram_settings.get('enabled', False):
                return False
            
            # Проверяем наличие токена бота и ID чата
            if not telegram_settings['bot_token'] or not telegram_settings['chat_id']:
                self.logger.warning("Не настроены параметры Telegram для отправки уведомлений")
                return False
            
            # Формируем сообщение
            telegram_message = f"{title}\n\n{message}"
            
            if site_url:
                telegram_message += f"\n\nURL сайта: {site_url}"
            
            if change_id:
                telegram_message += f"\n\nID изменения: {change_id}"
            
            # Формируем URL запроса
            bot_token = telegram_settings['bot_token']
            chat_id = telegram_settings['chat_id']
            api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            
            # Параметры запроса
            params = {
                'chat_id': chat_id,
                'text': telegram_message,
                'parse_mode': 'HTML'
            }
            
            # Добавляем параметры для отправки с дизайном
            if telegram_settings.get('use_markdown', False):
                params['parse_mode'] = 'MarkdownV2'
            
            # Получаем HTTP-клиент
            http_client = get_http_client()
            
            # Отправляем запрос с помощью HTTP-клиента
            response = http_client.post(
                url=api_url,
                json=params,
                timeout=10,
                retries=2
            )
            
            # Проверяем ответ
            if response.status_code == 200:
                self.logger.info("Уведомление в Telegram отправлено успешно")
                return True
            else:
                self.logger.error(f"Ошибка при отправке в Telegram. Код: {response.status_code}, Ответ: {response.text}")
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка при отправке уведомления в Telegram: {e}")
            log_exception(self.logger, "Ошибка отправки Telegram")
            return False
    
    def test_notification(self, notification_type):
        """
        Тестирование отправки уведомления
        
        Args:
            notification_type: Тип уведомления (desktop, email, telegram)
            
        Returns:
            bool: Результат тестирования
        """
        try:
            self.logger.debug(f"Тестирование уведомления типа {notification_type}")
            
            # Проверяем, включены ли уведомления
            if not self.settings['enabled']:
                self.logger.warning("Уведомления отключены")
                return False
            
            # Заголовок и текст тестового уведомления
            title = "Тестовое уведомление"
            message = f"Это тестовое уведомление. Время: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            # Отправляем уведомление в зависимости от типа
            if notification_type == 'desktop' and self.settings['desktop_notifications']:
                return self._send_desktop_notification(title, message)
            elif notification_type == 'email' and self.settings['email_notifications']:
                return self._send_email_notification(title, message)
            elif notification_type == 'telegram' and self.settings['telegram_notifications']:
                return self._send_telegram_notification(title, message)
            else:
                self.logger.warning(f"Неизвестный тип уведомления: {notification_type}")
                return False
        
        except Exception as e:
            self.logger.error(f"Ошибка при тестировании уведомления: {e}")
            log_exception(self.logger, "Ошибка тестирования уведомления")
            return False 