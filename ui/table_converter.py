#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль конвертации существующих таблиц в оптимизированные.
Содержит утилиты для устранения дублирования кода в UI и улучшения повторного использования.
"""

import os
from typing import Dict, List, Any, Optional, Union, Callable, Tuple, Set

from PyQt6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, 
    QHeaderView, QTableView, QAbstractItemView
)
from PyQt6.QtCore import Qt, QModelIndex, QVariant

from utils.logger import get_module_logger
from ui.table_utils import OptimizedTable, TableIndex, BatchDataLoader, get_ui_updater


class TableConverter:
    """
    Класс для конвертации стандартных QTableWidget в оптимизированные таблицы.
    Сохраняет все данные и настройки исходной таблицы.
    """
    
    def __init__(self):
        """Инициализация конвертера таблиц."""
        self.logger = get_module_logger('ui.table_converter.TableConverter')
    
    def convert_table(self, parent, table_name: str, index_columns: Optional[Dict[int, bool]] = None) -> OptimizedTable:
        """
        Конвертирует стандартную таблицу в оптимизированную.
        
        Args:
            parent: Родительский виджет, содержащий таблицу
            table_name: Имя таблицы для доступа через getattr
            index_columns: Словарь {column_idx: is_unique} для создания индексов
            
        Returns:
            OptimizedTable: Новая оптимизированная таблица
        """
        # Получаем исходную таблицу
        old_table = getattr(parent, table_name)
        if not isinstance(old_table, QTableWidget):
            self.logger.error(f"Объект {table_name} не является QTableWidget")
            return None
            
        # Сохраняем данные и настройки исходной таблицы
        row_count = old_table.rowCount()
        col_count = old_table.columnCount()
        headers = [old_table.horizontalHeaderItem(i).text() if old_table.horizontalHeaderItem(i) else f"Column {i}" 
                  for i in range(col_count)]
        selection_mode = old_table.selectionMode()
        selection_behavior = old_table.selectionBehavior()
        edit_triggers = old_table.editTriggers()
        sorting_enabled = old_table.isSortingEnabled()
        alternative_row_colors = old_table.alternatingRowColors()
        
        # Сохраняем данные
        data = []
        for row in range(row_count):
            row_data = {}
            for col in range(col_count):
                item = old_table.item(row, col)
                if item:
                    row_data[col] = {
                        'text': item.text(),
                        'flags': item.flags(),
                        'background': item.background(),
                        'foreground': item.foreground(),
                        'tooltip': item.toolTip(),
                        'icon': item.icon(),
                        'data': {Qt.ItemDataRole.UserRole + i: item.data(Qt.ItemDataRole.UserRole + i) 
                                for i in range(10) if item.data(Qt.ItemDataRole.UserRole + i) is not None}
                    }
            data.append(row_data)
        
        # Сохраняем размеры столбцов
        column_widths = [old_table.columnWidth(i) for i in range(col_count)]
        header_resize_modes = [old_table.horizontalHeader().sectionResizeMode(i) 
                              for i in range(col_count)]
        
        # Получаем сигналы
        connected_signals = {}
        for signal_name in ['cellClicked', 'cellDoubleClicked', 'itemSelectionChanged']:
            if hasattr(old_table, signal_name):
                signal = getattr(old_table, signal_name)
                connected_slots = []
                
                # К сожалению, нет прямого доступа к слотам, подключенным к сигналу
                # Это примерная реализация, которая может не учитывать все подключенные слоты
                # В реальном использовании необходимо подключить нужные сигналы вручную
                
                connected_signals[signal_name] = connected_slots
        
        # Создаем новую оптимизированную таблицу
        new_table = OptimizedTable(parent)
        new_table.setObjectName(old_table.objectName())
        
        # Настраиваем таблицу
        new_table.setColumnCount(col_count)
        new_table.setRowCount(row_count)
        new_table.setHorizontalHeaderLabels(headers)
        new_table.setSelectionMode(selection_mode)
        new_table.setSelectionBehavior(selection_behavior)
        new_table.setEditTriggers(edit_triggers)
        new_table.setSortingEnabled(sorting_enabled)
        new_table.setAlternatingRowColors(alternative_row_colors)
        
        # Устанавливаем размеры столбцов
        for i, width in enumerate(column_widths):
            new_table.setColumnWidth(i, width)
            new_table.horizontalHeader().setSectionResizeMode(i, header_resize_modes[i])
        
        # Устанавливаем блокировку обновлений при загрузке
        new_table.set_loading(True)
        
        # Заполняем данными
        for row, row_data in enumerate(data):
            for col, item_data in row_data.items():
                item = QTableWidgetItem(item_data['text'])
                item.setFlags(item_data['flags'])
                item.setBackground(item_data['background'])
                item.setForeground(item_data['foreground'])
                item.setToolTip(item_data['tooltip'])
                item.setIcon(item_data['icon'])
                
                for role, value in item_data['data'].items():
                    item.setData(role, value)
                
                new_table.setItem(row, col, item)
        
        # Создаем индексы
        if index_columns:
            for col, is_unique in index_columns.items():
                if 0 <= col < col_count:
                    new_table.create_index(col, is_unique)
        
        # Включаем обновление
        new_table.set_loading(False)
        
        # Заменяем таблицу в родительском объекте
        old_layout = old_table.parent().layout()
        if old_layout:
            # Находим индекс старой таблицы в layout
            for i in range(old_layout.count()):
                if old_layout.itemAt(i).widget() == old_table:
                    # Удаляем старую таблицу из layout
                    old_layout.removeWidget(old_table)
                    # Добавляем новую таблицу в то же место
                    old_layout.insertWidget(i, new_table)
                    break
        
        # Заменяем атрибут в родительском объекте
        setattr(parent, table_name, new_table)
        
        # Уничтожаем старую таблицу
        old_table.setParent(None)
        old_table.deleteLater()
        
        self.logger.info(f"Таблица {table_name} успешно конвертирована в оптимизированную таблицу")
        return new_table


class TableStyler:
    """
    Класс для применения стандартных стилей к таблицам.
    Устраняет дублирование кода настройки таблиц.
    """
    
    DEFAULT_STYLE = {
        'enable_sorting': True,
        'alternate_colors': True,
        'selection_behavior': QAbstractItemView.SelectionBehavior.SelectRows,
        'selection_mode': QAbstractItemView.SelectionMode.SingleSelection,
        'edit_triggers': QAbstractItemView.EditTrigger.NoEditTriggers,
        'hide_grid': False,
        'header_resize_mode': QHeaderView.ResizeMode.ResizeToContents,
        'stretch_last_column': True,
    }
    
    def __init__(self):
        """Инициализация стилизатора таблиц."""
        self.logger = get_module_logger('ui.table_converter.TableStyler')
    
    def apply_style(self, table: Union[QTableWidget, QTableView], 
                    style: Optional[Dict[str, Any]] = None):
        """
        Применяет стандартный стиль к таблице.
        
        Args:
            table: Таблица для стилизации
            style: Словарь с параметрами стиля, переопределяющими значения по умолчанию
        """
        # Объединяем стиль по умолчанию с переданным стилем
        full_style = self.DEFAULT_STYLE.copy()
        if style:
            full_style.update(style)
        
        # Применяем стиль
        if isinstance(table, (QTableWidget, QTableView)):
            # Общие настройки для QTableWidget и QTableView
            table.setSortingEnabled(full_style['enable_sorting'])
            table.setAlternatingRowColors(full_style['alternate_colors'])
            table.setSelectionBehavior(full_style['selection_behavior'])
            table.setSelectionMode(full_style['selection_mode'])
            table.setEditTriggers(full_style['edit_triggers'])
            
            # Настройки заголовков
            header = table.horizontalHeader()
            if full_style['header_resize_mode'] is not None:
                for i in range(table.columnCount()):
                    header.setSectionResizeMode(i, full_style['header_resize_mode'])
            
            if full_style['stretch_last_column']:
                header.setStretchLastSection(True)
            
            # Скрытие сетки
            if full_style['hide_grid']:
                table.setShowGrid(False)
            
            self.logger.debug(f"Стиль применен к таблице {table.objectName()}")
        else:
            self.logger.warning(f"Объект {table} не является QTableWidget или QTableView")


class CommonTableSetup:
    """
    Класс с общими методами для настройки таблиц.
    Устраняет дублирование кода в разных виджетах.
    """
    
    @staticmethod
    def setup_site_table(table: QTableWidget, connect_signals: bool = True, 
                        parent=None, double_click_handler=None):
        """
        Настраивает таблицу для отображения сайтов.
        
        Args:
            table: Таблица для настройки
            connect_signals: Флаг подключения сигналов
            parent: Родительский виджет для сигналов
            double_click_handler: Обработчик двойного клика
        """
        logger = get_module_logger('ui.table_converter.CommonTableSetup')
        
        # Устанавливаем заголовки
        headers = ["ID", "URL", "Название", "Тип", "Статус", "Последняя проверка", "Интервал", "Теги"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        
        # Применяем стиль
        styler = TableStyler()
        styler.apply_style(table, {
            'header_resize_mode': QHeaderView.ResizeMode.Interactive,
            'enable_sorting': True
        })
        
        # Подключаем сигналы
        if connect_signals and parent:
            if double_click_handler:
                table.cellDoubleClicked.connect(double_click_handler)
            else:
                # Стандартный обработчик
                def on_double_click(row, column):
                    item = table.item(row, 0)
                    if item:
                        site_id = item.text()
                        # Здесь должен быть код открытия сайта
                        logger.debug(f"Открытие сайта с ID {site_id}")
                
                table.cellDoubleClicked.connect(on_double_click)
        
        logger.debug("Таблица сайтов настроена")
        return table
    
    @staticmethod
    def setup_changes_table(table: QTableWidget, connect_signals: bool = True, 
                          parent=None, double_click_handler=None):
        """
        Настраивает таблицу для отображения изменений.
        
        Args:
            table: Таблица для настройки
            connect_signals: Флаг подключения сигналов
            parent: Родительский виджет для сигналов
            double_click_handler: Обработчик двойного клика
        """
        logger = get_module_logger('ui.table_converter.CommonTableSetup')
        
        # Устанавливаем заголовки
        headers = ["ID", "Сайт", "Время обнаружения", "Тип", "Статус", "Детали"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        
        # Применяем стиль
        styler = TableStyler()
        styler.apply_style(table, {
            'header_resize_mode': QHeaderView.ResizeMode.Interactive,
            'enable_sorting': True
        })
        
        # Подключаем сигналы
        if connect_signals and parent:
            if double_click_handler:
                table.cellDoubleClicked.connect(double_click_handler)
            else:
                # Стандартный обработчик
                def on_double_click(row, column):
                    item = table.item(row, 0)
                    if item:
                        change_id = item.text()
                        # Здесь должен быть код открытия изменения
                        logger.debug(f"Открытие изменения с ID {change_id}")
                
                table.cellDoubleClicked.connect(on_double_click)
        
        logger.debug("Таблица изменений настроена")
        return table
    
    @staticmethod
    def setup_monitoring_table(table: QTableWidget, connect_signals: bool = True, 
                             parent=None, double_click_handler=None):
        """
        Настраивает таблицу для отображения задач мониторинга.
        
        Args:
            table: Таблица для настройки
            connect_signals: Флаг подключения сигналов
            parent: Родительский виджет для сигналов
            double_click_handler: Обработчик двойного клика
        """
        logger = get_module_logger('ui.table_converter.CommonTableSetup')
        
        # Устанавливаем заголовки
        headers = ["ID", "Сайт", "Статус", "Прогресс", "Начало", "Оценочное время", "Действия"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        
        # Применяем стиль
        styler = TableStyler()
        styler.apply_style(table, {
            'header_resize_mode': QHeaderView.ResizeMode.Interactive,
            'enable_sorting': True
        })
        
        # Подключаем сигналы
        if connect_signals and parent:
            if double_click_handler:
                table.cellDoubleClicked.connect(double_click_handler)
        
        logger.debug("Таблица мониторинга настроена")
        return table 