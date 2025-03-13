#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль профиля пользователя для WDM_V12.
Содержит класс ProfileWidget, который позволяет пользователю редактировать свои данные.
"""

import os
import datetime
import re
from typing import Dict, List, Any, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QGridLayout, QLineEdit, QMessageBox, QFormLayout, 
    QGroupBox, QCheckBox, QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QFont

from utils.logger import get_module_logger, log_exception
from utils.common import format_timestamp, get_diff_color, get_status_color, handle_errors


class ChangePasswordDialog(QDialog):
    """Диалог для изменения пароля"""
    
    def __init__(self, app_context, parent=None):
        """
        Инициализация диалога
        
        Args:
            app_context: Контекст приложения
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger('ui.profile_widget.password_dialog')
        self.app_context = app_context
        
        # Настройка диалога
        self.setWindowTitle("Изменение пароля")
        self.resize(400, 200)
        
        # Инициализация UI
        self._init_ui()
        
        self.logger.debug("Диалог изменения пароля создан")
    
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        # Основной макет
        layout = QVBoxLayout(self)
        
        # Форма для ввода данных
        form_layout = QFormLayout()
        
        # Текущий пароль
        self.current_password_edit = QLineEdit()
        self.current_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("Текущий пароль:", self.current_password_edit)
        
        # Новый пароль
        self.new_password_edit = QLineEdit()
        self.new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("Новый пароль:", self.new_password_edit)
        
        # Подтверждение нового пароля
        self.confirm_password_edit = QLineEdit()
        self.confirm_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("Подтверждение пароля:", self.confirm_password_edit)
        
        layout.addLayout(form_layout)
        
        # Кнопки
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    @handle_errors(error_msg="Ошибка при изменении пароля")
    def accept(self):
        """Обработка подтверждения диалога"""
        try:
            # Проверяем введенные данные
            current_password = self.current_password_edit.text()
            new_password = self.new_password_edit.text()
            confirm_password = self.confirm_password_edit.text()
            
            # Валидация
            if not current_password:
                QMessageBox.warning(self, "Предупреждение", "Текущий пароль не может быть пустым")
                return
            
            if not new_password:
                QMessageBox.warning(self, "Предупреждение", "Новый пароль не может быть пустым")
                return
            
            if new_password != confirm_password:
                QMessageBox.warning(self, "Предупреждение", "Пароли не совпадают")
                return
            
            # Получаем текущего пользователя
            user = self.app_context.auth_manager.get_current_user()
            if not user:
                QMessageBox.critical(self, "Ошибка", "Не удалось получить информацию о текущем пользователе")
                return
            
            # Меняем пароль
            success, message = self.app_context.auth_manager.change_password(
                self.app_context,
                user_id=user['id'],
                new_password=new_password,
                current_password=current_password
            )
            
            if not success:
                QMessageBox.critical(self, "Ошибка", message)
                return
            
            QMessageBox.information(self, "Информация", "Пароль успешно изменен")
            
            # Закрываем диалог
            super().accept()
        
        except Exception as e:
            self.logger.error(f"Ошибка при изменении пароля: {e}")
            log_exception(self.logger, "Ошибка изменения пароля")
            QMessageBox.critical(self, "Ошибка", f"Не удалось изменить пароль: {e}")


class ProfileWidget(QWidget):
    """Виджет для отображения и редактирования профиля пользователя"""
    
    # Сигнал об изменении профиля
    profile_changed = pyqtSignal()
    
    def __init__(self, app_context, parent=None):
        """
        Инициализация виджета профиля
        
        Args:
            app_context: Контекст приложения
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger('ui.profile_widget')
        self.app_context = app_context
        self.parent = parent
        
        # Инициализация UI
        self._init_ui()
        
        # Обновление данных
        self.update_data()
        
        self.logger.debug("Виджет профиля пользователя инициализирован")
    
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        # Основной макет
        layout = QVBoxLayout(self)
        
        # Заголовок
        header_layout = QHBoxLayout()
        
        # Иконка
        icon_label = QLabel()
        icon_pixmap = QPixmap("resources/icons/user.png").scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio)
        icon_label.setPixmap(icon_pixmap)
        header_layout.addWidget(icon_label)
        
        # Заголовок
        title_label = QLabel("Профиль пользователя")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Разделитель
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)
        
        # Форма с данными профиля
        form_group = QGroupBox("Данные пользователя")
        form_layout = QFormLayout(form_group)
        
        # Имя пользователя
        self.username_label = QLabel()
        form_layout.addRow("Имя пользователя:", self.username_label)
        
        # Полное имя
        self.full_name_edit = QLineEdit()
        form_layout.addRow("Полное имя:", self.full_name_edit)
        
        # Email
        self.email_edit = QLineEdit()
        form_layout.addRow("Email:", self.email_edit)
        
        # Роль
        self.role_label = QLabel()
        form_layout.addRow("Роль:", self.role_label)
        
        # Последний вход
        self.last_login_label = QLabel()
        form_layout.addRow("Последний вход:", self.last_login_label)
        
        layout.addWidget(form_group)
        
        # Кнопки
        buttons_layout = QHBoxLayout()
        
        # Кнопка "Изменить пароль"
        self.btn_change_password = QPushButton("Изменить пароль")
        self.btn_change_password.setIcon(QIcon("resources/icons/password.png"))
        self.btn_change_password.clicked.connect(self._change_password)
        buttons_layout.addWidget(self.btn_change_password)
        
        # Кнопка "Сохранить изменения"
        self.btn_save = QPushButton("Сохранить изменения")
        self.btn_save.setIcon(QIcon("resources/icons/save.png"))
        self.btn_save.clicked.connect(self._save_profile)
        buttons_layout.addWidget(self.btn_save)
        
        buttons_layout.addStretch()
        
        layout.addLayout(buttons_layout)
        
        layout.addStretch()
    
    @handle_errors(error_msg="Ошибка при обновлении данных профиля")
    def update_data(self):
        """Обновление данных профиля"""
        try:
            # Получаем текущего пользователя
            user = self.app_context.auth_manager.get_current_user()
            
            if not user:
                self.logger.warning("Не удалось получить информацию о текущем пользователе")
                return
            
            # Обновляем данные в форме
            self.username_label.setText(user.get('username', ''))
            self.full_name_edit.setText(user.get('full_name', ''))
            self.email_edit.setText(user.get('email', ''))
            
            # Получаем информацию о роли
            role = self.app_context.auth_manager.get_user_role(self.app_context)
            self.role_label.setText(role.get('name', '') if role else '')
            
            # Форматируем дату последнего входа
            last_login = user.get('last_login')
            if last_login:
                if isinstance(last_login, str):
                    try:
                        dt = datetime.datetime.fromisoformat(last_login.replace('Z', '+00:00'))
                        date_str = dt.strftime("%d.%m.%Y %H:%M:%S")
                    except (ValueError, TypeError):
                        date_str = last_login
                elif isinstance(last_login, datetime.datetime):
                    date_str = last_login.strftime("%d.%m.%Y %H:%M:%S")
                else:
                    date_str = str(last_login)
            else:
                date_str = "Никогда"
            
            self.last_login_label.setText(date_str)
        
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении данных профиля: {e}")
            log_exception(self.logger, "Ошибка обновления данных профиля")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Ошибка", f"Не удалось обновить данные профиля: {e}", QMessageBox.Icon.Critical)
    
    @handle_errors(error_msg="Ошибка при сохранении профиля")
    def _save_profile(self):
        """Сохранение изменений профиля"""
        try:
            # Получаем текущего пользователя
            user = self.app_context.auth_manager.get_current_user()
            
            if not user:
                if hasattr(self.parent, "show_message"):
                    self.parent.show_message("Ошибка", "Не удалось получить информацию о текущем пользователе", QMessageBox.Icon.Critical)
                return
            
            # Получаем введенные данные
            full_name = self.full_name_edit.text().strip()
            email = self.email_edit.text().strip()
            
            # Обновляем данные пользователя
            success, message = self.app_context.auth_manager.update_user(
                self.app_context,
                user_id=user['id'],
                full_name=full_name,
                email=email
            )
            
            if not success:
                if hasattr(self.parent, "show_message"):
                    self.parent.show_message("Ошибка", message, QMessageBox.Icon.Critical)
                return
            
            # Обновляем данные
            self.update_data()
            
            # Отправляем сигнал об изменении профиля
            self.profile_changed.emit()
            
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Информация", "Профиль успешно обновлен")
            
            self.logger.info("Профиль пользователя обновлен")
        
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении профиля: {e}")
            log_exception(self.logger, "Ошибка сохранения профиля")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Ошибка", f"Не удалось сохранить профиль: {e}", QMessageBox.Icon.Critical)
    
    def _change_password(self):
        """Изменение пароля"""
        try:
            # Создаем и открываем диалог изменения пароля
            dialog = ChangePasswordDialog(self.app_context, self)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.logger.info("Пароль пользователя изменен")
        
        except Exception as e:
            self.logger.error(f"Ошибка при изменении пароля: {e}")
            log_exception(self.logger, "Ошибка изменения пароля")
            if hasattr(self.parent, "show_message"):
                self.parent.show_message("Ошибка", f"Не удалось изменить пароль: {e}", QMessageBox.Icon.Critical) 