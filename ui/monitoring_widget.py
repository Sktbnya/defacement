#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль виджета мониторинга для WDM_V12.
Обеспечивает интерфейс для управления процессом мониторинга,
отображения статистики и текущих задач мониторинга.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QGridLayout, QGroupBox,
    QSplitter, QMenu, QStatusBar, QFrame, QSpacerItem, QSizePolicy, QMessageBox
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QFont, QAction, QColor, QBrush

# Внутренние импорты
from utils.logger import get_module_logger, log_exception
from core.settings import Settings
from utils.common import format_timestamp, get_diff_color, get_status_color, handle_errors


class MonitoringWidget(QWidget):
    """
    Виджет для управления процессом мониторинга сайтов.
    Предоставляет интерфейс для запуска и остановки мониторинга,
    отображения текущего состояния и задач мониторинга.
    """
    
    def __init__(self, app_context, parent=None):
        """
        Инициализация виджета мониторинга
        
        Args:
            app_context: Контекст приложения
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger('ui.monitoring')
        self.logger.debug("Инициализация виджета мониторинга")
        
        self.app_context = app_context
        self.settings = Settings()
        
        # Статистика мониторинга
        self.monitoring_stats = {
            'total_sites': 0,
            'checked_sites': 0,
            'failed_sites': 0,
            'queued_sites': 0,
            'detected_changes': 0,
            'start_time': None,
            'active_time': 0
        }
        
        # Создание UI
        self._init_ui()
        
        # Таймер обновления статистики
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_statistics)
        self.update_timer.start(2000)  # Обновление каждые 2 секунды
        
        # Обновляем интерфейс
        self.refresh()
        
        self.logger.debug("Виджет мониторинга инициализирован")
    
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        # Основной макет
        main_layout = QVBoxLayout(self)
        
        # Макет для управления и статистики
        top_layout = QHBoxLayout()
        
        # Группа управления мониторингом
        control_group = QGroupBox("Управление мониторингом")
        control_layout = QGridLayout(control_group)
        
        # Кнопки управления
        self.start_button = QPushButton("Запустить мониторинг")
        self.start_button.setIcon(QIcon("resources/icons/start.png"))
        self.start_button.setMinimumWidth(180)
        self.start_button.clicked.connect(self._on_start_monitoring)
        control_layout.addWidget(self.start_button, 0, 0)
        
        self.stop_button = QPushButton("Остановить мониторинг")
        self.stop_button.setIcon(QIcon("resources/icons/stop.png"))
        self.stop_button.setMinimumWidth(180)
        self.stop_button.clicked.connect(self._on_stop_monitoring)
        self.stop_button.setEnabled(False)  # По умолчанию мониторинг не запущен
        control_layout.addWidget(self.stop_button, 0, 1)
        
        self.check_selected_button = QPushButton("Проверить выбранные сайты")
        self.check_selected_button.setIcon(QIcon("resources/icons/check.png"))
        self.check_selected_button.clicked.connect(self._on_check_selected)
        control_layout.addWidget(self.check_selected_button, 1, 0, 1, 2)
        
        top_layout.addWidget(control_group)
        
        # Группа статистики мониторинга
        stats_group = QGroupBox("Статистика мониторинга")
        stats_layout = QGridLayout(stats_group)
        
        # Статус мониторинга
        stats_layout.addWidget(QLabel("Статус:"), 0, 0)
        self.status_label = QLabel("Остановлен")
        self.status_label.setStyleSheet("font-weight: bold; color: red;")
        stats_layout.addWidget(self.status_label, 0, 1)
        
        # Время работы
        stats_layout.addWidget(QLabel("Время работы:"), 0, 2)
        self.uptime_label = QLabel("00:00:00")
        stats_layout.addWidget(self.uptime_label, 0, 3)
        
        # Прогресс
        stats_layout.addWidget(QLabel("Прогресс:"), 1, 0)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        stats_layout.addWidget(self.progress_bar, 1, 1, 1, 3)
        
        # Статистика проверок
        stats_layout.addWidget(QLabel("Проверено сайтов:"), 2, 0)
        self.checked_sites_label = QLabel("0 / 0")
        stats_layout.addWidget(self.checked_sites_label, 2, 1)
        
        stats_layout.addWidget(QLabel("Обнаружено изменений:"), 2, 2)
        self.changes_detected_label = QLabel("0")
        stats_layout.addWidget(self.changes_detected_label, 2, 3)
        
        stats_layout.addWidget(QLabel("Ошибок проверки:"), 3, 0)
        self.failed_sites_label = QLabel("0")
        stats_layout.addWidget(self.failed_sites_label, 3, 1)
        
        stats_layout.addWidget(QLabel("В очереди:"), 3, 2)
        self.queued_sites_label = QLabel("0")
        stats_layout.addWidget(self.queued_sites_label, 3, 3)
        
        top_layout.addWidget(stats_group)
        
        # Добавляем верхний макет в основной
        main_layout.addLayout(top_layout)
        
        # Таблица активных задач мониторинга
        tasks_group = QGroupBox("Активные задачи мониторинга")
        tasks_layout = QVBoxLayout(tasks_group)
        
        self.tasks_table = QTableWidget()
        self.tasks_table.setColumnCount(5)
        self.tasks_table.setHorizontalHeaderLabels([
            "ID", "Сайт", "URL", "Статус", "Время"
        ])
        self.tasks_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tasks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tasks_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tasks_table.verticalHeader().setVisible(False)
        self.tasks_table.setAlternatingRowColors(True)
        
        tasks_layout.addWidget(self.tasks_table)
        
        # Добавляем группу задач в основной макет
        main_layout.addWidget(tasks_group)
        
        # Строка состояния
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Мониторинг остановлен")
        main_layout.addWidget(self.status_bar)
    
    @handle_errors(error_msg="Ошибка при обновлении данных мониторинга")
    def refresh(self):
        """Обновление данных мониторинга"""
        # Получаем статус мониторинга
        status = self.app_context.get_status()
        
        # Обновляем статус мониторинга
        monitoring_status = status.get('monitoring_status', 'stopped')
        if monitoring_status == 'running':
            self.status_label.setText("Статус: Запущен")
            self.status_label.setStyleSheet("color: green;")
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.status_bar.showMessage("Мониторинг запущен и активен")
        else:
            self.status_label.setText("Статус: Остановлен")
            self.status_label.setStyleSheet("color: red;")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.status_bar.showMessage("Мониторинг остановлен")
        
        # Получаем и обновляем статистику
        self._update_statistics()
        
        # Обновляем таблицу задач
        self._update_tasks_table()
    
    @handle_errors(error_msg="Ошибка при обновлении статистики")
    def _update_statistics(self):
        """Обновление статистики мониторинга"""
        try:
            # Получаем статистику от менеджера мониторинга
            stats = self.app_context.monitor_manager.get_statistics()
            if not stats:
                return
            
            # Обновляем внутреннюю статистику
            self.monitoring_stats.update({
                'total_sites': stats.get('total_sites', 0),
                'checked_sites': stats.get('checked_sites', 0),
                'failed_sites': stats.get('failed_sites', 0),
                'queued_sites': stats.get('queued_sites', 0),
                'detected_changes': stats.get('detected_changes', 0),
                'start_time': stats.get('start_time'),
                'active_time': stats.get('active_time', 0)
            })
            
            # Обновляем отображение статистики
            self._update_statistics_display()
        
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении статистики мониторинга: {e}")
            log_exception(self.logger, "Ошибка обновления статистики мониторинга")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Ошибка", f"Не удалось обновить статистику мониторинга: {e}", QMessageBox.Icon.Critical)
    
    @handle_errors(error_msg="Ошибка при обновлении отображения статистики")
    def _update_statistics_display(self):
        """Обновление отображения статистики на виджете"""
        try:
            # Обновляем индикаторы
            total = self.monitoring_stats['total_sites']
            checked = self.monitoring_stats['checked_sites']
            
            # Проверено сайтов
            self.checked_sites_label.setText(f"{checked} / {total}")
            
            # Обнаруженные изменения
            self.changes_detected_label.setText(str(self.monitoring_stats['detected_changes']))
            
            # Ошибки
            self.failed_sites_label.setText(str(self.monitoring_stats['failed_sites']))
            
            # В очереди
            self.queued_sites_label.setText(str(self.monitoring_stats['queued_sites']))
            
            # Обновляем прогресс-бар
            if total > 0:
                progress = (checked / total) * 100
                self.progress_bar.setValue(int(progress))
            else:
                self.progress_bar.setValue(0)
            
            # Обновляем время активности
            if self.monitoring_stats['start_time']:
                start_time = format_timestamp(self.monitoring_stats['start_time'])
                active_time = self.monitoring_stats['active_time']
                hours = active_time // 3600
                minutes = (active_time % 3600) // 60
                seconds = active_time % 60
                
                self.uptime_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            else:
                self.uptime_label.setText("00:00:00")
        
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении отображения статистики: {e}")
            log_exception(self.logger, "Ошибка обновления отображения статистики")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Ошибка", f"Не удалось обновить отображение статистики: {e}", QMessageBox.Icon.Critical)
    
    def _update_tasks_table(self):
        """Обновление таблицы задач мониторинга"""
        try:
            # Получаем список активных задач от менеджера мониторинга
            active_tasks = self.app_context.get_active_monitoring_tasks()
            
            # Очищаем таблицу
            self.tasks_table.setRowCount(0)
            
            # Заполняем таблицу
            for task in active_tasks:
                row_position = self.tasks_table.rowCount()
                self.tasks_table.insertRow(row_position)
                
                # ID задачи
                task_id_item = QTableWidgetItem(str(task.get('id', '')))
                self.tasks_table.setItem(row_position, 0, task_id_item)
                
                # Название сайта
                site_name_item = QTableWidgetItem(task.get('site_name', ''))
                self.tasks_table.setItem(row_position, 1, site_name_item)
                
                # URL сайта
                url_item = QTableWidgetItem(task.get('url', ''))
                self.tasks_table.setItem(row_position, 2, url_item)
                
                # Статус задачи
                status = task.get('status', '')
                status_item = QTableWidgetItem(status)
                
                # Устанавливаем цвет статуса
                if status == 'В процессе':
                    status_item.setForeground(QBrush(QColor('blue')))
                elif status == 'Завершено':
                    status_item.setForeground(QBrush(QColor('green')))
                elif status == 'Ошибка':
                    status_item.setForeground(QBrush(QColor('red')))
                
                self.tasks_table.setItem(row_position, 3, status_item)
                
                # Время выполнения
                time_item = QTableWidgetItem(task.get('time', ''))
                self.tasks_table.setItem(row_position, 4, time_item)
        
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении таблицы задач мониторинга: {e}")
            log_exception(self.logger, "Ошибка обновления таблицы задач мониторинга")
    
    def _on_start_monitoring(self):
        """Обработчик запуска мониторинга"""
        self.logger.debug("Вызван метод запуска мониторинга из виджета мониторинга")
        
        try:
            # Запускаем мониторинг через контекст приложения
            success = self.app_context.start_monitoring()
            
            if success:
                self.logger.info("Мониторинг успешно запущен")
                self.status_label.setText("Статус: Запущен")
                self.status_label.setStyleSheet("color: green;")
                self.start_button.setEnabled(False)
                self.stop_button.setEnabled(True)
                self.status_bar.showMessage("Мониторинг запущен и активен")
                self.app_context.update_status(monitoring_active=True)
            else:
                self.logger.warning("Не удалось запустить мониторинг")
                self.status_label.setText("Статус: Остановлен")
                self.status_label.setStyleSheet("color: red;")
                self.start_button.setEnabled(True)
                self.stop_button.setEnabled(False)
                self.status_bar.showMessage("Мониторинг остановлен")
        
        except Exception as e:
            self.logger.error(f"Ошибка при запуске мониторинга: {e}")
            log_exception(self.logger, "Ошибка запуска мониторинга")
    
    def _on_stop_monitoring(self):
        """Обработчик остановки мониторинга"""
        self.logger.debug("Вызван метод остановки мониторинга из виджета мониторинга")
        
        try:
            # Останавливаем мониторинг через контекст приложения
            success = self.app_context.stop_monitoring()
            
            if success:
                self.logger.info("Мониторинг успешно остановлен")
                self.status_label.setText("Статус: Остановлен")
                self.status_label.setStyleSheet("color: red;")
                self.start_button.setEnabled(True)
                self.stop_button.setEnabled(False)
                self.status_bar.showMessage("Мониторинг остановлен")
                self.app_context.update_status(monitoring_active=False)
            else:
                self.logger.warning("Не удалось остановить мониторинг")
        
        except Exception as e:
            self.logger.error(f"Ошибка при остановке мониторинга: {e}")
            log_exception(self.logger, "Ошибка остановки мониторинга")
    
    def _on_check_selected(self):
        """Обработчик проверки выбранных сайтов"""
        self.logger.debug("Вызван метод проверки выбранных сайтов")
        
        try:
            # Получаем выбранные сайты из виджета сайтов
            selected_sites = self.app_context.get_selected_sites()
            
            if not selected_sites:
                self.logger.warning("Нет выбранных сайтов для проверки")
                self.status_bar.showMessage("Нет выбранных сайтов для проверки")
                return
            
            # Запускаем проверку выбранных сайтов
            success = self.app_context.check_sites(selected_sites)
            
            if success:
                self.logger.info(f"Запущена проверка {len(selected_sites)} выбранных сайтов")
                self.status_bar.showMessage(f"Запущена проверка {len(selected_sites)} выбранных сайтов")
            else:
                self.logger.warning("Не удалось запустить проверку выбранных сайтов")
                self.status_bar.showMessage("Не удалось запустить проверку выбранных сайтов")
        
        except Exception as e:
            self.logger.error(f"Ошибка при проверке выбранных сайтов: {e}")
            log_exception(self.logger, "Ошибка проверки выбранных сайтов")
            self.status_bar.showMessage(f"Ошибка: {str(e)}") 