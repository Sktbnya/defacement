import sys
import logging
import traceback
import threading
import datetime
import functools
import os
import inspect
import json
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List, Type, Tuple, Union

from utils.logger import get_module_logger, log_exception


class ErrorHandler:
    """
    Класс централизованной обработки ошибок в приложении.
    Позволяет регистрировать, логировать и обрабатывать различные типы ошибок.
    """
    
    # Уровни серьезности ошибок
    SEVERITY = {
        'CRITICAL': 50,  # Критическая ошибка, требующая немедленного внимания
        'HIGH': 40,      # Важная ошибка, требующая скорого решения
        'MEDIUM': 30,    # Ошибка среднего приоритета
        'LOW': 20,       # Незначительная ошибка
        'INFO': 10       # Информационное сообщение об ошибке
    }
    
    # Настройки обработки ошибок для разных сред
    ENVIRONMENT_SETTINGS = {
        'development': {
            'log_all_errors': True,           # Логировать все ошибки
            'show_full_traceback': True,      # Показывать полную трассировку
            'ignore_repeated_errors': False,  # Не игнорировать повторяющиеся ошибки
            'notification_threshold': 'LOW',  # Порог уведомлений
            'store_errors_count': 100         # Количество хранимых ошибок
        },
        'testing': {
            'log_all_errors': True,
            'show_full_traceback': True,
            'ignore_repeated_errors': True,
            'notification_threshold': 'MEDIUM',
            'store_errors_count': 50
        },
        'production': {
            'log_all_errors': False,
            'show_full_traceback': False,
            'ignore_repeated_errors': True,
            'notification_threshold': 'HIGH',
            'store_errors_count': 20
        }
    }
    
    def __init__(self, environment=None):
        """
        Инициализация обработчика ошибок
        
        Args:
            environment: Среда исполнения ('development', 'testing', 'production')
        """
        self.logger = get_module_logger('utils.error_handler')
        self.logger.debug("Инициализация централизованного обработчика ошибок")
        
        # Определение текущей среды исполнения
        self.environment = environment or os.environ.get('WDM_ENVIRONMENT', 'development')
        self.settings = self._load_settings()
        
        # Словарь для хранения обработчиков ошибок
        self._handlers = {}
        
        # Словарь для хранения настроек различных типов ошибок
        self._error_settings = {}
        
        # Блокировка для потокобезопасности
        self.lock = threading.RLock()
        
        # Количество обработанных ошибок
        self.errors_count = 0
        
        # Время последней ошибки
        self.last_error_time = None
        
        # Часто повторяющиеся ошибки (ключ - хеш ошибки, значение - информация о ней)
        self.frequent_errors = {}
        
        # История ошибок для анализа
        self.error_history = []
        self.max_history_size = self.settings.get('store_errors_count', 100)
        
        # Флаг для включения/отключения обработки ошибок
        self.enabled = True
        
        # Регистрируем стандартные обработчики
        self._register_default_handlers()
        
        self.logger.info(f"Обработчик ошибок инициализирован для среды: {self.environment}")
    
    def _load_settings(self) -> Dict[str, Any]:
        """
        Загрузка настроек обработчика ошибок из файла или использование стандартных
        
        Returns:
            Dict[str, Any]: Настройки обработчика ошибок
        """
        # Проверка наличия файла настроек
        base_dir = Path(__file__).parent.parent
        settings_file = base_dir / "config" / "error_handler_settings.json"
        
        if settings_file.exists():
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    custom_settings = json.load(f)
                
                if self.environment in custom_settings:
                    return custom_settings[self.environment]
            except Exception as e:
                self.logger.error(f"Ошибка при загрузке настроек обработчика ошибок: {e}")
        
        # Возвращаем стандартные настройки для выбранной среды
        return self.ENVIRONMENT_SETTINGS.get(self.environment, self.ENVIRONMENT_SETTINGS['development'])
    
    def register_handler(self, error_type: Type[Exception], handler: Callable[[Exception, Dict[str, Any]], None], 
                        severity: str = 'MEDIUM', notify: bool = False):
        """
        Регистрирует обработчик для определенного типа ошибок
        
        Args:
            error_type: Тип исключения
            handler: Функция-обработчик
            severity: Уровень серьезности ошибки ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO')
            notify: Отправлять ли уведомление при возникновении ошибки
        """
        with self.lock:
            self._handlers[error_type] = handler
            self._error_settings[error_type] = {
                'severity': severity,
                'count': 0,
                'last_time': None,
                'reported': False,
                'notify': notify
            }
            self.logger.debug(f"Зарегистрирован обработчик для {error_type.__name__}")
    
    def handle_error(self, exception: Exception, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Обработка ошибки с использованием подходящего обработчика
        
        Args:
            exception: Исключение
            context: Дополнительный контекст ошибки
            
        Returns:
            bool: True, если ошибка обработана успешно
        """
        if not self.enabled:
            return False
            
        if context is None:
            context = {}
            
        # Добавляем информацию о текущем потоке
        context['thread_id'] = threading.get_ident()
        context['thread_name'] = threading.current_thread().name
        
        # Добавляем временную метку
        current_time = datetime.datetime.now()
        context['timestamp'] = current_time
        
        # Добавляем трассировку
        exc_info = sys.exc_info()
        if self.settings.get('show_full_traceback', True):
            context['traceback'] = traceback.format_exception(*exc_info) if exc_info[0] else None
        else:
            # Сокращенная трассировка (только тип ошибки и сообщение)
            context['traceback'] = str(exception)
        
        # Обновляем статистику
        with self.lock:
            self.errors_count += 1
            self.last_error_time = current_time
            
            # Создаем запись об ошибке для истории
            error_record = {
                'error_type': type(exception).__name__,
                'message': str(exception),
                'timestamp': current_time,
                'context': context
            }
            
            # Добавляем в историю с ограничением размера
            self.error_history.append(error_record)
            if len(self.error_history) > self.max_history_size:
                self.error_history.pop(0)
            
            # Поиск подходящего обработчика
            handler = None
            error_class = None
            
            for ec in self._handlers:
                if isinstance(exception, ec):
                    handler = self._handlers[ec]
                    error_class = ec
                    break
            
            # Если не нашли конкретный обработчик, используем общий
            if handler is None and Exception in self._handlers:
                handler = self._handlers[Exception]
                error_class = Exception
            
            # Если нашли обработчик, обновляем статистику и выполняем его
            if error_class and handler:
                # Обновляем статистику для данного типа ошибки
                settings = self._error_settings[error_class]
                settings['count'] += 1
                settings['last_time'] = current_time
                
                # Проверяем, является ли ошибка часто повторяющейся
                is_frequent = self._check_frequent_error(error_class, exception)
                
                # Если это частая ошибка и мы должны игнорировать повторения
                if is_frequent and self.settings.get('ignore_repeated_errors', False):
                    return True
                
                # Проверяем, нужно ли отправлять уведомление
                if settings['notify'] and self._should_notify(settings['severity']):
                    self._send_notification(exception, context)
        
        # Вызываем обработчик, если нашли
        if handler:
            try:
                handler(exception, context)
                self.logger.debug(f"Ошибка {type(exception).__name__} обработана")
                return True
            except Exception as handler_error:
                self.logger.error(f"Ошибка в обработчике: {handler_error}")
                log_exception(self.logger, "Ошибка в обработчике ошибок")
                return False
        else:
            # Логируем ошибку, если нет подходящего обработчика
            if self.settings.get('log_all_errors', True):
                self.logger.error(f"Необработанная ошибка: {exception}")
                if 'traceback' in context and isinstance(context['traceback'], list):
                    self.logger.error("Трассировка:\n" + ''.join(context['traceback']))
                elif 'traceback' in context:
                    self.logger.error(f"Трассировка: {context['traceback']}")
            return False
    
    def _check_frequent_error(self, error_class: Type[Exception], exception: Exception) -> bool:
        """
        Проверяет, является ли ошибка часто повторяющейся
        
        Args:
            error_class: Класс ошибки
            exception: Экземпляр исключения
            
        Returns:
            bool: True, если ошибка часто повторяется
        """
        # Создаем уникальный идентификатор для ошибки на основе типа и сообщения
        error_key = f"{error_class.__name__}:{str(exception)}"
        
        # Получаем текущее время
        now = datetime.datetime.now()
        
        if error_key in self.frequent_errors:
            error_info = self.frequent_errors[error_key]
            
            # Проверяем, прошло ли меньше часа с момента последней такой ошибки
            time_diff = (now - error_info['last_time']).total_seconds()
            if time_diff < 3600:  # 1 час в секундах
                error_info['count'] += 1
                error_info['last_time'] = now
                
                # Если ошибка повторяется часто и еще не отмечена как частая
                if error_info['count'] >= 5 and not error_info['reported']:
                    error_info['reported'] = True
                    self.logger.warning(f"Обнаружена часто повторяющаяся ошибка: {error_key} ({error_info['count']} раз за час)")
                    
                    # Можно добавить дополнительные действия по обработке частых ошибок
                    # Например, отправка уведомления администратору
                    
                return True
            else:
                # Если прошло больше часа, сбрасываем счетчик
                error_info['count'] = 1
                error_info['last_time'] = now
                error_info['reported'] = False
                return False
        else:
            # Первое появление ошибки
            self.frequent_errors[error_key] = {
                'count': 1,
                'last_time': now,
                'reported': False
            }
            return False
    
    def _should_notify(self, severity: str) -> bool:
        """
        Проверяет, нужно ли отправлять уведомление для данного уровня серьезности
        
        Args:
            severity: Уровень серьезности ошибки
            
        Returns:
            bool: True, если нужно отправить уведомление
        """
        threshold = self.settings.get('notification_threshold', 'MEDIUM')
        threshold_level = self.SEVERITY.get(threshold, 30)
        severity_level = self.SEVERITY.get(severity, 0)
        
        return severity_level >= threshold_level
    
    def _send_notification(self, exception: Exception, context: Dict[str, Any]):
        """
        Отправляет уведомление об ошибке
        
        Args:
            exception: Исключение
            context: Контекст ошибки
        """
        # Здесь должна быть логика отправки уведомлений (email, SMS, webhook и т.д.)
        # Для простоты сейчас просто логируем это
        self.logger.warning(f"Отправка уведомления об ошибке: {type(exception).__name__}: {exception}")
        
        # В реальности здесь должен быть код для отправки уведомления:
        # - По email
        # - В мессенджер (Telegram, Slack и т.д.)
        # - На веб-хук
        # - В систему мониторинга (Sentry, New Relic и т.д.)
    
    def _register_default_handlers(self):
        """Регистрирует стандартные обработчики ошибок"""
        # Общий обработчик для всех исключений
        self.register_handler(Exception, self._default_exception_handler, 'MEDIUM')
        
        # Обработчик для ошибок ввода-вывода
        self.register_handler(IOError, self._io_error_handler, 'HIGH')
        
        # Обработчик для ошибок доступа
        self.register_handler(PermissionError, self._permission_error_handler, 'HIGH')
        
        # Обработчик для ошибок времени выполнения
        self.register_handler(RuntimeError, self._runtime_error_handler, 'MEDIUM')
        
        # Обработчик для ошибок сети
        self.register_handler(ConnectionError, self._connection_error_handler, 'HIGH', notify=True)
        
        # Обработчик для ошибок базы данных
        try:
            import sqlite3
            self.register_handler(sqlite3.Error, self._database_error_handler, 'HIGH', notify=True)
        except ImportError:
            pass
        
        self.logger.debug("Зарегистрированы стандартные обработчики ошибок")
    
    def _default_exception_handler(self, exception: Exception, context: Dict[str, Any]):
        """
        Стандартный обработчик исключений
        
        Args:
            exception: Исключение
            context: Контекст ошибки
        """
        self.logger.error(f"Исключение: {type(exception).__name__}: {exception}")
        
        if 'traceback' in context and context['traceback']:
            if isinstance(context['traceback'], list):
                traceback_str = ''.join(context['traceback'])
                self.logger.error(f"Трассировка:\n{traceback_str}")
            else:
                self.logger.error(f"Трассировка: {context['traceback']}")
    
    def _io_error_handler(self, exception: IOError, context: Dict[str, Any]):
        """
        Обработчик ошибок ввода-вывода
        
        Args:
            exception: Исключение
            context: Контекст ошибки
        """
        self.logger.error(f"Ошибка ввода-вывода: {exception}")
        
        # Дополнительная диагностика для ошибок ввода-вывода
        if hasattr(exception, 'filename'):
            self.logger.error(f"Файл: {exception.filename}")
        
        if 'traceback' in context and context['traceback']:
            if isinstance(context['traceback'], list):
                traceback_str = ''.join(context['traceback'])
                self.logger.error(f"Трассировка:\n{traceback_str}")
            else:
                self.logger.error(f"Трассировка: {context['traceback']}")
    
    def _permission_error_handler(self, exception: PermissionError, context: Dict[str, Any]):
        """
        Обработчик ошибок доступа
        
        Args:
            exception: Исключение
            context: Контекст ошибки
        """
        self.logger.error(f"Ошибка доступа: {exception}")
        
        # Дополнительная диагностика для ошибок доступа
        if hasattr(exception, 'filename'):
            self.logger.error(f"Файл: {exception.filename}")
        
        if 'traceback' in context and context['traceback']:
            if isinstance(context['traceback'], list):
                traceback_str = ''.join(context['traceback'])
                self.logger.error(f"Трассировка:\n{traceback_str}")
            else:
                self.logger.error(f"Трассировка: {context['traceback']}")
    
    def _runtime_error_handler(self, exception: RuntimeError, context: Dict[str, Any]):
        """
        Обработчик ошибок времени выполнения
        
        Args:
            exception: Исключение
            context: Контекст ошибки
        """
        self.logger.error(f"Ошибка времени выполнения: {exception}")
        
        if 'traceback' in context and context['traceback']:
            if isinstance(context['traceback'], list):
                traceback_str = ''.join(context['traceback'])
                self.logger.error(f"Трассировка:\n{traceback_str}")
            else:
                self.logger.error(f"Трассировка: {context['traceback']}")
    
    def _connection_error_handler(self, exception: ConnectionError, context: Dict[str, Any]):
        """
        Обработчик ошибок сети
        
        Args:
            exception: Исключение
            context: Контекст ошибки
        """
        self.logger.error(f"Ошибка сети: {exception}")
        
        # Дополнительная диагностика для сетевых ошибок
        if 'url' in context:
            self.logger.error(f"URL: {context['url']}")
        
        if 'traceback' in context and context['traceback']:
            if isinstance(context['traceback'], list):
                traceback_str = ''.join(context['traceback'])
                self.logger.error(f"Трассировка:\n{traceback_str}")
            else:
                self.logger.error(f"Трассировка: {context['traceback']}")
    
    def _database_error_handler(self, exception: Exception, context: Dict[str, Any]):
        """
        Обработчик ошибок базы данных
        
        Args:
            exception: Исключение
            context: Контекст ошибки
        """
        self.logger.error(f"Ошибка базы данных: {exception}")
        
        # Дополнительная диагностика для ошибок БД
        if 'query' in context:
            self.logger.error(f"Запрос: {context['query']}")
        if 'params' in context:
            self.logger.error(f"Параметры: {context['params']}")
        
        if 'traceback' in context and context['traceback']:
            if isinstance(context['traceback'], list):
                traceback_str = ''.join(context['traceback'])
                self.logger.error(f"Трассировка:\n{traceback_str}")
            else:
                self.logger.error(f"Трассировка: {context['traceback']}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Возвращает статистику обработки ошибок
        
        Returns:
            Dict[str, Any]: Статистика ошибок
        """
        with self.lock:
            stats = {
                'errors_count': self.errors_count,
                'last_error_time': self.last_error_time,
                'error_types': {},
                'frequent_errors': len(self.frequent_errors),
            }
            
            for error_type, settings in self._error_settings.items():
                stats['error_types'][error_type.__name__] = {
                    'count': settings['count'],
                    'last_time': settings['last_time'],
                    'severity': settings['severity']
                }
            
            return stats
    
    def reset_stats(self):
        """Сбрасывает статистику обработки ошибок"""
        with self.lock:
            self.errors_count = 0
            self.last_error_time = None
            self.frequent_errors.clear()
            self.error_history.clear()
            
            for error_type, settings in self._error_settings.items():
                settings['count'] = 0
                settings['last_time'] = None
                settings['reported'] = False
    
    def enable(self):
        """Включает обработку ошибок"""
        with self.lock:
            self.enabled = True
            self.logger.debug("Обработка ошибок включена")
    
    def disable(self):
        """Выключает обработку ошибок"""
        with self.lock:
            self.enabled = False
            self.logger.debug("Обработка ошибок выключена")
    
    def get_recent_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Возвращает список последних ошибок
        
        Args:
            limit: Максимальное количество ошибок
            
        Returns:
            List[Dict[str, Any]]: Список последних ошибок
        """
        with self.lock:
            return self.error_history[-limit:] if self.error_history else []


# Создаем глобальный экземпляр обработчика ошибок
_error_handler = ErrorHandler()


def get_error_handler() -> ErrorHandler:
    """
    Возвращает глобальный экземпляр обработчика ошибок
    
    Returns:
        ErrorHandler: Глобальный экземпляр обработчика ошибок
    """
    return _error_handler


def handle_error(exception: Exception, context: Optional[Dict[str, Any]] = None) -> bool:
    """
    Функция для удобного вызова обработчика ошибок
    
    Args:
        exception: Исключение
        context: Контекст ошибки
        
    Returns:
        bool: True, если ошибка обработана успешно
    """
    return get_error_handler().handle_error(exception, context)


def with_error_handling(func=None, *, retries=0, retry_delay=1, 
                     error_types=None, severity='MEDIUM', notify=False):
    """
    Декоратор для обработки исключений в функциях с дополнительными опциями.
    Поддерживает настройку повторных попыток, фильтрацию по типам ошибок и т.д.
    
    Args:
        func: Декорируемая функция
        retries: Количество повторных попыток при возникновении ошибки
        retry_delay: Задержка между повторными попытками в секундах
        error_types: Список типов ошибок, которые нужно обрабатывать
        severity: Уровень серьезности ошибки
        notify: Отправлять ли уведомление при возникновении ошибки
        
    Returns:
        Function: Декорированная функция с обработкой ошибок
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Получаем информацию о функции
            function_info = {
                'function': fn.__name__,
                'module': fn.__module__,
                'args': args,
                'kwargs': kwargs,
                'timestamp': datetime.datetime.now()
            }
            
            # Добавляем информацию о вызывающем коде
            caller_frame = inspect.currentframe().f_back
            if caller_frame:
                function_info['caller'] = {
                    'file': caller_frame.f_code.co_filename,
                    'line': caller_frame.f_lineno,
                    'function': caller_frame.f_code.co_name
                }
            
            # Попытка выполнения функции с повторными попытками
            for attempt in range(retries + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    # Проверяем, нужно ли обрабатывать этот тип ошибки
                    if error_types and not any(isinstance(e, et) for et in error_types):
                        raise
                    
                    # Добавляем информацию о попытке
                    function_info['attempt'] = attempt + 1
                    function_info['max_attempts'] = retries + 1
                    
                    # Обрабатываем ошибку
                    handler = get_error_handler()
                    handler.handle_error(e, function_info)
                    
                    # Если это последняя попытка, пробрасываем исключение дальше
                    if attempt >= retries:
                        raise
                    
                    # Ждем перед следующей попыткой
                    if retry_delay > 0:
                        import time
                        time.sleep(retry_delay)
            
            # Этот код не должен быть достигнут, но добавлен для полноты
            raise RuntimeError("Произошла необработанная ошибка")
        
        return wrapper
    
    # Поддержка вызова декоратора как с аргументами, так и без
    if func is None:
        return decorator
    return decorator(func)


def retry(retries=3, retry_delay=1, error_types=(Exception,)):
    """
    Декоратор для повторного выполнения функции при возникновении ошибки
    
    Args:
        retries: Количество повторных попыток
        retry_delay: Задержка между попытками в секундах
        error_types: Типы ошибок, которые нужно перехватывать
        
    Returns:
        Function: Декоратор для повторного выполнения функции
    """
    return with_error_handling(
        retries=retries,
        retry_delay=retry_delay,
        error_types=error_types
    )


def handle_errors(error_msg=None, notify=False, severity='MEDIUM'):
    """
    Декоратор для обработки ошибок в функциях с указанием сообщения
    
    Args:
        error_msg: Сообщение об ошибке
        notify: Отправлять ли уведомление при возникновении ошибки
        severity: Уровень серьезности ошибки
        
    Returns:
        Function: Декоратор для обработки ошибок
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Создаем контекст с информацией о функции
                context = {
                    'function': func.__name__,
                    'module': func.__module__,
                    'args': args,
                    'kwargs': kwargs,
                    'error_msg': error_msg,
                    'timestamp': datetime.datetime.now()
                }
                
                # Получаем информацию о вызывающем коде
                caller_frame = inspect.currentframe().f_back
                if caller_frame:
                    context['caller'] = {
                        'file': caller_frame.f_code.co_filename,
                        'line': caller_frame.f_lineno,
                        'function': caller_frame.f_code.co_name
                    }
                
                # Задаем контекст для обработчика
                handler = get_error_handler()
                handler.handle_error(e, context)
                
                # Логируем ошибку с указанным сообщением
                if error_msg:
                    logger = get_module_logger(func.__module__)
                    logger.error(f"{error_msg}: {e}")
                
                # Пробрасываем исключение дальше
                raise
        
        return wrapper
    
    return decorator 