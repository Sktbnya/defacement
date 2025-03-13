#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль основного окна приложения для WDM_V12.
Содержит класс MainWindow, который отвечает за отображение основного интерфейса.
"""

import os
import sys
import time
import logging
import webbrowser
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTabWidget, QPushButton, QLabel, QStatusBar, QMessageBox, 
    QFrame, QSplitter, QToolBar, QDialog, QMenu, QFileDialog,
    QCheckBox, QComboBox, QLineEdit, QFormLayout, QListWidget
)
from PyQt6.QtCore import Qt, QSize, QTimer, QThread, pyqtSignal, QSettings
from PyQt6.QtGui import QIcon, QAction, QPixmap, QFont, QColor, QPalette

from utils.logger import get_module_logger, log_exception
from core.app_context import AppContext
from ui.dashboard_widget import DashboardWidget
from ui.sites_widget import SitesWidget
from ui.changes_widget import ChangesWidget
from ui.settings_widget import SettingsWidget
from ui.about_dialog import AboutDialog
from utils.common import format_timestamp, get_diff_color, get_status_color, handle_errors


class MainWindow(QMainWindow):
    """Главное окно приложения"""
    
    def __init__(self, app_context=None):
        """
        Инициализация главного окна
        
        Args:
            app_context: Контекст приложения (если None, будет создан новый)
        """
        super().__init__(None)  # Передаем None как parent
        
        self.logger = get_module_logger('ui.main_window')
        self.logger.debug("Инициализация главного окна")
        
        # Получение контекста приложения
        self.app_context = app_context if app_context else AppContext()
        
        # Сохранение настроек
        self.settings = QSettings("WDM", "WebDiffer")
        
        # Настройка основного окна
        self.setWindowTitle("WDM v12 - Система мониторинга веб-сайтов")
        self.resize(1200, 800)
        
        # Центрирование окна на экране
        self.center_window()
        
        # Установка иконки
        self.setWindowIcon(QIcon("resources/icons/app_icon.png"))
        
        # Инициализация UI
        self._init_ui()
        
        # Таймер для обновления статуса
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status_bar)
        self.status_timer.start(1000)  # Обновление каждую секунду
        
        # Восстановление геометрии и состояния
        self.restore_window_state()
        
        self.logger.debug("Главное окно инициализировано")
    
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        # Создание центрального виджета
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        # Основной макет
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Создание панели инструментов
        self._create_toolbar()
        
        # Создание вкладок
        self.tab_widget = QTabWidget(self)
        main_layout.addWidget(self.tab_widget)
        
        # Создание и добавление виджетов вкладок
        self.dashboard_widget = DashboardWidget(self.app_context, self)
        self.sites_widget = SitesWidget(self.app_context, self)
        self.changes_widget = ChangesWidget(self.app_context, self)
        self.settings_widget = SettingsWidget(self.app_context, self)
        
        self.tab_widget.addTab(self.dashboard_widget, "Панель управления")
        self.tab_widget.addTab(self.sites_widget, "Сайты")
        self.tab_widget.addTab(self.changes_widget, "Изменения")
        self.tab_widget.addTab(self.settings_widget, "Настройки")
        
        # Создание строки состояния
        self._create_status_bar()
        
        # Подключение сигналов
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
    
    def _create_toolbar(self):
        """Создание панели инструментов"""
        toolbar = QToolBar("Основная панель", self)
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        # Кнопка запуска/остановки мониторинга
        self.action_toggle_monitoring = QAction(
            QIcon("resources/icons/play.png"), 
            "Запустить мониторинг", 
            self
        )
        self.action_toggle_monitoring.triggered.connect(self._toggle_monitoring)
        toolbar.addAction(self.action_toggle_monitoring)
        
        # Кнопка проверки всех сайтов
        self.action_check_all = QAction(
            QIcon("resources/icons/refresh.png"), 
            "Проверить все сайты", 
            self
        )
        self.action_check_all.triggered.connect(self._check_all_sites)
        toolbar.addAction(self.action_check_all)
        
        toolbar.addSeparator()
        
        # Кнопка добавления сайта
        self.action_add_site = QAction(
            QIcon("resources/icons/add.png"), 
            "Добавить сайт", 
            self
        )
        self.action_add_site.triggered.connect(self._add_site)
        toolbar.addAction(self.action_add_site)
        
        # Кнопка резервного копирования
        self.action_backup = QAction(
            QIcon("resources/icons/backup.png"), 
            "Создать резервную копию", 
            self
        )
        self.action_backup.triggered.connect(self._create_backup)
        toolbar.addAction(self.action_backup)
        
        toolbar.addSeparator()
        
        # Кнопка "О программе"
        self.action_about = QAction(
            QIcon("resources/icons/info.png"), 
            "О программе", 
            self
        )
        self.action_about.triggered.connect(self._show_about)
        toolbar.addAction(self.action_about)
        
        # Кнопка выхода
        self.action_exit = QAction(
            QIcon("resources/icons/exit.png"), 
            "Выход", 
            self
        )
        self.action_exit.triggered.connect(self.close)
        toolbar.addAction(self.action_exit)
    
    def _create_status_bar(self):
        """Создание строки состояния"""
        self.statusbar = QStatusBar(self)
        self.setStatusBar(self.statusbar)
        
        # Информация о мониторинге
        self.status_monitoring = QLabel("Мониторинг: остановлен")
        self.statusbar.addWidget(self.status_monitoring)
        
        # Разделитель
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.VLine)
        separator1.setFrameShadow(QFrame.Shadow.Sunken)
        self.statusbar.addWidget(separator1)
        
        # Информация о количестве сайтов
        self.status_sites = QLabel("Сайтов: 0")
        self.statusbar.addWidget(self.status_sites)
        
        # Разделитель
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.VLine)
        separator2.setFrameShadow(QFrame.Shadow.Sunken)
        self.statusbar.addWidget(separator2)
        
        # Информация о количестве активных задач
        self.status_workers = QLabel("Активных задач: 0")
        self.statusbar.addWidget(self.status_workers)
        
        # Разделитель
        separator3 = QFrame()
        separator3.setFrameShape(QFrame.Shape.VLine)
        separator3.setFrameShadow(QFrame.Shadow.Sunken)
        self.statusbar.addWidget(separator3)
        
        # Информация о количестве изменений
        self.status_changes = QLabel("Изменений: 0")
        self.statusbar.addWidget(self.status_changes)
        
        # Растягивающийся элемент
        self.statusbar.addPermanentWidget(QWidget(), 1)
        
        # Версия приложения
        self.status_version = QLabel("WDM v12.0")
        self.statusbar.addPermanentWidget(self.status_version)
    
    @handle_errors(error_msg="Ошибка при обновлении статусной строки")
    def update_status_bar(self):
        """Обновление статусной строки"""
        try:
            status = self.app_context.get_status()
            if not status:
                return
            
            # Статус мониторинга
            monitoring_active = status.get('monitoring_active', False)
            monitoring_status = status.get('monitoring_status', 'stopped')
            
            if monitoring_active:
                if monitoring_status == 'running':
                    self.status_monitoring.setText("Мониторинг: Активен")
                    self.status_monitoring.setStyleSheet("color: green;")
                    self.action_toggle_monitoring.setText("Остановить мониторинг")
                    self.action_toggle_monitoring.setIcon(QIcon("resources/icons/stop.png"))
                elif monitoring_status == 'paused':
                    self.status_monitoring.setText("Мониторинг: Приостановлен")
                    self.status_monitoring.setStyleSheet("color: orange;")
                    self.action_toggle_monitoring.setText("Возобновить мониторинг")
                    self.action_toggle_monitoring.setIcon(QIcon("resources/icons/play.png"))
            else:
                self.status_monitoring.setText("Мониторинг: Остановлен")
                self.status_monitoring.setStyleSheet("color: red;")
                self.action_toggle_monitoring.setText("Запустить мониторинг")
                self.action_toggle_monitoring.setIcon(QIcon("resources/icons/play.png"))
            
            # Количество сайтов
            sites_count = status.get('sites_count', 0)
            active_sites = status.get('active_sites_count', 0)
            self.status_sites.setText(f"Сайтов: {sites_count} (активных: {active_sites})")
            
            # Активные задачи
            active_tasks = status.get('active_tasks', 0)
            queued_tasks = status.get('queued_tasks', 0)
            self.status_workers.setText(f"Задач: {active_tasks} активных, {queued_tasks} в очереди")
            
            # Последняя и следующая проверки
            last_check = status.get('last_check')
            next_check = status.get('next_check')
            
            if last_check and next_check:
                self.status_changes.setText(
                    f"Последняя проверка: {format_timestamp(last_check)} | "
                    f"Следующая проверка: {format_timestamp(next_check)}"
                )
            elif last_check:
                self.status_changes.setText(f"Последняя проверка: {format_timestamp(last_check)}")
            elif next_check:
                self.status_changes.setText(f"Следующая проверка: {format_timestamp(next_check)}")
            else:
                self.status_changes.setText("Нет данных о проверках")
            
            # Обновляем активную вкладку
            current_widget = self.tab_widget.currentWidget()
            if hasattr(current_widget, "update_data"):
                current_widget.update_data()
        
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении статусной строки: {e}")
            log_exception(self.logger, "Ошибка обновления статусной строки")
            self.show_message("Ошибка", f"Не удалось обновить статусную строку: {e}", QMessageBox.Icon.Critical)
    
    def _toggle_monitoring(self):
        """Переключение состояния мониторинга"""
        try:
            # Получаем текущий статус
            status = self.app_context.get_status()
            
            if status['monitoring_active']:
                # Останавливаем мониторинг
                if self.app_context.stop_monitoring():
                    self.logger.info("Мониторинг остановлен")
                    self.show_message("Информация", "Мониторинг остановлен")
                else:
                    self.logger.error("Не удалось остановить мониторинг")
                    self.show_message("Ошибка", "Не удалось остановить мониторинг", QMessageBox.Icon.Critical)
            else:
                # Запускаем мониторинг
                if self.app_context.start_monitoring():
                    self.logger.info("Мониторинг запущен")
                    self.show_message("Информация", "Мониторинг запущен")
                else:
                    self.logger.error("Не удалось запустить мониторинг")
                    self.show_message("Ошибка", "Не удалось запустить мониторинг", QMessageBox.Icon.Critical)
            
            # Обновляем строку состояния
            self.update_status_bar()
        
        except Exception as e:
            self.logger.error(f"Ошибка при переключении состояния мониторинга: {e}")
            log_exception(self.logger, "Ошибка переключения состояния мониторинга")
            self.show_message("Ошибка", f"Не удалось переключить состояние мониторинга: {e}", QMessageBox.Icon.Critical)
    
    def _check_all_sites(self):
        """Проверка всех сайтов"""
        try:
            # Запрашиваем подтверждение
            reply = QMessageBox.question(
                self,
                "Подтверждение",
                "Вы уверены, что хотите проверить все сайты сейчас?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Проверяем все сайты
                if self.app_context.check_all_sites_now():
                    self.logger.info("Запущена проверка всех сайтов")
                    self.show_message("Информация", "Запущена проверка всех сайтов")
                else:
                    self.logger.error("Не удалось запустить проверку всех сайтов")
                    self.show_message("Ошибка", "Не удалось запустить проверку всех сайтов", QMessageBox.Icon.Critical)
        
        except Exception as e:
            self.logger.error(f"Ошибка при проверке всех сайтов: {e}")
            log_exception(self.logger, "Ошибка проверки всех сайтов")
            self.show_message("Ошибка", f"Не удалось проверить все сайты: {e}", QMessageBox.Icon.Critical)
    
    def _add_site(self):
        """Добавление нового сайта"""
        # Переключаемся на вкладку "Сайты"
        for i in range(self.tab_widget.count()):
            if isinstance(self.tab_widget.widget(i), SitesWidget):
                self.tab_widget.setCurrentIndex(i)
                break
        
        # Вызываем метод добавления сайта
        if hasattr(self.sites_widget, "show_add_site_dialog"):
            self.sites_widget.show_add_site_dialog()
    
    def _create_backup(self):
        """Создание резервной копии базы данных"""
        try:
            # Выбор директории для сохранения
            backup_dir = QFileDialog.getExistingDirectory(
                self,
                "Выберите директорию для сохранения резервной копии",
                "",
                QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
            )
            
            if backup_dir:
                # Формируем имя файла
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                backup_file = os.path.join(backup_dir, f"wdm_backup_{timestamp}.db")
                
                # Создаем резервную копию
                backup_path = self.app_context.db_manager.backup_database(backup_file)
                
                if backup_path:
                    self.logger.info(f"Резервная копия создана: {backup_path}")
                    self.show_message("Информация", f"Резервная копия создана:\n{backup_path}")
                else:
                    self.logger.error("Не удалось создать резервную копию")
                    self.show_message("Ошибка", "Не удалось создать резервную копию", QMessageBox.Icon.Critical)
        
        except Exception as e:
            self.logger.error(f"Ошибка при создании резервной копии: {e}")
            log_exception(self.logger, "Ошибка создания резервной копии")
            self.show_message("Ошибка", f"Не удалось создать резервную копию: {e}", QMessageBox.Icon.Critical)
    
    def _show_about(self):
        """Отображение диалога "О программе" """
        about_dialog = AboutDialog(self)
        about_dialog.exec()
    
    def _on_tab_changed(self, index):
        """Обработчик изменения активной вкладки"""
        # Получаем текущий виджет
        current_widget = self.tab_widget.widget(index)
        
        # Обновляем данные в виджете, если есть соответствующий метод
        if hasattr(current_widget, "update_data"):
            current_widget.update_data()
    
    @handle_errors(error_msg="Ошибка при отображении сообщения")
    def show_message(self, title, message, icon=QMessageBox.Icon.Information):
        """
        Отображение сообщения пользователю
        
        Args:
            title: Заголовок сообщения
            message: Текст сообщения
            icon: Иконка сообщения
        """
        if icon == QMessageBox.Icon.Critical:
            QMessageBox.critical(self, title, message)
        elif icon == QMessageBox.Icon.Warning:
            QMessageBox.warning(self, title, message)
        else:
            QMessageBox.information(self, title, message)
    
    @handle_errors(error_msg="Ошибка при центрировании окна")
    def center_window(self):
        """Центрирование окна на экране"""
        frame_geometry = self.frameGeometry()
        center_point = QApplication.primaryScreen().availableGeometry().center()
        frame_geometry.moveCenter(center_point)
        self.move(frame_geometry.topLeft())
    
    @handle_errors(error_msg="Ошибка при сохранении состояния окна")
    def save_window_state(self):
        """Сохранение состояния окна"""
        settings = QSettings('WDM', 'WDM_V12')
        settings.setValue('window_geometry', self.saveGeometry())
        settings.setValue('window_state', self.saveState())
    
    @handle_errors(error_msg="Ошибка при восстановлении состояния окна")
    def restore_window_state(self):
        """Восстановление состояния окна"""
        settings = QSettings('WDM', 'WDM_V12')
        geometry = settings.value('window_geometry')
        state = settings.value('window_state')
        
        if geometry:
            self.restoreGeometry(geometry)
        if state:
            self.restoreState(state)
    
    @handle_errors(error_msg="Ошибка при закрытии приложения")
    def closeEvent(self, event):
        """
        Обработчик события закрытия окна
        
        Args:
            event: Событие закрытия
        """
        # Сохраняем состояние окна
        self.save_window_state()
        
        # Останавливаем мониторинг
        self.app_context.stop_monitoring()
        
        # Завершаем работу приложения
        self.app_context.shutdown()
        
        # Принимаем событие закрытия
        event.accept()


# Для тестирования виджета в отдельном режиме
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app_context = AppContext()
    app_context.initialize()
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec()) 