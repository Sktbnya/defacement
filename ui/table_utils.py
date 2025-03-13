#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль оптимизированных компонентов для работы с таблицами и отложенным обновлением UI.
Содержит классы для индексирования таблиц и эффективного обновления интерфейса.
"""

import os
import time
import threading
from typing import Dict, List, Any, Optional, Union, Callable, Tuple, Set
from functools import lru_cache

from PyQt6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QApplication, QWidget
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QModelIndex

from utils.logger import get_module_logger
from utils.error_handler import handle_errors


class TableIndex:
    """
    Класс для создания и поддержки индексов для быстрого доступа к элементам таблицы.
    Позволяет осуществлять быстрый поиск по значениям в определенных столбцах.
    """
    
    def __init__(self, table: QTableWidget):
        """
        Инициализация индекса таблицы.
        
        Args:
            table: Таблица для индексирования
        """
        self.logger = get_module_logger('ui.table_utils.TableIndex')
        self.table = table
        self.indices: Dict[int, Dict[str, List[int]]] = {}  # {column_idx: {value: [row_indices]}}
        self.unique_indices: Dict[int, Dict[str, int]] = {}  # {column_idx: {value: row_idx}}
        self.indexed_columns: Set[int] = set()
        
        self.logger.debug("Индекс таблицы инициализирован")
    
    def create_index(self, column: int, unique: bool = False):
        """
        Создает индекс для указанного столбца.
        
        Args:
            column: Индекс столбца для индексирования
            unique: Флаг, указывающий, являются ли значения в столбце уникальными
        """
        self.logger.debug(f"Создание индекса для столбца {column}, unique={unique}")
        
        if unique:
            self.unique_indices[column] = {}
        else:
            self.indices[column] = {}
        
        self.indexed_columns.add(column)
        self.rebuild_index(column, unique)
    
    def rebuild_index(self, column: int, unique: bool = False):
        """
        Перестраивает индекс для указанного столбца.
        
        Args:
            column: Индекс столбца для перестроения индекса
            unique: Флаг, указывающий, являются ли значения в столбце уникальными
        """
        if unique:
            if column not in self.unique_indices:
                self.unique_indices[column] = {}
            else:
                self.unique_indices[column].clear()
                
            # Построение уникального индекса
            for row in range(self.table.rowCount()):
                item = self.table.item(row, column)
                if item:
                    value = item.text()
                    self.unique_indices[column][value] = row
        else:
            if column not in self.indices:
                self.indices[column] = {}
            else:
                self.indices[column].clear()
                
            # Построение неуникального индекса
            for row in range(self.table.rowCount()):
                item = self.table.item(row, column)
                if item:
                    value = item.text()
                    if value not in self.indices[column]:
                        self.indices[column][value] = []
                    self.indices[column][value].append(row)
    
    def update_index(self, row: int, column: int, value: str):
        """
        Обновляет индекс при изменении значения в ячейке.
        
        Args:
            row: Индекс строки
            column: Индекс столбца
            value: Новое значение
        """
        if column not in self.indexed_columns:
            return
            
        # Обновление уникального индекса
        if column in self.unique_indices:
            # Удаляем старую запись для этой строки (если есть)
            for old_value, old_row in list(self.unique_indices[column].items()):
                if old_row == row:
                    del self.unique_indices[column][old_value]
                    break
            
            # Добавляем новую запись
            self.unique_indices[column][value] = row
        
        # Обновление неуникального индекса
        elif column in self.indices:
            # Удаляем строку из старых записей
            for old_value, rows in list(self.indices[column].items()):
                if row in rows:
                    rows.remove(row)
                    if not rows:  # Если список пуст, удаляем запись
                        del self.indices[column][old_value]
                    break
            
            # Добавляем строку в новую запись
            if value not in self.indices[column]:
                self.indices[column][value] = []
            self.indices[column][value].append(row)
    
    def find_rows(self, column: int, value: str) -> List[int]:
        """
        Находит строки по значению в указанном столбце.
        
        Args:
            column: Индекс столбца для поиска
            value: Значение для поиска
            
        Returns:
            List[int]: Список индексов строк, содержащих указанное значение
        """
        if column in self.unique_indices and value in self.unique_indices[column]:
            return [self.unique_indices[column][value]]
        
        if column in self.indices and value in self.indices[column]:
            return self.indices[column][value].copy()
        
        return []
    
    def find_row(self, column: int, value: str) -> Optional[int]:
        """
        Находит строку по уникальному значению в указанном столбце.
        
        Args:
            column: Индекс столбца для поиска
            value: Значение для поиска
            
        Returns:
            Optional[int]: Индекс строки или None, если строка не найдена
        """
        if column in self.unique_indices and value in self.unique_indices[column]:
            return self.unique_indices[column][value]
        
        # Для неуникальных индексов возвращаем первую найденную строку
        if column in self.indices and value in self.indices[column] and self.indices[column][value]:
            return self.indices[column][value][0]
        
        return None
    
    def clear_indices(self):
        """Очищает все индексы."""
        self.indices.clear()
        self.unique_indices.clear()
        self.indexed_columns.clear()


class OptimizedTable(QTableWidget):
    """
    Оптимизированная таблица с поддержкой индексов и кэширования.
    """
    
    def __init__(self, *args, **kwargs):
        """Инициализация оптимизированной таблицы."""
        super().__init__(*args, **kwargs)
        self.logger = get_module_logger('ui.table_utils.OptimizedTable')
        self.index = TableIndex(self)
        self._row_data = {}  # Кэширование данных строк
        self._loading = False
        
        # Подключаем сигналы для обновления индексов
        self.cellChanged.connect(self._on_cell_changed)
        
        self.logger.debug("Оптимизированная таблица инициализирована")
    
    def setItem(self, row: int, column: int, item: QTableWidgetItem):
        """
        Переопределенный метод установки элемента с обновлением индексов.
        
        Args:
            row: Индекс строки
            column: Индекс столбца
            item: Элемент для установки
        """
        super().setItem(row, column, item)
        
        # Кэшируем данные элемента
        if row not in self._row_data:
            self._row_data[row] = {}
        self._row_data[row][column] = item.text() if item else ""
        
        # Обновляем индекс, если элемент был изменен не в процессе загрузки данных
        if not self._loading and column in self.index.indexed_columns:
            self.index.update_index(row, column, item.text() if item else "")
    
    def _on_cell_changed(self, row: int, column: int):
        """
        Обработчик изменения ячейки.
        
        Args:
            row: Индекс строки
            column: Индекс столбца
        """
        if not self._loading and column in self.index.indexed_columns:
            item = self.item(row, column)
            value = item.text() if item else ""
            self.index.update_index(row, column, value)
            
            # Обновляем кэш
            if row not in self._row_data:
                self._row_data[row] = {}
            self._row_data[row][column] = value
    
    def clear(self):
        """Очищает таблицу и все индексы."""
        super().clear()
        self.index.clear_indices()
        self._row_data.clear()
    
    def create_index(self, column: int, unique: bool = False):
        """
        Создает индекс для указанного столбца.
        
        Args:
            column: Индекс столбца для индексирования
            unique: Флаг, указывающий, являются ли значения в столбце уникальными
        """
        self.index.create_index(column, unique)
    
    def find_rows(self, column: int, value: str) -> List[int]:
        """
        Находит строки по значению в указанном столбце.
        
        Args:
            column: Индекс столбца для поиска
            value: Значение для поиска
            
        Returns:
            List[int]: Список индексов строк, содержащих указанное значение
        """
        return self.index.find_rows(column, value)
    
    def find_row(self, column: int, value: str) -> Optional[int]:
        """
        Находит строку по уникальному значению в указанном столбце.
        
        Args:
            column: Индекс столбца для поиска
            value: Значение для поиска
            
        Returns:
            Optional[int]: Индекс строки или None, если строка не найдена
        """
        return self.index.find_row(column, value)
    
    def get_row_data(self, row: int) -> Dict[int, str]:
        """
        Возвращает данные строки из кэша.
        
        Args:
            row: Индекс строки
            
        Returns:
            Dict[int, str]: Словарь с данными строки {column: value}
        """
        return self._row_data.get(row, {})
    
    def set_loading(self, loading: bool):
        """
        Устанавливает флаг загрузки данных для оптимизации обновления индексов.
        
        Args:
            loading: Флаг загрузки данных
        """
        self._loading = loading
        if not loading:
            # После загрузки перестраиваем все индексы
            for column in self.index.indexed_columns:
                is_unique = column in self.index.unique_indices
                self.index.rebuild_index(column, is_unique)
    
    def rebuild_indices(self):
        """Перестраивает все индексы."""
        for column in self.index.indexed_columns:
            is_unique = column in self.index.unique_indices
            self.index.rebuild_index(column, is_unique)


class UIUpdater(QObject):
    """
    Класс для управления отложенным обновлением UI.
    Позволяет группировать и отложить обновления интерфейса для повышения производительности.
    """
    
    # Сигнал для обновления UI
    update_signal = pyqtSignal(str, object)
    
    def __init__(self, parent=None):
        """
        Инициализация менеджера обновлений UI.
        
        Args:
            parent: Родительский объект
        """
        super().__init__(parent)
        self.logger = get_module_logger('ui.table_utils.UIUpdater')
        
        # Очередь обновлений: {target_id: {property: value}}
        self._updates = {}
        
        # Таймер для отложенного обновления
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._process_updates)
        
        # Время задержки обновления (мс)
        self._delay = 100
        
        # Флаг блокировки обновлений
        self._update_blocked = False
        
        # Обработчики обновлений для разных целей
        self._handlers = {}
        
        self.logger.debug("Менеджер обновлений UI инициализирован")
    
    def register_handler(self, target_id: str, handler: Callable[[Dict[str, Any]], None]):
        """
        Регистрирует обработчик обновлений для указанной цели.
        
        Args:
            target_id: Идентификатор цели обновления
            handler: Функция-обработчик, принимающая словарь обновлений
        """
        self._handlers[target_id] = handler
        self.logger.debug(f"Зарегистрирован обработчик для {target_id}")
    
    def schedule_update(self, target_id: str, property_name: str, value: Any):
        """
        Планирует обновление свойства цели.
        
        Args:
            target_id: Идентификатор цели обновления
            property_name: Имя свойства для обновления
            value: Новое значение свойства
        """
        if self._update_blocked:
            return
            
        if target_id not in self._updates:
            self._updates[target_id] = {}
        
        self._updates[target_id][property_name] = value
        
        # Запускаем таймер, если он не активен
        if not self._update_timer.isActive():
            self._update_timer.start(self._delay)
    
    def _process_updates(self):
        """Обрабатывает все запланированные обновления."""
        # Копируем обновления и очищаем очередь
        updates = self._updates.copy()
        self._updates.clear()
        
        # Обрабатываем каждое обновление
        for target_id, properties in updates.items():
            # Отправляем сигнал для обновления
            self.update_signal.emit(target_id, properties)
            
            # Вызываем зарегистрированный обработчик, если есть
            if target_id in self._handlers:
                try:
                    self._handlers[target_id](properties)
                except Exception as e:
                    self.logger.error(f"Ошибка в обработчике обновлений для {target_id}: {e}")
    
    def block_updates(self, blocked: bool = True):
        """
        Блокирует или разблокирует обновления.
        
        Args:
            blocked: Флаг блокировки
        """
        self._update_blocked = blocked
        
        if not blocked and self._updates:
            # Запускаем обработку накопившихся обновлений
            self._update_timer.start(0)
    
    def set_delay(self, delay_ms: int):
        """
        Устанавливает задержку перед обновлением.
        
        Args:
            delay_ms: Задержка в миллисекундах
        """
        self._delay = max(0, delay_ms)
    
    def flush(self):
        """Немедленно обрабатывает все запланированные обновления."""
        if self._update_timer.isActive():
            self._update_timer.stop()
        
        self._process_updates()


class BatchDataLoader:
    """
    Класс для пакетной загрузки данных в таблицу.
    Оптимизирует заполнение таблицы большим количеством данных.
    """
    
    def __init__(self, table: QTableWidget):
        """
        Инициализация загрузчика данных.
        
        Args:
            table: Таблица для загрузки данных
        """
        self.logger = get_module_logger('ui.table_utils.BatchDataLoader')
        self.table = table
        self.batch_size = 100  # Размер пакета по умолчанию
        
        # Если таблица оптимизированная, используем её функционал
        self.optimized = isinstance(table, OptimizedTable)
        
        self.logger.debug("Загрузчик данных инициализирован")
    
    @handle_errors(error_msg="Ошибка при пакетной загрузке данных в таблицу")
    def load_data(self, data: List[Dict[str, Any]], column_mapping: Dict[str, int], 
                  item_creators: Optional[Dict[str, Callable[[Any], QTableWidgetItem]]] = None):
        """
        Загружает данные в таблицу пакетами.
        
        Args:
            data: Список словарей с данными
            column_mapping: Маппинг ключей данных на индексы столбцов {key: column_index}
            item_creators: Функции создания элементов для разных полей {key: creator_func}
        """
        if not data:
            return
            
        # Устанавливаем флаг загрузки для оптимизированной таблицы
        if self.optimized:
            self.table.set_loading(True)
        
        # Блокируем обновление UI таблицы
        self.table.setUpdatesEnabled(False)
        
        try:
            # Устанавливаем количество строк
            row_count = len(data)
            self.table.setRowCount(row_count)
            
            # Определяем создателей элементов по умолчанию
            default_creator = lambda value: QTableWidgetItem(str(value) if value is not None else "")
            creators = item_creators or {}
            
            # Загружаем данные пакетами
            for start_idx in range(0, row_count, self.batch_size):
                end_idx = min(start_idx + self.batch_size, row_count)
                
                # Обрабатываем пакет
                for row_idx in range(start_idx, end_idx):
                    row_data = data[row_idx]
                    
                    for key, col_idx in column_mapping.items():
                        if key in row_data:
                            value = row_data[key]
                            
                            # Используем специальный создатель элемента, если есть
                            creator = creators.get(key, default_creator)
                            item = creator(value)
                            
                            self.table.setItem(row_idx, col_idx, item)
                
                # Даем возможность обработать события между пакетами
                QApplication.processEvents()
        
        finally:
            # Включаем обновление UI таблицы
            self.table.setUpdatesEnabled(True)
            
            # Сбрасываем флаг загрузки для оптимизированной таблицы
            if self.optimized:
                self.table.set_loading(False)
            
            self.logger.debug(f"Загружено {row_count} строк данных в таблицу")


# Создаем синглтон для глобального доступа к обновлению UI
_ui_updater = UIUpdater()


def get_ui_updater() -> UIUpdater:
    """
    Возвращает глобальный экземпляр менеджера обновлений UI.
    
    Returns:
        UIUpdater: Глобальный экземпляр менеджера обновлений UI
    """
    return _ui_updater 