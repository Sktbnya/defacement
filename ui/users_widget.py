#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль виджета управления пользователями для WDM_V12.
Содержит класс UsersWidget, который отображает список пользователей и позволяет управлять ими.
"""

import os
import datetime
import re
from typing import Dict, List, Any, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QScrollArea, QSizePolicy, QGridLayout, QTableWidget, 
    QTableWidgetItem, QHeaderView, QSplitter, QTabWidget,
    QSpacerItem, QMessageBox, QDialog, QFormLayout,
    QLineEdit, QComboBox, QCheckBox, QDialogButtonBox, QListWidget
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QFont, QColor

from utils.logger import get_module_logger, log_exception
from utils.common import format_timestamp, get_diff_color, get_status_color, handle_errors


class UserDialog(QDialog):
    """Диалог для добавления или редактирования пользователя"""
    
    def __init__(self, app_context, user_id=None, parent=None):
        """
        Инициализация диалога
        
        Args:
            app_context: Контекст приложения
            user_id: ID пользователя для редактирования (None для нового пользователя)
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger('ui.users_widget.user_dialog')
        self.app_context = app_context
        self.user_id = user_id
        self.user_data = None
        
        # Получаем данные о пользователе, если это редактирование
        if user_id:
            self.user_data = self.app_context.auth_manager.get_user(self.app_context, user_id)
        
        # Настройка диалога
        self.setWindowTitle("Редактирование пользователя" if user_id else "Добавление пользователя")
        self.resize(400, 400)
        
        # Инициализация UI
        self._init_ui()
        
        self.logger.debug(f"Диалог {'редактирования' if user_id else 'добавления'} пользователя создан")
    
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        # Основной макет
        layout = QVBoxLayout(self)
        
        # Форма для ввода данных
        form_layout = QFormLayout()
        
        # Имя пользователя
        self.username_edit = QLineEdit()
        if self.user_data:
            self.username_edit.setText(self.user_data.get('username', ''))
        form_layout.addRow("Имя пользователя:", self.username_edit)
        
        # Пароль (только для нового пользователя)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("Пароль:", self.password_edit)
        
        # Подтверждение пароля
        self.confirm_password_edit = QLineEdit()
        self.confirm_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("Подтверждение пароля:", self.confirm_password_edit)
        
        # Если это редактирование, добавляем примечание
        if self.user_data:
            note_label = QLabel("Оставьте поля пароля пустыми, если не хотите его менять")
            note_label.setStyleSheet("color: gray;")
            form_layout.addRow("", note_label)
        
        # Полное имя
        self.full_name_edit = QLineEdit()
        if self.user_data:
            self.full_name_edit.setText(self.user_data.get('full_name', ''))
        form_layout.addRow("Полное имя:", self.full_name_edit)
        
        # Email
        self.email_edit = QLineEdit()
        if self.user_data:
            self.email_edit.setText(self.user_data.get('email', ''))
        form_layout.addRow("Email:", self.email_edit)
        
        # Роль
        self.role_combo = QComboBox()
        self._fill_roles_combo()
        form_layout.addRow("Роль:", self.role_combo)
        
        # Активен
        self.active_check = QCheckBox("Активен")
        self.active_check.setChecked(True)
        if self.user_data:
            self.active_check.setChecked(bool(self.user_data.get('is_active', 1)))
        form_layout.addRow("", self.active_check)
        
        layout.addLayout(form_layout)
        
        # Кнопки
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _fill_roles_combo(self):
        """Заполнение выпадающего списка ролей"""
        try:
            # Получаем список ролей
            roles = self.app_context.auth_manager.get_all_roles(self.app_context)
            
            # Заполняем комбобокс
            self.role_combo.clear()
            
            for role in roles:
                self.role_combo.addItem(role['name'], role['id'])
            
            # Если это редактирование, выбираем текущую роль
            if self.user_data and 'role_id' in self.user_data:
                role_id = self.user_data['role_id']
                index = self.role_combo.findData(role_id)
                if index >= 0:
                    self.role_combo.setCurrentIndex(index)
        
        except Exception as e:
            self.logger.error(f"Ошибка при заполнении списка ролей: {e}")
            log_exception(self.logger, "Ошибка заполнения списка ролей")
    
    @handle_errors(error_msg="Ошибка при сохранении пользователя")
    def accept(self):
        """Сохранение изменений пользователя"""
        # Получаем данные из формы
        user_data = {
            'username': self.username_edit.text().strip(),
            'email': self.email_edit.text().strip(),
            'role': self.role_combo.currentText(),
            'active': self.active_check.isChecked()
        }
        
        # Проверяем обязательные поля
        if not user_data['username']:
            QMessageBox.warning(self, "Ошибка", "Имя пользователя не может быть пустым")
            return
        
        if not user_data['email']:
            QMessageBox.warning(self, "Ошибка", "Email не может быть пустым")
            return
        
        # Проверяем формат email
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, user_data['email']):
            QMessageBox.warning(self, "Ошибка", "Некорректный формат email")
            return
        
        # Если это новый пользователь, проверяем пароль
        if not self.user_id:
            password = self.password_edit.text()
            confirm_password = self.confirm_password_edit.text()
            
            if not password:
                QMessageBox.warning(self, "Ошибка", "Пароль не может быть пустым")
                return
            
            if password != confirm_password:
                QMessageBox.warning(self, "Ошибка", "Пароли не совпадают")
                return
            
            user_data['password'] = password
        
        # Сохраняем изменения
        if self.user_id:
            success = self.app_context.auth_manager.update_user(self.app_context, user_id=self.user_id, **user_data)
        else:
            success = self.app_context.auth_manager.create_user(self.app_context, **user_data)
        
        if success:
            super().accept()
        else:
            QMessageBox.critical(self, "Ошибка", "Не удалось сохранить пользователя")


class RolesManagementDialog(QDialog):
    """Диалог для управления ролями и разрешениями"""
    
    def __init__(self, app_context, parent=None):
        """
        Инициализация диалога
        
        Args:
            app_context: Контекст приложения
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger('ui.users_widget.roles_dialog')
        self.app_context = app_context
        
        # Настройка диалога
        self.setWindowTitle("Управление ролями и разрешениями")
        self.resize(600, 500)
        
        # Инициализация UI
        self._init_ui()
        
        # Заполнение данными
        self._load_roles()
        
        self.logger.debug("Диалог управления ролями и разрешениями создан")
    
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        # Основной макет
        layout = QVBoxLayout(self)
        
        # Создаем разделитель
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Левая панель - список ролей
        roles_widget = QWidget()
        roles_layout = QVBoxLayout(roles_widget)
        
        roles_label = QLabel("Роли:")
        roles_layout.addWidget(roles_label)
        
        self.roles_list = QListWidget()
        self.roles_list.currentItemChanged.connect(self._on_role_selected)
        roles_layout.addWidget(self.roles_list)
        
        splitter.addWidget(roles_widget)
        
        # Правая панель - разрешения для выбранной роли
        permissions_widget = QWidget()
        permissions_layout = QVBoxLayout(permissions_widget)
        
        permissions_label = QLabel("Разрешения:")
        permissions_layout.addWidget(permissions_label)
        
        self.permissions_table = QTableWidget(0, 2)
        self.permissions_table.setHorizontalHeaderLabels(["Разрешение", "Описание"])
        self.permissions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.permissions_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.permissions_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.permissions_table.setAlternatingRowColors(True)
        permissions_layout.addWidget(self.permissions_table)
        
        splitter.addWidget(permissions_widget)
        
        # Устанавливаем соотношение ширины
        splitter.setSizes([200, 400])
        
        layout.addWidget(splitter)
        
        # Кнопки
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        # Добавляем кнопку "Сохранить"
        self.btn_save = button_box.addButton("Сохранить", QDialogButtonBox.ButtonRole.ActionRole)
        self.btn_save.clicked.connect(self._save_permissions)
        
        layout.addWidget(button_box)
    
    def _load_roles(self):
        """Загрузка списка ролей"""
        try:
            # Получаем список ролей
            roles = self.app_context.auth_manager.get_all_roles(self.app_context)
            
            # Заполняем список
            self.roles_list.clear()
            
            for role in roles:
                item = QListWidgetItem(role['name'])
                item.setData(Qt.ItemDataRole.UserRole, role['id'])
                self.roles_list.addItem(item)
            
            # Выбираем первую роль по умолчанию
            if self.roles_list.count() > 0:
                self.roles_list.setCurrentRow(0)
        
        except Exception as e:
            self.logger.error(f"Ошибка при загрузке списка ролей: {e}")
            log_exception(self.logger, "Ошибка загрузки списка ролей")
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить список ролей: {e}")
    
    def _on_role_selected(self, current, previous):
        """
        Обработчик выбора роли
        
        Args:
            current: Текущий выбранный элемент
            previous: Предыдущий выбранный элемент
        """
        if not current:
            return
        
        # Получаем ID выбранной роли
        role_id = current.data(Qt.ItemDataRole.UserRole)
        
        # Загружаем разрешения для этой роли
        self._load_permissions(role_id)
    
    def _load_permissions(self, role_id):
        """
        Загрузка разрешений для роли
        
        Args:
            role_id: ID роли
        """
        try:
            # Получаем список всех разрешений
            all_permissions = self.app_context.auth_manager.get_all_permissions(self.app_context)
            
            # Получаем список ID разрешений для выбранной роли
            role_permissions = self.app_context.auth_manager.get_role_permissions(self.app_context, role_id)
            
            # Очищаем таблицу
            self.permissions_table.setRowCount(0)
            
            # Заполняем таблицу
            for i, perm in enumerate(all_permissions):
                self.permissions_table.insertRow(i)
                
                # Чекбокс для выбора разрешения
                checkbox_item = QTableWidgetItem()
                checkbox_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                checkbox_item.setCheckState(
                    Qt.CheckState.Checked if perm['id'] in role_permissions else Qt.CheckState.Unchecked
                )
                checkbox_item.setData(Qt.ItemDataRole.UserRole, perm['id'])
                
                # Название разрешения
                name_item = QTableWidgetItem(perm['name'])
                name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                
                # Описание разрешения
                desc_item = QTableWidgetItem(perm['description'])
                desc_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                
                self.permissions_table.setItem(i, 0, name_item)
                self.permissions_table.setItem(i, 1, desc_item)
                
                # Устанавливаем чекбокс в первый столбец
                self.permissions_table.setCellWidget(i, 0, self._create_checkbox(
                    perm['name'], 
                    perm['id'] in role_permissions
                ))
        
        except Exception as e:
            self.logger.error(f"Ошибка при загрузке разрешений для роли ID={role_id}: {e}")
            log_exception(self.logger, f"Ошибка загрузки разрешений для роли")
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить разрешения для роли: {e}")
    
    def _create_checkbox(self, text, checked=False):
        """
        Создание чекбокса для таблицы
        
        Args:
            text: Текст чекбокса
            checked: Состояние чекбокса
            
        Returns:
            QWidget: Виджет с чекбоксом
        """
        # Создаем виджет-контейнер
        widget = QWidget()
        
        # Создаем горизонтальный макет
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 2, 5, 2)
        
        # Создаем чекбокс
        checkbox = QCheckBox(text)
        checkbox.setChecked(checked)
        
        layout.addWidget(checkbox)
        layout.addStretch()
        
        return widget
    
    def _save_permissions(self):
        """Сохранение разрешений для выбранной роли"""
        try:
            # Получаем выбранную роль
            current_item = self.roles_list.currentItem()
            if not current_item:
                QMessageBox.warning(self, "Предупреждение", "Выберите роль")
                return
            
            role_id = current_item.data(Qt.ItemDataRole.UserRole)
            
            # Собираем выбранные разрешения
            selected_permissions = []
            
            for row in range(self.permissions_table.rowCount()):
                # Получаем виджет ячейки
                cell_widget = self.permissions_table.cellWidget(row, 0)
                
                # Ищем чекбокс в виджете
                checkbox = cell_widget.findChild(QCheckBox)
                
                if checkbox and checkbox.isChecked():
                    # Получаем ID разрешения из данных ячейки
                    perm_id = row + 1  # Предполагаем, что ID разрешений последовательны и начинаются с 1
                    selected_permissions.append(perm_id)
            
            # Сохраняем разрешения
            success, message = self.app_context.auth_manager.update_role_permissions(
                self.app_context, role_id, selected_permissions
            )
            
            if success:
                QMessageBox.information(self, "Информация", "Разрешения успешно сохранены")
                self.logger.info(f"Сохранены разрешения для роли ID={role_id}")
            else:
                QMessageBox.critical(self, "Ошибка", message)
                self.logger.warning(f"Не удалось сохранить разрешения для роли ID={role_id}: {message}")
        
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении разрешений: {e}")
            log_exception(self.logger, "Ошибка сохранения разрешений")
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить разрешения: {e}")
    
    def accept(self):
        """Обработка подтверждения диалога"""
        super().accept()


class UsersWidget(QWidget):
    """Виджет для управления пользователями"""
    
    def __init__(self, app_context, parent=None):
        """
        Инициализация виджета управления пользователями
        
        Args:
            app_context: Контекст приложения
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger('ui.users_widget')
        self.app_context = app_context
        self.parent = parent
        
        # Инициализация UI
        self._init_ui()
        
        # Обновление данных
        self.update_data()
        
        self.logger.debug("Виджет управления пользователями инициализирован")
    
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        # Основной макет
        layout = QVBoxLayout(self)
        
        # Панель инструментов
        toolbar_layout = QHBoxLayout()
        
        # Кнопка "Обновить"
        self.btn_refresh = QPushButton("Обновить")
        self.btn_refresh.setIcon(QIcon("resources/icons/refresh.png"))
        self.btn_refresh.clicked.connect(self.update_data)
        toolbar_layout.addWidget(self.btn_refresh)
        
        # Кнопка "Добавить пользователя"
        self.btn_add_user = QPushButton("Добавить пользователя")
        self.btn_add_user.setIcon(QIcon("resources/icons/add_user.png"))
        self.btn_add_user.clicked.connect(self._add_user)
        toolbar_layout.addWidget(self.btn_add_user)
        
        # Кнопка "Удалить пользователя"
        self.btn_delete_user = QPushButton("Удалить пользователя")
        self.btn_delete_user.setIcon(QIcon("resources/icons/delete_user.png"))
        self.btn_delete_user.clicked.connect(self._delete_user)
        toolbar_layout.addWidget(self.btn_delete_user)
        
        # Кнопка "Управление ролями"
        self.btn_manage_roles = QPushButton("Управление ролями")
        self.btn_manage_roles.setIcon(QIcon("resources/icons/roles.png"))
        self.btn_manage_roles.clicked.connect(self._manage_roles)
        toolbar_layout.addWidget(self.btn_manage_roles)
        
        toolbar_layout.addStretch()
        
        layout.addLayout(toolbar_layout)
        
        # Таблица пользователей
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ID", "Имя пользователя", "Полное имя", "Email", "Роль", "Активен"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        
        # Подключение сигнала по двойному клику
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        
        layout.addWidget(self.table)
        
        # Панель статуса
        status_layout = QHBoxLayout()
        
        self.status_label = QLabel("Всего пользователей: 0")
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        
        layout.addLayout(status_layout)
    
    @handle_errors(error_msg="Ошибка при обновлении данных о пользователях")
    def update_data(self):
        """Обновление данных о пользователях"""
        # Получаем список пользователей
        users = self.app_context.auth_manager.get_all_users(self.app_context)
        
        # Очищаем таблицу
        self.table.setRowCount(0)
        
        if not users:
            self.status_label.setText("Всего пользователей: 0")
            return
        
        # Заполняем таблицу
        for i, user in enumerate(users):
            self.table.insertRow(i)
            
            # ID
            self.table.setItem(i, 0, QTableWidgetItem(str(user.get('id', ''))))
            
            # Имя пользователя
            self.table.setItem(i, 1, QTableWidgetItem(user.get('username', '')))
            
            # Полное имя
            self.table.setItem(i, 2, QTableWidgetItem(user.get('full_name', '')))
            
            # Email
            self.table.setItem(i, 3, QTableWidgetItem(user.get('email', '')))
            
            # Роль
            role_name = user.get('role_name', '')
            role_item = QTableWidgetItem(role_name)
            
            # Установка цвета в зависимости от роли
            if role_name == 'admin':
                role_item.setForeground(QColor(255, 0, 0))  # Красный
            elif role_name == 'manager':
                role_item.setForeground(QColor(0, 0, 255))  # Синий
            
            self.table.setItem(i, 4, role_item)
            
            # Активен
            is_active = user.get('is_active', 0)
            active_text = "Да" if is_active else "Нет"
            active_item = QTableWidgetItem(active_text)
            
            # Установка цвета в зависимости от статуса
            if is_active:
                active_item.setForeground(QColor(0, 128, 0))  # Зеленый
            else:
                active_item.setForeground(QColor(128, 128, 128))  # Серый
            
            self.table.setItem(i, 5, active_item)
        
        # Обновляем панель статуса
        self.status_label.setText(f"Всего пользователей: {len(users)}")
    
    def _on_cell_double_clicked(self, row, column):
        """
        Обработчик двойного клика по ячейке
        
        Args:
            row: Индекс строки
            column: Индекс столбца
        """
        try:
            # Получаем ID пользователя
            user_id = int(self.table.item(row, 0).text())
            
            # Открываем диалог редактирования
            self._edit_user(user_id)
        
        except Exception as e:
            self.logger.error(f"Ошибка при обработке двойного клика: {e}")
            log_exception(self.logger, "Ошибка обработки двойного клика")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Ошибка", f"Ошибка при открытии пользователя: {e}", QMessageBox.Icon.Critical)
    
    def _add_user(self):
        """Добавление нового пользователя"""
        try:
            # Создаем и открываем диалог добавления пользователя
            dialog = UserDialog(self.app_context, parent=self)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                # Обновляем данные в таблице
                self.update_data()
                
                self.logger.info("Добавлен новый пользователь")
        
        except Exception as e:
            self.logger.error(f"Ошибка при добавлении пользователя: {e}")
            log_exception(self.logger, "Ошибка добавления пользователя")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Ошибка", f"Не удалось добавить пользователя: {e}", QMessageBox.Icon.Critical)
    
    def _edit_user(self, user_id):
        """
        Редактирование пользователя
        
        Args:
            user_id: ID пользователя
        """
        try:
            # Создаем и открываем диалог редактирования пользователя
            dialog = UserDialog(self.app_context, user_id=user_id, parent=self)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                # Обновляем данные в таблице
                self.update_data()
                
                self.logger.info(f"Отредактирован пользователь ID={user_id}")
        
        except Exception as e:
            self.logger.error(f"Ошибка при редактировании пользователя ID={user_id}: {e}")
            log_exception(self.logger, f"Ошибка редактирования пользователя")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Ошибка", f"Не удалось отредактировать пользователя: {e}", QMessageBox.Icon.Critical)
    
    def _delete_user(self):
        """Удаление выбранного пользователя"""
        try:
            # Получаем выбранные строки
            selected_rows = self.table.selectionModel().selectedRows()
            
            if not selected_rows:
                if hasattr(self.parent, "show_message"):
                    self.parent.show_message("Предупреждение", "Выберите пользователя для удаления", QMessageBox.Icon.Warning)
                return
            
            # Получаем ID пользователя
            row = selected_rows[0].row()
            user_id = int(self.table.item(row, 0).text())
            username = self.table.item(row, 1).text()
            
            # Запрашиваем подтверждение
            reply = QMessageBox.question(
                self,
                "Подтверждение",
                f"Вы уверены, что хотите удалить пользователя {username}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Удаляем пользователя
                success, message = self.app_context.auth_manager.delete_user(self.app_context, user_id)
                
                if success:
                    # Обновляем данные в таблице
                    self.update_data()
                    
                    if hasattr(self.parent, "show_message"):
                        self.parent.show_message("Информация", "Пользователь успешно удален")
                    
                    self.logger.info(f"Удален пользователь ID={user_id}")
                else:
                    if hasattr(self.parent, "show_message"):
                        self.parent.show_message("Ошибка", message, QMessageBox.Icon.Critical)
                    
                    self.logger.warning(f"Не удалось удалить пользователя ID={user_id}: {message}")
        
        except Exception as e:
            self.logger.error(f"Ошибка при удалении пользователя: {e}")
            log_exception(self.logger, "Ошибка удаления пользователя")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Ошибка", f"Не удалось удалить пользователя: {e}", QMessageBox.Icon.Critical)
    
    def _manage_roles(self):
        """Открытие диалога управления ролями и разрешениями"""
        try:
            # Проверяем, есть ли разрешение на управление ролями
            if not self.app_context.auth_manager.has_permission(self.app_context, "manage_roles"):
                if hasattr(self.parent, "show_message"):
                    self.parent.show_message(
                        "Предупреждение", 
                        "У вас нет разрешения на управление ролями", 
                        QMessageBox.Icon.Warning
                    )
                return
            
            # Создаем и открываем диалог
            dialog = RolesManagementDialog(self.app_context, self)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                # Обновляем данные в таблице
                self.update_data()
                
                self.logger.info("Управление ролями и разрешениями выполнено")
        
        except Exception as e:
            self.logger.error(f"Ошибка при открытии диалога управления ролями: {e}")
            log_exception(self.logger, "Ошибка открытия диалога управления ролями")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message(
                    "Ошибка", 
                    f"Не удалось открыть диалог управления ролями: {e}", 
                    QMessageBox.Icon.Critical
                ) 