#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модульные тесты для оптимизированных компонентов пользовательского интерфейса.
Тестирует функциональность индексации таблиц и отложенного обновления UI.
"""

import os
import sys
import unittest
import time
from unittest.mock import MagicMock, patch

# Добавляем корневую директорию проекта в путь импорта
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PyQt6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QWidget
from PyQt6.QtCore import Qt, QTimer

from ui.table_utils import TableIndex, OptimizedTable, UIUpdater, BatchDataLoader, get_ui_updater
from ui.table_converter import TableConverter, TableStyler, CommonTableSetup


# Создаем экземпляр приложения для тестов
app = QApplication.instance() or QApplication([])


class TableIndexTest(unittest.TestCase):
    """Тесты для класса TableIndex."""
    
    def setUp(self):
        """Подготовка к тестам."""
        self.table = QTableWidget(5, 3)
        self.index = TableIndex(self.table)
        
        # Заполняем таблицу данными
        data = [
            ["1", "Alice", "Developer"],
            ["2", "Bob", "Manager"],
            ["3", "Carol", "Developer"],
            ["4", "Dave", "Designer"],
            ["5", "Eve", "Developer"]
        ]
        
        for row, row_data in enumerate(data):
            for col, value in enumerate(row_data):
                self.table.setItem(row, col, QTableWidgetItem(value))
    
    def test_create_index(self):
        """Тест создания индекса."""
        # Создаем индекс для столбца с профессиями (не уникальный)
        self.index.create_index(2, False)
        
        # Проверяем, что столбец добавлен в индексированные столбцы
        self.assertIn(2, self.index.indexed_columns)
        
        # Проверяем, что индекс создан
        self.assertIn(2, self.index.indices)
        
        # Проверяем содержимое индекса
        self.assertEqual(len(self.index.indices[2]["Developer"]), 3)
        self.assertEqual(len(self.index.indices[2]["Manager"]), 1)
        self.assertEqual(len(self.index.indices[2]["Designer"]), 1)
    
    def test_create_unique_index(self):
        """Тест создания уникального индекса."""
        # Создаем индекс для столбца с ID (уникальный)
        self.index.create_index(0, True)
        
        # Проверяем, что столбец добавлен в индексированные столбцы
        self.assertIn(0, self.index.indexed_columns)
        
        # Проверяем, что уникальный индекс создан
        self.assertIn(0, self.index.unique_indices)
        
        # Проверяем содержимое индекса
        self.assertEqual(self.index.unique_indices[0]["1"], 0)
        self.assertEqual(self.index.unique_indices[0]["2"], 1)
        self.assertEqual(self.index.unique_indices[0]["3"], 2)
    
    def test_find_rows(self):
        """Тест поиска строк по значению."""
        # Создаем индекс для столбца с профессиями
        self.index.create_index(2, False)
        
        # Ищем всех разработчиков
        rows = self.index.find_rows(2, "Developer")
        
        # Проверяем, что найдены все строки
        self.assertEqual(len(rows), 3)
        self.assertIn(0, rows)  # Alice
        self.assertIn(2, rows)  # Carol
        self.assertIn(4, rows)  # Eve
    
    def test_find_row(self):
        """Тест поиска строки по уникальному значению."""
        # Создаем индекс для столбца с ID
        self.index.create_index(0, True)
        
        # Ищем пользователя с ID 3
        row = self.index.find_row(0, "3")
        
        # Проверяем, что найдена правильная строка
        self.assertEqual(row, 2)  # Carol
    
    def test_update_index(self):
        """Тест обновления индекса при изменении значения в ячейке."""
        # Создаем индекс для столбца с профессиями
        self.index.create_index(2, False)
        
        # Меняем профессию Боба с Manager на Developer
        self.table.item(1, 2).setText("Developer")
        self.index.update_index(1, 2, "Developer")
        
        # Ищем всех разработчиков
        rows = self.index.find_rows(2, "Developer")
        
        # Проверяем, что Боб теперь тоже разработчик
        self.assertEqual(len(rows), 4)
        self.assertIn(1, rows)  # Bob
        
        # Проверяем, что нет больше менеджеров
        rows = self.index.find_rows(2, "Manager")
        self.assertEqual(len(rows), 0)


class OptimizedTableTest(unittest.TestCase):
    """Тесты для класса OptimizedTable."""
    
    def setUp(self):
        """Подготовка к тестам."""
        self.table = OptimizedTable(5, 3)
        
        # Заполняем таблицу данными
        data = [
            ["1", "Alice", "Developer"],
            ["2", "Bob", "Manager"],
            ["3", "Carol", "Developer"],
            ["4", "Dave", "Designer"],
            ["5", "Eve", "Developer"]
        ]
        
        for row, row_data in enumerate(data):
            for col, value in enumerate(row_data):
                self.table.setItem(row, col, QTableWidgetItem(value))
    
    def test_create_index(self):
        """Тест создания индекса в оптимизированной таблице."""
        # Создаем индекс для столбца с ID
        self.table.create_index(0, True)
        
        # Проверяем, что индекс создан
        self.assertIn(0, self.table.index.indexed_columns)
        
        # Ищем пользователя по ID
        row = self.table.find_row(0, "3")
        self.assertEqual(row, 2)  # Carol
    
    def test_setItem_with_index(self):
        """Тест обновления индекса при изменении элемента."""
        # Создаем индекс для столбца с профессиями
        self.table.create_index(2, False)
        
        # Меняем профессию Боба через setItem
        self.table.setItem(1, 2, QTableWidgetItem("Developer"))
        
        # Ищем всех разработчиков
        rows = self.table.find_rows(2, "Developer")
        
        # Проверяем, что Боб теперь тоже разработчик
        self.assertEqual(len(rows), 4)
        self.assertIn(1, rows)  # Bob
    
    def test_get_row_data(self):
        """Тест получения данных строки из кэша."""
        # Получаем данные первой строки
        row_data = self.table.get_row_data(0)
        
        # Проверяем данные
        self.assertEqual(row_data[0], "1")
        self.assertEqual(row_data[1], "Alice")
        self.assertEqual(row_data[2], "Developer")
    
    def test_loading_mode(self):
        """Тест режима загрузки данных."""
        # Создаем индекс для столбца с профессиями
        self.table.create_index(2, False)
        
        # Включаем режим загрузки
        self.table.set_loading(True)
        
        # Меняем профессию Боба
        self.table.setItem(1, 2, QTableWidgetItem("Developer"))
        
        # В режиме загрузки индекс не должен обновляться
        rows = self.table.find_rows(2, "Developer")
        self.assertEqual(len(rows), 3)  # Боб еще не считается разработчиком
        
        # Выключаем режим загрузки
        self.table.set_loading(False)
        
        # Теперь индекс должен быть перестроен
        rows = self.table.find_rows(2, "Developer")
        self.assertEqual(len(rows), 4)  # Боб теперь разработчик


class UIUpdaterTest(unittest.TestCase):
    """Тесты для класса UIUpdater."""
    
    def setUp(self):
        """Подготовка к тестам."""
        self.updater = UIUpdater()
        
        # Мок для обработчика обновлений
        self.handler = MagicMock()
        self.updater.register_handler("test_target", self.handler)
    
    def test_schedule_update(self):
        """Тест планирования обновления."""
        # Ставим минимальную задержку
        self.updater.set_delay(1)
        
        # Планируем обновление
        self.updater.schedule_update("test_target", "count", 5)
        
        # Проверяем, что обновление добавлено в очередь
        self.assertIn("test_target", self.updater._updates)
        self.assertEqual(self.updater._updates["test_target"]["count"], 5)
        
        # Ждем обработки обновления (>1ms)
        QTimer.singleShot(10, app.quit)
        app.exec()
        
        # Проверяем, что обработчик был вызван с правильными аргументами
        self.handler.assert_called_once_with({"count": 5})
    
    def test_block_updates(self):
        """Тест блокировки обновлений."""
        # Блокируем обновления
        self.updater.block_updates(True)
        
        # Планируем обновление
        self.updater.schedule_update("test_target", "count", 5)
        
        # Проверяем, что обновление не добавлено в очередь
        self.assertNotIn("test_target", self.updater._updates)
        
        # Разблокируем обновления
        self.updater.block_updates(False)
        
        # Планируем обновление снова
        self.updater.schedule_update("test_target", "count", 5)
        
        # Проверяем, что обновление добавлено в очередь
        self.assertIn("test_target", self.updater._updates)
    
    def test_flush(self):
        """Тест немедленной обработки обновлений."""
        # Планируем обновление с большой задержкой
        self.updater.set_delay(1000)
        self.updater.schedule_update("test_target", "count", 5)
        
        # Немедленно обрабатываем все обновления
        self.updater.flush()
        
        # Проверяем, что очередь пуста
        self.assertEqual(len(self.updater._updates), 0)
        
        # Проверяем, что обработчик был вызван
        self.handler.assert_called_once_with({"count": 5})


class BatchDataLoaderTest(unittest.TestCase):
    """Тесты для класса BatchDataLoader."""
    
    def setUp(self):
        """Подготовка к тестам."""
        self.table = QTableWidget()
        self.loader = BatchDataLoader(self.table)
        
        # Создаем тестовые данные
        self.data = [
            {"id": "1", "name": "Alice", "role": "Developer"},
            {"id": "2", "name": "Bob", "role": "Manager"},
            {"id": "3", "name": "Carol", "role": "Developer"},
            {"id": "4", "name": "Dave", "role": "Designer"},
            {"id": "5", "name": "Eve", "role": "Developer"}
        ]
        
        self.column_mapping = {
            "id": 0,
            "name": 1,
            "role": 2
        }
    
    def test_load_data(self):
        """Тест загрузки данных в таблицу."""
        # Устанавливаем маленький размер пакета для тестирования
        self.loader.batch_size = 2
        
        # Загружаем данные
        self.loader.load_data(self.data, self.column_mapping)
        
        # Проверяем количество строк
        self.assertEqual(self.table.rowCount(), 5)
        
        # Проверяем данные в таблице
        self.assertEqual(self.table.item(0, 0).text(), "1")
        self.assertEqual(self.table.item(0, 1).text(), "Alice")
        self.assertEqual(self.table.item(0, 2).text(), "Developer")
        
        self.assertEqual(self.table.item(1, 0).text(), "2")
        self.assertEqual(self.table.item(1, 1).text(), "Bob")
        self.assertEqual(self.table.item(1, 2).text(), "Manager")


class TableConverterTest(unittest.TestCase):
    """Тесты для класса TableConverter."""
    
    def setUp(self):
        """Подготовка к тестам."""
        self.parent = QWidget()
        self.old_table = QTableWidget(3, 3)
        self.old_table.setObjectName("test_table")
        
        # Заполняем таблицу данными
        data = [
            ["1", "Alice", "Developer"],
            ["2", "Bob", "Manager"],
            ["3", "Carol", "Developer"]
        ]
        
        for row, row_data in enumerate(data):
            for col, value in enumerate(row_data):
                self.old_table.setItem(row, col, QTableWidgetItem(value))
        
        # Устанавливаем заголовки
        self.old_table.setHorizontalHeaderLabels(["ID", "Name", "Role"])
        
        # Добавляем таблицу как атрибут родителя
        setattr(self.parent, "test_table", self.old_table)
        
        # Создаем конвертер
        self.converter = TableConverter()
    
    @patch('ui.table_converter.TableConverter.logger')
    def test_convert_table(self, mock_logger):
        """Тест конвертации таблицы."""
        # Конвертируем таблицу с индексом для ID
        index_columns = {0: True}  # Столбец ID, уникальный
        result = self.converter.convert_table(self.parent, "test_table", index_columns)
        
        # Проверяем, что результат является OptimizedTable
        self.assertIsInstance(result, OptimizedTable)
        
        # Проверяем, что атрибут родителя обновлен
        self.assertIsInstance(getattr(self.parent, "test_table"), OptimizedTable)
        
        # Проверяем, что данные скопированы
        table = getattr(self.parent, "test_table")
        self.assertEqual(table.rowCount(), 3)
        self.assertEqual(table.columnCount(), 3)
        
        # Проверяем заголовки
        self.assertEqual(table.horizontalHeaderItem(0).text(), "ID")
        self.assertEqual(table.horizontalHeaderItem(1).text(), "Name")
        self.assertEqual(table.horizontalHeaderItem(2).text(), "Role")
        
        # Проверяем данные
        self.assertEqual(table.item(0, 0).text(), "1")
        self.assertEqual(table.item(0, 1).text(), "Alice")
        self.assertEqual(table.item(0, 2).text(), "Developer")
        
        # Проверяем, что индекс создан
        self.assertIn(0, table.index.indexed_columns)
        
        # Проверяем, что запись в лог выполнена
        mock_logger.info.assert_called_once()


class TableStylerTest(unittest.TestCase):
    """Тесты для класса TableStyler."""
    
    def setUp(self):
        """Подготовка к тестам."""
        self.table = QTableWidget(3, 3)
        self.table.setObjectName("test_table")
        self.styler = TableStyler()
    
    def test_apply_style(self):
        """Тест применения стиля к таблице."""
        # Применяем стиль по умолчанию
        self.styler.apply_style(self.table)
        
        # Проверяем настройки
        self.assertTrue(self.table.isSortingEnabled())
        self.assertTrue(self.table.alternatingRowColors())
        self.assertEqual(self.table.selectionBehavior(), 
                        self.styler.DEFAULT_STYLE['selection_behavior'])
        self.assertEqual(self.table.selectionMode(), 
                        self.styler.DEFAULT_STYLE['selection_mode'])
        self.assertEqual(self.table.editTriggers(), 
                        self.styler.DEFAULT_STYLE['edit_triggers'])
        
        # Проверяем настройки заголовка
        header = self.table.horizontalHeader()
        self.assertTrue(header.stretchLastSection())
        
        # Проверяем режим изменения размера для первого столбца
        self.assertEqual(header.sectionResizeMode(0), 
                        self.styler.DEFAULT_STYLE['header_resize_mode'])


class CommonTableSetupTest(unittest.TestCase):
    """Тесты для класса CommonTableSetup."""
    
    def setUp(self):
        """Подготовка к тестам."""
        self.parent = QWidget()
        self.table = QTableWidget()
        self.handler = MagicMock()
    
    def test_setup_site_table(self):
        """Тест настройки таблицы сайтов."""
        # Настраиваем таблицу
        CommonTableSetup.setup_site_table(self.table, connect_signals=True, 
                                        parent=self.parent, double_click_handler=self.handler)
        
        # Проверяем количество столбцов и заголовки
        self.assertEqual(self.table.columnCount(), 8)
        self.assertEqual(self.table.horizontalHeaderItem(0).text(), "ID")
        self.assertEqual(self.table.horizontalHeaderItem(1).text(), "URL")
        
        # Проверяем, что сигнал подключен
        self.table.cellDoubleClicked.emit(0, 0)
        self.handler.assert_called_once_with(0, 0)
    
    def test_setup_changes_table(self):
        """Тест настройки таблицы изменений."""
        # Настраиваем таблицу
        CommonTableSetup.setup_changes_table(self.table, connect_signals=True, 
                                          parent=self.parent, double_click_handler=self.handler)
        
        # Проверяем количество столбцов и заголовки
        self.assertEqual(self.table.columnCount(), 6)
        self.assertEqual(self.table.horizontalHeaderItem(0).text(), "ID")
        self.assertEqual(self.table.horizontalHeaderItem(1).text(), "Сайт")
        
        # Проверяем, что сигнал подключен
        self.table.cellDoubleClicked.emit(0, 0)
        self.handler.assert_called_once_with(0, 0)
    
    def test_setup_monitoring_table(self):
        """Тест настройки таблицы мониторинга."""
        # Настраиваем таблицу
        CommonTableSetup.setup_monitoring_table(self.table, connect_signals=True, 
                                              parent=self.parent, double_click_handler=self.handler)
        
        # Проверяем количество столбцов и заголовки
        self.assertEqual(self.table.columnCount(), 7)
        self.assertEqual(self.table.horizontalHeaderItem(0).text(), "ID")
        self.assertEqual(self.table.horizontalHeaderItem(1).text(), "Сайт")
        
        # Проверяем, что сигнал подключен
        self.table.cellDoubleClicked.emit(0, 0)
        self.handler.assert_called_once_with(0, 0)


if __name__ == '__main__':
    unittest.main() 