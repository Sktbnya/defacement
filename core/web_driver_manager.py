import os
import time
import threading
import logging
from typing import Dict, Optional, List, Any, Tuple, Union
from pathlib import Path
import tempfile
import contextlib

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

from utils.logger import get_module_logger, log_exception
from utils.error_handler import handle_errors, retry


class WebDriverPool:
    """
    Пул веб-драйверов для эффективного управления и повторного использования экземпляров Selenium.
    """
    
    # Единственный экземпляр класса (шаблон Singleton)
    _instance = None
    
    # Блокировка для обеспечения потокобезопасности
    _lock = threading.RLock()
    
    # Максимальное время простоя драйвера (в секундах)
    MAX_IDLE_TIME = 300  # 5 минут
    
    # Максимальное количество драйверов в пуле
    MAX_POOL_SIZE = 5
    
    def __new__(cls, *args, **kwargs):
        """
        Реализация шаблона Singleton для класса WebDriverPool.
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(WebDriverPool, cls).__new__(cls)
            return cls._instance
    
    def __init__(self):
        """
        Инициализация пула веб-драйверов.
        """
        # Предотвращаем повторную инициализацию для Singleton
        if hasattr(self, 'initialized') and self.initialized:
            return
            
        self.logger = get_module_logger('core.web_driver_manager')
        self.logger.debug("Инициализация пула веб-драйверов")
        
        # Пул драйверов, хранит кортежи (драйвер, время последнего использования, busy флаг)
        self._drivers: List[Tuple[webdriver.Chrome, float, bool]] = []
        
        # Блокировка для управления пулом драйверов
        self._pool_lock = threading.RLock()
        
        # Настройки Chrome по умолчанию
        self._default_options = self._create_default_options()
        
        # Директория для временных файлов
        self._temp_dir = tempfile.mkdtemp(prefix="web_driver_")
        
        # Флаг инициализации
        self.initialized = True
        
        # Запускаем поток очистки устаревших драйверов
        self._start_cleanup_thread()
        
        self.logger.info("Пул веб-драйверов инициализирован")
    
    def _create_default_options(self) -> Options:
        """
        Создает опции Chrome по умолчанию.
        
        Returns:
            Options: Настройки Chrome по умолчанию
        """
        options = Options()
        # Добавляем стандартные аргументы для безголового режима
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--blink-settings=imagesEnabled=false')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36')
        
        return options
    
    def _start_cleanup_thread(self):
        """
        Запускает фоновый поток для очистки неиспользуемых драйверов.
        """
        cleanup_thread = threading.Thread(
            target=self._cleanup_drivers_worker, 
            name="WebDriverCleanup", 
            daemon=True
        )
        cleanup_thread.start()
        self.logger.debug("Запущен поток очистки драйверов")
    
    def _cleanup_drivers_worker(self):
        """
        Фоновый процесс для периодической очистки неиспользуемых драйверов.
        """
        while True:
            try:
                # Спим 2 минуты перед каждой проверкой
                time.sleep(120)
                
                # Очищаем неиспользуемые драйверы
                self._cleanup_idle_drivers()
            except Exception as e:
                self.logger.error(f"Ошибка в процессе очистки драйверов: {e}")
    
    def _cleanup_idle_drivers(self):
        """
        Очищает неиспользуемые драйверы на основе времени простоя.
        """
        current_time = time.time()
        drivers_to_close = []
        
        with self._pool_lock:
            # Находим все неиспользуемые драйверы
            for i, (driver, last_used, busy) in enumerate(self._drivers):
                # Закрываем только свободные драйверы с превышенным временем простоя
                if not busy and current_time - last_used > self.MAX_IDLE_TIME:
                    drivers_to_close.append((i, driver))
            
            # Закрываем и удаляем устаревшие драйверы (в обратном порядке для корректных индексов)
            for i, driver in reversed(drivers_to_close):
                try:
                    driver.quit()
                except Exception as e:
                    self.logger.warning(f"Ошибка при закрытии драйвера: {e}")
                
                # Удаляем драйвер из пула
                del self._drivers[i]
        
        if drivers_to_close:
            self.logger.debug(f"Очищено {len(drivers_to_close)} неиспользуемых драйверов")
    
    def get_driver(self, custom_options: Optional[Options] = None) -> webdriver.Chrome:
        """
        Получает свободный драйвер из пула или создает новый.
        
        Args:
            custom_options: Пользовательские опции Chrome
            
        Returns:
            webdriver.Chrome: Экземпляр Chrome WebDriver
        """
        with self._pool_lock:
            # Сначала ищем свободный драйвер в пуле
            for i, (driver, last_used, busy) in enumerate(self._drivers):
                if not busy:
                    # Помечаем драйвер как занятый
                    self._drivers[i] = (driver, time.time(), True)
                    self.logger.debug(f"Получен существующий драйвер из пула (индекс {i})")
                    return driver
            
            # Если пул переполнен, пытаемся закрыть свободные драйверы
            if len(self._drivers) >= self.MAX_POOL_SIZE:
                self._cleanup_idle_drivers()
            
            # Если все равно нет места, выбрасываем исключение
            if len(self._drivers) >= self.MAX_POOL_SIZE:
                raise RuntimeError(f"Пул веб-драйверов переполнен (максимум {self.MAX_POOL_SIZE})")
            
            # Создаем новый драйвер
            try:
                options = custom_options or self._default_options
                
                # Устанавливаем временную директорию для Chrome
                options.add_argument(f"--user-data-dir={os.path.join(self._temp_dir, f'profile_{len(self._drivers)}')}")
                
                # Создаем сервис
                service = Service(ChromeDriverManager().install())
                
                # Создаем драйвер
                driver = webdriver.Chrome(service=service, options=options)
                
                # Добавляем драйвер в пул
                self._drivers.append((driver, time.time(), True))
                
                self.logger.debug(f"Создан новый драйвер (всего в пуле: {len(self._drivers)})")
                return driver
            except Exception as e:
                self.logger.error(f"Ошибка при создании веб-драйвера: {e}")
                log_exception(self.logger, "Ошибка создания драйвера")
                raise
    
    def release_driver(self, driver: webdriver.Chrome):
        """
        Освобождает драйвер, возвращая его в пул.
        
        Args:
            driver: Драйвер для освобождения
        """
        with self._pool_lock:
            # Находим драйвер в пуле
            for i, (pool_driver, last_used, busy) in enumerate(self._drivers):
                if pool_driver == driver:
                    # Помечаем драйвер как свободный
                    self._drivers[i] = (driver, time.time(), False)
                    self.logger.debug(f"Драйвер освобожден (индекс {i})")
                    return
            
            # Если драйвер не найден, пытаемся закрыть его
            try:
                driver.quit()
                self.logger.warning("Драйвер не найден в пуле, закрыт принудительно")
            except Exception as e:
                self.logger.error(f"Ошибка при закрытии драйвера: {e}")
    
    def close_all_drivers(self):
        """
        Закрывает все драйверы в пуле.
        """
        with self._pool_lock:
            for driver, _, _ in self._drivers:
                try:
                    driver.quit()
                except Exception as e:
                    self.logger.warning(f"Ошибка при закрытии драйвера: {e}")
            
            # Очищаем пул
            self._drivers.clear()
        
        self.logger.debug("Все драйверы закрыты")
    
    def cleanup(self):
        """
        Очищает все ресурсы, включая драйверы и временные директории.
        """
        # Закрываем все драйверы
        self.close_all_drivers()
        
        # Удаляем временную директорию
        try:
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self.logger.debug(f"Временная директория удалена: {self._temp_dir}")
        except Exception as e:
            self.logger.error(f"Ошибка при удалении временной директории: {e}")


# Создаем синглтон пула драйверов
_driver_pool = WebDriverPool()


def get_driver_pool() -> WebDriverPool:
    """
    Получает глобальный экземпляр пула веб-драйверов.
    
    Returns:
        WebDriverPool: Глобальный экземпляр пула веб-драйверов
    """
    return _driver_pool


@contextlib.contextmanager
def driver_context(custom_options: Optional[Options] = None):
    """
    Контекстный менеджер для безопасного использования веб-драйвера.
    Автоматически освобождает драйвер при выходе из контекста.
    
    Args:
        custom_options: Пользовательские опции Chrome
        
    Yields:
        webdriver.Chrome: Экземпляр Chrome WebDriver
    """
    driver = None
    try:
        # Получаем драйвер из пула
        driver = get_driver_pool().get_driver(custom_options)
        
        # Передаем управление вызывающему коду
        yield driver
    finally:
        # Освобождаем драйвер, даже если произошло исключение
        if driver:
            try:
                # Сначала отменяем все текущие операции
                driver.execute_script("window.stop();")
            except Exception:
                pass
            
            # Возвращаем драйвер в пул
            get_driver_pool().release_driver(driver) 