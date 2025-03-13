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
from utils.cache_manager import get_snapshot_cache
from utils.http_client import get_http_client
from core.web_driver_manager import driver_context  # Импортируем контекстный менеджер драйвера


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
        Получение контента сайта в динамическом режиме (с помощью Selenium).
        
        Args:
            site_data: Данные о сайте
            
        Returns:
            Tuple[Optional[str], Optional[str]]: HTML-контент и сообщение об ошибке (если есть)
        """
        try:
            self.logger.debug(f"Получение динамического контента для URL: {site_data['url']}")
            
            # Параметры для Selenium
            timeout = site_data.get('timeout', 30)
            wait_for_selector = site_data.get('wait_for_selector')
            wait_for_xpath = site_data.get('wait_for_xpath')
            wait_time = site_data.get('wait_time', 0)
            scroll_to_bottom = site_data.get('scroll_to_bottom', False)
            click_selectors = site_data.get('click_selectors', [])
            css_selector = site_data.get('css_selector')
            xpath = site_data.get('xpath')
            
            # Создаем пользовательские настройки для драйвера
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            # Отключаем изображения для ускорения загрузки
            chrome_options.add_argument('--blink-settings=imagesEnabled=false')
            
            # Устанавливаем размер окна
            chrome_options.add_argument('--window-size=1920,1080')
            
            # Устанавливаем User-Agent
            user_agent = site_data.get('user_agent') or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'
            chrome_options.add_argument(f'--user-agent={user_agent}')
            
            # Используем контекстный менеджер для работы с драйвером
            with driver_context(chrome_options) as driver:
                # Открываем страницу
                driver.get(site_data['url'])
                
                # Ожидаем загрузки элемента, если указан
                if wait_for_selector:
                    self.logger.debug(f"Ожидание селектора: {wait_for_selector}")
                    WebDriverWait(driver, timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector))
                    )
                
                if wait_for_xpath:
                    self.logger.debug(f"Ожидание XPath: {wait_for_xpath}")
                    WebDriverWait(driver, timeout).until(
                        EC.presence_of_element_located((By.XPATH, wait_for_xpath))
                    )
                
                # Дополнительное ожидание, если указано
                if wait_time > 0:
                    self.logger.debug(f"Дополнительное ожидание: {wait_time} сек.")
                    time.sleep(wait_time)
                
                # Прокрутка страницы вниз, если требуется
                if scroll_to_bottom:
                    self.logger.debug("Прокрутка страницы вниз")
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    # Даем время на подгрузку контента
                    time.sleep(1)
                
                # Клик по элементам, если указаны
                for selector in click_selectors:
                    try:
                        self.logger.debug(f"Клик по селектору: {selector}")
                        element = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                        driver.execute_script("arguments[0].click();", element)
                        # Небольшая пауза после клика
                        time.sleep(0.5)
                    except Exception as e:
                        self.logger.warning(f"Не удалось кликнуть по селектору {selector}: {e}")
                
                # Получаем HTML страницы
                html = driver.page_source
                
                # Если нужно извлечь конкретный элемент
                if css_selector or xpath:
                    try:
                        if css_selector:
                            self.logger.debug(f"Извлечение по CSS-селектору: {css_selector}")
                            element = driver.find_element(By.CSS_SELECTOR, css_selector)
                            html = element.get_attribute('outerHTML')
                        elif xpath:
                            self.logger.debug(f"Извлечение по XPath: {xpath}")
                            element = driver.find_element(By.XPATH, xpath)
                            html = element.get_attribute('outerHTML')
                    except NoSuchElementException:
                        self.logger.warning(f"Элемент не найден: {css_selector or xpath}")
                
                # Фильтрация контента по регулярным выражениям
                html = self._filter_content(html, site_data)
                
                return html, None
                
        except TimeoutException as e:
            error_msg = f"Тайм-аут при загрузке страницы: {e}"
            self.logger.error(error_msg)
            return None, error_msg
        except WebDriverException as e:
            error_msg = f"Ошибка WebDriver: {e}"
            self.logger.error(error_msg)
            return None, error_msg
        except Exception as e:
            self.logger.error(f"Ошибка при получении контента в динамическом режиме: {e}")
            log_exception(self.logger, "Ошибка динамического получения контента")
            return None, str(e)
    
    def _get_content_static(self, site_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """
        Получение контента сайта в статическом режиме (с помощью HTTP-запроса).
        
        Args:
            site_data: Данные о сайте
            
        Returns:
            Tuple[Optional[str], Optional[str]]: HTML-контент и сообщение об ошибке (если есть)
        """
        url = site_data['url']
        css_selector = site_data.get('css_selector', None)
        xpath = site_data.get('xpath', None)
        
        try:
            self.logger.debug(f"Получение статического контента для URL: {url}")
            
            # Параметры запроса
            headers = site_data.get('headers', {})
            timeout = site_data.get('timeout', 30)
            retries = site_data.get('retries', 3)
            retry_delay = site_data.get('retry_delay', 1)
            
            # Если заголовки не указаны, используем стандартные
            if not headers:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'
                }
            
            # Получаем HTTP-клиент
            http_client = get_http_client()
            
            # Выполняем запрос с повторными попытками через HTTP-клиент
            response = http_client.get(
                url=url, 
                headers=headers, 
                timeout=timeout, 
                retries=retries, 
                retry_delay=retry_delay
            )
            
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
            # Используем кэш снимков для чтения файлов
            cache = get_snapshot_cache()
            
            # Чтение файлов из кэша
            old_content = cache.get_snapshot_content(old_path)
            new_content = cache.get_snapshot_content(new_path)
            
            if old_content is None or new_content is None:
                self.logger.error(f"Не удалось прочитать контент из файлов {old_path} и/или {new_path}")
                return 0.0, {'error': 'Не удалось прочитать контент'}
            
            # Разбиение на строки
            old_lines = old_content.splitlines()
            new_lines = new_content.splitlines()
            
            # Проверка на слишком большие документы
            max_lines = 5000  # Максимальное количество строк для полного сравнения
            
            if len(old_lines) > max_lines or len(new_lines) > max_lines:
                self.logger.warning(f"Файлы слишком большие для полного сравнения: {len(old_lines)} и {len(new_lines)} строк")
                
                # Оптимизированное сравнение для больших документов
                return self._compare_large_documents(old_lines, new_lines)
            
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
    
    def _compare_large_documents(self, old_lines: List[str], new_lines: List[str]) -> Tuple[float, Dict[str, Any]]:
        """
        Оптимизированное сравнение больших документов с использованием выборочного сравнения
        и хеширования секций документа
        
        Args:
            old_lines: Строки старого документа
            new_lines: Строки нового документа
            
        Returns:
            Tuple[float, Dict[str, Any]]: Процент изменений и структурированная информация о изменениях
        """
        try:
            # Определяем размер блока для сравнения (меньшие блоки для больших документов)
            block_size = min(500, max(100, min(len(old_lines), len(new_lines)) // 20))
            
            # Функция для вычисления хеша блока строк
            def hash_block(lines, start, size):
                block = ''.join(lines[start:start+size])
                return hashlib.md5(block.encode('utf-8')).hexdigest()
            
            # Разбиваем документы на блоки и сравниваем хеши блоков
            old_blocks = [hash_block(old_lines, i, block_size) 
                          for i in range(0, len(old_lines), block_size)]
            new_blocks = [hash_block(new_lines, i, block_size) 
                          for i in range(0, len(new_lines), block_size)]
            
            # Количество измененных блоков
            different_blocks = sum(1 for old, new in zip(old_blocks, new_blocks) if old != new)
            
            # Учитываем разницу в количестве блоков
            total_blocks = max(len(old_blocks), len(new_blocks))
            added_blocks = max(0, len(new_blocks) - len(old_blocks))
            removed_blocks = max(0, len(old_blocks) - len(new_blocks))
            
            # Вычисление процента изменений
            if total_blocks > 0:
                diff_percent = ((different_blocks + added_blocks + removed_blocks) / total_blocks) * 100
            else:
                diff_percent = 0.0
            
            # Создание структурированной информации о изменениях
            changes = {
                'added_blocks': added_blocks,
                'removed_blocks': removed_blocks,
                'changed_blocks': different_blocks,
                'total_blocks': total_blocks,
                'diff_percent': diff_percent,
                'is_approximation': True,
                'block_size': block_size
            }
            
            self.logger.debug(f"Приблизительное сравнение больших документов: {diff_percent:.2f}% изменений")
            return diff_percent, changes
        
        except Exception as e:
            self.logger.error(f"Ошибка при сравнении больших документов: {e}")
            log_exception(self.logger, "Ошибка сравнения больших документов")
            return 0.0, {'error': str(e)}
    
    def close(self):
        """Закрытие монитора и освобождение ресурсов"""
        self.logger.debug("Закрытие WebMonitor")
        self.close_browser()
        self.logger.debug("WebMonitor закрыт успешно")

class BrowserContextManager:
    """
    Контекстный менеджер для работы с веб-драйвером.
    Гарантирует возврат ресурса даже при возникновении исключений.
    """
    
    def __init__(self, web_monitor):
        """
        Инициализация контекстного менеджера
        
        Args:
            web_monitor: Объект WebMonitor, содержащий драйвер
        """
        self.web_monitor = web_monitor
        self.logger = get_module_logger('core.web_monitor.browser_manager')
        self.driver = None
    
    def __enter__(self):
        """
        Вход в контекстный блок
        
        Returns:
            webdriver: Инициализированный веб-драйвер
        """
        self.logger.debug("Вход в контекстный блок для работы с браузером")
        
        # Инициализируем браузер, если не инициализирован
        if not self.web_monitor.driver:
            success = self.web_monitor.initialize_browser()
            if not success:
                self.logger.error("Не удалось инициализировать браузер")
                raise RuntimeError("Не удалось инициализировать браузер")
        
        self.driver = self.web_monitor.driver
        return self.driver
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Выход из контекстного блока
        
        Args:
            exc_type: Тип исключения, если оно возникло
            exc_val: Значение исключения
            exc_tb: Трассировка исключения
            
        Returns:
            bool: Флаг обработки исключения
        """
        # Логируем исключение, если оно возникло
        if exc_type:
            self.logger.error(f"Произошло исключение при работе с браузером: {exc_val}")
            log_exception(self.logger, "Ошибка при работе с браузером")
        
        # Проверяем состояние драйвера
        try:
            if self.driver:
                # Проверяем, что сессия активна
                self.driver.current_window_handle  # Это вызовет исключение, если драйвер разрушен
        except Exception as e:
            self.logger.warning(f"Драйвер браузера в некорректном состоянии: {e}")
            # Если драйвер в некорректном состоянии, закрываем и сбрасываем его
            try:
                self.web_monitor.close_browser()
                self.web_monitor.driver = None
            except Exception as close_error:
                self.logger.error(f"Ошибка при закрытии драйвера: {close_error}")
        
        self.logger.debug("Выход из контекстного блока для работы с браузером")
        return False  # Не подавляем исключения

def get_browser(self):
    """
    Получение браузера через контекстный менеджер
    
    Returns:
        BrowserContextManager: Контекстный менеджер для работы с браузером
    """
    return BrowserContextManager(self)

def _get_content_dynamic(self, site_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Получение динамического контента сайта с использованием Selenium
    
    Args:
        site_data: Данные о сайте
        
    Returns:
        Tuple[Optional[str], Optional[str]]: HTML-контент и текстовое содержимое сайта
    """
    url = site_data.get('url')
    site_id = site_data.get('id')
    wait_time = site_data.get('wait_time', self.config['monitoring']['page_wait_seconds'])
    
    self.logger.debug(f"Получение динамического контента для сайта {site_id}: {url}")
    
    html_content = None
    text_content = None
    
    # Используем контекстный менеджер для работы с браузером
    with self.get_browser() as driver:
        try:
            # Загрузка страницы
            self.logger.debug(f"Загрузка страницы {url}")
            driver.get(url)
            
            # Ожидание загрузки страницы
            self.logger.debug(f"Ожидание загрузки страницы {wait_time} сек.")
            time.sleep(wait_time)
            
            # Получение HTML-контента
            html_content = driver.page_source
            
            # Получение текстового содержимого
            body_element = driver.find_element(By.TAG_NAME, 'body')
            text_content = body_element.text
            
            # Фильтрация контента по настройкам сайта
            html_content = self._filter_content(html_content, site_data)
            
            # Создание скриншота
            self._take_screenshot(site_id)
            
            self.logger.debug(f"Динамический контент для сайта {site_id} получен успешно")
            
        except TimeoutException:
            self.logger.error(f"Таймаут при загрузке страницы {url}")
            self.error_count += 1
            
        except WebDriverException as e:
            self.logger.error(f"Ошибка браузера при загрузке {url}: {e}")
            log_exception(self.logger, f"Ошибка браузера для сайта {site_id}")
            self.error_count += 1
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении динамического контента {url}: {e}")
            log_exception(self.logger, f"Ошибка получения контента для сайта {site_id}")
            self.error_count += 1
    
    return html_content, text_content

def _get_static_content(self, url: str, site_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Получение контента сайта в статическом режиме (с помощью HTTP-запроса).
    
    Args:
        url: URL сайта
        site_data: Данные о сайте
        
    Returns:
        Tuple[Optional[str], Optional[str]]: HTML-контент и сообщение об ошибке (если есть)
    """
    try:
        self.logger.debug(f"Получение статического контента для URL: {url}")
        
        # Параметры запроса
        headers = site_data.get('headers', {})
        timeout = site_data.get('timeout', 30)
        retries = site_data.get('retries', 3)
        retry_delay = site_data.get('retry_delay', 1)
        css_selector = site_data.get('css_selector', None)
        xpath = site_data.get('xpath', None)
        
        # Если заголовки не указаны, используем стандартные
        if not headers:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'
            }
        
        # Получаем HTTP-клиент
        http_client = get_http_client()
        
        # Выполняем запрос с повторными попытками через HTTP-клиент
        response = http_client.get(
            url=url, 
            headers=headers, 
            timeout=timeout, 
            retries=retries, 
            retry_delay=retry_delay
        )
        
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