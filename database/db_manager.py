#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль менеджера базы данных для WDM_V12.
Отвечает за подключение и работу с базой данных SQLite.
"""

import os
import sqlite3
import time
import threading
import logging
from typing import List, Dict, Tuple, Optional, Any, Union
from pathlib import Path
import json

from utils.logger import get_module_logger, log_exception
from config.config import get_config


class DBManager:
    """
    Класс для управления подключением к базе данных и выполнения запросов.
    Обеспечивает потокобезопасный доступ к базе данных SQLite.
    """
    
    def __init__(self, db_path=None):
        """
        Инициализация менеджера базы данных
        
        Args:
            db_path: Путь к файлу базы данных (если None, будет использован путь из конфигурации)
        """
        try:
            self.logger = get_module_logger('database.db_manager')
            self.logger.debug("Инициализация менеджера базы данных")
            
            # Загружаем конфигурацию
            try:
                config = get_config()
            except FileNotFoundError:
                # Создаем базовую конфигурацию
                config = {
                    'database': {
                        'path': 'data/wdm_database.db',
                        'log_queries': False,
                        'slow_query_threshold': 1.0
                    }
                }
                self.logger.warning("Файл конфигурации не найден, используются значения по умолчанию")
            
            # Инициализируем базовые атрибуты
            self.connections = {}
            self.lock = threading.RLock()
            self.connected = False
            self.queries_count = 0
            self.log_queries = config.get('database', {}).get('log_queries', False)
            self.slow_query_threshold = config.get('database', {}).get('slow_query_threshold', 1.0)
            
            # Если путь не указан, используем путь из конфигурации
            if not db_path:
                db_path = config.get('database', {}).get('path')
                if not db_path:
                    db_path = 'data/wdm_database.db'
                    self.logger.warning("Путь к базе данных не найден в конфигурации, используется значение по умолчанию")
            
            self.db_path = db_path
            
            # Создаем необходимые директории
            if not self.ensure_directories():
                raise RuntimeError("Не удалось создать необходимые директории")
            
            # Устанавливаем соединение
            self._connect()
            
            self.logger.debug("Менеджер базы данных инициализирован")
            
        except Exception as e:
            self.logger.error(f"Ошибка при инициализации менеджера базы данных: {e}")
            log_exception(self.logger, "Ошибка инициализации БД")
            raise
    
    def _connect(self):
        """Установка соединения с базой данных"""
        try:
            # Получаем соединение для текущего потока
            connection = self._get_connection()
            
            # Настройка соединения
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            
            self.connected = True
            self.logger.debug(f"Соединение с базой данных установлено: {self.db_path}")
        
        except Exception as e:
            self.connected = False
            self.logger.error(f"Ошибка при подключении к базе данных: {e}")
            log_exception(self.logger, "Ошибка подключения к базе данных")
            raise
    
    def _get_connection(self):
        """
        Получение соединения с базой данных для текущего потока
        
        Returns:
            sqlite3.Connection: Соединение с базой данных
        """
        # Получаем ID текущего потока
        thread_id = threading.get_ident()
        
        with self.lock:
            # Проверяем, есть ли уже соединение для этого потока
            if thread_id not in self.connections:
                # Создаем новое соединение
                connection = sqlite3.connect(
                    self.db_path,
                    detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
                    check_same_thread=False  # Соединение будет использоваться только в одном потоке
                )
                
                # Настраиваем соединение для возврата словарей вместо кортежей
                connection.row_factory = self._dict_factory
                
                # Сохраняем соединение для повторного использования
                self.connections[thread_id] = connection
                
                self.logger.debug(f"Создано новое соединение для потока {thread_id}")
            
            return self.connections[thread_id]
    
    def _dict_factory(self, cursor, row):
        """
        Фабрика для преобразования результатов запроса в словари
        
        Args:
            cursor: Курсор SQLite
            row: Строка результата
            
        Returns:
            Dict[str, Any]: Словарь с результатами запроса
        """
        return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
    
    def execute_query(self, query, params=None, fetch_all=True, commit=True):
        """
        Выполнение SQL-запроса к базе данных
        
        Args:
            query: SQL-запрос
            params: Параметры запроса (tuple, dict или None)
            fetch_all: Возвращать ли все результаты (если False, возвращается только первый)
            commit: Выполнять ли commit после запроса
            
        Returns:
            Union[List[Dict[str, Any]], Dict[str, Any], None]: Результаты запроса
        """
        if not self.connected:
            self._connect()
        
        try:
            if self.log_queries:
                self.logger.debug(f"SQL: {query} | Params: {params}")
            
            with self.lock:
                connection = self._get_connection()
                cursor = connection.cursor()
                
                start_time = time.time()
                
                try:
                    # Выполняем запрос
                    if params:
                        cursor.execute(query, params)
                    else:
                        cursor.execute(query)
                
                    # Если запрос изменяет данные и требуется commit, делаем его
                    if commit and query.strip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                        connection.commit()
                
                    # Получаем результаты, если запрос возвращает данные
                    results = None
                    if query.strip().upper().startswith("SELECT"):
                        if fetch_all:
                            results = cursor.fetchall()
                        else:
                            result = cursor.fetchone()
                            results = result if result else None
                
                    # Если запрос возвращает lastrowid, сохраняем его
                    last_id = cursor.lastrowid if cursor.lastrowid else None
                
                    # Закрываем курсор
                    cursor.close()
                
                    # Увеличиваем счетчик запросов
                    self.queries_count += 1
                
                    # Логирование времени выполнения
                    execution_time = time.time() - start_time
                    if execution_time > self.slow_query_threshold:
                        self.logger.warning(f"Медленный запрос ({execution_time:.2f} сек): {query}")
                
                    return results
                
                except sqlite3.Error as e:
                    if commit:
                        connection.rollback()
                    self.logger.error(f"Ошибка при выполнении запроса: {e}")
                    self.logger.error(f"Запрос: {query}")
                    self.logger.error(f"Параметры: {params}")
                    log_exception(self.logger, "Ошибка выполнения запроса")
                    raise
                
        except Exception as e:
            self.logger.error(f"Критическая ошибка при выполнении запроса: {e}")
            log_exception(self.logger, "Критическая ошибка выполнения запроса")
            raise
    
    def _reconnect(self):
        """
        Переподключение к базе данных в случае ошибок.
        Закрывает все текущие соединения и создает новые.
        """
        try:
            self.logger.debug("Начало переподключения к базе данных")
            
            with self.lock:
                # Закрываем все текущие соединения
                for thread_id, connection in self.connections.items():
                    try:
                        connection.close()
                        self.logger.debug(f"Соединение для потока {thread_id} закрыто")
                    except Exception as e:
                        self.logger.error(f"Ошибка при закрытии соединения для потока {thread_id}: {e}")
                        log_exception(self.logger, f"Ошибка закрытия соединения для потока {thread_id}")
                
                # Очищаем список соединений
                self.connections.clear()
                
                # Проверяем существование файла базы данных
                if not os.path.exists(self.db_path):
                    self.logger.error(f"Файл базы данных не найден: {self.db_path}")
                    raise FileNotFoundError(f"Файл базы данных не найден: {self.db_path}")
                
                # Проверяем права доступа к файлу базы данных
                if not os.access(self.db_path, os.R_OK | os.W_OK):
                    self.logger.error(f"Нет прав доступа к файлу базы данных: {self.db_path}")
                    raise PermissionError(f"Нет прав доступа к файлу базы данных: {self.db_path}")
                
                # Устанавливаем новое соединение
                self._connect()
                
                # Проверяем целостность базы данных
                try:
                    self.execute_query("PRAGMA integrity_check")
                    self.logger.debug("Проверка целостности базы данных успешно пройдена")
                except Exception as e:
                    self.logger.error(f"Ошибка при проверке целостности базы данных: {e}")
                    log_exception(self.logger, "Ошибка проверки целостности базы данных")
                    raise
                
                self.logger.info("Переподключение к базе данных выполнено успешно")
        
        except Exception as e:
            self.logger.error(f"Критическая ошибка при переподключении к базе данных: {e}")
            log_exception(self.logger, "Критическая ошибка переподключения к базе данных")
            self.connected = False
            raise
    
    def close(self):
        """
        Закрытие всех соединений с базой данных.
        Гарантирует корректное завершение всех транзакций и освобождение ресурсов.
        """
        try:
            self.logger.debug("Начало закрытия соединений с базой данных")
            
            with self.lock:
                # Закрываем все соединения
                for thread_id, connection in self.connections.items():
                    try:
                        # Проверяем наличие активных транзакций
                        try:
                            connection.execute("SELECT * FROM sqlite_master LIMIT 1")
                        except sqlite3.OperationalError:
                            # Если есть активная транзакция, откатываем её
                            connection.rollback()
                            self.logger.debug(f"Откат активной транзакции для потока {thread_id}")
                        
                        # Закрываем соединение
                        connection.close()
                        self.logger.debug(f"Соединение для потока {thread_id} закрыто")
                    except Exception as e:
                        self.logger.error(f"Ошибка при закрытии соединения для потока {thread_id}: {e}")
                        log_exception(self.logger, f"Ошибка закрытия соединения для потока {thread_id}")
                
                # Очищаем список соединений
                self.connections.clear()
                
                # Сбрасываем флаг подключения
                self.connected = False
                
                # Сбрасываем счетчик запросов
                self.queries_count = 0
                
                self.logger.info("Все соединения с базой данных успешно закрыты")
        
        except Exception as e:
            self.logger.error(f"Критическая ошибка при закрытии соединений с базой данных: {e}")
            log_exception(self.logger, "Критическая ошибка закрытия соединений")
            raise
    
    def get_table_info(self, table_name):
        """
        Получение информации о структуре таблицы
        
        Args:
            table_name: Имя таблицы
            
        Returns:
            List[Dict[str, Any]]: Список с информацией о колонках таблицы
        """
        try:
            self.logger.debug(f"Получение информации о таблице: {table_name}")
            
            # Проверяем существование таблицы
            if not self.table_exists(table_name):
                self.logger.error(f"Таблица не найдена: {table_name}")
                raise ValueError(f"Таблица не найдена: {table_name}")
            
            # Получаем информацию о структуре таблицы
            query = f"PRAGMA table_info({table_name})"
            result = self.execute_query(query)
            
            if not result:
                self.logger.warning(f"Не удалось получить информацию о таблице: {table_name}")
                return []
            
            # Преобразуем результат в более удобный формат
            columns = []
            for row in result:
                column = {
                    'name': row['name'],
                    'type': row['type'],
                    'notnull': bool(row['notnull']),
                    'default_value': row['dflt_value'],
                    'pk': bool(row['pk'])
                }
                columns.append(column)
            
            self.logger.debug(f"Информация о таблице {table_name} успешно получена")
            return columns
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении информации о таблице {table_name}: {e}")
            log_exception(self.logger, f"Ошибка получения информации о таблице: {table_name}")
            raise
    
    def table_exists(self, table_name):
        """
        Проверка существования таблицы в базе данных
        
        Args:
            table_name: Имя таблицы
            
        Returns:
            bool: True, если таблица существует
        """
        try:
            query = """
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name=?
            """
            result = self.execute_query(query, (table_name,), fetch_all=False)
            return result is not None
        except Exception as e:
            self.logger.error(f"Ошибка при проверке существования таблицы {table_name}: {e}")
            return False
    
    def get_row_count(self, table_name, condition=None, params=None):
        """
        Получение количества строк в таблице
        
        Args:
            table_name: Имя таблицы
            condition: Условие WHERE (без самого слова WHERE)
            params: Параметры для условия
            
        Returns:
            int: Количество строк
        """
        try:
            self.logger.debug(f"Подсчет строк в таблице: {table_name}")
            
            # Проверяем существование таблицы
            if not self.table_exists(table_name):
                self.logger.error(f"Таблица не найдена: {table_name}")
                raise ValueError(f"Таблица не найдена: {table_name}")
            
            # Формируем запрос
            query = f"SELECT COUNT(*) as count FROM {table_name}"
            if condition:
                query += f" WHERE {condition}"
            
            # Выполняем запрос
            result = self.execute_query(query, params)
        
            if not result:
                self.logger.warning(f"Не удалось получить количество строк в таблице: {table_name}")
                return 0
            
            count = result[0]['count']
            self.logger.debug(f"В таблице {table_name} найдено {count} строк")
            return count
        
        except Exception as e:
            self.logger.error(f"Ошибка при подсчете строк в таблице {table_name}: {e}")
            from utils.logger import log_exception
            log_exception(self.logger, f"Ошибка подсчета строк в таблице: {table_name}")
            raise
    
    def get_all_records(self, table_name, columns="*", condition=None, params=None, order_by=None, limit=None, offset=None):
        """
        Получение записей из таблицы с учетом условий и сортировки
        
        Args:
            table_name: Имя таблицы
            columns: Список колонок для выборки (по умолчанию все)
            condition: Условие WHERE (без самого слова WHERE)
            params: Параметры для условия
            order_by: Условие ORDER BY (без самого слова ORDER BY)
            limit: Максимальное количество записей
            offset: Смещение для пагинации
            
        Returns:
            List[Dict[str, Any]]: Список записей
        """
        try:
            self.logger.debug(f"Получение записей из таблицы: {table_name}")
            
            # Проверяем существование таблицы
            if not self.table_exists(table_name):
                self.logger.error(f"Таблица не найдена: {table_name}")
                raise ValueError(f"Таблица не найдена: {table_name}")
            
            # Формируем запрос
            query = f"SELECT {columns} FROM {table_name}"
            
            # Добавляем условие WHERE
            if condition:
                query += f" WHERE {condition}"
            
            # Добавляем сортировку
            if order_by:
                query += f" ORDER BY {order_by}"
            
            # Добавляем ограничение
            if limit is not None:
                query += f" LIMIT {limit}"
                if offset is not None:
                    query += f" OFFSET {offset}"
            
            # Выполняем запрос
            result = self.execute_query(query, params)
            
            if not result:
                self.logger.debug(f"В таблице {table_name} не найдено записей")
                return []
            
            self.logger.debug(f"Из таблицы {table_name} получено {len(result)} записей")
            return result
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении записей из таблицы {table_name}: {e}")
            from utils.logger import log_exception
            log_exception(self.logger, f"Ошибка получения записей из таблицы: {table_name}")
            raise
    
    def insert_record(self, table_name, data):
        """
        Вставка записи в таблицу
        
        Args:
            table_name: Имя таблицы
            data: Словарь с данными для вставки
            
        Returns:
            int: ID вставленной записи
        """
        try:
            self.logger.debug(f"Вставка записи в таблицу: {table_name}")
            
            # Проверяем существование таблицы
            if not self.table_exists(table_name):
                self.logger.error(f"Таблица не найдена: {table_name}")
                raise ValueError(f"Таблица не найдена: {table_name}")
            
            # Проверяем данные
            if not data or not isinstance(data, dict):
                self.logger.error(f"Некорректные данные для вставки: {data}")
                raise ValueError(f"Некорректные данные для вставки: {data}")
            
            # Получаем информацию о структуре таблицы
            table_info = self.get_table_info(table_name)
            if not table_info:
                self.logger.error(f"Не удалось получить информацию о структуре таблицы: {table_name}")
                raise ValueError(f"Не удалось получить информацию о структуре таблицы: {table_name}")
            
            # Формируем запрос
            columns = []
            values = []
            params = []
            
            for column in table_info:
                if column['name'] in data:
                    columns.append(column['name'])
                    values.append('?')
                    params.append(data[column['name']])
            
            if not columns:
                self.logger.error("Нет данных для вставки")
                raise ValueError("Нет данных для вставки")
            
            query = f"""
            INSERT INTO {table_name} 
            ({', '.join(columns)}) 
            VALUES ({', '.join(values)})
            """
            
            # Выполняем запрос
            record_id = self.execute_query(query, params)
            
            if not record_id:
                self.logger.error("Не удалось вставить запись")
                raise RuntimeError("Не удалось вставить запись")
            
            self.logger.debug(f"Запись успешно вставлена в таблицу {table_name} с ID {record_id}")
            return record_id
        
        except Exception as e:
            self.logger.error(f"Ошибка при вставке записи в таблицу {table_name}: {e}")
            from utils.logger import log_exception
            log_exception(self.logger, f"Ошибка вставки записи в таблицу: {table_name}")
            raise
    
    def update_record(self, table_name, data, condition, params=None):
        """
        Обновление записей в таблице
        
        Args:
            table_name: Имя таблицы
            data: Словарь с данными для обновления
            condition: Условие WHERE (без самого слова WHERE)
            params: Параметры для условия
            
        Returns:
            int: Количество обновленных записей
        """
        try:
            self.logger.debug(f"Обновление записей в таблице: {table_name}")
            
            # Проверяем существование таблицы
            if not self.table_exists(table_name):
                self.logger.error(f"Таблица не найдена: {table_name}")
                raise ValueError(f"Таблица не найдена: {table_name}")
            
            # Проверяем данные
            if not data or not isinstance(data, dict):
                self.logger.error(f"Некорректные данные для обновления: {data}")
                raise ValueError(f"Некорректные данные для обновления: {data}")
            
            # Получаем информацию о структуре таблицы
            table_info = self.get_table_info(table_name)
            if not table_info:
                self.logger.error(f"Не удалось получить информацию о структуре таблицы: {table_name}")
                raise ValueError(f"Не удалось получить информацию о структуре таблицы: {table_name}")
            
            # Формируем запрос
            set_clause = []
            update_params = []
            
            for column in table_info:
                if column['name'] in data:
                    set_clause.append(f"{column['name']} = ?")
                    update_params.append(data[column['name']])
            
            if not set_clause:
                self.logger.error("Нет данных для обновления")
                raise ValueError("Нет данных для обновления")
            
            query = f"""
            UPDATE {table_name} 
            SET {', '.join(set_clause)}
            WHERE {condition}
            """
            
            # Объединяем параметры
            if params:
                update_params.extend(params)
            
            # Выполняем запрос
            self.execute_query(query, update_params)
            
            # Получаем количество обновленных записей
            count_query = f"SELECT changes() as count"
            result = self.execute_query(count_query)
            
            if not result:
                self.logger.warning("Не удалось получить количество обновленных записей")
                return 0
            
            count = result[0]['count']
            self.logger.debug(f"В таблице {table_name} обновлено {count} записей")
            return count
        
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении записей в таблице {table_name}: {e}")
            from utils.logger import log_exception
            log_exception(self.logger, f"Ошибка обновления записей в таблице: {table_name}")
            raise
    
    def delete_record(self, table_name, condition, params=None):
        """
        Удаление записей из таблицы
        
        Args:
            table_name: Имя таблицы
            condition: Условие WHERE (без самого слова WHERE)
            params: Параметры для условия
            
        Returns:
            int: Количество удаленных записей
        """
        try:
            self.logger.debug(f"Удаление записей из таблицы: {table_name}")
            
            # Проверяем существование таблицы
            if not self.table_exists(table_name):
                self.logger.error(f"Таблица не найдена: {table_name}")
                raise ValueError(f"Таблица не найдена: {table_name}")
            
            # Формируем запрос
            query = f"DELETE FROM {table_name} WHERE {condition}"
            
            # Выполняем запрос
            self.execute_query(query, params)
            
            # Получаем количество удаленных записей
            count_query = f"SELECT changes() as count"
            result = self.execute_query(count_query)
            
            if not result:
                self.logger.warning("Не удалось получить количество удаленных записей")
                return 0
            
            count = result[0]['count']
            self.logger.debug(f"Из таблицы {table_name} удалено {count} записей")
            return count
        
        except Exception as e:
            self.logger.error(f"Ошибка при удалении записей из таблицы {table_name}: {e}")
            from utils.logger import log_exception
            log_exception(self.logger, f"Ошибка удаления записей из таблицы: {table_name}")
            raise
    
    def backup_database(self, backup_path=None):
        """
        Создание резервной копии базы данных
        
        Args:
            backup_path: Путь для сохранения резервной копии (если None, используется имя файла БД + timestamp)
            
        Returns:
            str: Путь к файлу резервной копии или None в случае ошибки
        """
        try:
            if not backup_path:
                # Создаем имя файла резервной копии с timestamp
                db_name = os.path.splitext(os.path.basename(self.db_path))[0]
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                backup_path = os.path.join(
                    os.path.dirname(self.db_path),
                    f"{db_name}_backup_{timestamp}.db"
                )
            
            self.logger.info(f"Создание резервной копии базы данных: {backup_path}")
            
            # Получаем соединение для текущего потока
            connection = self._get_connection()
            
            # Создаем резервную копию
            backup_connection = sqlite3.connect(backup_path)
            connection.backup(backup_connection)
            backup_connection.close()
            
            self.logger.info(f"Резервная копия базы данных создана успешно: {backup_path}")
            return backup_path
        
        except Exception as e:
            self.logger.error(f"Ошибка при создании резервной копии базы данных: {e}")
            log_exception(self.logger, "Ошибка создания резервной копии базы данных")
            return None
    
    def execute_script(self, script):
        """
        Выполнение SQL-скрипта
        
        Args:
            script: SQL-скрипт
            
        Returns:
            bool: True, если скрипт выполнен успешно
        """
        try:
            if not self.connected:
                self._connect()
            
            # Получаем соединение для текущего потока
            connection = self._get_connection()
            
            # Выполняем скрипт
            connection.executescript(script)
            connection.commit()
            
            return True
        
        except Exception as e:
            self.logger.error(f"Ошибка при выполнении SQL-скрипта: {e}")
            log_exception(self.logger, "Ошибка выполнения SQL-скрипта")
            return False
    
    def get_database_stats(self):
        """
        Получение статистики по базе данных
        
        Returns:
            Dict[str, Any]: Статистика базы данных
        """
        try:
            stats = {
                'tables': {}
            }
            
            # Получаем список всех таблиц
            tables_query = "SELECT name FROM sqlite_master WHERE type='table'"
            tables = self.execute_query(tables_query)
            
            for table in tables:
                table_name = table['name']
                # Получаем количество строк в таблице
                count_query = f"SELECT COUNT(*) as count FROM {table_name}"
                count_result = self.execute_query(count_query, fetch_all=False)
                stats['tables'][table_name] = {
                    'row_count': count_result['count'] if count_result else 0
                }
            
            return stats
        
        except Exception as e:
            self.logger.error(f"Ошибка при получении статистики базы данных: {e}")
            return {'tables': {}}
    
    def get_setting(self, key, default=None):
        """
        Получение значения настройки
        
        Args:
            key: Ключ настройки
            default: Значение по умолчанию
            
        Returns:
            Any: Значение настройки или значение по умолчанию
        """
        try:
            query = "SELECT value FROM settings WHERE key = ?"
            result = self.execute_query(query, (key,), fetch_all=False)
            return result['value'] if result else default
        except Exception as e:
            self.logger.error(f"Ошибка при получении настройки {key}: {e}")
            return default
    
    def update_setting(self, key, value):
        """
        Обновление значения настройки с валидацией
        
        Args:
            key: Ключ настройки
            value: Новое значение
            
        Returns:
            tuple: (bool, str) - результат обновления и сообщение об ошибке
        """
        try:
            # Валидируем значение
            is_valid, error_message = self.validate_setting(key, value)
            if not is_valid:
                self.logger.error(f"Ошибка валидации настройки {key}: {error_message}")
                return False, error_message
            
            # Сериализуем значение если это словарь или список
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            
            query = """
            INSERT INTO settings (key, value, updated_at) 
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET 
            value = excluded.value,
            updated_at = excluded.updated_at
            """
            self.execute_query(query, (key, value))
            return True, ""
        
        except Exception as e:
            error_msg = f"Ошибка при обновлении настройки {key}: {e}"
            self.logger.error(error_msg)
            return False, error_msg
    
    def validate_setting(self, key, value):
        """
        Валидация значения настройки перед сохранением
        
        Args:
            key: Ключ настройки
            value: Значение для проверки
            
        Returns:
            tuple: (bool, str) - результат валидации и сообщение об ошибке
        """
        try:
            # Получаем схему валидации из конфигурации
            validation_schema = self.get_setting('validation_schema', {})
            if not validation_schema:
                return True, ""
            
            # Загружаем схему если она в JSON
            if isinstance(validation_schema, str):
                validation_schema = json.loads(validation_schema)
            
            # Проверяем наличие правил для данного ключа
            if key not in validation_schema:
                return True, ""
            
            rules = validation_schema[key]
            
            # Проверяем тип
            if 'type' in rules:
                expected_type = rules['type']
                if not isinstance(value, eval(expected_type)):
                    return False, f"Неверный тип данных. Ожидается {expected_type}"
                
            # Проверяем диапазон для чисел
            if isinstance(value, (int, float)):
                if 'min' in rules and value < rules['min']:
                    return False, f"Значение меньше минимального ({rules['min']})"
                if 'max' in rules and value > rules['max']:
                    return False, f"Значение больше максимального ({rules['max']})"
                
            # Проверяем длину для строк
            if isinstance(value, str):
                if 'min_length' in rules and len(value) < rules['min_length']:
                    return False, f"Длина строки меньше минимальной ({rules['min_length']})"
                if 'max_length' in rules and len(value) > rules['max_length']:
                    return False, f"Длина строки больше максимальной ({rules['max_length']})"
                
            # Проверяем регулярное выражение
            if 'pattern' in rules and isinstance(value, str):
                import re
                if not re.match(rules['pattern'], value):
                    return False, "Значение не соответствует шаблону"
                
            return True, ""
        
        except Exception as e:
            self.logger.error(f"Ошибка при валидации настройки {key}: {e}")
            return False, f"Ошибка валидации: {str(e)}"
    
    def get_all_settings(self):
        """
        Получение всех настроек
        
        Returns:
            Dict[str, str]: Словарь с настройками
        """
        try:
            query = "SELECT key, value FROM settings"
            result = self.execute_query(query)
            return {row['key']: row['value'] for row in result}
        except Exception as e:
            self.logger.error(f"Ошибка при получении всех настроек: {e}")
            return {}
    
    def get_all_records(self, table_name, condition=None, params=None):
        """
        Получение всех записей из таблицы
        
        Args:
            table_name: Имя таблицы
            condition: Условие WHERE (опционально)
            params: Параметры условия (опционально)
            
        Returns:
            List[Dict[str, Any]]: Список записей
        """
        try:
            query = f"SELECT * FROM {table_name}"
            if condition:
                query += f" WHERE {condition}"
            return self.execute_query(query, params)
        except Exception as e:
            self.logger.error(f"Ошибка при получении записей из таблицы {table_name}: {e}")
            return []
    
    def insert_record(self, table_name, record):
        """
        Вставка записи в таблицу
        
        Args:
            table_name: Имя таблицы
            record: Словарь с данными записи
            
        Returns:
            bool: Результат вставки
        """
        try:
            # Формируем список полей и значений
            fields = list(record.keys())
            values = list(record.values())
            
            # Формируем SQL-запрос
            fields_str = ', '.join(fields)
            placeholders = ', '.join(['?' for _ in fields])
            query = f"INSERT INTO {table_name} ({fields_str}) VALUES ({placeholders})"
            
            # Выполняем запрос
            self.execute_query(query, tuple(values))
            return True
        except Exception as e:
            self.logger.error(f"Ошибка при вставке записи в таблицу {table_name}: {e}")
            return False
    
    def index_exists(self, index_name):
        """
        Проверка существования индекса в базе данных
        
        Args:
            index_name: Имя индекса
            
        Returns:
            bool: True, если индекс существует
        """
        try:
            query = """
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name=?
            """
            result = self.execute_query(query, (index_name,), fetch_all=False)
            return result is not None
        except Exception as e:
            self.logger.error(f"Ошибка при проверке существования индекса {index_name}: {e}")
            return False
    
    def cleanup_old_backups(self, max_age_days=30, max_count=10):
        """
        Очистка старых резервных копий
        
        Args:
            max_age_days: Максимальный возраст файлов в днях
            max_count: Максимальное количество файлов для хранения
            
        Returns:
            int: Количество удаленных файлов
        """
        try:
            backup_dir = os.path.dirname(self.db_path)
            backup_pattern = "*_backup_*.db"
            deleted_count = 0
            
            # Получаем список файлов резервных копий
            backup_files = []
            for file in Path(backup_dir).glob(backup_pattern):
                backup_files.append({
                    'path': file,
                    'mtime': file.stat().st_mtime
                })
            
            # Сортируем по времени изменения
            backup_files.sort(key=lambda x: x['mtime'], reverse=True)
            
            # Удаляем старые файлы
            current_time = time.time()
            for idx, file_info in enumerate(backup_files):
                file_age_days = (current_time - file_info['mtime']) / (24 * 3600)
                
                # Удаляем если файл старый или превышен лимит
                if idx >= max_count or file_age_days > max_age_days:
                    try:
                        file_info['path'].unlink()
                        deleted_count += 1
                        self.logger.debug(f"Удалена старая резервная копия: {file_info['path']}")
                    except Exception as e:
                        self.logger.error(f"Ошибка при удалении файла {file_info['path']}: {e}")
                    
            return deleted_count
        
        except Exception as e:
            self.logger.error(f"Ошибка при очистке старых резервных копий: {e}")
            return 0
    
    def restore_from_backup(self, backup_path=None):
        """
        Восстановление базы данных из резервной копии
        
        Args:
            backup_path: Путь к файлу резервной копии (если None, используется последняя)
            
        Returns:
            bool: Результат восстановления
        """
        try:
            if not backup_path:
                # Ищем последнюю резервную копию
                backup_dir = os.path.dirname(self.db_path)
                backup_pattern = "*_backup_*.db"
                backup_files = list(Path(backup_dir).glob(backup_pattern))
                
                if not backup_files:
                    self.logger.error("Резервные копии не найдены")
                    return False
                
                # Выбираем самую свежую копию
                backup_path = str(max(backup_files, key=lambda x: x.stat().st_mtime))
            
            self.logger.info(f"Восстановление из резервной копии: {backup_path}")
            
            # Проверяем существование файла резервной копии
            if not os.path.exists(backup_path):
                self.logger.error(f"Файл резервной копии не найден: {backup_path}")
                return False
            
            # Закрываем текущие соединения
            self.close()
            
            # Создаем временную копию текущей базы
            temp_backup = f"{self.db_path}.temp"
            import shutil
            shutil.copy2(self.db_path, temp_backup)
            
            try:
                # Восстанавливаем из резервной копии
                shutil.copy2(backup_path, self.db_path)
                
                # Проверяем восстановленную базу
                self._connect()
                self.execute_query("PRAGMA integrity_check")
                
                # Удаляем временную копию
                os.remove(temp_backup)
                
                self.logger.info("База данных успешно восстановлена")
                return True
            
            except Exception as e:
                # В случае ошибки восстанавливаем из временной копии
                self.logger.error(f"Ошибка при восстановлении: {e}")
                shutil.copy2(temp_backup, self.db_path)
                os.remove(temp_backup)
                self._connect()
                return False
            
        except Exception as e:
            self.logger.error(f"Критическая ошибка при восстановлении базы данных: {e}")
            return False
    
    def apply_migrations(self, migrations_dir='migrations'):
        """
        Применение миграций базы данных
        
        Args:
            migrations_dir: Директория с файлами миграций
            
        Returns:
            tuple: (bool, str) - результат применения миграций и сообщение
        """
        try:
            # Проверяем/создаем таблицу для отслеживания миграций
            self.execute_query("""
            CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            # Получаем список примененных миграций
            applied = {row['name'] for row in self.execute_query("SELECT name FROM migrations")}
            
            # Проверяем директорию с миграциями
            migrations_path = Path(migrations_dir)
            if not migrations_path.exists():
                return True, "Директория с миграциями не найдена"
            
            # Получаем список файлов миграций
            migration_files = sorted([f for f in migrations_path.glob("*.sql")])
            
            if not migration_files:
                return True, "Файлы миграций не найдены"
            
            # Применяем миграции
            applied_count = 0
            for migration_file in migration_files:
                migration_name = migration_file.name
                
                if migration_name in applied:
                    continue
                
                try:
                    # Читаем и выполняем SQL из файла
                    with open(migration_file, 'r', encoding='utf-8') as f:
                        sql = f.read()
                    
                    # Выполняем миграцию в транзакции
                    self.execute_query("BEGIN TRANSACTION")
                    
                    try:
                        # Выполняем SQL миграции
                        self.execute_script(sql)
                        
                        # Записываем информацию о выполнении
                        self.execute_query(
                            "INSERT INTO migrations (name) VALUES (?)",
                            (migration_name,)
                        )
                        
                        self.execute_query("COMMIT")
                        applied_count += 1
                        
                        self.logger.info(f"Применена миграция: {migration_name}")
                        
                    except Exception as e:
                        self.execute_query("ROLLBACK")
                        raise Exception(f"Ошибка в миграции {migration_name}: {e}")
                    
                except Exception as e:
                    return False, f"Ошибка при применении миграции {migration_name}: {e}"
                
            return True, f"Успешно применено миграций: {applied_count}"
            
        except Exception as e:
            error_msg = f"Ошибка при применении миграций: {e}"
            self.logger.error(error_msg)
            return False, error_msg
    
    def ensure_directories(self):
        """
        Проверка и создание необходимых директорий
        
        Returns:
            bool: True, если все директории созданы успешно
        """
        try:
            # Список необходимых директорий
            dirs = [
                os.path.dirname(self.db_path),  # Директория с базой данных
                'logs',                         # Директория для логов
                'backups',                      # Директория для резервных копий
                'migrations'                    # Директория для миграций
            ]
            
            # Создаем директории если они не существуют
            for dir_path in dirs:
                if not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)
                    self.logger.debug(f"Создана директория: {dir_path}")
                
            return True
        
        except Exception as e:
            self.logger.error(f"Ошибка при создании директорий: {e}")
            return False 