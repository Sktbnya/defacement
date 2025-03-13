#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль виджета панели мониторинга для WDM_V12.
Содержит класс DashboardWidget, который отображает общую информацию о мониторинге.
"""

import os
import time
import csv
import datetime
from typing import Dict, List, Any, Optional, Union

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QScrollArea, QSizePolicy, QGridLayout, QTableWidget, 
    QTableWidgetItem, QHeaderView, QProgressBar, QTabWidget,
    QSpacerItem, QMessageBox, QMenu, QFileDialog
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QRect, QPointF, QPoint, QPropertyAnimation
from PyQt6.QtGui import (
    QIcon, QPixmap, QFont, QColor, QPalette, QAction, QPainter, 
    QPen, QBrush, QPainterPath, QPaintEvent
)
from PyQt6.QtWidgets import QApplication

from utils.logger import get_module_logger, log_exception
from utils.common import format_timestamp, get_diff_color, get_status_color, handle_errors


class StatusCard(QFrame):
    """Карточка с информацией о статусе"""
    
    # Сигнал для оповещения об изменении значения
    value_changed = pyqtSignal(str, str)  # old_value, new_value
    
    def __init__(self, title, value, icon_path=None, parent=None):
        """
        Инициализация карточки статуса
        
        Args:
            title: Заголовок карточки
            value: Значение
            icon_path: Путь к иконке (опционально)
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger('ui.dashboard_widget.status_card')
        self.logger.debug(f"Инициализация карточки статуса: {title}")
        
        try:
            # Кэш для иконок
            self._icon_cache = {}
            
            # Текущее значение
            self._current_value = str(value)
            
            # Настройка стиля
            self.setFrameShape(QFrame.Shape.StyledPanel)
            self.setFrameShadow(QFrame.Shadow.Raised)
            self.setStyleSheet("""
                StatusCard {
                    background-color: #F5F7FA;
                    border-radius: 5px;
                    border: 1px solid #E2E8F0;
                    padding: 10px;
                }
                StatusCard:hover {
                    background-color: #EDF2F7;
                    border-color: #CBD5E0;
                }
                QLabel {
                    background: transparent;
                }
            """)
            
            # Основной макет
            layout = QHBoxLayout(self)
            layout.setContentsMargins(15, 15, 15, 15)
            layout.setSpacing(10)
            
            # Добавление иконки, если она указана
            self.icon_label = None
            if icon_path:
                self.icon_label = self._create_icon_label(icon_path)
                if self.icon_label:
                    layout.addWidget(self.icon_label)
            
            # Макет для текста
            text_layout = QVBoxLayout()
            text_layout.setSpacing(5)
            
            # Заголовок
            self.title_label = QLabel(title)
            self.title_label.setStyleSheet("""
                font-size: 12px;
                color: #718096;
                font-weight: 500;
            """)
            text_layout.addWidget(self.title_label)
            
            # Значение
            self.value_label = QLabel(self._current_value)
            self.value_label.setStyleSheet("""
                font-size: 20px;
                font-weight: bold;
                color: #2D3748;
            """)
            text_layout.addWidget(self.value_label)
            
            layout.addLayout(text_layout)
            layout.addStretch()
            
            # Анимация для изменения значения
            self.value_animation = QPropertyAnimation(self, b"value_opacity")
            self.value_animation.setDuration(300)  # 300ms для анимации
            self.value_animation.setStartValue(1.0)
            self.value_animation.setEndValue(0.0)
            self.value_animation.finished.connect(self._on_animation_finished)
            
            # Свойство для анимации
            self._value_opacity = 1.0
            
            self.logger.debug(f"Карточка статуса {title} успешно инициализирована")
            
        except Exception as e:
            self.logger.error(f"Ошибка при инициализации карточки статуса {title}: {e}")
            log_exception(self.logger, "Ошибка инициализации карточки статуса")
            raise
    
    def _create_icon_label(self, icon_path: str) -> Optional[QLabel]:
        """
        Создает метку с иконкой
        
        Args:
            icon_path: Путь к иконке
            
        Returns:
            QLabel: Метка с иконкой или None в случае ошибки
        """
        try:
            if not isinstance(icon_path, str) or not icon_path:
                self.logger.error("Некорректный путь к иконке")
                return None
                
            # Проверяем кэш
            if icon_path in self._icon_cache:
                icon = self._icon_cache[icon_path]
            else:
                # Загружаем иконку
                icon = QIcon(icon_path)
                if icon.isNull():
                    self.logger.error(f"Не удалось загрузить иконку: {icon_path}")
                    return None
                    
                # Масштабируем иконку
                pixmap = icon.pixmap(QSize(24, 24))
                icon = QIcon(pixmap)
                
                # Сохраняем в кэш
                self._icon_cache[icon_path] = icon
                
            # Создаем метку
            label = QLabel()
            label.setPixmap(icon.pixmap(QSize(24, 24)))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            return label
            
        except Exception as e:
            self.logger.error(f"Ошибка при создании метки с иконкой: {e}")
            log_exception(self.logger, "Ошибка создания метки с иконкой")
            return None
    
    def _format_value(self, value: Union[int, float]) -> str:
        """
        Форматирует числовое значение
        
        Args:
            value: Числовое значение
            
        Returns:
            str: Отформатированное значение
        """
        try:
            if not isinstance(value, (int, float)):
                self.logger.error(f"Некорректный тип значения: {type(value)}")
                return str(value)
                
            if value >= 1000000:
                return f"{value/1000000:.1f}M"
            elif value >= 1000:
                return f"{value/1000:.1f}K"
            else:
                return str(value)
                
        except Exception as e:
            self.logger.error(f"Ошибка при форматировании значения {value}: {e}")
            log_exception(self.logger, "Ошибка форматирования значения")
            return str(value)
    
    def _highlight_value_change(self, old_value: str, new_value: str):
        """
        Подсвечивает изменение значения
        
        Args:
            old_value: Старое значение
            new_value: Новое значение
        """
        try:
            if old_value != new_value:
                # Определяем цвет подсветки
                if self._is_numeric(old_value) and self._is_numeric(new_value):
                    old_num = float(old_value.replace('K', '000').replace('M', '000000'))
                    new_num = float(new_value.replace('K', '000').replace('M', '000000'))
                    
                    if new_num > old_num:
                        color = QColor("#48BB78")  # Зеленый
                    elif new_num < old_num:
                        color = QColor("#F56565")  # Красный
                    else:
                        color = QColor("#2D3748")  # Серый
                else:
                    color = QColor("#2D3748")  # Серый
                
                # Применяем цвет
                self.value_label.setStyleSheet(f"""
                    font-size: 20px;
                    font-weight: bold;
                    color: {color.name()};
                """)
                
                # Запускаем анимацию
                self.value_animation.start()
        except Exception as e:
            self.logger.error(f"Ошибка при подсветке изменения значения: {e}")
            log_exception(self.logger, "Ошибка подсветки изменения значения")
    
    def _is_numeric(self, value: str) -> bool:
        """
        Проверяет, является ли строка числовой
        
        Args:
            value: Строка для проверки
            
        Returns:
            bool: True если строка числовая, False в противном случае
        """
        try:
            if not isinstance(value, str):
                return False
                
            # Удаляем суффиксы K и M
            value = value.replace('K', '').replace('M', '')
            
            # Пробуем преобразовать в число
            try:
                float(value)
                return True
            except ValueError:
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка при проверке числового значения {value}: {e}")
            log_exception(self.logger, "Ошибка проверки числового значения")
            return False
    
    def _reset_value_color(self):
        """Сбрасывает цвет значения на стандартный"""
        try:
            self.value_label.setStyleSheet("""
                font-size: 20px;
                font-weight: bold;
                color: #2D3748;
            """)
        except Exception as e:
            self.logger.error(f"Ошибка при сбросе цвета значения: {e}")
            log_exception(self.logger, "Ошибка сброса цвета значения")
    
    def _on_animation_finished(self):
        """Обработчик завершения анимации"""
        try:
            self._reset_value_color()
        except Exception as e:
            self.logger.error(f"Ошибка при завершении анимации: {e}")
            log_exception(self.logger, "Ошибка завершения анимации")
    
    @handle_errors(error_msg="Ошибка при обновлении значения индикатора")
    def update_value(self, value):
        """
        Обновляет значение индикатора
        
        Args:
            value: Новое значение
        """
        try:
            # Преобразуем значение в строку
            new_value = str(value)
            
            # Если значение изменилось
            if new_value != self._current_value:
                # Сохраняем старое значение
                old_value = self._current_value
                
                # Обновляем значение
                self._current_value = new_value
                self.value_label.setText(new_value)
                
                # Подсвечиваем изменение
                self._highlight_value_change(old_value, new_value)
                
                # Оповещаем об изменении
                self.value_changed.emit(old_value, new_value)
                
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении значения {value}: {e}")
            log_exception(self.logger, "Ошибка обновления значения")
            raise
    
    def get_value(self) -> str:
        """
        Возвращает текущее значение
        
        Returns:
            str: Текущее значение
        """
        try:
            return self._current_value
        except Exception as e:
            self.logger.error(f"Ошибка при получении значения: {e}")
            log_exception(self.logger, "Ошибка получения значения")
            return ""

class ActivityChartWidget(QWidget):
    """Виджет для отображения графика активности"""
    
    # Сигнал для оповещения об изменении данных
    data_changed = pyqtSignal(list)  # old_data, new_data
    
    def __init__(self, parent=None):
        """
        Инициализация виджета графика активности
        
        Args:
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger('ui.dashboard_widget.activity_chart')
        self.logger.debug("Инициализация виджета графика активности")
        
        try:
            # Данные для графика
            self.data = []
            
            # Ограничение количества точек
            self.max_points = 100
            
            # Кэш для отрисовки
            self._data_cache = {
                'last_cleanup': datetime.datetime.now()
            }
            
            # Настройка размеров
            self.setMinimumSize(400, 200)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            
            # Настройка стиля
            self.setStyleSheet("""
                ActivityChartWidget {
                    background-color: #F5F7FA;
                    border-radius: 5px;
                    border: 1px solid #E2E8F0;
                    padding: 10px;
                }
            """)
            
            # Позиция курсора для подсказки
            self._cursor_pos = None
            
            # Настраиваем отслеживание мыши
            self.setMouseTracking(True)
            
            self.logger.debug("Виджет графика активности успешно инициализирован")
            
        except Exception as e:
            self.logger.error(f"Ошибка при инициализации виджета графика активности: {e}")
            log_exception(self.logger, "Ошибка инициализации виджета графика активности")
            raise
    
    def mouseMoveEvent(self, event):
        """
        Обработчик движения мыши
        
        Args:
            event: Событие движения мыши
        """
        try:
            self._cursor_pos = event.pos()
            self.update()  # Перерисовываем виджет
            self._cleanup_cache()
        except Exception as e:
            self.logger.error(f"Ошибка при обработке движения мыши: {e}")
            log_exception(self.logger, "Ошибка обработки движения мыши")
    
    def leaveEvent(self, event):
        """
        Обработчик ухода мыши
        
        Args:
            event: Событие ухода мыши
        """
        try:
            self._cursor_pos = None
            self.update()  # Перерисовываем виджет без подсказки
            self._limit_data_points()
        except Exception as e:
            self.logger.error(f"Ошибка при обработке ухода мыши: {e}")
            log_exception(self.logger, "Ошибка обработки ухода мыши")
    
    def _get_tooltip_text(self, pos: QPoint) -> str:
        """
        Получает текст подсказки для указанной позиции
        
        Args:
            pos: Позиция курсора
            
        Returns:
            str: Текст подсказки
        """
        try:
            value = self._get_value_at_position(pos.x(), pos.y())
            if value is None:
                return ""
                
            return f"Проверок: {value}"
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении текста подсказки: {e}")
            log_exception(self.logger, "Ошибка получения текста подсказки")
            return ""
    
    def _draw_tooltip(self, painter: QPainter, pos: QPoint):
        """
        Отрисовывает подсказку
        
        Args:
            painter: Объект QPainter
            pos: Позиция курсора
        """
        try:
            text = self._get_tooltip_text(pos)
            if not text:
                return
                
            # Настройки для подсказки
            font = QFont()
            font.setPointSize(8)
            painter.setFont(font)
            
            # Размеры текста
            text_rect = painter.fontMetrics().boundingRect(text)
            
            # Размеры подсказки
            padding = 5
            tooltip_width = text_rect.width() + 2 * padding
            tooltip_height = text_rect.height() + 2 * padding
            
            # Позиция подсказки
            tooltip_x = pos.x() - tooltip_width // 2
            tooltip_y = pos.y() - tooltip_height - 10
            
            # Корректируем позицию, чтобы подсказка не выходила за границы
            rect = self.rect()
            if tooltip_x < 0:
                tooltip_x = 0
            elif tooltip_x + tooltip_width > rect.width():
                tooltip_x = rect.width() - tooltip_width
                
            if tooltip_y < 0:
                tooltip_y = pos.y() + 10
                
            # Фон подсказки
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(45, 55, 72, 230))
            painter.drawRoundedRect(tooltip_x, tooltip_y, tooltip_width, tooltip_height, 3, 3)
            
            # Текст подсказки
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(
                tooltip_x + padding,
                tooltip_y + padding + text_rect.height() - 4,
                text
            )
            
        except Exception as e:
            self.logger.error(f"Ошибка при отрисовке подсказки: {e}")
            log_exception(self.logger, "Ошибка отрисовки подсказки")
    
    def _cleanup_cache(self):
        """Очищает устаревшие данные из кэша"""
        try:
            current_time = datetime.datetime.now()
            if (current_time - self._data_cache['last_cleanup']).total_seconds() > 3600:  # Каждый час
                self._data_cache.clear()
                self._data_cache['last_cleanup'] = current_time
                self.logger.debug("Кэш очищен")
        except Exception as e:
            self.logger.error(f"Ошибка при очистке кэша: {e}")
            log_exception(self.logger, "Ошибка очистки кэша")
    
    def _limit_data_points(self):
        """Ограничивает количество точек данных"""
        try:
            if len(self.data) > self.max_points:
                self.data = self.data[-self.max_points:]
                self.logger.debug(f"Количество точек данных ограничено до {self.max_points}")
        except Exception as e:
            self.logger.error(f"Ошибка при ограничении количества точек данных: {e}")
            log_exception(self.logger, "Ошибка ограничения количества точек данных")
    
    @handle_errors(error_msg="Ошибка при добавлении точки данных")
    def add_data_point(self, timestamp, checks):
        """
        Добавляет точку данных
        
        Args:
            timestamp: Временная метка
            checks: Количество проверок
        """
        try:
            # Конвертируем timestamp в datetime если это строка
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.datetime.fromisoformat(timestamp)
                except ValueError:
                    # Пробуем другие форматы
                    try:
                        timestamp = datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        self.logger.error(f"Некорректный формат времени: {timestamp}")
                        return
            
            # Проверяем, что timestamp это datetime
            if not isinstance(timestamp, datetime.datetime):
                self.logger.error(f"Некорректный тип временной метки: {type(timestamp)}")
                return
                
            # Проверяем, что checks это число
            if not isinstance(checks, (int, float)) or checks < 0:
                self.logger.error(f"Некорректное количество проверок: {checks}")
                return
                
            # Сохраняем старые данные
            old_data = self.data.copy()
            
            # Добавляем новую точку
            self.data.append((timestamp, checks))
            
            # Очищаем кэш
            self._cleanup_cache()
            
            # Ограничиваем количество точек
            self._limit_data_points()
            
            # Оповещаем об изменении
            self.data_changed.emit(old_data)
            
            # Перерисовываем виджет
            self.update()
            
            self.logger.debug(f"Добавлена точка данных: {timestamp}, {checks}")
            
        except Exception as e:
            self.logger.error(f"Ошибка при добавлении точки данных: {e}")
            log_exception(self.logger, "Ошибка добавления точки данных")
            raise
    
    def _update_activity_chart(self, data):
        """
        Обновляет данные графика активности
        
        Args:
            data: Данные для графика
        """
        try:
            if not isinstance(data, list):
                self.logger.error("Некорректный тип данных для графика")
                return
                
            # Сохраняем старые данные
            old_data = self.data.copy()
            
            # Обновляем данные
            self.data = data
            
            # Ограничиваем количество точек
            self._limit_data_points()
            
            # Очищаем кэш
            self._cleanup_cache()
            
            # Перерисовываем виджет
            self.update()
            
            # Оповещаем об изменении
            self.data_changed.emit(old_data)
            
            self.logger.debug(f"Обновлены данные графика активности: {len(data)} точек")
            
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении графика активности: {e}")
            log_exception(self.logger, "Ошибка обновления графика активности")
    
    def _update_cache(self, rect: QRect) -> bool:
        """
        Обновляет кэш для отрисовки
        
        Args:
            rect: Прямоугольник для отрисовки
            
        Returns:
            bool: True если кэш обновлен, False в противном случае
        """
        try:
            # Проверяем необходимость обновления
            need_update = False
            
            if 'rect' not in self._data_cache:
                need_update = True
            elif self._data_cache['rect'] != rect:
                need_update = True
            elif 'data' not in self._data_cache:
                need_update = True
            elif self._data_cache['data'] != self.data:
                need_update = True
                
            if not need_update:
                return False
                
            # Обновляем кэш
            self._data_cache['rect'] = rect
            self._data_cache['data'] = self.data.copy()
            
            # Вычисляем масштаб
            if self.data:
                # Находим диапазон времени
                timestamps = [d[0] for d in self.data]
                min_time = min(timestamps)
                max_time = max(timestamps)
                time_range = (max_time - min_time).total_seconds()
                
                # Находим диапазон значений
                values = [d[1] for d in self.data]
                min_value = min(values)
                max_value = max(values)
                value_range = max(1, max_value - min_value)
                
                # Вычисляем масштаб
                x_scale = rect.width() / max(1, time_range)
                y_scale = rect.height() / max(1, value_range)
                
                # Сохраняем в кэш
                self._data_cache['min_time'] = min_time
                self._data_cache['max_time'] = max_time
                self._data_cache['min_value'] = min_value
                self._data_cache['max_value'] = max_value
                self._data_cache['x_scale'] = x_scale
                self._data_cache['y_scale'] = y_scale
                
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении кэша: {e}")
            log_exception(self.logger, "Ошибка обновления кэша")
            return False
    
    @handle_errors(error_msg="Ошибка при отрисовке графика")
    def paintEvent(self, event: QPaintEvent):
        """
        Обработчик события отрисовки
        
        Args:
            event: Событие отрисовки
        """
        try:
            rect = self.rect()
            
            # Создаем объект для рисования
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Обновляем кэш если нужно
            self._update_cache(rect)
            
            # Рисуем сетку
            self._draw_grid(painter, rect)
            
            # Рисуем данные
            self._draw_data(painter, rect)
            
            # Рисуем курсор и подсказку
            if self._cursor_pos:
                self._draw_tooltip(painter, self._cursor_pos)
                
        except Exception as e:
            self.logger.error(f"Ошибка при отрисовке графика: {e}")
            log_exception(self.logger, "Ошибка отрисовки графика")
    
    def _draw_cursor(self, painter: QPainter, rect: QRect):
        """
        Отрисовывает курсор на графике
        
        Args:
            painter: Объект QPainter
            rect: Прямоугольник для отрисовки
        """
        try:
            if not self._cursor_pos:
                return
                
            # Настройки для курсора
            painter.setPen(QPen(QColor(0, 0, 0, 100), 1, Qt.PenStyle.DashLine))
            
            # Горизонтальная линия
            painter.drawLine(
                rect.left(),
                self._cursor_pos.y(),
                rect.right(),
                self._cursor_pos.y()
            )
            
            # Вертикальная линия
            painter.drawLine(
                self._cursor_pos.x(),
                rect.top(),
                self._cursor_pos.x(),
                rect.bottom()
            )
            
        except Exception as e:
            self.logger.error(f"Ошибка при отрисовке курсора: {e}")
            log_exception(self.logger, "Ошибка отрисовки курсора")
    
    def _draw_axes(self, painter: QPainter, rect: QRect):
        """
        Отрисовывает оси графика
        
        Args:
            painter: Объект QPainter
            rect: Прямоугольник для отрисовки
        """
        try:
            # Настройки для осей
            painter.setPen(QPen(QColor(0, 0, 0, 150), 1))
            
            # Ось X
            painter.drawLine(
                rect.left(),
                rect.bottom(),
                rect.right(),
                rect.bottom()
            )
            
            # Ось Y
            painter.drawLine(
                rect.left(),
                rect.top(),
                rect.left(),
                rect.bottom()
            )
            
            # Метки на оси X
            if 'min_time' in self._data_cache and 'max_time' in self._data_cache:
                min_time = self._data_cache['min_time']
                max_time = self._data_cache['max_time']
                
                # Рисуем метки времени через каждые 20% ширины
                for i in range(0, 6):
                    x = rect.left() + i * rect.width() / 5
                    y = rect.bottom() + 15
                    
                    # Засечка
                    painter.drawLine(
                        int(x),
                        rect.bottom(),
                        int(x),
                        rect.bottom() + 5
                    )
                    
                    # Текст
                    if i < 5:  # Не рисуем последнюю метку, чтобы не выходить за границы
                        time_point = min_time + (max_time - min_time) * (i / 5)
                        time_str = time_point.strftime("%H:%M")
                        painter.drawText(int(x - 15), int(y), 30, 15, Qt.AlignmentFlag.AlignCenter, time_str)
            
            # Метки на оси Y
            if 'min_value' in self._data_cache and 'max_value' in self._data_cache:
                min_value = self._data_cache['min_value']
                max_value = self._data_cache['max_value']
                
                # Рисуем метки значений через каждые 20% высоты
                for i in range(0, 6):
                    x = rect.left() - 5
                    y = rect.bottom() - i * rect.height() / 5
                    
                    # Засечка
                    painter.drawLine(
                        rect.left() - 5,
                        int(y),
                        rect.left(),
                        int(y)
                    )
                    
                    # Текст
                    value = min_value + (max_value - min_value) * (i / 5)
                    value_str = str(int(value))
                    painter.drawText(int(x - 30), int(y - 10), 30, 20, Qt.AlignmentFlag.AlignRight, value_str)
            
        except Exception as e:
            self.logger.error(f"Ошибка при отрисовке осей: {e}")
            log_exception(self.logger, "Ошибка отрисовки осей")
    
    def _get_value_at_position(self, x: int, y: int) -> Optional[float]:
        """
        Получает значение в указанной позиции графика
        
        Args:
            x: X-координата
            y: Y-координата
            
        Returns:
            Optional[float]: Значение в указанной позиции или None
        """
        try:
            if not self.data:
                return None
                
            # Получаем размеры виджета
            rect = self.rect()
            if not rect.isValid():
                return None
                
            # Определяем временной диапазон
            time_range = self._get_time_range()
            if not time_range:
                return None
                
            # Находим ближайшую точку по времени
            target_time = time_range[0] + (time_range[1] - time_range[0]) * (x / rect.width())
            closest_time = min(self.data, key=lambda p: abs((p[0] - target_time).total_seconds()))
            
            # Проверяем, достаточно ли близко точка
            time_diff = abs((closest_time[0] - target_time).total_seconds())
            if time_diff > (time_range[1] - time_range[0]).total_seconds() / len(self.data):
                return None
                
            return closest_time[1]
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении значения в позиции ({x}, {y}): {e}")
            log_exception(self.logger, "Ошибка получения значения в позиции")
            return None
    
    def _draw_grid(self, painter: QPainter, rect: QRect):
        """
        Отрисовывает сетку графика
        
        Args:
            painter: Объект QPainter
            rect: Прямоугольник для отрисовки
        """
        try:
            # Настройки для сетки
            painter.setPen(QPen(QColor(0, 0, 0, 30), 1, Qt.PenStyle.DotLine))
            
            # Горизонтальные линии (5 линий)
            for i in range(1, 5):
                y = rect.top() + i * rect.height() / 5
                painter.drawLine(
                    rect.left(),
                    int(y),
                    rect.right(),
                    int(y)
                )
                
            # Вертикальные линии (5 линий)
            for i in range(1, 5):
                x = rect.left() + i * rect.width() / 5
                painter.drawLine(
                    int(x),
                    rect.top(),
                    int(x),
                    rect.bottom()
                )
                
        except Exception as e:
            self.logger.error(f"Ошибка при отрисовке сетки: {e}")
            log_exception(self.logger, "Ошибка отрисовки сетки")
    
    def _draw_data(self, painter: QPainter, rect: QRect):
        """
        Отрисовывает данные графика
        
        Args:
            painter: Объект QPainter
            rect: Прямоугольник для отрисовки
        """
        try:
            if not self.data or len(self.data) < 2:
                return
                
            if 'min_time' not in self._data_cache or 'max_time' not in self._data_cache:
                return
                
            if 'min_value' not in self._data_cache or 'max_value' not in self._data_cache:
                return
                
            min_time = self._data_cache['min_time']
            max_time = self._data_cache['max_time']
            min_value = self._data_cache['min_value']
            max_value = self._data_cache['max_value']
            
            # Настройки для линии
            painter.setPen(QPen(QColor("#3182CE"), 2))
            
            # Путь для графика
            path = QPainterPath()
            first_point = True
            
            # Строим путь
            for timestamp, value in self.data:
                # Вычисляем координаты
                x = rect.left() + rect.width() * (timestamp - min_time).total_seconds() / max(1, (max_time - min_time).total_seconds())
                y = rect.bottom() - rect.height() * (value - min_value) / max(1, max_value - min_value)
                
                # Добавляем точку в путь
                if first_point:
                    path.moveTo(x, y)
                    first_point = False
                else:
                    path.lineTo(x, y)
                    
            # Рисуем путь
            painter.drawPath(path)
            
        except Exception as e:
            self.logger.error(f"Ошибка при отрисовке данных: {e}")
            log_exception(self.logger, "Ошибка отрисовки данных")
    
    def _get_time_range(self):
        """
        Получает диапазон времени для графика
        
        Returns:
            tuple: Кортеж (min_time, max_time) или None если данных нет
        """
        try:
            if not self.data:
                return None
                
            timestamps = [d[0] for d in self.data]
            min_time = min(timestamps)
            max_time = max(timestamps)
            
            return (min_time, max_time)
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении диапазона времени: {e}")
            log_exception(self.logger, "Ошибка получения диапазона времени")
            return None

class DashboardWidget(QWidget):
    """Виджет панели мониторинга"""
    
    def __init__(self, app_context, parent=None):
        """
        Инициализация виджета панели мониторинга
        
        Args:
            app_context: Контекст приложения
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger('ui.dashboard_widget')
        self.logger.debug("Инициализация виджета панели мониторинга")
        
        try:
            self.app_context = app_context
            
            # Основной макет
            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(10)
            
            # Контроллер обновления данных
            self.update_timer = QTimer(self)
            self.update_timer.timeout.connect(self.update_data)
            self.update_timer.start(60000)  # Обновление каждую минуту
            
            # Загружаем данные при инициализации
            self.update_data()
            
            self.logger.debug("Виджет панели мониторинга успешно инициализирован")
            
        except Exception as e:
            self.logger.error(f"Ошибка при инициализации виджета панели мониторинга: {e}")
            log_exception(self.logger, "Ошибка инициализации виджета панели мониторинга")
            raise
    
    def update_data(self):
        """Обновляет данные на панели мониторинга"""
        try:
            self.logger.debug("Обновление данных панели мониторинга")
            
            # Получаем данные от API
            try:
                data = self.app_context.api.get_dashboard_data()
                if data:
                    self._update_dashboard_data(data)
            except Exception as e:
                self.logger.error(f"Ошибка при получении данных от API: {e}")
                log_exception(self.logger, "Ошибка получения данных от API")
            
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении данных панели мониторинга: {e}")
            log_exception(self.logger, "Ошибка обновления данных панели мониторинга")
    
    @handle_errors(error_msg="Ошибка при переключении состояния мониторинга")
    def _toggle_monitoring(self):
        """Переключает состояние мониторинга (вкл/выкл)"""
        try:
            self.logger.debug("Переключение состояния мониторинга")
            
            try:
                # Получаем текущее состояние
                is_active = self.app_context.api.is_monitoring_active()
                
                # Переключаем состояние
                if is_active:
                    self.app_context.api.stop_monitoring()
                    self.status_monitoring.update_value("Остановлен")
                    self.toggle_monitoring_btn.setText("Запустить мониторинг")
                else:
                    self.app_context.api.start_monitoring()
                    self.status_monitoring.update_value("Активен")
                    self.toggle_monitoring_btn.setText("Остановить мониторинг")
                    
                self.logger.debug(f"Состояние мониторинга изменено на: {'Остановлен' if is_active else 'Активен'}")
                
            except Exception as e:
                self.logger.error(f"Ошибка при обращении к API для переключения состояния мониторинга: {e}")
                log_exception(self.logger, "Ошибка обращения к API для переключения состояния мониторинга")
                QMessageBox.critical(self, "Ошибка", "Не удалось переключить состояние мониторинга")
                
        except Exception as e:
            self.logger.error(f"Ошибка при переключении состояния мониторинга: {e}")
            log_exception(self.logger, "Ошибка переключения состояния мониторинга")
            raise
    
    @handle_errors(error_msg="Ошибка при проверке всех сайтов")
    def _check_all_sites(self):
        """Запускает проверку всех сайтов"""
        try:
            self.logger.debug("Запуск проверки всех сайтов")
            
            try:
                # Запускаем проверку
                self.app_context.api.check_all_sites()
                QMessageBox.information(self, "Информация", "Проверка сайтов запущена")
                self.logger.debug("Проверка всех сайтов запущена")
                
            except Exception as e:
                self.logger.error(f"Ошибка при обращении к API для проверки всех сайтов: {e}")
                log_exception(self.logger, "Ошибка обращения к API для проверки всех сайтов")
                QMessageBox.critical(self, "Ошибка", "Не удалось запустить проверку сайтов")
                
        except Exception as e:
            self.logger.error(f"Ошибка при проверке всех сайтов: {e}")
            log_exception(self.logger, "Ошибка проверки всех сайтов")
            raise
    
    @handle_errors(error_msg="Ошибка при открытии информации об изменении")
    def _open_change(self, change_id):
        """
        Открывает информацию об изменении
        
        Args:
            change_id: ID изменения
        """
        try:
            self.logger.debug(f"Попытка открытия информации об изменении {change_id}")
            
            if not isinstance(change_id, int) or change_id <= 0:
                self.logger.error(f"Некорректный ID изменения: {change_id}")
                return
                
            try:
                # Открываем информацию об изменении
                self.app_context.main_window.open_change_details(change_id)
                self.logger.debug(f"Информация об изменении {change_id} открыта")
                
            except Exception as e:
                self.logger.error(f"Ошибка при открытии информации об изменении {change_id}: {e}")
                log_exception(self.logger, "Ошибка открытия информации об изменении")
                QMessageBox.critical(self, "Ошибка", "Не удалось открыть информацию об изменении")
                
        except Exception as e:
            self.logger.error(f"Ошибка при открытии информации об изменении {change_id}: {e}")
            log_exception(self.logger, "Ошибка открытия информации об изменении")
            raise
    
    @handle_errors(error_msg="Ошибка при открытии информации о сайте")
    def _open_site(self, site_id):
        """
        Открывает информацию о сайте
        
        Args:
            site_id: ID сайта
        """
        try:
            self.logger.debug(f"Попытка открытия информации о сайте {site_id}")
            
            if not isinstance(site_id, int) or site_id <= 0:
                self.logger.error(f"Некорректный ID сайта: {site_id}")
                return
                
            try:
                # Открываем информацию о сайте
                self.app_context.main_window.open_site_details(site_id)
                self.logger.debug(f"Информация о сайте {site_id} открыта")
                
            except Exception as e:
                self.logger.error(f"Ошибка при открытии информации о сайте {site_id}: {e}")
                log_exception(self.logger, "Ошибка открытия информации о сайте")
                QMessageBox.critical(self, "Ошибка", "Не удалось открыть информацию о сайте")
                
        except Exception as e:
            self.logger.error(f"Ошибка при открытии информации о сайте {site_id}: {e}")
            log_exception(self.logger, "Ошибка открытия информации о сайте")
            raise
    
    def _update_dashboard_data(self, data: dict):
        """
        Обновляет данные на панели мониторинга
        
        Args:
            data: Данные для обновления
        """
        try:
            if not isinstance(data, dict):
                self.logger.error(f"Некорректный формат данных: {type(data)}")
                return
                
            # Обновляем карточки статуса
            if 'total_sites' in data:
                self.status_sites.update_value(data['total_sites'])
                
            if 'active_sites' in data:
                self.status_active.update_value(data['active_sites'])
                
            if 'sites_with_changes' in data:
                self.status_changes.update_value(data['sites_with_changes'])
                
            if 'sites_with_errors' in data:
                self.status_errors.update_value(data['sites_with_errors'])
                
            # Обновляем таблицы и графики
            # ... (тут можно добавить обновление других виджетов)
            
            self.logger.debug("Данные панели мониторинга обновлены")
            
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении данных на панели мониторинга: {e}")
            log_exception(self.logger, "Ошибка обновления данных на панели мониторинга")
    
    def set_update_interval(self, interval: int):
        """
        Устанавливает интервал обновления данных
        
        Args:
            interval: Интервал в секундах
        """
        try:
            if interval < 10:
                self.logger.warning(f"Слишком малый интервал обновления: {interval} сек. Минимум 10 сек.")
                interval = 10
                
            self.update_timer.stop()
            self.update_timer.setInterval(interval * 1000)
            self.update_timer.start()
            
            self.logger.debug(f"Установлен интервал обновления: {interval} сек.")
            
        except Exception as e:
            self.logger.error(f"Ошибка при установке интервала обновления: {e}")
            log_exception(self.logger, "Ошибка установки интервала обновления") 