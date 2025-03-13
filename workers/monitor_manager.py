#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль менеджера задач мониторинга для WDM_V12.
Отвечает за планирование и выполнение асинхронных задач проверки сайтов.
"""

import threading
import time
import datetime
import queue
import logging
import traceback
from typing import Dict, List, Tuple, Union, Optional, Any

# Внутренние импорты
from utils.logger import get_module_logger, log_exception
from core.web_monitor import WebMonitor
from config.config import get_config


class MonitorTask:
    """
    Класс задачи мониторинга.
    Содержит данные сайта и состояние задачи.
    """
    
    def __init__(self, site_data: Dict[str, Any]):
        """
        Инициализация задачи мониторинга
        
        Args:
            site_data: Данные сайта из БД
        """
        self.site_data = site_data
        self.id = site_data['id']
        self.url = site_data['url']
        self.name = site_data['name']
        
        # Состояние задачи
        self.status = 'pending'  # pending, running, completed, failed
        self.result = None
        self.error = None
        self.start_time = None
        self.end_time = None
        self.next_check_time = None
    
    def get_status(self) -> Dict[str, Any]:
        """
        Получение статуса задачи
        
        Returns:
            Dict[str, Any]: Статус задачи
        """
        return {
            'id': self.id,
            'url': self.url,
            'name': self.name,
            'status': self.status,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'next_check_time': self.next_check_time,
            'error': self.error
        }
    
    def mark_as_running(self):
        """Отмечает задачу как выполняемую"""
        self.status = 'running'
        self.start_time = datetime.datetime.now()
    
    def mark_as_completed(self, result: Dict[str, Any]):
        """
        Отмечает задачу как завершенную
        
        Args:
            result: Результат выполнения задачи
        """
        self.status = 'completed'
        self.end_time = datetime.datetime.now()
        self.result = result
        
        # Вычисление времени следующей проверки
        check_interval = self.site_data.get('check_interval', 3600)  # В секундах
        self.next_check_time = self.end_time + datetime.timedelta(seconds=check_interval)
    
    def mark_as_failed(self, error: str):
        """
        Отмечает задачу как завершенную с ошибкой
        
        Args:
            error: Сообщение об ошибке
        """
        self.status = 'failed'
        self.end_time = datetime.datetime.now()
        self.error = error
        
        # Вычисление времени следующей проверки
        check_interval = self.site_data.get('check_interval', 3600)  # В секундах
        self.next_check_time = self.end_time + datetime.timedelta(seconds=check_interval)


class MonitorWorker(threading.Thread):
    """
    Класс потока-работника для выполнения задач мониторинга.
    """
    
    def __init__(self, app_context, task_queue, result_queue, worker_id=None):
        """
        Инициализация работника
        
        Args:
            app_context: Контекст приложения
            task_queue: Очередь задач
            result_queue: Очередь результатов
            worker_id: Идентификатор работника
        """
        super().__init__()
        self.daemon = True  # Поток завершится при завершении основного потока
        
        self.worker_id = worker_id or f"worker-{threading.get_ident()}"
        self.logger = get_module_logger(f'workers.monitor_worker.{self.worker_id}')
        self.logger.debug(f"Инициализация работника {self.worker_id}")
        
        self.app_context = app_context
        self.config = get_config()
        self.task_queue = task_queue
        self.result_queue = result_queue
        
        # Флаг для остановки работника
        self.should_stop = threading.Event()
        
        # Монитор веб-сайтов
        self.web_monitor = WebMonitor(app_context)
        
        self.logger.debug(f"Работник {self.worker_id} инициализирован")
    
    def run(self):
        """Основной метод работника"""
        self.logger.info(f"Работник {self.worker_id} запущен")
        
        try:
            while not self.should_stop.is_set():
                try:
                    # Получаем задачу из очереди с таймаутом
                    task = self.task_queue.get(timeout=1.0)
                    
                    # Если задача - это специальный сигнал остановки
                    if task == "STOP":
                        self.logger.debug(f"Получен сигнал остановки для работника {self.worker_id}")
                        break
                    
                    # Выполняем задачу
                    self._process_task(task)
                    
                    # Отмечаем задачу как выполненную
                    self.task_queue.task_done()
                
                except queue.Empty:
                    # Если очередь пуста, просто продолжаем
                    continue
                
                except Exception as e:
                    self.logger.error(f"Ошибка в работнике {self.worker_id}: {e}")
                    log_exception(self.logger, "Ошибка в работнике")
        
        finally:
            # Освобождаем ресурсы
            self.logger.debug(f"Закрытие работника {self.worker_id}")
            self.web_monitor.close()
            self.logger.info(f"Работник {self.worker_id} остановлен")
    
    def _process_task(self, task: MonitorTask):
        """
        Обработка задачи мониторинга
        
        Args:
            task: Задача мониторинга
        """
        site_id = task.site_data['id']
        site_name = task.site_data['name']
        url = task.site_data['url']
        
        self.logger.info(f"Начало обработки задачи для сайта {site_name} ({url})")
        
        # Отмечаем задачу как выполняемую
        task.mark_as_running()
        
        try:
            # Проверка сайта
            result = self.web_monitor.check_site(task.site_data)
            
            # Сохранение результата в базу данных
            if result['success']:
                self._save_snapshot(site_id, result)
                
                # Если есть изменения и они превышают порог
                if result.get('diff_percent') is not None:
                    threshold = self.config['monitoring']['diff_threshold_percent']
                    if result['diff_percent'] > threshold:
                        # Сохраняем информацию об изменениях
                        self._save_changes(site_id, result)
                
                # Отмечаем задачу как успешно завершенную
                task.mark_as_completed(result)
                self.logger.info(f"Задача для сайта {site_name} выполнена успешно")
            else:
                # Сохраняем информацию об ошибке
                self._save_error(site_id, result['error'])
                
                # Отмечаем задачу как завершенную с ошибкой
                task.mark_as_failed(result['error'])
                self.logger.warning(f"Задача для сайта {site_name} завершена с ошибкой: {result['error']}")
            
            # Помещаем результат в очередь результатов
            self.result_queue.put(task)
        
        except Exception as e:
            error_message = f"Исключение при обработке задачи: {e}"
            self.logger.error(error_message)
            log_exception(self.logger, "Исключение при обработке задачи")
            
            # Отмечаем задачу как завершенную с ошибкой
            task.mark_as_failed(error_message)
            
            # Помещаем результат в очередь результатов
            self.result_queue.put(task)
    
    def _save_snapshot(self, site_id: int, result: Dict[str, Any]):
        """
        Сохранение снимка сайта в базу данных
        
        Args:
            site_id: ID сайта
            result: Результат проверки сайта
        """
        try:
            query = """
            INSERT INTO snapshots (
                site_id, timestamp, content_hash, content_path, 
                screenshot_path, content_size, content_type, 
                diff_percent, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            params = (
                site_id,
                result['timestamp'],
                result['content_hash'],
                result['content_path'],
                result.get('screenshot_path'),
                result.get('content_size'),
                'html',  # Тип контента
                result.get('diff_percent'),
                'success'
            )
            
            self.app_context.execute_db_query(query, params)
            self.logger.debug(f"Снимок для сайта ID={site_id} сохранен в базу данных")
            
            # Обновляем время последней проверки и изменения сайта
            self._update_site_check_time(site_id, result)
        
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении снимка в базу данных: {e}")
            log_exception(self.logger, "Ошибка сохранения снимка")
    
    def _save_changes(self, site_id: int, result: Dict[str, Any]):
        """
        Сохранение информации об изменениях в базу данных
        
        Args:
            site_id: ID сайта
            result: Результат проверки сайта
        """
        try:
            # Получаем ID последнего снимка
            snapshot_query = """
            SELECT id FROM snapshots 
            WHERE site_id = ? 
            ORDER BY timestamp DESC 
            LIMIT 1
            """
            
            snapshot_result = self.app_context.execute_db_query(snapshot_query, (site_id,))
            if not snapshot_result:
                self.logger.warning(f"Не удалось найти последний снимок для сайта ID={site_id}")
                return
            
            new_snapshot_id = snapshot_result[0]['id']
            
            # Получаем ID предпоследнего снимка
            old_snapshot_query = """
            SELECT id FROM snapshots 
            WHERE site_id = ? AND id != ?
            ORDER BY timestamp DESC 
            LIMIT 1
            """
            
            old_snapshot_result = self.app_context.execute_db_query(
                old_snapshot_query, (site_id, new_snapshot_id)
            )
            
            old_snapshot_id = old_snapshot_result[0]['id'] if old_snapshot_result else None
            
            # Сохраняем информацию об изменениях
            changes_query = """
            INSERT INTO changes (
                site_id, old_snapshot_id, new_snapshot_id, 
                timestamp, diff_percent, diff_details, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            
            import json
            diff_details = json.dumps(result.get('changes', {}), ensure_ascii=False)
            
            params = (
                site_id,
                old_snapshot_id,
                new_snapshot_id,
                result['timestamp'],
                result.get('diff_percent'),
                diff_details,
                'unread'  # Статус "не просмотрено"
            )
            
            self.app_context.execute_db_query(changes_query, params)
            self.logger.debug(f"Информация об изменениях для сайта ID={site_id} сохранена в базу данных")
            
            # Увеличиваем счетчик изменений в статусе приложения
            status = self.app_context.get_status()
            self.app_context.update_status(
                changed_sites_count=status.get('changed_sites_count', 0) + 1
            )
        
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении информации об изменениях: {e}")
            log_exception(self.logger, "Ошибка сохранения информации об изменениях")
    
    def _save_error(self, site_id: int, error_message: str):
        """
        Сохранение информации об ошибке в базу данных
        
        Args:
            site_id: ID сайта
            error_message: Сообщение об ошибке
        """
        try:
            # Создаем запись о снимке с ошибкой
            query = """
            INSERT INTO snapshots (
                site_id, timestamp, status, error_message
            ) VALUES (?, ?, ?, ?)
            """
            
            params = (
                site_id,
                datetime.datetime.now(),
                'error',
                error_message
            )
            
            self.app_context.execute_db_query(query, params)
            self.logger.debug(f"Информация об ошибке для сайта ID={site_id} сохранена в базу данных")
            
            # Увеличиваем счетчик ошибок в статусе приложения
            status = self.app_context.get_status()
            self.app_context.update_status(
                error_count=status.get('error_count', 0) + 1
            )
            
            # Обновляем время последней проверки сайта
            self._update_site_check_time(site_id, {'timestamp': datetime.datetime.now()})
        
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении информации об ошибке: {e}")
            log_exception(self.logger, "Ошибка сохранения информации об ошибке")
    
    def _update_site_check_time(self, site_id: int, result: Dict[str, Any]):
        """
        Обновление времени последней проверки и изменения сайта
        
        Args:
            site_id: ID сайта
            result: Результат проверки сайта
        """
        try:
            # Обновляем время последней проверки
            update_query = """
            UPDATE sites 
            SET last_check = ?
            WHERE id = ?
            """
            
            self.app_context.execute_db_query(
                update_query, (result['timestamp'], site_id)
            )
            
            # Если есть изменения и они превышают порог, обновляем время последнего изменения
            if result.get('diff_percent') is not None:
                threshold = self.config['monitoring']['diff_threshold_percent']
                if result['diff_percent'] > threshold:
                    update_query = """
                    UPDATE sites 
                    SET last_change = ?
                    WHERE id = ?
                    """
                    
                    self.app_context.execute_db_query(
                        update_query, (result['timestamp'], site_id)
                    )
                    
                    self.logger.debug(f"Время последнего изменения сайта ID={site_id} обновлено")
            
            self.logger.debug(f"Время последней проверки сайта ID={site_id} обновлено")
        
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении времени проверки сайта: {e}")
            log_exception(self.logger, "Ошибка обновления времени проверки")
    
    def stop(self):
        """Остановка работника"""
        self.logger.debug(f"Запрос на остановку работника {self.worker_id}")
        self.should_stop.set()


class MonitorManager:
    """
    Менеджер задач мониторинга.
    Отвечает за планирование и выполнение задач проверки сайтов.
    """
    
    def __init__(self, app_context):
        """
        Инициализация менеджера задач
        
        Args:
            app_context: Контекст приложения
        """
        self.logger = get_module_logger('workers.monitor_manager')
        self.logger.debug("Инициализация менеджера задач мониторинга")
        
        self.app_context = app_context
        self.config = get_config()
        
        # Очереди для задач и результатов
        self.task_queue = queue.Queue()
        self.result_queue = queue.Queue()
        
        # Пул работников
        self.workers = []
        self.worker_contexts = []  # Список контекстных менеджеров работников
        self.max_workers = self.config['monitoring']['max_workers']
        
        # Словарь задач (ключ - ID сайта, значение - задача)
        self.tasks = {}
        
        # Флаг активности мониторинга
        self.is_active = False
        
        # Поток обработки результатов
        self.result_thread = None
        
        # Поток планирования задач
        self.scheduler_thread = None
        
        # Блокировка для потокобезопасного доступа к данным
        self.lock = threading.RLock()
        
        # Событие для остановки потоков
        self.stop_event = threading.Event()
        
        self.logger.debug("Менеджер задач мониторинга инициализирован")
    
    def start(self):
        """Запуск менеджера задач"""
        start_time = time.time()
        start_id = f"start_{int(time.time())}"
        self.logger.debug(f"Запуск менеджера задач [{start_id}] начат")
        
        if self.is_active:
            self.logger.warning(f"Попытка запуска уже активного менеджера задач [{start_id}]")
            return True  # Считаем, что менеджер уже успешно запущен
        
        try:
            self.logger.info(f"Запуск менеджера задач мониторинга [{start_id}]")
            
            # Проверяем состояние перед запуском
            if self.workers:
                self.logger.warning(f"Обнаружены работники ({len(self.workers)}) при неактивном менеджере, очищаем список")
                self.workers.clear()
            
            if self.worker_contexts:
                self.logger.warning(f"Обнаружены контексты работников ({len(self.worker_contexts)}) при неактивном менеджере, очищаем список")
                self.worker_contexts.clear()
            
            # Проверяем очереди
            if not self.task_queue.empty() or not self.result_queue.empty():
                self.logger.warning(f"Обнаружены незавершенные задачи при запуске менеджера [{start_id}], очищаем очереди")
                
                # Очищаем очереди
                try:
                    while not self.task_queue.empty():
                        self.task_queue.get_nowait()
                        self.task_queue.task_done()
                except Exception as queue_err:
                    self.logger.error(f"Ошибка при очистке очереди задач: {queue_err}")
                
                try:
                    while not self.result_queue.empty():
                        self.result_queue.get_nowait()
                except Exception as queue_err:
                    self.logger.error(f"Ошибка при очистке очереди результатов: {queue_err}")
            
            # Сбрасываем событие остановки
            self.stop_event.clear()
            
            # Создаем и запускаем работников, используя контекстный менеджер
            worker_start_errors = 0
            for i in range(self.max_workers):
                try:
                    # Используем контекстный менеджер для создания работника
                    worker_ctx = WorkerContextManager(
                        self.app_context, 
                        self.task_queue, 
                        self.result_queue, 
                        worker_id=f"worker-{i+1}"
                    )
                    # Входим в контекст и получаем работника
                    worker = worker_ctx.__enter__()
                    self.workers.append(worker)
                    self.worker_contexts.append(worker_ctx)  # Сохраняем контекстный менеджер
                    self.logger.debug(f"Запущен работник {worker.worker_id} через контекстный менеджер")
                except Exception as worker_err:
                    self.logger.error(f"Ошибка при создании и запуске работника #{i+1}: {worker_err}")
                    worker_start_errors += 1
                    
            # Проверяем, удалось ли запустить хотя бы одного работника
            if not self.workers:
                self.logger.error(f"Не удалось запустить ни одного работника, запуск менеджера [{start_id}] отменен")
                return False
                
            if worker_start_errors > 0:
                self.logger.warning(f"Не удалось запустить {worker_start_errors} из {self.max_workers} работников")
            
            # Запускаем поток обработки результатов
            try:
                self.result_thread = threading.Thread(
                    target=self._process_results,
                    name="result-processor"
                )
                self.result_thread.daemon = True
                self.result_thread.start()
                self.logger.debug("Запущен поток обработки результатов")
            except Exception as result_thread_err:
                self.logger.error(f"Ошибка при запуске потока обработки результатов: {result_thread_err}")
                log_exception(self.logger, "Ошибка запуска потока обработки результатов")
                self.stop()
                return False
            
            # Запускаем поток планирования задач
            try:
                self.scheduler_thread = threading.Thread(
                    target=self._schedule_tasks,
                    name="task-scheduler"
                )
                self.scheduler_thread.daemon = True
                self.scheduler_thread.start()
                self.logger.debug("Запущен поток планирования задач")
            except Exception as scheduler_thread_err:
                self.logger.error(f"Ошибка при запуске потока планирования задач: {scheduler_thread_err}")
                log_exception(self.logger, "Ошибка запуска потока планирования задач")
                self.stop()
                return False
            
            # Обновляем флаг активности и статус приложения
            self.is_active = True
            self.app_context.update_status(
                monitoring_active=True,
                active_workers=len(self.workers),
                max_workers=self.max_workers,
                last_start_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            
            # Логируем время запуска
            execution_time = time.time() - start_time
            self.logger.info(f"Менеджер задач мониторинга запущен успешно [{start_id}] за {execution_time:.3f} сек")
            return True
        
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Ошибка при запуске менеджера задач [{start_id}] (время: {execution_time:.3f} сек): {e}")
            log_exception(self.logger, f"Ошибка запуска менеджера задач [{start_id}]")
            # Пытаемся остановить частично запущенные компоненты
            try:
                self.stop()
            except Exception as stop_err:
                self.logger.error(f"Ошибка при остановке частично запущенного менеджера: {stop_err}")
            return False
    
    def stop(self):
        """Остановка менеджера задач"""
        start_time = time.time()
        stop_id = f"stop_{int(time.time())}"
        self.logger.debug(f"Остановка менеджера задач [{stop_id}] начата")
        
        if not self.is_active and not self.workers and not self.result_thread and not self.scheduler_thread:
            self.logger.warning(f"Попытка остановки неактивного менеджера задач [{stop_id}]")
            return True  # Считаем, что менеджер уже успешно остановлен
        
        try:
            self.logger.info(f"Остановка менеджера задач мониторинга [{stop_id}]")
            
            # Обновляем флаг активности в начале процесса остановки
            # Это предотвратит добавление новых задач во время остановки
            was_active = self.is_active
            self.is_active = False
            
            # Устанавливаем событие остановки
            self.stop_event.set()
            
            # Добавляем сигналы остановки в очередь задач для работников
            worker_count = len(self.workers)
            if worker_count > 0:
                try:
                    for _ in range(worker_count):
                        self.task_queue.put("STOP")
                except Exception as stop_signal_err:
                    self.logger.error(f"Ошибка при добавлении сигналов остановки: {stop_signal_err}")
            
            # Используем контекстные менеджеры для корректного завершения работников
            worker_errors = 0
            
            # Сначала пытаемся остановить через контекстный менеджер
            for worker_ctx in list(self.worker_contexts):
                try:
                    # Если у контекстного менеджера есть связанный работник
                    if worker_ctx.worker:
                        worker_id = worker_ctx.worker.worker_id
                        self.logger.debug(f"Остановка работника {worker_id} через контекстный менеджер")
                        # Вызываем метод выхода из контекста
                        worker_ctx.__exit__(None, None, None)
                except Exception as worker_err:
                    self.logger.error(f"Ошибка при остановке работника через контекстный менеджер: {worker_err}")
                    worker_errors += 1
            
            # Очищаем списки работников и контекстных менеджеров
            self.workers.clear()
            self.worker_contexts.clear()
            
            # Ожидаем завершения потока обработки результатов
            if self.result_thread and self.result_thread.is_alive():
                try:
                    self.result_thread.join(timeout=3.0)
                    if self.result_thread.is_alive():
                        self.logger.warning(f"Поток обработки результатов не завершился за отведенное время [{stop_id}]")
                except Exception as result_thread_err:
                    self.logger.error(f"Ошибка при ожидании завершения потока обработки результатов: {result_thread_err}")
            
            # Ожидаем завершения потока планирования задач
            if self.scheduler_thread and self.scheduler_thread.is_alive():
                try:
                    self.scheduler_thread.join(timeout=3.0)
                    if self.scheduler_thread.is_alive():
                        self.logger.warning(f"Поток планирования задач не завершился за отведенное время [{stop_id}]")
                except Exception as scheduler_thread_err:
                    self.logger.error(f"Ошибка при ожидании завершения потока планирования задач: {scheduler_thread_err}")
            
            # Сбрасываем ссылки на потоки
            self.result_thread = None
            self.scheduler_thread = None
            
            # Очищаем очереди
            queue_errors = 0
            try:
                queue_items_removed = 0
                while not self.task_queue.empty():
                    try:
                        self.task_queue.get_nowait()
                        self.task_queue.task_done()
                        queue_items_removed += 1
                    except queue.Empty:
                        break
                if queue_items_removed > 0:
                    self.logger.debug(f"Удалено {queue_items_removed} задач из очереди задач")
            except Exception as task_queue_err:
                self.logger.error(f"Ошибка при очистке очереди задач: {task_queue_err}")
                queue_errors += 1
            
            try:
                result_items_removed = 0
                while not self.result_queue.empty():
                    try:
                        self.result_queue.get_nowait()
                        result_items_removed += 1
                    except queue.Empty:
                        break
                if result_items_removed > 0:
                    self.logger.debug(f"Удалено {result_items_removed} задач из очереди результатов")
            except Exception as result_queue_err:
                self.logger.error(f"Ошибка при очистке очереди результатов: {result_queue_err}")
                queue_errors += 1
            
            # Очищаем словарь задач
            task_count = 0
            with self.lock:
                task_count = len(self.tasks)
                self.tasks.clear()
            
            if task_count > 0:
                self.logger.debug(f"Очищено {task_count} задач из словаря задач")
            
            # Обновляем статус приложения
            self.app_context.update_status(
                monitoring_active=False,
                active_workers=0,
                last_stop_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            
            # Подводим итоги остановки
            execution_time = time.time() - start_time
            if worker_errors > 0:
                self.logger.warning(
                    f"Менеджер задач мониторинга остановлен с предупреждениями [{stop_id}] за {execution_time:.3f} сек. "
                    f"Ошибки работников: {worker_errors}"
                )
            else:
                self.logger.info(f"Менеджер задач мониторинга остановлен успешно [{stop_id}] за {execution_time:.3f} сек")
            
            return True
        
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Критическая ошибка при остановке менеджера задач [{stop_id}] (время: {execution_time:.3f} сек): {e}")
            log_exception(self.logger, f"Критическая ошибка остановки менеджера задач [{stop_id}]")
            
            # В случае критической ошибки принудительно сбрасываем состояние
            self.is_active = False
            self.workers.clear()
            self.result_thread = None
            self.scheduler_thread = None
            self.app_context.update_status(monitoring_active=False)
            
            return False
    
    def check_now(self, site_id=None):
        """
        Запрос на немедленную проверку сайта
        
        Args:
            site_id: ID сайта для проверки (если None, проверяются все сайты)
            
        Returns:
            bool: Результат выполнения запроса
        """
        start_time = time.time()
        check_id = f"check_{int(time.time())}"
        self.logger.debug(f"Запрос проверки [{check_id}] стартовал")
        
        try:
            # Проверка текущего размера очереди и количества активных задач
            queue_size = self.task_queue.qsize()
            active_tasks = self.get_active_tasks_count()
            
            # Проверка активности менеджера
            if not self.is_active:
                self.logger.warning(f"Попытка запроса проверки [{check_id}] при неактивном менеджере задач")
                return False
            
            # Проверка перегрузки системы
            if queue_size > 1000:  # Установите здесь подходящий лимит для вашей системы
                self.logger.warning(f"Очередь задач слишком большая ({queue_size}), запрос проверки [{check_id}] отклонен")
                return False
            
            # Если указан ID сайта, проверяем его корректность
            if site_id is not None:
                # Проверяем тип данных ID
                if not isinstance(site_id, (int, str)):
                    self.logger.error(f"Некорректный тип данных ID сайта: {type(site_id)}, запрос проверки [{check_id}] отклонен")
                    return False
                
                # Преобразуем ID в целое число, если это строка
                if isinstance(site_id, str):
                    try:
                        site_id = int(site_id)
                    except ValueError:
                        self.logger.error(f"Некорректный формат ID сайта: {site_id}, запрос проверки [{check_id}] отклонен")
                        return False
                
                # Проверка конкретного сайта
                site_data = self._get_site_data(site_id)
                if not site_data:
                    self.logger.warning(f"Сайт с ID={site_id} не найден, запрос проверки [{check_id}] отклонен")
                    return False
                
                # Проверка статуса сайта
                if site_data.get('status') != 'active':
                    self.logger.warning(f"Сайт {site_data.get('name', '')} (ID={site_id}) не активен, запрос проверки [{check_id}] отклонен")
                    return False
                
                # Проверка наличия необходимых полей
                required_fields = ['id', 'name', 'url']
                missing_fields = [field for field in required_fields if field not in site_data]
                if missing_fields:
                    self.logger.warning(f"В данных сайта ID={site_id} отсутствуют обязательные поля: {missing_fields}, запрос проверки [{check_id}] отклонен")
                    return False
                
                # Проверка наличия уже выполняющейся задачи
                with self.lock:
                    existing_task = self.tasks.get(site_id)
                    if existing_task and hasattr(existing_task, 'status') and existing_task.status == 'running':
                        self.logger.warning(f"Для сайта {site_data['name']} (ID={site_id}) уже выполняется задача, запрос проверки [{check_id}] отклонен")
                        return False
                
                self.logger.info(f"Запрос на немедленную проверку сайта {site_data['name']} (ID={site_id}) [{check_id}]")
                
                try:
                    # Создаем и добавляем задачу в очередь
                    task = MonitorTask(site_data)
                    with self.lock:
                        # Сохраняем задачу в словаре задач
                        self.tasks[site_id] = task
                    # Добавляем в очередь задач
                    self.task_queue.put(task)
                    
                    # Логируем успешное выполнение и возвращаем результат
                    execution_time = time.time() - start_time
                    self.logger.debug(f"Запрос проверки [{check_id}] выполнен за {execution_time:.3f} сек")
                    return True
                except Exception as task_e:
                    self.logger.error(f"Ошибка при создании или добавлении задачи: {task_e}, запрос проверки [{check_id}] не выполнен")
                    log_exception(self.logger, f"Ошибка создания задачи [{check_id}]")
                    return False
            else:
                # Проверка всех активных сайтов
                self.logger.info(f"Запрос на немедленную проверку всех сайтов [{check_id}]")
                result = self._queue_all_sites()
                
                # Логируем результат и время выполнения
                execution_time = time.time() - start_time
                if result:
                    self.logger.debug(f"Запрос проверки всех сайтов [{check_id}] выполнен за {execution_time:.3f} сек")
                else:
                    self.logger.warning(f"Запрос проверки всех сайтов [{check_id}] не выполнен, затрачено {execution_time:.3f} сек")
                
                return result
        
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Ошибка при запросе проверки [{check_id}] (время: {execution_time:.3f} сек): {e}")
            log_exception(self.logger, f"Ошибка запроса проверки [{check_id}]")
            return False
    
    def get_active_tasks_count(self):
        """
        Получение количества активных задач
        
        Returns:
            int: Количество активных задач
        """
        try:
            self.logger.debug("Получение количества активных задач")
            active_count = 0
            invalid_count = 0
            
            with self.lock:
                if not self.tasks:
                    return 0
                    
                for site_id, task in list(self.tasks.items()):
                    try:
                        # Проверяем валидность задачи
                        if not isinstance(task, MonitorTask):
                            self.logger.warning(f"Невалидная задача для сайта ID={site_id}, тип: {type(task)}")
                            invalid_count += 1
                            continue
                            
                        # Проверяем наличие атрибута status
                        if not hasattr(task, 'status'):
                            self.logger.warning(f"Задача для сайта ID={site_id} не имеет атрибута status")
                            invalid_count += 1
                            continue
                            
                        # Проверяем статус задачи
                        if task.status == 'running':
                            active_count += 1
                    except Exception as task_error:
                        self.logger.error(f"Ошибка при проверке задачи для сайта ID={site_id}: {task_error}")
                        invalid_count += 1
            
            # Логируем, если есть невалидные задачи
            if invalid_count > 0:
                self.logger.warning(f"Обнаружено {invalid_count} невалидных задач при подсчете активных задач")
                
            return active_count
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении количества активных задач: {e}")
            log_exception(self.logger, "Ошибка получения количества активных задач")
            return 0
    
    def get_tasks_status(self):
        """
        Получение статуса всех задач
        
        Returns:
            List[Dict[str, Any]]: Список статусов задач
        """
        try:
            self.logger.debug("Получение статуса всех задач")
            
            # Сохраняем текущее количество задач для логирования
            tasks_count = 0
            tasks_by_status = {}
            invalid_tasks = 0
            
            # Получаем статусы задач с защитой от ошибок
            task_statuses = []
            
            with self.lock:
                tasks_count = len(self.tasks)
                
                for site_id, task in list(self.tasks.items()):
                    try:
                        # Проверяем валидность задачи
                        if not isinstance(task, MonitorTask):
                            self.logger.warning(f"Обнаружена невалидная задача для сайта ID={site_id}, тип: {type(task)}")
                            invalid_tasks += 1
                            continue
                            
                        # Проверяем метод get_status
                        if not hasattr(task, 'get_status') or not callable(getattr(task, 'get_status')):
                            self.logger.warning(f"Задача для сайта ID={site_id} не имеет метода get_status")
                            invalid_tasks += 1
                            continue
                            
                        # Получаем статус задачи
                        status_data = task.get_status()
                        
                        # Добавляем дополнительную информацию
                        if hasattr(task, 'status'):
                            # Обновляем счетчик по статусам
                            if task.status not in tasks_by_status:
                                tasks_by_status[task.status] = 0
                            tasks_by_status[task.status] += 1
                            
                            # Добавляем временные метки в строковом формате для удобства
                            if hasattr(task, 'start_time') and task.start_time:
                                status_data['start_time_str'] = task.start_time.strftime('%Y-%m-%d %H:%M:%S')
                                
                            if hasattr(task, 'end_time') and task.end_time:
                                status_data['end_time_str'] = task.end_time.strftime('%Y-%m-%d %H:%M:%S')
                                
                            if hasattr(task, 'next_check_time') and task.next_check_time:
                                status_data['next_check_time_str'] = task.next_check_time.strftime('%Y-%m-%d %H:%M:%S')
                                
                                # Добавляем время до следующей проверки в секундах
                                time_to_next = (task.next_check_time - datetime.datetime.now()).total_seconds()
                                status_data['time_to_next_check'] = max(0, int(time_to_next))
                            
                            # Добавляем время выполнения, если доступно
                            if hasattr(task, 'start_time') and hasattr(task, 'end_time') and task.start_time and task.end_time:
                                execution_time = (task.end_time - task.start_time).total_seconds()
                                status_data['execution_time'] = round(execution_time, 2)
                        
                        task_statuses.append(status_data)
                    except Exception as task_error:
                        self.logger.error(f"Ошибка при получении статуса задачи для сайта ID={site_id}: {task_error}")
                        invalid_tasks += 1
            
            # Логируем результаты
            self.logger.debug(f"Получены статусы задач: всего - {tasks_count}, обработано - {len(task_statuses)}, невалидных - {invalid_tasks}")
            if tasks_by_status:
                status_info = ", ".join([f"{status}: {count}" for status, count in tasks_by_status.items()])
                self.logger.debug(f"Распределение задач по статусам: {status_info}")
                
            return task_statuses
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении статуса задач: {e}")
            log_exception(self.logger, "Ошибка получения статуса задач")
            return []
    
    def _process_results(self):
        """Обработка результатов от работников"""
        process_id = f"process_{int(time.time())}"
        self.logger.debug(f"Запуск обработчика результатов [{process_id}]")
        
        # Счетчики для статистики
        processed_count = 0
        successful_count = 0
        error_count = 0
        last_stats_time = time.time()
        stats_interval = 100  # Логировать каждые 100 обработанных результатов
        hourly_log_time = time.time() + 3600  # Логировать общую статистику каждый час
        
        try:
            while not self.stop_event.is_set():
                try:
                    # Получаем результат из очереди с таймаутом для возможности проверки флага остановки
                    try:
                        result = self.result_queue.get(timeout=1.0)
                        processed_count += 1
                    except queue.Empty:
                        # Пауза перед следующей попыткой чтения из очереди
                        time.sleep(0.1)
                        continue
                    
                    # Преобразуем объект задачи в словарь, если это объект MonitorTask
                    if isinstance(result, MonitorTask):
                        task_dict = {
                            'id': result.id,
                            'status': result.status,
                            'site_name': result.name,
                            'error': result.error,
                            'start_time': result.start_time,
                            'end_time': result.end_time
                        }
                        result = task_dict
                    
                    # Проверяем, что результат содержит необходимые поля
                    if not isinstance(result, dict):
                        self.logger.warning(f"Получен невалидный результат (не словарь): {type(result)} [{process_id}]")
                        error_count += 1
                        continue
                    
                    # Проверяем основные атрибуты результата
                    task_id = result.get('id')
                    if not task_id:
                        self.logger.warning(f"Получен результат без ID задачи: {result} [{process_id}]")
                        error_count += 1
                        continue
                    
                    # Проверяем, что task_id является целым числом (ID сайта)
                    try:
                        site_id = int(task_id)
                    except (ValueError, TypeError):
                        self.logger.warning(f"Некорректный ID задачи: {task_id} [{process_id}]")
                        error_count += 1
                        continue
                    
                    # Получаем статус выполнения задачи
                    status = result.get('status')
                    if not status:
                        self.logger.warning(f"Получен результат без статуса для задачи {task_id} [{process_id}]")
                        error_count += 1
                        continue
                    
                    # Обновляем статус задачи в словаре
                    with self.lock:
                        if site_id in self.tasks:
                            # Обновляем статус
                            self.tasks[site_id].status = status
                            
                            # Учитываем успешные и неуспешные задачи
                            if status == 'completed':
                                successful_count += 1
                                self.logger.debug(f"Задача ID={site_id} выполнена успешно [{process_id}]")
                            elif status == 'failed':
                                error_count += 1
                                error_message = result.get('error', 'Неизвестная ошибка')
                                self.logger.error(f"Задача ID={site_id} завершилась с ошибкой: {error_message} [{process_id}]")
                            
                            # Вычисляем и логируем время выполнения задачи, если есть метки времени
                            start_time = result.get('start_time')
                            end_time = result.get('end_time')
                            if start_time and end_time:
                                execution_time = end_time - start_time
                                self.logger.debug(f"Время выполнения задачи ID={site_id}: {execution_time:.3f} сек [{process_id}]")
                        else:
                            self.logger.warning(f"Получен результат для несуществующей задачи ID={site_id} [{process_id}]")
                    
                    # Обновляем статус в контексте приложения
                    site_name = result.get('site_name', f'ID={site_id}')
                    last_check_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    self.app_context.update_status(
                        last_check=last_check_time,
                        last_site_name=site_name,
                        last_site_id=site_id,
                        last_site_status=status
                    )
                    
                    # Периодически логируем статистику
                    if processed_count % stats_interval == 0:
                        current_time = time.time()
                        duration = current_time - last_stats_time
                        rate = stats_interval / duration if duration > 0 else 0
                        self.logger.info(
                            f"Обработка результатов [{process_id}]: "
                            f"всего={processed_count}, успешных={successful_count}, "
                            f"ошибок={error_count}, скорость={rate:.2f} задач/сек"
                        )
                        last_stats_time = current_time
                    
                    # Логируем итоговую статистику каждый час
                    current_time = time.time()
                    if current_time >= hourly_log_time:
                        self.logger.info(
                            f"Статистика обработки за час [{process_id}]: "
                            f"всего={processed_count}, успешных={successful_count}, ошибок={error_count}"
                        )
                        hourly_log_time = current_time + 3600  # Следующий лог через час
                
                except Exception as result_error:
                    self.logger.error(f"Ошибка при обработке результата [{process_id}]: {result_error}")
                    log_exception(self.logger, f"Ошибка обработки результата [{process_id}]")
                    error_count += 1
                    # Короткая пауза перед продолжением
                    time.sleep(0.5)
            
            self.logger.debug(f"Обработчик результатов остановлен [{process_id}]: обработано {processed_count} результатов")
        
        except Exception as critical_error:
            self.logger.critical(f"Критическая ошибка в обработчике результатов [{process_id}]: {critical_error}")
            log_exception(self.logger, f"Критическая ошибка обработчика результатов [{process_id}]")
            # Пауза перед выходом
            time.sleep(1.0)
    
    def _schedule_tasks(self):
        """Планирование задач мониторинга"""
        # Загружаем все активные сайты при старте
        schedule_id = f"schedule_{int(time.time())}"
        self.logger.debug(f"Запуск планировщика задач [{schedule_id}]")
        
        try:
            # Загружаем все активные сайты в очередь при первом запуске
            init_success = self._queue_all_sites()
            if not init_success:
                self.logger.warning(f"Не удалось добавить сайты в очередь при инициализации [{schedule_id}]")
        except Exception as e:
            self.logger.error(f"Ошибка при начальной загрузке сайтов [{schedule_id}]: {e}")
            log_exception(self.logger, f"Ошибка начальной загрузки сайтов [{schedule_id}]")
        
        # Время последней проверки запланированных задач
        last_check_time = time.time()
        
        # Время последней проверки здоровья системы
        last_health_check_time = time.time()
        
        # Интервалы
        check_interval = 10  # секунд
        health_check_interval = 5 * 60  # 5 минут
        
        # Счетчик циклов
        loop_count = 0
        
        # Счетчик последовательных ошибок
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while not self.stop_event.is_set():
            try:
                # Периодически логируем активность планировщика
                loop_count += 1
                if loop_count % 1000 == 0:
                    self.logger.debug(f"Планировщик задач активен, цикл #{loop_count} [{schedule_id}]")
                
                # Проверяем, пора ли выполнить следующую проверку задач
                current_time = time.time()
                
                # Проверка запланированных задач
                if current_time - last_check_time >= check_interval:
                    try:
                        self._check_scheduled_tasks()
                        consecutive_errors = 0  # Сбрасываем счетчик ошибок при успешном выполнении
                    except Exception as e:
                        consecutive_errors += 1
                        self.logger.error(f"Ошибка при проверке запланированных задач [{schedule_id}]: {e}")
                        log_exception(self.logger, f"Ошибка проверки запланированных задач [{schedule_id}]")
                        
                        # При большом количестве последовательных ошибок увеличиваем паузу
                        if consecutive_errors >= max_consecutive_errors:
                            self.logger.critical(f"Обнаружено {consecutive_errors} последовательных ошибок, увеличиваем паузу [{schedule_id}]")
                            time.sleep(30)  # Увеличенная пауза
                            consecutive_errors = 0  # Сбрасываем счетчик
                    
                    last_check_time = current_time
                
                # Периодический контроль здоровья системы
                if current_time - last_health_check_time >= health_check_interval:
                    try:
                        # Проверяем состояние очередей и работников
                        queue_size = self.task_queue.qsize()
                        result_queue_size = self.result_queue.qsize()
                        active_workers = sum(1 for w in self.workers if w.is_alive())
                        
                        self.logger.info(
                            f"Контроль здоровья системы [{schedule_id}]: "
                            f"активные работники: {active_workers}/{len(self.workers)}, "
                            f"размер очереди задач: {queue_size}, "
                            f"размер очереди результатов: {result_queue_size}"
                        )
                        
                        # Проверяем работников и перезапускаем неактивных
                        if self.is_active and active_workers < len(self.workers):
                            self.logger.warning(f"Обнаружены неактивные работники: {len(self.workers) - active_workers}, попытка перезапуска")
                            # Перезапуск в рамках отдельного метода или при следующем запуске приложения
                        
                        # Проверяем размер очереди задач, предупреждаем если слишком большой
                        if queue_size > 100:
                            self.logger.warning(f"Очередь задач слишком велика: {queue_size} задач")
                    
                    except Exception as health_e:
                        self.logger.error(f"Ошибка при проверке здоровья системы [{schedule_id}]: {health_e}")
                    
                    last_health_check_time = current_time
                
                # Пауза для снижения нагрузки на CPU
                time.sleep(0.1)
            
            except Exception as e:
                consecutive_errors += 1
                self.logger.error(f"Ошибка в цикле планирования задач [{schedule_id}]: {e}")
                log_exception(self.logger, f"Ошибка планирования задач [{schedule_id}]")
                time.sleep(1)  # Пауза перед повторной попыткой
        
        self.logger.debug(f"Планировщик задач остановлен [{schedule_id}]")
    
    def _cleanup_finished_workers(self):
        """Очистка завершенных потоков из списка workers"""
        try:
            self.logger.debug("Очистка завершенных потоков")
            
            # Фиксируем исходное количество потоков
            initial_workers_count = len(self.workers)
            
            # Фильтруем только живые потоки и сохраняем их индексы
            active_worker_indices = []
            active_workers = []
            
            for idx, worker in enumerate(self.workers):
                if worker.is_alive():
                    active_workers.append(worker)
                    active_worker_indices.append(idx)
            
            # Если есть завершенные потоки, обновляем список
            if len(active_workers) < initial_workers_count:
                self.logger.info(f"Удаление {initial_workers_count - len(active_workers)} завершенных потоков")
                self.workers = active_workers
                
                # Обновляем список контекстных менеджеров, сохраняя только те, которые соответствуют живым потокам
                active_contexts = []
                for idx in active_worker_indices:
                    if idx < len(self.worker_contexts):  # Защита от выхода за границы
                        active_contexts.append(self.worker_contexts[idx])
                
                # Если размеры не совпадают, логируем предупреждение
                if len(active_contexts) != len(active_workers):
                    self.logger.warning(f"Несоответствие количества активных работников ({len(active_workers)}) "
                                       f"и контекстных менеджеров ({len(active_contexts)})")
                
                self.worker_contexts = active_contexts
                
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка при очистке завершенных потоков: {e}")
            log_exception(self.logger, "Ошибка очистки завершенных потоков")
            return False
    
    def _perform_health_check(self):
        """Проверка здоровья системы мониторинга"""
        try:
            self.logger.debug("Выполнение проверки здоровья системы мониторинга")
            
            # Очистка завершенных потоков
            self._cleanup_finished_workers()
            
            # Проверка очереди задач
            queue_size = self.task_queue.qsize()
            self.logger.debug(f"Размер очереди задач: {queue_size}")
            
            # Проверка активных задач
            active_tasks = self.get_active_tasks_count()
            self.logger.debug(f"Активных задач: {active_tasks}")
            
            # Проверка работников
            active_workers = sum(1 for worker in self.workers if worker.is_alive())
            self.logger.debug(f"Активных работников: {active_workers}/{len(self.workers)}")
            
            # Если не все работники активны, логируем предупреждение
            if active_workers < len(self.workers):
                self.logger.warning(f"Некоторые работники неактивны: {active_workers}/{len(self.workers)}")
                
                # Перезапуск неактивных работников, если менеджер активен
                if self.is_active:
                    self._restart_inactive_workers()
            
            # Если очередь слишком большая, логируем предупреждение
            max_queue_size = self.max_workers * 10  # Примерное ограничение на размер очереди
            if queue_size > max_queue_size:
                self.logger.warning(f"Очередь задач слишком большая: {queue_size} > {max_queue_size}")
            
            # Периодическое обновление списка сайтов
            if self.is_active and len(self.tasks) == 0:
                self.logger.warning("Нет активных задач, выполняем повторную загрузку сайтов")
                self._queue_all_sites()
                
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка при проверке здоровья системы: {e}")
            log_exception(self.logger, "Ошибка проверки здоровья")
            return False
    
    def _restart_inactive_workers(self):
        """Перезапуск неактивных работников"""
        try:
            self.logger.info("Перезапуск неактивных работников")
            
            # Проходим по всем работникам и перезапускаем неактивные
            for i, worker in enumerate(self.workers):
                if not worker.is_alive():
                    worker_id = worker.worker_id
                    self.logger.warning(f"Работник #{worker_id} неактивен, перезапуск")
                    
                    # Если есть соответствующий контекстный менеджер, закрываем его
                    if i < len(self.worker_contexts) and self.worker_contexts[i]:
                        try:
                            self.logger.debug(f"Закрытие контекстного менеджера для работника #{worker_id}")
                            self.worker_contexts[i].__exit__(None, None, None)
                        except Exception as ctx_err:
                            self.logger.error(f"Ошибка при закрытии контекстного менеджера: {ctx_err}")
                    
                    # Создаем нового работника с тем же ID через контекстный менеджер
                    new_worker, new_ctx = self.get_worker(worker_id=worker_id)
                    
                    if new_worker and new_ctx:
                        # Заменяем неактивного работника и его контекстный менеджер
                        self.workers[i] = new_worker
                        
                        # Обновляем контекстный менеджер, если индекс в пределах списка
                        if i < len(self.worker_contexts):
                            self.worker_contexts[i] = new_ctx
                        else:
                            # Если индекс за пределами списка, добавляем новый контекст
                            self.worker_contexts.append(new_ctx)
                            
                        self.logger.info(f"Работник #{new_worker.worker_id} успешно перезапущен")
                    else:
                        self.logger.error(f"Не удалось перезапустить работника #{worker_id}")
                    
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка при перезапуске работников: {e}")
            log_exception(self.logger, "Ошибка перезапуска работников")
            return False
    
    def _check_scheduled_tasks(self):
        """Проверка задач на готовность к выполнению"""
        try:
            current_time = datetime.datetime.now()
            tasks_added = 0
            tasks_skipped = 0
            tasks_removed = 0
            tasks_error = 0
            
            with self.lock:
                # Проверяем все задачи
                for site_id, task in list(self.tasks.items()):
                    try:
                        # Проверяем состояние задачи
                        if not hasattr(task, 'status') or not hasattr(task, 'next_check_time'):
                            self.logger.warning(f"Некорректный объект задачи для сайта ID={site_id}, удаляем")
                            del self.tasks[site_id]
                            tasks_removed += 1
                            continue
                            
                        # Если задача завершена и пришло время для следующей проверки
                        if (task.status in ['completed', 'failed'] and 
                            task.next_check_time and 
                            task.next_check_time <= current_time):
                            
                            # Обновляем данные сайта
                            site_data = self._get_site_data(site_id)
                            if not site_data:
                                self.logger.warning(f"Сайт с ID={site_id} не найден, удаляем задачу")
                                del self.tasks[site_id]
                                tasks_removed += 1
                                continue
                            
                            # Проверяем статус сайта
                            if site_data.get('status') != 'active':
                                self.logger.debug(f"Сайт {site_data.get('name', '')} (ID={site_id}) не активен, пропускаем")
                                tasks_skipped += 1
                                continue
                            
                            # Проверяем наличие обязательных полей
                            if 'url' not in site_data or 'name' not in site_data:
                                self.logger.warning(f"Отсутствуют обязательные поля для сайта ID={site_id}, пропускаем")
                                tasks_skipped += 1
                                continue
                                
                            try:
                                # Создаем новую задачу и добавляем в очередь
                                self.logger.debug(f"Планирование проверки сайта {site_data['name']} (ID={site_id})")
                                new_task = MonitorTask(site_data)
                                self.tasks[site_id] = new_task
                                self.task_queue.put(new_task)
                                tasks_added += 1
                            except Exception as task_error:
                                self.logger.error(f"Ошибка при создании задачи для сайта {site_data.get('name', '')} (ID={site_id}): {task_error}")
                                log_exception(self.logger, f"Ошибка создания задачи для сайта ID={site_id}")
                                tasks_error += 1
                    
                    except Exception as e:
                        self.logger.error(f"Ошибка при обработке задачи для сайта ID={site_id}: {e}")
                        log_exception(self.logger, f"Ошибка обработки задачи для сайта ID={site_id}")
                        tasks_error += 1
            
            # Если были добавлены, удалены или пропущены задачи, логируем итоги
            if tasks_added > 0 or tasks_removed > 0 or tasks_skipped > 0 or tasks_error > 0:
                self.logger.info(f"Итоги планирования задач: добавлено - {tasks_added}, удалено - {tasks_removed}, пропущено - {tasks_skipped}, с ошибками - {tasks_error}")
        
        except Exception as e:
            self.logger.error(f"Ошибка при планировании задач: {e}")
            log_exception(self.logger, "Ошибка планирования задач")
    
    def _queue_all_sites(self):
        """
        Добавляет все активные сайты в очередь задач
        
        Returns:
            bool: True, если хотя бы один сайт добавлен в очередь
        """
        queue_id = f"queue_{int(time.time())}"
        self.logger.debug(f"Добавление всех активных сайтов в очередь задач [{queue_id}]")
        
        # Проверяем активность менеджера
        if not self.is_active:
            self.logger.warning(f"Попытка добавить сайты в очередь при неактивном менеджере [{queue_id}]")
            return False
            
        try:
            # Получаем список активных сайтов
            active_sites = self._get_all_active_sites()
            
            if not active_sites:
                self.logger.warning(f"Не найдено активных сайтов для добавления в очередь [{queue_id}]")
                return False
            
            # Счетчики для логирования
            added_count = 0
            skipped_count = 0
            error_count = 0
            
            # Проходим по каждому сайту и добавляем его в очередь
            for site in active_sites:
                try:
                    # Проверяем валидность данных сайта
                    if not isinstance(site, dict):
                        self.logger.warning(f"Некорректный формат данных сайта: {type(site)} [{queue_id}]")
                        error_count += 1
                        continue
                        
                    # Проверяем наличие обязательных полей
                    if 'id' not in site:
                        self.logger.warning(f"В данных сайта отсутствует поле 'id': {site} [{queue_id}]")
                        error_count += 1
                        continue
                        
                    if 'url' not in site or 'name' not in site:
                        self.logger.warning(f"В данных сайта {site['id']} отсутствуют обязательные поля 'url' или 'name' [{queue_id}]")
                        error_count += 1
                        continue
                    
                    # Получаем ID сайта
                    site_id = site['id']
                    
                    # Проверяем, нет ли уже задачи для этого сайта в очереди
                    with self.lock:
                        if site_id in self.tasks and self.tasks[site_id].status == 'running':
                            self.logger.debug(f"Сайт {site['name']} (ID={site_id}) уже имеет запущенную задачу, пропускаем [{queue_id}]")
                            skipped_count += 1
                            continue
                    
                    # Создаем задачу и добавляем в очередь
                    task = MonitorTask(site)
                    
                    # Сохраняем задачу в словаре задач
                    with self.lock:
                        self.tasks[site_id] = task
                    
                    # Добавляем в очередь задач
                    self.task_queue.put(task)
                    added_count += 1
                    
                    self.logger.debug(f"Сайт {site['name']} (ID={site_id}) добавлен в очередь задач [{queue_id}]")
                    
                except Exception as site_error:
                    self.logger.error(f"Ошибка при добавлении сайта в очередь: {site_error} [{queue_id}]")
                    log_exception(self.logger, f"Ошибка добавления сайта в очередь [{queue_id}]")
                    error_count += 1
            
            # Логируем результаты
            self.logger.info(
                f"Добавление сайтов в очередь завершено [{queue_id}]: "
                f"добавлено={added_count}, пропущено={skipped_count}, ошибок={error_count}"
            )
            
            # Обновляем статус приложения
            sites_count = len(active_sites)
            self.app_context.update_status(sites_count=sites_count)
            
            # Возвращаем True, если хотя бы один сайт был добавлен
            return added_count > 0
            
        except Exception as e:
            self.logger.error(f"Ошибка при добавлении сайтов в очередь [{queue_id}]: {e}")
            log_exception(self.logger, f"Ошибка добавления сайтов в очередь [{queue_id}]")
            return False
    
    def _get_all_active_sites(self):
        """
        Получение всех активных сайтов из базы данных
        
        Returns:
            List[Dict[str, Any]]: Список активных сайтов
        """
        try:
            self.logger.debug("Получение всех активных сайтов из базы данных")
            
            # Запрос к базе данных с таймаутом
            start_time = time.time()
            query = "SELECT * FROM sites WHERE status = 'active'"
            result = self.app_context.execute_db_query(query)
            query_time = time.time() - start_time
            
            # Проверяем время выполнения запроса
            if query_time > 0.5:  # Если запрос занял более 0.5 секунды
                self.logger.warning(f"Запрос активных сайтов выполнялся слишком долго: {query_time:.2f} сек")
            
            # Проверяем результат
            if result is None:
                self.logger.error("Запрос активных сайтов вернул None")
                return []
                
            # Проверяем структуру данных
            if not isinstance(result, list):
                self.logger.error(f"Запрос активных сайтов вернул неожиданный тип данных: {type(result)}")
                return []
                
            # Логируем результат
            sites_count = len(result)
            if sites_count == 0:
                self.logger.warning("Не найдено активных сайтов")
            else:
                self.logger.info(f"Найдено {sites_count} активных сайтов")
                
            # Проверяем данные каждого сайта
            valid_sites = []
            for site in result:
                if not isinstance(site, dict):
                    self.logger.warning(f"Пропуск некорректных данных сайта: {site}")
                    continue
                    
                # Проверяем наличие необходимых полей
                required_fields = ['id', 'name', 'url', 'status']
                missing_fields = [field for field in required_fields if field not in site]
                
                if missing_fields:
                    self.logger.warning(f"Сайт ID={site.get('id', 'unknown')} не содержит обязательных полей: {missing_fields}")
                    continue
                    
                # Проверяем статус
                if site['status'] != 'active':
                    self.logger.warning(f"Сайт {site['name']} (ID={site['id']}) имеет неактивный статус: {site['status']}")
                    continue
                    
                valid_sites.append(site)
            
            # Если количество валидных сайтов отличается от исходного результата
            if len(valid_sites) != sites_count:
                self.logger.warning(f"Отфильтровано {sites_count - len(valid_sites)} сайтов с некорректными данными")
                
            return valid_sites
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении активных сайтов: {e}")
            log_exception(self.logger, "Ошибка получения активных сайтов")
            return []
    
    def _get_site_data(self, site_id):
        """
        Получение данных сайта из базы данных
        
        Args:
            site_id: ID сайта
            
        Returns:
            Dict[str, Any]: Данные сайта или None, если сайт не найден
        """
        try:
            # Защита от некорректного ID
            if site_id is None:
                self.logger.error("Получен пустой ID сайта")
                return None
                
            # Преобразуем ID в целое число, если это строка
            if isinstance(site_id, str):
                try:
                    site_id = int(site_id)
                except ValueError:
                    self.logger.error(f"Некорректный формат ID сайта: {site_id}")
                    return None
            
            self.logger.debug(f"Получение данных сайта ID={site_id}")
            
            # Запрос к базе данных с таймаутом
            start_time = time.time()
            query = "SELECT * FROM sites WHERE id = ?"
            result = self.app_context.execute_db_query(query, (site_id,))
            query_time = time.time() - start_time
            
            # Проверяем время выполнения запроса
            if query_time > 0.2:  # Если запрос занял более 0.2 секунды
                self.logger.warning(f"Запрос данных сайта ID={site_id} выполнялся слишком долго: {query_time:.2f} сек")
            
            # Проверка результата
            if not result:
                self.logger.warning(f"Сайт с ID={site_id} не найден")
                return None
                
            if not isinstance(result, list) or len(result) == 0:
                self.logger.warning(f"Запрос данных сайта ID={site_id} вернул пустой результат")
                return None
                
            site_data = result[0]
            
            # Проверяем структуру данных
            if not isinstance(site_data, dict):
                self.logger.error(f"Данные сайта имеют неверный формат: {type(site_data)}")
                return None
                
            # Проверяем наличие необходимых полей
            required_fields = ['id', 'name', 'url', 'status']
            missing_fields = [field for field in required_fields if field not in site_data]
            
            if missing_fields:
                self.logger.warning(f"Данные сайта ID={site_id} не содержат обязательных полей: {missing_fields}")
                # Можно вернуть None, или решить вернуть данные даже с отсутствующими полями
                # return None
            
            return site_data
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении данных сайта ID={site_id}: {e}")
            log_exception(self.logger, f"Ошибка получения данных сайта ID={site_id}")
            return None
    
    def get_dashboard_data(self):
        """
        Получение данных для дашборда
        
        Returns:
            Dict[str, Any]: Данные для дашборда или сообщение об ошибке
        """
        try:
            self.logger.debug("Получение данных для дашборда")
            
            # Проверяем активность менеджера
            if not self.is_active:
                self.logger.warning("Попытка получения данных для дашборда при неактивном менеджере задач")
                return self.app_context.get_dashboard_data()
            
            # Используем базовые данные из контекста приложения
            base_data = self.app_context.get_dashboard_data()
            if not base_data:
                self.logger.warning("Не удалось получить базовые данные для дашборда")
                return None
            
            # Добавляем специфичные данные от менеджера задач
            try:
                # Получаем статистику активных задач
                active_tasks = self.get_active_tasks_count()
                total_tasks = len(self.tasks)
                
                # Получаем статистику по статусам задач
                task_status_stats = {}
                with self.lock:
                    for task in self.tasks.values():
                        if not hasattr(task, 'status'):
                            continue
                        status = task.status
                        if status not in task_status_stats:
                            task_status_stats[status] = 0
                        task_status_stats[status] += 1
                
                # Получаем статистику проверок по часам
                current_time = datetime.datetime.now()
                hourly_checks = []
                
                # Создаем данные за последние 24 часа
                for i in range(24):
                    hour_time = current_time - datetime.timedelta(hours=23-i)
                    # Используем случайные данные для тестирования
                    # В реальной системе здесь должен быть запрос к БД для получения статистики
                    try:
                        # Запрос к БД для получения количества проверок за определенный час
                        hour_start = hour_time.replace(minute=0, second=0, microsecond=0)
                        hour_end = hour_start + datetime.timedelta(hours=1)
                        
                        query = """
                        SELECT COUNT(*) as count 
                        FROM snapshots 
                        WHERE timestamp >= ? AND timestamp < ?
                        """
                        result = self.app_context.execute_db_query(
                            query, 
                            (hour_start.isoformat(), hour_end.isoformat()),
                            fetch_all=False
                        )
                        
                        count = result['count'] if result else 0
                        hourly_checks.append((hour_time.isoformat(), count))
                    except Exception as hour_error:
                        self.logger.error(f"Ошибка при получении статистики за час {hour_time.isoformat()}: {hour_error}")
                        hourly_checks.append((hour_time.isoformat(), 0))
                
                # Обновляем данные для дашборда
                base_data.update({
                    'active_tasks': active_tasks,
                    'total_tasks': total_tasks,
                    'task_status_stats': task_status_stats,
                    'hourly_checks': hourly_checks
                })
                
                return base_data
            except Exception as manager_error:
                self.logger.error(f"Ошибка при сборе специфичных данных менеджера: {manager_error}")
                log_exception(self.logger, "Ошибка сбора данных менеджера")
                # В случае ошибки все равно возвращаем базовые данные
                return base_data
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении данных для дашборда: {e}")
            log_exception(self.logger, "Ошибка получения данных для дашборда")
            
            # В случае критической ошибки возвращаем минимальный набор данных
            return {
                'status': self.app_context.get_status(),
                'error': str(e)
            } 

    def get_worker(self, worker_id=None):
        """
        Создает и возвращает нового работника через контекстный менеджер
        
        Args:
            worker_id: Идентификатор работника (опционально)
            
        Returns:
            Tuple[MonitorWorker, WorkerContextManager]: Работник и его контекстный менеджер
        """
        try:
            # Генерируем ID работника, если не указан
            if not worker_id:
                worker_id = f"worker-{len(self.workers) + 1}"
                
            self.logger.debug(f"Создание нового работника {worker_id} через контекстный менеджер")
            
            # Создаем контекстный менеджер
            worker_ctx = WorkerContextManager(
                self.app_context,
                self.task_queue,
                self.result_queue,
                worker_id=worker_id
            )
            
            # Входим в контекст и получаем работника
            worker = worker_ctx.__enter__()
            
            return worker, worker_ctx
            
        except Exception as e:
            self.logger.error(f"Ошибка при создании работника {worker_id}: {e}")
            log_exception(self.logger, "Ошибка создания работника")
            return None, None


class WorkerContextManager:
    """
    Контекстный менеджер для безопасной работы с потоком мониторинга.
    Гарантирует корректное освобождение ресурсов даже при возникновении исключений.
    """
    
    def __init__(self, app_context, task_queue, result_queue, worker_id=None):
        """
        Инициализация контекстного менеджера
        
        Args:
            app_context: Контекст приложения
            task_queue: Очередь задач
            result_queue: Очередь результатов
            worker_id: Идентификатор работника (опционально)
        """
        self.logger = get_module_logger('workers.monitor_manager.worker_ctx')
        self.app_context = app_context
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.worker_id = worker_id
        self.worker = None
        
    def __enter__(self):
        """
        Вход в контекстный блок - создание и запуск работника
        
        Returns:
            MonitorWorker: Инициализированный и запущенный работник
        """
        self.logger.debug(f"Создание и запуск работника {self.worker_id}")
        
        # Создаем работника
        self.worker = MonitorWorker(
            self.app_context, 
            self.task_queue, 
            self.result_queue, 
            self.worker_id
        )
        
        # Запускаем поток
        self.worker.start()
        
        return self.worker
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Выход из контекстного блока - корректная остановка работника
        
        Args:
            exc_type: Тип исключения, если оно возникло
            exc_val: Значение исключения
            exc_tb: Трассировка исключения
            
        Returns:
            bool: Флаг обработки исключения
        """
        # Логируем исключение, если оно возникло
        if exc_type:
            self.logger.error(f"Произошло исключение при работе с потоком: {exc_val}")
            log_exception(self.logger, "Ошибка при работе с потоком мониторинга")
        
        # Корректно останавливаем работника, если он был создан
        if self.worker:
            try:
                self.logger.debug(f"Остановка работника {self.worker.worker_id}")
                self.worker.stop()
                
                # Ждем завершения потока максимум 5 секунд
                if self.worker.is_alive():
                    self.worker.join(5.0)
                
                # Если поток все еще жив, логируем ошибку
                if self.worker.is_alive():
                    self.logger.warning(f"Работник {self.worker.worker_id} не остановился корректно")
            except Exception as e:
                self.logger.error(f"Ошибка при остановке работника {self.worker.worker_id}: {e}")
                log_exception(self.logger, "Ошибка при остановке работника")
        
        self.logger.debug("Выход из контекстного блока работника")
        return False  # Не подавляем исключения