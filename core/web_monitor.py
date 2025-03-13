#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль мониторинга веб-сайтов для WDM_V12.
Отвечает за получение контента веб-сайтов, анализ изменений и сохранение результатов.
"""

import os
import time
import hashlib
import datetime
import re
import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple, Union, Optional, Any
import difflib
import json
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, WebDriverException, NoSuchElementException
)
from webdriver_manager.chrome import ChromeDriverManager

# Внутренние импорты
from utils.logger import get_module_logger, log_exception
from config.config import get_config


class WebMonitor:
    """
    Класс для мониторинга веб-сайтов.
    Поддерживает статический (requests) и динамический (Selenium) режимы получения контента.
    """
    
    def __init__(self, app_context):
        """
        Инициализация монитора веб-сайтов
        
        Args:
            app_context: Контекст приложения с доступом к конфигурации и БД
        """
        self.logger = get_module_logger('core.web_monitor')
        self.logger.debug("Инициализация WebMonitor")
        
        self.app_context = app_context
        self.config = get_config()
        
        # Директория для хранения снимков контента
        self.screenshots_dir = Path(self.config['database']['path']).parent / "screenshots"
        self.content_dir = Path(self.config['database']['path']).parent / "content"
        
        # Создаем директории, если они не существуют
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.content_dir.mkdir(parents=True, exist_ok=True)
        
        # Инициализация драйвера браузера
        self.driver = None
        
        # Счетчик ошибок
        self.error_count = 0
        
        self.logger.debug("WebMonitor инициализирован")
    
    def initialize_browser(self):
        """
        Инициализация браузера для динамического режима
        
        Returns:
            bool: Результат инициализации
        """
        if self.driver:
            self.logger.debug("Браузер уже инициализирован")
            return True
        
        try:
            self.logger.debug("Инициализация браузера")
            
            # Получение настроек браузера из конфигурации
            browser_type = self.config['browser']['browser_type']
            use_headless = self.config['monitoring']['use_headless_browser']
            user_agent = self.config['browser']['user_agent']
            use_wdm = self.config['browser']['use_webdriver_manager']
            
            # Настройка опций Chrome
            chrome_options = Options()
            
            # Установка безголового режима, если нужно
            if use_headless:
                chrome_options.add_argument("--headless")
            
            # Дополнительные опции для улучшения производительности и совместимости
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument(f"user-agent={user_agent}")
            
            # Инициализация драйвера
            if use_wdm:
                # Использование webdriver_manager для автоматической загрузки драйвера
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                # Использование предустановленного драйвера
                executable_path = self.config['browser']['executable_path']
                if not executable_path:
                    # Если путь не указан, устанавливаем драйвер автоматически
                    executable_path = ChromeDriverManager().install()
                service = Service(executable_path)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Установка таймаута ожидания
            self.driver.set_page_load_timeout(self.config['monitoring']['timeout_seconds'])
            self.driver.implicitly_wait(5)  # Имплицитное ожидание элементов
            
            self.logger.info(f"Браузер {browser_type} инициализирован успешно")
            return True
        
        except Exception as e:
            self.logger.error(f"Ошибка инициализации браузера: {e}")
            log_exception(self.logger, "Ошибка инициализации браузера")
            self.error_count += 1
            return False
    
    def close_browser(self):
        """Закрытие браузера"""
        if self.driver:
            try:
                self.logger.debug("Закрытие браузера")
                self.driver.quit()
                self.driver = None
                self.logger.debug("Браузер закрыт успешно")
            except Exception as e:
                self.logger.error(f"Ошибка при закрытии браузера: {e}")
                log_exception(self.logger, "Ошибка закрытия браузера")
                self.driver = None  # На всякий случай сбрасываем ссылку
    
    def check_site(self, site_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Проверка сайта на изменения
        
        Args:
            site_data: Данные сайта из БД (id, url, name, check_method, css_selector, xpath, etc.)
            
        Returns:
            Dict[str, Any]: Результат проверки с ключами:
                success (bool): Успешность проверки
                error (str): Ошибка, если проверка не удалась
                content_hash (str): Хеш контента
                content_path (str): Путь к файлу с контентом
                screenshot_path (str): Путь к скриншоту (если доступен)
                diff_percent (float): Процент изменений (если доступен)
                changes (Dict): Информация об изменениях (если доступны)
        """
        self.logger.info(f"Проверка сайта {site_data['name']} ({site_data['url']})")
        
        # Выбор метода проверки
        check_method = site_data.get('check_method', 'dynamic')
        
        # Результат по умолчанию
        result = {
            'success': False,
            'error': None,
            'content_hash': None,
            'content_path': None,
            'screenshot_path': None,
            'diff_percent': None,
            'changes': None,
            'timestamp': datetime.datetime.now()
        }
        
        # Определяем функцию проверки в зависимости от метода
        if check_method == 'dynamic':
            content, error = self._get_content_dynamic(site_data)
            if error and not content:
                # Если динамический метод не сработал, пробуем статический
                self.logger.warning(f"Динамический метод не сработал для {site_data['url']}: {error}. Пробуем статический метод.")
                content, error = self._get_content_static(site_data)
        else:
            content, error = self._get_content_static(site_data)
            if error and not content:
                # Если статический метод не сработал, пробуем динамический
                self.logger.warning(f"Статический метод не сработал для {site_data['url']}: {error}. Пробуем динамический метод.")
                content, error = self._get_content_dynamic(site_data)
        
        # Если ни один метод не сработал
        if error:
            self.logger.error(f"Не удалось получить контент сайта {site_data['url']}: {error}")
            result['error'] = str(error)
            self.error_count += 1
            return result
        
        # Если контент получен успешно
        if content:
            content_hash = self._calculate_hash(content)
            content_path = self._save_content(content, site_data['id'], content_hash)
            
            result.update({
                'success': True,
                'content_hash': content_hash,
                'content_path': str(content_path),
                'content_size': len(content)
            })
            
            # Получение последнего снимка сайта для сравнения
            last_snapshot = self._get_last_snapshot(site_data['id'])
            
            # Если есть предыдущий снимок, сравниваем
            if last_snapshot:
                diff_percent, changes = self._compare_content(
                    last_snapshot['content_path'], 
                    content_path
                )
                
                # Добавляем информацию о различиях в результат
                result.update({
                    'diff_percent': diff_percent,
                    'changes': changes
                })
                
                # Если процент изменений превышает порог
                threshold = self.config['monitoring']['diff_threshold_percent']
                if diff_percent > threshold:
                    self.logger.info(f"Обнаружены изменения на сайте {site_data['name']}: {diff_percent:.2f}%")
                    # TODO: Генерация уведомления о изменениях
                else:
                    self.logger.debug(f"Изменения на сайте {site_data['name']} ниже порога: {diff_percent:.2f}% < {threshold}%")
            else:
                self.logger.debug(f"Первичный снимок сайта {site_data['name']}")
            
            self.logger.info(f"Проверка сайта {site_data['name']} завершена успешно")
            return result
        
        # Если дошли до этого места, значит что-то пошло не так
        result['error'] = "Не удалось получить контент сайта по неизвестной причине"
        self.error_count += 1
        self.logger.error(f"Неизвестная ошибка при проверке сайта {site_data['url']}")
        return result
    
    def _get_content_dynamic(self, site_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """
        Получение контента сайта с помощью Selenium (динамический режим)
        
        Args:
            site_data: Данные сайта
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (контент, ошибка)
        """
        url = site_data['url']
        css_selector = site_data.get('css_selector')
        xpath = site_data.get('xpath')
        
        try:
            if not self.initialize_browser():
                return None, "Не удалось инициализировать браузер"
            
            # Загрузка страницы
            self.logger.debug(f"Загрузка страницы {url} в динамическом режиме")
            self.driver.get(url)
            
            # Ожидание загрузки страницы
            wait_time = self.config['browser']['wait_time_seconds']
            
            # Делаем скриншот для отладки и архивирования
            screenshot_path = self._take_screenshot(site_data['id'])
            
            # Получение контента
            if css_selector:
                # Ожидание появления элемента по CSS селектору
                try:
                    element = WebDriverWait(self.driver, wait_time).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
                    )
                    html = element.get_attribute('outerHTML')
                except (TimeoutException, NoSuchElementException) as e:
                    self.logger.warning(f"Элемент по CSS селектору не найден: {e}")
                    html = self.driver.page_source
            elif xpath:
                # Ожидание появления элемента по XPath
                try:
                    element = WebDriverWait(self.driver, wait_time).until(
                        EC.presence_of_element_located((By.XPATH, xpath))
                    )
                    html = element.get_attribute('outerHTML')
                except (TimeoutException, NoSuchElementException) as e:
                    self.logger.warning(f"Элемент по XPath не найден: {e}")
                    html = self.driver.page_source
            else:
                # Если селектор не указан, берем весь HTML
                html = self.driver.page_source
            
            # Фильтрация контента по регулярным выражениям
            html = self._filter_content(html, site_data)
            
            return html, None
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении контента в динамическом режиме: {e}")
            log_exception(self.logger, "Ошибка динамического получения контента")
            
            # Пытаемся закрыть и переинициализировать браузер
            self.close_browser()
            
            return None, str(e)
    
    def _get_content_static(self, site_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """
        Получение контента сайта с помощью requests (статический режим)
        
        Args:
            site_data: Данные сайта
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (контент, ошибка)
        """
        url = site_data['url']
        css_selector = site_data.get('css_selector')
        xpath = site_data.get('xpath')
        
        try:
            # Настройка заголовков запроса
            headers = {
                'User-Agent': self.config['browser']['user_agent'],
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Cache-Control': 'max-age=0',
                'Upgrade-Insecure-Requests': '1'
            }
            
            # Выполнение запроса с учетом таймаута и повторных попыток
            timeout = self.config['monitoring']['timeout_seconds']
            retries = self.config['monitoring']['retries']
            retry_delay = self.config['monitoring']['retry_delay_seconds']
            
            self.logger.debug(f"Загрузка страницы {url} в статическом режиме")
            
            # Повторяем запрос при необходимости
            for attempt in range(retries):
                try:
                    response = requests.get(url, headers=headers, timeout=timeout)
                    response.raise_for_status()  # Проверка статуса ответа
                    break
                except requests.RequestException as e:
                    if attempt < retries - 1:
                        self.logger.warning(f"Попытка {attempt+1}/{retries} не удалась: {e}. Повтор через {retry_delay} сек.")
                        time.sleep(retry_delay)
                    else:
                        raise
            
            # Получение HTML из ответа
            html = response.text
            
            # Если нужно извлечь конкретный элемент
            if css_selector or xpath:
                soup = BeautifulSoup(html, 'html.parser')
                
                if css_selector:
                    element = soup.select_one(css_selector)
                    if element:
                        html = str(element)
                    else:
                        self.logger.warning(f"Элемент по CSS селектору {css_selector} не найден")
                elif xpath:
                    # BeautifulSoup не поддерживает XPath напрямую, используем lxml
                    from lxml import etree
                    
                    dom = etree.HTML(html)
                    elements = dom.xpath(xpath)
                    if elements:
                        html = etree.tostring(elements[0], encoding='unicode')
                    else:
                        self.logger.warning(f"Элемент по XPath {xpath} не найден")
            
            # Фильтрация контента по регулярным выражениям
            html = self._filter_content(html, site_data)
            
            return html, None
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении контента в статическом режиме: {e}")
            log_exception(self.logger, "Ошибка статического получения контента")
            return None, str(e)
    
    def _filter_content(self, html: str, site_data: Dict[str, Any]) -> str:
        """
        Фильтрация контента по регулярным выражениям
        
        Args:
            html: HTML-контент
            site_data: Данные сайта с регулярными выражениями
            
        Returns:
            str: Отфильтрованный HTML-контент
        """
        include_regex = site_data.get('include_regex')
        exclude_regex = site_data.get('exclude_regex')
        
        if include_regex:
            try:
                pattern = re.compile(include_regex, re.DOTALL)
                matches = pattern.findall(html)
                if matches:
                    html = '\n'.join(matches)
                    self.logger.debug(f"Контент отфильтрован по include_regex, найдено {len(matches)} совпадений")
                else:
                    self.logger.warning(f"По include_regex {include_regex} ничего не найдено")
            except re.error as e:
                self.logger.error(f"Ошибка в include_regex: {e}")
        
        if exclude_regex:
            try:
                pattern = re.compile(exclude_regex, re.DOTALL)
                html = pattern.sub('', html)
                self.logger.debug(f"Контент отфильтрован по exclude_regex")
            except re.error as e:
                self.logger.error(f"Ошибка в exclude_regex: {e}")
        
        return html
    
    def _take_screenshot(self, site_id: int) -> Optional[str]:
        """
        Создание скриншота текущей страницы
        
        Args:
            site_id: ID сайта
            
        Returns:
            Optional[str]: Путь к файлу скриншота или None в случае ошибки
        """
        if not self.driver:
            return None
        
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"site_{site_id}_{timestamp}.png"
            filepath = self.screenshots_dir / filename
            
            self.driver.save_screenshot(str(filepath))
            self.logger.debug(f"Скриншот сохранен: {filepath}")
            
            return str(filepath)
        except Exception as e:
            self.logger.error(f"Ошибка при создании скриншота: {e}")
            return None
    
    def _calculate_hash(self, content: str) -> str:
        """
        Вычисление хеша контента
        
        Args:
            content: Контент для хеширования
            
        Returns:
            str: Хеш контента
        """
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _save_content(self, content: str, site_id: int, content_hash: str) -> Path:
        """
        Сохранение контента в файл
        
        Args:
            content: Контент для сохранения
            site_id: ID сайта
            content_hash: Хеш контента
            
        Returns:
            Path: Путь к файлу с контентом
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"site_{site_id}_{timestamp}_{content_hash[:8]}.html"
        filepath = self.content_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        self.logger.debug(f"Контент сохранен: {filepath}")
        return filepath
    
    def _get_last_snapshot(self, site_id: int) -> Optional[Dict[str, Any]]:
        """
        Получение последнего снимка сайта из БД
        
        Args:
            site_id: ID сайта
            
        Returns:
            Optional[Dict[str, Any]]: Данные последнего снимка или None
        """
        try:
            query = """
            SELECT * FROM snapshots 
            WHERE site_id = ? AND status = 'success'
            ORDER BY timestamp DESC
            LIMIT 1
            """
            
            result = self.app_context.execute_db_query(query, (site_id,))
            
            if result and len(result) > 0:
                return result[0]
            
            return None
        except Exception as e:
            self.logger.error(f"Ошибка при получении последнего снимка: {e}")
            return None
    
    def _compare_content(self, old_path: str, new_path: str) -> Tuple[float, Dict[str, Any]]:
        """
        Сравнение содержимого файлов и вычисление процента изменений
        
        Args:
            old_path: Путь к старому файлу
            new_path: Путь к новому файлу
            
        Returns:
            Tuple[float, Dict[str, Any]]: Процент изменений и структурированная информация о изменениях
        """
        try:
            # Чтение файлов
            with open(old_path, 'r', encoding='utf-8') as f:
                old_content = f.read()
            
            with open(new_path, 'r', encoding='utf-8') as f:
                new_content = f.read()
            
            # Разбиение на строки
            old_lines = old_content.splitlines()
            new_lines = new_content.splitlines()
            
            # Вычисление различий
            differ = difflib.Differ()
            diff = list(differ.compare(old_lines, new_lines))
            
            # Подсчет добавленных, удаленных и измененных строк
            added = sum(1 for line in diff if line.startswith('+ '))
            removed = sum(1 for line in diff if line.startswith('- '))
            changed = added + removed
            total_lines = max(len(old_lines), len(new_lines))
            
            # Вычисление процента изменений
            if total_lines > 0:
                diff_percent = (changed / total_lines) * 100
            else:
                diff_percent = 0.0
            
            # Создание структурированной информации о изменениях
            changes = {
                'added_lines': added,
                'removed_lines': removed,
                'total_changes': changed,
                'total_lines': total_lines,
                'diff_percent': diff_percent,
                # Примеры изменений (первые 5 добавленных и удаленных строк)
                'examples': {
                    'added': [line[2:] for line in diff if line.startswith('+ ')][:5],
                    'removed': [line[2:] for line in diff if line.startswith('- ')][:5]
                }
            }
            
            self.logger.debug(f"Сравнение контента: {diff_percent:.2f}% изменений")
            return diff_percent, changes
        
        except Exception as e:
            self.logger.error(f"Ошибка при сравнении контента: {e}")
            log_exception(self.logger, "Ошибка сравнения контента")
            return 0.0, {'error': str(e)}
    
    def close(self):
        """Закрытие монитора и освобождение ресурсов"""
        self.logger.debug("Закрытие WebMonitor")
        self.close_browser()
        self.logger.debug("WebMonitor закрыт успешно") 