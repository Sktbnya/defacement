#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль диалога "О программе" для WDM_V12.
"""

import os
import sys
import platform
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QTextEdit, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap, QFont

from utils.logger import get_module_logger


class AboutDialog(QDialog):
    """Диалог "О программе" """
    
    def __init__(self, parent=None):
        """
        Инициализация диалога
        
        Args:
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger('ui.about_dialog')
        
        # Настройка диалога
        self.setWindowTitle("О программе")
        self.setMinimumSize(500, 400)
        
        # Инициализация UI
        self._init_ui()
        
        self.logger.debug("Диалог 'О программе' инициализирован")
    
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        # Основной макет
        layout = QVBoxLayout(self)
        
        # Заголовок
        header_layout = QHBoxLayout()
        
        # Логотип
        logo_label = QLabel()
        logo_pixmap = QPixmap("resources/icons/app_icon.png")
        if not logo_pixmap.isNull():
            logo_pixmap = logo_pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(logo_pixmap)
        else:
            logo_label.setText("WDM")
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        
        logo_label.setFixedSize(80, 80)
        header_layout.addWidget(logo_label)
        
        # Информация о программе
        info_layout = QVBoxLayout()
        
        title_label = QLabel("WDM - Web Difference Monitor")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        info_layout.addWidget(title_label)
        
        version_label = QLabel("Версия 12.0")
        version_label.setStyleSheet("font-size: 14px;")
        info_layout.addWidget(version_label)
        
        description_label = QLabel("Система мониторинга изменений веб-сайтов")
        description_label.setStyleSheet("font-size: 12px;")
        info_layout.addWidget(description_label)
        
        copyright_label = QLabel("© 2025 AT-Consulting")
        copyright_label.setStyleSheet("font-size: 10px;")
        info_layout.addWidget(copyright_label)
        
        header_layout.addLayout(info_layout)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Вкладки
        tab_widget = QTabWidget()
        
        # Вкладка "О программе"
        about_tab = QWidget()
        about_layout = QVBoxLayout(about_tab)
        
        about_text = QTextEdit()
        about_text.setReadOnly(True)
        about_text.setHtml("""
        <h3>О программе</h3>
        <p>WDM (Web Difference Monitor) — система мониторинга изменений веб-сайтов. 
        Программа отслеживает изменения на указанных веб-сайтах и уведомляет пользователя о найденных изменениях.</p>
        
        <p>Основные возможности:</p>
        <ul>
            <li>Мониторинг изменений на веб-сайтах</li>
            <li>Поддержка как статических (requests), так и динамических (Selenium) страниц</li>
            <li>Фильтрация контента с помощью CSS-селекторов, XPath и регулярных выражений</li>
            <li>Сохранение снимков и скриншотов страниц</li>
            <li>Уведомления об изменениях</li>
            <li>Группировка сайтов для удобного управления</li>
            <li>Экспорт и импорт списка сайтов</li>
        </ul>
        """)
        
        about_layout.addWidget(about_text)
        
        tab_widget.addTab(about_tab, "О программе")
        
        # Вкладка "Системная информация"
        system_tab = QWidget()
        system_layout = QVBoxLayout(system_tab)
        
        system_text = QTextEdit()
        system_text.setReadOnly(True)
        
        # Собираем информацию о системе
        python_version = sys.version.split("\n")[0]
        os_info = f"{platform.system()} {platform.release()} ({platform.version()})"
        arch = platform.machine()
        processor = platform.processor()
        
        system_html = f"""
        <h3>Системная информация</h3>
        <table>
            <tr><td><b>ОС:</b></td><td>{os_info}</td></tr>
            <tr><td><b>Архитектура:</b></td><td>{arch}</td></tr>
            <tr><td><b>Процессор:</b></td><td>{processor}</td></tr>
            <tr><td><b>Python:</b></td><td>{python_version}</td></tr>
            <tr><td><b>PyQt6:</b></td><td>6.5.0</td></tr>
            <tr><td><b>Selenium:</b></td><td>4.9.0</td></tr>
            <tr><td><b>Requests:</b></td><td>2.29.0</td></tr>
            <tr><td><b>BeautifulSoup4:</b></td><td>4.12.2</td></tr>
        </table>
        """
        
        system_text.setHtml(system_html)
        
        system_layout.addWidget(system_text)
        
        tab_widget.addTab(system_tab, "Системная информация")
        
        # Вкладка "Лицензия"
        license_tab = QWidget()
        license_layout = QVBoxLayout(license_tab)
        
        license_text = QTextEdit()
        license_text.setReadOnly(True)
        license_text.setHtml("""
        <h3>Лицензия</h3>
        <p>Коммерческая лицензия</p>
        
        <p>Copyright (c) 2025 AT-Consulting</p>
        
        <p>Все права защищены.</p>
        
        <p>Данное программное обеспечение является коммерческим продуктом и защищено законом об авторских правах. 
        Несанкционированное копирование, распространение, модификация или использование данного программного 
        обеспечения строго запрещено.</p>
        
        <p>Использование данного программного обеспечения разрешается только при наличии действующей лицензии, 
        приобретенной у официальных представителей.</p>
        
        <p>Для получения информации о приобретении лицензии обратитесь к официальным представителям AT-Consulting.</p>
        """)
        
        license_layout.addWidget(license_text)
        
        tab_widget.addTab(license_tab, "Лицензия")
        
        layout.addWidget(tab_widget)
        
        # Кнопки
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        
        layout.addWidget(button_box) 