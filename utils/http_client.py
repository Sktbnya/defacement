import requests
import time
import logging
import threading
from typing import Dict, Any, Optional, Union, List, Tuple
from functools import wraps

from utils.logger import get_module_logger
from utils.error_handler import handle_errors, retry


class HttpClient:
    """
    Оптимизированный HTTP-клиент для выполнения запросов
    с использованием сессий requests и эффективным управлением ресурсами.
    """
    
    # Единственный экземпляр класса (шаблон Singleton)
    _instance = None
    
    # Блокировка для обеспечения потокобезопасности
    _lock = threading.RLock()
    
    # Время жизни сессии в секундах (1 час)
    SESSION_TTL = 3600
    
    def __new__(cls):
        """
        Реализация шаблона Singleton для класса HttpClient.
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(HttpClient, cls).__new__(cls)
            return cls._instance
    
    def __init__(self):
        """
        Инициализация HTTP клиента.
        """
        # Предотвращаем повторную инициализацию для Singleton
        if hasattr(self, 'initialized') and self.initialized:
            return
            
        self.logger = get_module_logger('utils.http_client')
        self.logger.debug("Инициализация HTTP клиента")
        
        # Словарь сессий для разных контекстов (например, по доменам)
        self._sessions: Dict[str, Dict[str, Any]] = {}
        
        # Стандартные заголовки для всех запросов
        self._default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        # Стандартные параметры тайм-аутов
        self._default_timeout = (5, 30)  # (connect, read)
        
        # Стандартные параметры повторных попыток
        self._default_retries = 3
        self._default_retry_delay = 1
        
        # Блокировка для управления сессиями
        self._session_lock = threading.RLock()
        
        # Флаг инициализации
        self.initialized = True
        
        # Запускаем поток очистки устаревших сессий
        self._start_cleanup_thread()
        
        self.logger.info("HTTP клиент инициализирован")
    
    def _start_cleanup_thread(self):
        """
        Запускает фоновый поток для очистки устаревших сессий.
        """
        cleanup_thread = threading.Thread(
            target=self._cleanup_sessions_worker, 
            name="HttpSessionCleanup", 
            daemon=True
        )
        cleanup_thread.start()
        self.logger.debug("Запущен поток очистки сессий")
    
    def _cleanup_sessions_worker(self):
        """
        Фоновый процесс для периодической очистки устаревших сессий.
        """
        while True:
            try:
                # Спим 10 минут перед каждой проверкой
                time.sleep(600)
                
                # Очищаем устаревшие сессии
                self._cleanup_expired_sessions()
            except Exception as e:
                self.logger.error(f"Ошибка в процессе очистки сессий: {e}")
    
    def _cleanup_expired_sessions(self):
        """
        Очищает устаревшие сессии на основе их времени жизни.
        """
        current_time = time.time()
        expired_keys = []
        
        with self._session_lock:
            # Находим все устаревшие сессии
            for key, session_data in self._sessions.items():
                last_used = session_data.get('last_used', 0)
                if current_time - last_used > self.SESSION_TTL:
                    expired_keys.append(key)
            
            # Закрываем и удаляем устаревшие сессии
            for key in expired_keys:
                session = self._sessions[key].get('session')
                if session:
                    try:
                        session.close()
                    except Exception as e:
                        self.logger.warning(f"Ошибка при закрытии сессии {key}: {e}")
                del self._sessions[key]
        
        if expired_keys:
            self.logger.debug(f"Очищено {len(expired_keys)} устаревших сессий")
    
    def _get_session(self, domain: str = 'default') -> requests.Session:
        """
        Получает существующую или создает новую сессию для указанного домена.
        
        Args:
            domain: Ключ домена для сессии
            
        Returns:
            requests.Session: Сессия для указанного домена
        """
        with self._session_lock:
            # Если сессия уже существует и актуальна, возвращаем её
            if domain in self._sessions:
                session_data = self._sessions[domain]
                session_data['last_used'] = time.time()
                return session_data['session']
            
            # Создаем новую сессию
            session = requests.Session()
            
            # Устанавливаем стандартные заголовки
            session.headers.update(self._default_headers)
            
            # Сохраняем сессию
            self._sessions[domain] = {
                'session': session,
                'created': time.time(),
                'last_used': time.time(),
            }
            
            return session
    
    def _get_domain_from_url(self, url: str) -> str:
        """
        Извлекает домен из URL.
        
        Args:
            url: URL для обработки
            
        Returns:
            str: Домен из URL
        """
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc
        except Exception:
            # В случае ошибки, используем исходный URL в качестве ключа
            return url
    
    def close_all_sessions(self):
        """
        Закрывает все открытые сессии.
        """
        with self._session_lock:
            for key, session_data in self._sessions.items():
                session = session_data.get('session')
                if session:
                    try:
                        session.close()
                    except Exception as e:
                        self.logger.warning(f"Ошибка при закрытии сессии {key}: {e}")
            
            # Очищаем словарь сессий
            self._sessions.clear()
        
        self.logger.debug("Все HTTP-сессии закрыты")
    
    @handle_errors(error_msg="Ошибка при выполнении GET-запроса")
    def get(self, url: str, params: Optional[Dict[str, Any]] = None, 
            headers: Optional[Dict[str, str]] = None, timeout: Optional[Union[float, Tuple[float, float]]] = None, 
            retries: int = None, retry_delay: int = None, use_domain_session: bool = True, 
            **kwargs) -> requests.Response:
        """
        Выполняет GET-запрос с использованием сессии.
        
        Args:
            url: URL для запроса
            params: Параметры запроса
            headers: Заголовки запроса
            timeout: Тайм-аут запроса
            retries: Количество повторных попыток
            retry_delay: Задержка между повторными попытками
            use_domain_session: Использовать ли общую сессию для домена
            **kwargs: Дополнительные параметры для requests
            
        Returns:
            requests.Response: Ответ на запрос
        """
        # Устанавливаем значения по умолчанию, если они не предоставлены
        retries = self._default_retries if retries is None else retries
        retry_delay = self._default_retry_delay if retry_delay is None else retry_delay
        timeout = self._default_timeout if timeout is None else timeout
        
        # Определяем домен из URL
        domain = self._get_domain_from_url(url) if use_domain_session else 'default'
        
        # Получаем или создаем сессию
        session = self._get_session(domain)
        
        # Объединяем переданные заголовки с заголовками по умолчанию
        merged_headers = dict(self._default_headers)
        if headers:
            merged_headers.update(headers)
        
        # Выполняем запрос с повторными попытками
        for attempt in range(retries):
            try:
                response = session.get(
                    url=url,
                    params=params,
                    headers=merged_headers,
                    timeout=timeout,
                    **kwargs
                )
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                # Если это не последняя попытка, повторяем
                if attempt < retries - 1:
                    self.logger.warning(f"Попытка {attempt+1}/{retries} не удалась: {e}. Повтор через {retry_delay} сек.")
                    time.sleep(retry_delay)
                else:
                    raise
    
    @handle_errors(error_msg="Ошибка при выполнении POST-запроса")
    def post(self, url: str, data: Optional[Dict[str, Any]] = None, json: Optional[Dict[str, Any]] = None,
             headers: Optional[Dict[str, str]] = None, timeout: Optional[Union[float, Tuple[float, float]]] = None,
             retries: int = None, retry_delay: int = None, use_domain_session: bool = True,
             **kwargs) -> requests.Response:
        """
        Выполняет POST-запрос с использованием сессии.
        
        Args:
            url: URL для запроса
            data: Данные формы
            json: JSON-данные
            headers: Заголовки запроса
            timeout: Тайм-аут запроса
            retries: Количество повторных попыток
            retry_delay: Задержка между повторными попытками
            use_domain_session: Использовать ли общую сессию для домена
            **kwargs: Дополнительные параметры для requests
            
        Returns:
            requests.Response: Ответ на запрос
        """
        # Устанавливаем значения по умолчанию, если они не предоставлены
        retries = self._default_retries if retries is None else retries
        retry_delay = self._default_retry_delay if retry_delay is None else retry_delay
        timeout = self._default_timeout if timeout is None else timeout
        
        # Определяем домен из URL
        domain = self._get_domain_from_url(url) if use_domain_session else 'default'
        
        # Получаем или создаем сессию
        session = self._get_session(domain)
        
        # Объединяем переданные заголовки с заголовками по умолчанию
        merged_headers = dict(self._default_headers)
        if headers:
            merged_headers.update(headers)
        
        # Выполняем запрос с повторными попытками
        for attempt in range(retries):
            try:
                response = session.post(
                    url=url,
                    data=data,
                    json=json,
                    headers=merged_headers,
                    timeout=timeout,
                    **kwargs
                )
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                # Если это не последняя попытка, повторяем
                if attempt < retries - 1:
                    self.logger.warning(f"Попытка {attempt+1}/{retries} не удалась: {e}. Повтор через {retry_delay} сек.")
                    time.sleep(retry_delay)
                else:
                    raise
    
    # Аналогично можно реализовать методы put, delete, patch и т.д.
    
    def download_file(self, url: str, destination: str, chunk_size: int = 8192,
                      headers: Optional[Dict[str, str]] = None, timeout: Optional[Union[float, Tuple[float, float]]] = None,
                      retries: int = None, retry_delay: int = None) -> bool:
        """
        Скачивает файл по URL.
        
        Args:
            url: URL файла
            destination: Путь для сохранения файла
            chunk_size: Размер блока для скачивания
            headers: Заголовки запроса
            timeout: Тайм-аут запроса
            retries: Количество повторных попыток
            retry_delay: Задержка между повторными попытками
            
        Returns:
            bool: True, если файл успешно скачан
        """
        # Устанавливаем значения по умолчанию, если они не предоставлены
        retries = self._default_retries if retries is None else retries
        retry_delay = self._default_retry_delay if retry_delay is None else retry_delay
        timeout = self._default_timeout if timeout is None else timeout
        
        # Определяем домен из URL
        domain = self._get_domain_from_url(url)
        
        # Получаем или создаем сессию
        session = self._get_session(domain)
        
        # Объединяем переданные заголовки с заголовками по умолчанию
        merged_headers = dict(self._default_headers)
        if headers:
            merged_headers.update(headers)
        
        # Выполняем запрос с повторными попытками
        for attempt in range(retries):
            try:
                response = session.get(
                    url=url,
                    headers=merged_headers,
                    timeout=timeout,
                    stream=True  # Важно для скачивания файлов
                )
                response.raise_for_status()
                
                # Сохраняем файл
                with open(destination, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:  # Фильтруем пустые куски
                            f.write(chunk)
                
                return True
            except (requests.RequestException, IOError) as e:
                # Если это не последняя попытка, повторяем
                if attempt < retries - 1:
                    self.logger.warning(f"Попытка скачивания {attempt+1}/{retries} не удалась: {e}. Повтор через {retry_delay} сек.")
                    time.sleep(retry_delay)
                else:
                    self.logger.error(f"Не удалось скачать файл {url}: {e}")
                    return False


# Создаем синглтон HTTP-клиента
_http_client = HttpClient()


def get_http_client() -> HttpClient:
    """
    Получает глобальный экземпляр HTTP-клиента.
    
    Returns:
        HttpClient: Глобальный экземпляр HTTP-клиента
    """
    return _http_client 