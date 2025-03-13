#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль генерации отчетов для WDM_V12.
Обеспечивает создание различных типов отчетов на основе данных мониторинга.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
from pathlib import Path

from utils.logger import get_module_logger, log_exception
from core.settings import Settings

class ReportGenerator:
    """
    Класс для генерации отчетов различных типов.
    Поддерживает форматы HTML, CSV, XLSX и PDF.
    """
    
    def __init__(self, app_context):
        """
        Инициализация генератора отчетов
        
        Args:
            app_context: Контекст приложения
        """
        self.logger = get_module_logger('reports.generator')
        self.app_context = app_context
        self.settings = Settings()
        
        # Создаем директорию для отчетов, если её нет
        self.reports_dir = Path("reports_output")
        self.reports_dir.mkdir(exist_ok=True)
        
        # Константы для категоризации изменений
        self.CRITICAL_CHANGE_THRESHOLD = 50  # Изменения более 50% считаются критическими
        self.NORMAL_CHANGE_THRESHOLD = 10    # Изменения более 10% считаются значительными
        
        # Лимиты для запросов к базе данных
        self.DEFAULT_QUERY_LIMIT = 1000
        self.DEFAULT_PAGE_SIZE = 100
    
    def analyze_content_changes(self, old_snapshot: Dict[str, Any], new_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """
        Анализирует конкретные изменения между двумя снимками сайта
        
        Args:
            old_snapshot: Предыдущий снимок сайта
            new_snapshot: Новый снимок сайта
            
        Returns:
            Dict[str, Any]: Структурированный отчет об изменениях
        """
        if not old_snapshot or not new_snapshot:
            return {"error": "Снимки отсутствуют"}
        
        try:
            # Получаем содержимое снимков
            old_content = old_snapshot.get('content', '')
            new_content = new_snapshot.get('content', '')
            
            # Если содержимое отсутствует, возвращаем ошибку
            if not old_content or not new_content:
                return {"error": "Содержимое снимков отсутствует"}
            
            # Анализ изменений в метаданных
            old_metadata = old_snapshot.get('metadata', {}) or {}
            new_metadata = new_snapshot.get('metadata', {}) or {}
            
            metadata_changes = {
                "title_changed": old_metadata.get('title') != new_metadata.get('title'),
                "description_changed": old_metadata.get('description') != new_metadata.get('description'),
                "keywords_changed": old_metadata.get('keywords') != new_metadata.get('keywords')
            }
            
            # Анализ изменений в размере контента
            size_diff = len(new_content) - len(old_content)
            size_change_percent = (size_diff / max(1, len(old_content))) * 100
            
            # Определение типа изменений
            changes_type = self._categorize_single_change(old_snapshot.get('diff_percent', 0))
            
            # Создаем структурированный отчет
            analysis = {
                "metadata_changes": metadata_changes,
                "size_diff": size_diff,
                "size_change_percent": size_change_percent,
                "changes_type": changes_type,
                "old_hash": old_snapshot.get('content_hash', ''),
                "new_hash": new_snapshot.get('content_hash', '')
            }
            
            return analysis
        except Exception as e:
            self.logger.error(f"Ошибка при анализе изменений контента: {e}")
            log_exception(self.logger, "Ошибка анализа контента")
            return {"error": str(e)}
    
    def categorize_changes(self, changes_data: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Категоризирует изменения по важности
        
        Args:
            changes_data: Список изменений
            
        Returns:
            Dict[str, List]: Словарь с категоризированными изменениями
        """
        try:
            critical_changes = []
            normal_changes = []
            minor_changes = []
            
            for change in changes_data:
                diff_percent = change.get('diff_percent', 0)
                
                if diff_percent > self.CRITICAL_CHANGE_THRESHOLD:
                    critical_changes.append(change)
                elif diff_percent > self.NORMAL_CHANGE_THRESHOLD:
                    normal_changes.append(change)
                else:
                    minor_changes.append(change)
            
            return {
                'critical': critical_changes,
                'normal': normal_changes,
                'minor': minor_changes
            }
        except Exception as e:
            self.logger.error(f"Ошибка при категоризации изменений: {e}")
            log_exception(self.logger, "Ошибка категоризации изменений")
            return {
                'critical': [],
                'normal': [],
                'minor': [],
                'error': str(e)
            }
    
    def _categorize_single_change(self, diff_percent: float) -> str:
        """
        Определяет категорию отдельного изменения
        
        Args:
            diff_percent: Процент изменений
            
        Returns:
            str: Категория изменения
        """
        if diff_percent > self.CRITICAL_CHANGE_THRESHOLD:
            return "critical"
        elif diff_percent > self.NORMAL_CHANGE_THRESHOLD:
            return "normal"
        else:
            return "minor"
    
    def generate_sites_report(self, date_from: datetime, date_to: datetime) -> Dict[str, Any]:
        """
        Генерация отчета по сайтам
        
        Args:
            date_from: Начальная дата
            date_to: Конечная дата
            
        Returns:
            Dict[str, Any]: Данные отчета
        """
        try:
            # Получаем общее количество сайтов для пагинации
            count_query = """
            SELECT COUNT(*) as total_count
            FROM sites s
            WHERE s.created_at <= ?
            """
            
            total_count_result = self.app_context.execute_db_query(
                count_query, 
                (date_to,),
                fetch_all=False
            )
            
            total_count = total_count_result['total_count']
            self.logger.debug(f"Всего сайтов для отчета: {total_count}")
            
            # Определяем максимальное количество сайтов для отчета
            max_sites = min(total_count, self.DEFAULT_QUERY_LIMIT)
            
            # Получаем данные о сайтах за период с лимитом
            query = """
            SELECT s.*, g.name as group_name,
                   (SELECT COUNT(*) FROM changes c WHERE c.site_id = s.id 
                    AND c.timestamp BETWEEN ? AND ? LIMIT 1000) as changes_count,
                   (SELECT COUNT(*) FROM snapshots sn WHERE sn.site_id = s.id 
                    AND sn.status = 'error' AND sn.timestamp BETWEEN ? AND ? LIMIT 1000) as errors_count
            FROM sites s
            LEFT JOIN groups g ON s.group_id = g.id
            WHERE s.created_at <= ?
            ORDER BY s.name
            LIMIT ?
            """
            
            sites = self.app_context.execute_db_query(
                query, 
                (date_from, date_to, date_from, date_to, date_to, max_sites)
            )
            
            # Если сайтов очень много, выводим предупреждение в лог
            if total_count > max_sites:
                self.logger.warning(f"Отчет ограничен {max_sites} сайтами из {total_count}")
            
            # Формируем статистику
            total_sites = len(sites)
            active_sites = sum(1 for site in sites if site['status'] == 'active')
            total_changes = sum(site['changes_count'] for site in sites)
            total_errors = sum(site['errors_count'] for site in sites)
            
            # Группируем сайты по группам
            sites_by_group = {}
            for site in sites:
                group = site['group_name'] or 'Без группы'
                if group not in sites_by_group:
                    sites_by_group[group] = []
                sites_by_group[group].append(site)
            
            # Проверяем, есть ли данные для отчета
            if not sites:
                self.logger.warning("В отчете не найдено данных по сайтам за указанный период")
            
            return {
                'type': 'sites',
                'date_from': date_from,
                'date_to': date_to,
                'total_sites': total_sites,
                'active_sites': active_sites,
                'total_changes': total_changes,
                'total_errors': total_errors,
                'sites': sites,
                'sites_by_group': sites_by_group,
                'limited_results': total_count > max_sites,
                'total_available': total_count
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка при генерации отчета по сайтам: {e}")
            log_exception(self.logger, "Ошибка генерации отчета по сайтам")
            raise
    
    def generate_changes_report(self, date_from: datetime, date_to: datetime) -> Dict[str, Any]:
        """
        Генерация отчета по изменениям
        
        Args:
            date_from: Начальная дата
            date_to: Конечная дата
            
        Returns:
            Dict[str, Any]: Данные отчета
        """
        try:
            # Получаем общее количество изменений для пагинации
            count_query = """
            SELECT COUNT(*) as total_count
            FROM changes c
            WHERE c.timestamp BETWEEN ? AND ?
            """
            
            total_count_result = self.app_context.execute_db_query(
                count_query, 
                (date_from, date_to),
                fetch_all=False
            )
            
            total_count = total_count_result['total_count']
            self.logger.debug(f"Всего изменений для отчета: {total_count}")
            
            # Определяем максимальное количество изменений для отчета
            max_changes = min(total_count, self.DEFAULT_QUERY_LIMIT)
            
            # Получаем данные об изменениях за период с лимитом
            query = """
            SELECT c.*, s.name as site_name, s.url as site_url,
                   old.content_hash as old_hash, new.content_hash as new_hash,
                   old.content_size as old_size, new.content_size as new_size
            FROM changes c
            JOIN sites s ON c.site_id = s.id
            LEFT JOIN snapshots old ON c.old_snapshot_id = old.id
            JOIN snapshots new ON c.new_snapshot_id = new.id
            WHERE c.timestamp BETWEEN ? AND ?
            ORDER BY c.timestamp DESC
            LIMIT ?
            """
            
            changes = self.app_context.execute_db_query(
                query, 
                (date_from, date_to, max_changes)
            )
            
            # Если изменений очень много, выводим предупреждение в лог
            if total_count > max_changes:
                self.logger.warning(f"Отчет ограничен {max_changes} изменениями из {total_count}")
            
            # Категоризируем изменения
            categorized_changes = self.categorize_changes(changes)
            
            # Анализируем детали изменений для выборочных элементов
            # (для экономии ресурсов анализируем не более 20 элементов)
            detailed_analysis = []
            sample_size = min(20, len(changes))
            
            for i in range(sample_size):
                change = changes[i]
                # Получаем снимки для анализа
                old_snapshot_query = """
                SELECT * FROM snapshots WHERE id = ? LIMIT 1
                """
                new_snapshot_query = """
                SELECT * FROM snapshots WHERE id = ? LIMIT 1
                """
                
                old_snapshot = self.app_context.execute_db_query(
                    old_snapshot_query, 
                    (change['old_snapshot_id'],),
                    fetch_all=False
                ) if change['old_snapshot_id'] else None
                
                new_snapshot = self.app_context.execute_db_query(
                    new_snapshot_query, 
                    (change['new_snapshot_id'],),
                    fetch_all=False
                )
                
                if old_snapshot and new_snapshot:
                    analysis = self.analyze_content_changes(old_snapshot, new_snapshot)
                    detailed_analysis.append({
                        'change_id': change['id'],
                        'site_id': change['site_id'],
                        'site_name': change['site_name'],
                        'timestamp': change['timestamp'],
                        'analysis': analysis
                    })
            
            # Группируем изменения по сайтам
            changes_by_site = {}
            for change in changes:
                site_name = change['site_name']
                if site_name not in changes_by_site:
                    changes_by_site[site_name] = []
                changes_by_site[site_name].append(change)
            
            # Считаем статистику
            total_changes = len(changes)
            avg_diff = sum(change['diff_percent'] for change in changes) / total_changes if total_changes > 0 else 0
            sites_with_changes = len(changes_by_site)
            
            # Проверяем, есть ли данные для отчета
            if not changes:
                self.logger.warning("В отчете не найдено данных по изменениям за указанный период")
            
            return {
                'type': 'changes',
                'date_from': date_from,
                'date_to': date_to,
                'total_changes': total_changes,
                'avg_diff_percent': avg_diff,
                'sites_with_changes': sites_with_changes,
                'changes': changes,
                'changes_by_site': changes_by_site,
                'categorized_changes': categorized_changes,
                'detailed_analysis': detailed_analysis,
                'limited_results': total_count > max_changes,
                'total_available': total_count
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка при генерации отчета по изменениям: {e}")
            log_exception(self.logger, "Ошибка генерации отчета по изменениям")
            raise
    
    def generate_errors_report(self, date_from: datetime, date_to: datetime) -> Dict[str, Any]:
        """
        Генерация отчета по ошибкам
        
        Args:
            date_from: Начальная дата
            date_to: Конечная дата
            
        Returns:
            Dict[str, Any]: Данные отчета
        """
        try:
            # Получаем общее количество ошибок для пагинации
            count_query = """
            SELECT COUNT(*) as total_count
            FROM snapshots sn
            WHERE sn.status = 'error'
            AND sn.timestamp BETWEEN ? AND ?
            """
            
            total_count_result = self.app_context.execute_db_query(
                count_query, 
                (date_from, date_to),
                fetch_all=False
            )
            
            total_count = total_count_result['total_count']
            self.logger.debug(f"Всего ошибок для отчета: {total_count}")
            
            # Определяем максимальное количество ошибок для отчета
            max_errors = min(total_count, self.DEFAULT_QUERY_LIMIT)
            
            # Получаем данные об ошибках за период с лимитом
            query = """
            SELECT s.*, sn.timestamp as error_time, sn.error_message,
                   g.name as group_name
            FROM snapshots sn
            JOIN sites s ON sn.site_id = s.id
            LEFT JOIN groups g ON s.group_id = g.id
            WHERE sn.status = 'error'
            AND sn.timestamp BETWEEN ? AND ?
            ORDER BY sn.timestamp DESC
            LIMIT ?
            """
            
            errors = self.app_context.execute_db_query(
                query, 
                (date_from, date_to, max_errors)
            )
            
            # Если ошибок очень много, выводим предупреждение в лог
            if total_count > max_errors:
                self.logger.warning(f"Отчет ограничен {max_errors} ошибками из {total_count}")
            
            # Группируем ошибки по сайтам
            errors_by_site = {}
            for error in errors:
                site_name = error['name']
                if site_name not in errors_by_site:
                    errors_by_site[site_name] = []
                errors_by_site[site_name].append(error)
            
            # Группируем ошибки по типу
            errors_by_type = {}
            for error in errors:
                error_msg = error['error_message']
                error_type = self._categorize_error(error_msg)
                
                if error_type not in errors_by_type:
                    errors_by_type[error_type] = []
                errors_by_type[error_type].append(error)
            
            # Считаем статистику
            total_errors = len(errors)
            sites_with_errors = len(errors_by_site)
            
            # Проверяем, есть ли данные для отчета
            if not errors:
                self.logger.warning("В отчете не найдено данных по ошибкам за указанный период")
            
            return {
                'type': 'errors',
                'date_from': date_from,
                'date_to': date_to,
                'total_errors': total_errors,
                'sites_with_errors': sites_with_errors,
                'errors': errors,
                'errors_by_site': errors_by_site,
                'errors_by_type': errors_by_type,
                'limited_results': total_count > max_errors,
                'total_available': total_count
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка при генерации отчета по ошибкам: {e}")
            log_exception(self.logger, "Ошибка генерации отчета по ошибкам")
            raise
    
    def _categorize_error(self, error_message: str) -> str:
        """
        Категоризирует ошибку по её сообщению
        
        Args:
            error_message: Текст ошибки
            
        Returns:
            str: Категория ошибки
        """
        error_message = error_message.lower()
        
        if 'connection' in error_message or 'timeout' in error_message:
            return 'Проблемы подключения'
        elif 'ssl' in error_message or 'certificate' in error_message:
            return 'Проблемы с SSL-сертификатом'
        elif '404' in error_message or 'not found' in error_message:
            return 'Страница не найдена'
        elif '403' in error_message or 'forbidden' in error_message:
            return 'Доступ запрещен'
        elif '500' in error_message or 'server error' in error_message:
            return 'Ошибка сервера'
        elif 'javascript' in error_message or 'script' in error_message:
            return 'Ошибка JavaScript'
        elif 'dns' in error_message:
            return 'Проблемы с DNS'
        elif 'proxy' in error_message or 'blocked' in error_message:
            return 'Блокировка доступа'
        else:
            return 'Другие ошибки'
    
    def generate_stats_report(self, date_from: datetime, date_to: datetime) -> Dict[str, Any]:
        """
        Генерация статистического отчета
        
        Args:
            date_from: Начальная дата
            date_to: Конечная дата
            
        Returns:
            Dict[str, Any]: Данные отчета
        """
        try:
            # Общая статистика по сайтам
            sites_query = """
            SELECT 
                COUNT(*) as total_sites,
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_sites,
                AVG(check_interval) as avg_check_interval
            FROM sites
            """
            sites_stats = self.app_context.execute_db_query(sites_query, fetch_all=False)
            
            # Статистика по изменениям
            changes_query = """
            SELECT 
                COUNT(*) as total_changes,
                COUNT(DISTINCT site_id) as sites_with_changes,
                AVG(diff_percent) as avg_diff_percent,
                MAX(diff_percent) as max_diff_percent
            FROM changes
            WHERE timestamp BETWEEN ? AND ?
            """
            changes_stats = self.app_context.execute_db_query(
                changes_query, 
                (date_from, date_to),
                fetch_all=False
            )
            
            # Статистика по ошибкам
            errors_query = """
            SELECT 
                COUNT(*) as total_errors,
                COUNT(DISTINCT site_id) as sites_with_errors
            FROM snapshots
            WHERE status = 'error' AND timestamp BETWEEN ? AND ?
            """
            errors_stats = self.app_context.execute_db_query(
                errors_query,
                (date_from, date_to),
                fetch_all=False
            )
            
            # Статистика по группам
            groups_query = """
            SELECT g.name, COUNT(s.id) as sites_count
            FROM groups g
            LEFT JOIN sites s ON g.id = s.group_id
            GROUP BY g.id
            """
            groups_stats = self.app_context.execute_db_query(groups_query)
            
            return {
                'type': 'stats',
                'date_from': date_from,
                'date_to': date_to,
                'sites_stats': sites_stats,
                'changes_stats': changes_stats,
                'errors_stats': errors_stats,
                'groups_stats': groups_stats
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка при генерации статистического отчета: {e}")
            log_exception(self.logger, "Ошибка генерации статистического отчета")
            raise
    
    def format_report_html(self, report_data: Dict[str, Any]) -> str:
        """
        Форматирование отчета в HTML
        
        Args:
            report_data: Данные отчета
            
        Returns:
            str: HTML-представление отчета
        """
        try:
            # Базовый шаблон HTML
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Отчет WDM - {report_data['type']}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; color: #333; line-height: 1.6; }}
                    h1, h2, h3, h4 {{ color: #444; margin-top: 20px; }}
                    h1 {{ border-bottom: 2px solid #5d87a1; padding-bottom: 10px; }}
                    h2 {{ border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
                    
                    /* Основные блоки */
                    .container {{ max-width: 1200px; margin: 0 auto; }}
                    .section {{ margin: 30px 0; }}
                    
                    /* Таблицы */
                    table {{ border-collapse: collapse; width: 100%; margin: 20px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.12); }}
                    th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                    th {{ background-color: #f5f5f5; font-weight: bold; position: sticky; top: 0; }}
                    tr:nth-child(even) {{ background-color: #f9f9f9; }}
                    tr:hover {{ background-color: #f1f1f1; }}
                    
                    /* Карточки статистики */
                    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
                    .stat-card {{ background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); 
                                 transition: transform 0.3s, box-shadow 0.3s; text-align: center; }}
                    .stat-card:hover {{ transform: translateY(-5px); box-shadow: 0 5px 15px rgba(0,0,0,0.1); }}
                    .stat-card h3 {{ margin-top: 0; color: #666; font-size: 16px; }}
                    .stat-card p {{ font-size: 28px; font-weight: bold; margin: 10px 0 0; color: #333; }}
                    
                    /* Категории изменений */
                    .changes-categories {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 20px 0; }}
                    .category {{ padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                    .category.critical {{ background-color: rgba(255, 82, 82, 0.1); border-left: 4px solid #ff5252; }}
                    .category.normal {{ background-color: rgba(255, 193, 7, 0.1); border-left: 4px solid #ffc107; }}
                    .category.minor {{ background-color: rgba(76, 175, 80, 0.1); border-left: 4px solid #4caf50; }}
                    .category h3 {{ margin-top: 0; }}
                    
                    /* Индикатор прогресса */
                    .progress-bar {{ width: 100%; height: 10px; background-color: #f0f0f0; border-radius: 5px; overflow: hidden; margin: 10px 0; }}
                    .progress {{ height: 100%; border-radius: 5px; }}
                    .critical .progress {{ background-color: #ff5252; }}
                    .normal .progress {{ background-color: #ffc107; }}
                    .minor .progress {{ background-color: #4caf50; }}
                    
                    /* Детальный анализ изменений */
                    .detailed-changes {{ margin: 20px 0; }}
                    .change-analysis {{ padding: 15px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); }}
                    .change-analysis.critical {{ background-color: rgba(255, 82, 82, 0.05); border-left: 4px solid #ff5252; }}
                    .change-analysis.normal {{ background-color: rgba(255, 193, 7, 0.05); border-left: 4px solid #ffc107; }}
                    .change-analysis.minor {{ background-color: rgba(76, 175, 80, 0.05); border-left: 4px solid #4caf50; }}
                    .change-analysis h3 {{ margin-top: 0; }}
                    .analysis-details {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
                    .changed {{ color: #ff5252; font-weight: bold; }}
                    span.critical {{ color: #ff5252; font-weight: bold; }}
                    span.normal {{ color: #ff9800; font-weight: bold; }}
                    span.minor {{ color: #4caf50; font-weight: bold; }}
                    
                    /* Таблицы по категориям */
                    .changes-table.critical th {{ background-color: rgba(255, 82, 82, 0.2); }}
                    .changes-table.normal th {{ background-color: rgba(255, 193, 7, 0.2); }}
                    .changes-table.minor th {{ background-color: rgba(76, 175, 80, 0.2); }}
                    
                    /* Круговая диаграмма для ошибок */
                    .pie-chart-container {{ display: flex; justify-content: center; align-items: center; margin: 30px 0; flex-wrap: wrap; }}
                    .pie-chart {{ position: relative; width: 250px; height: 250px; border-radius: 50%; background-color: #f0f0f0; margin: 20px; }}
                    .pie-segment {{ position: absolute; width: 100%; height: 100%; border-radius: 50%; clip-path: polygon(50% 50%, 50% 0%, 100% 0%, 100% 100%, 0% 100%, 0% 0%, 50% 0%); 
                                  transform-origin: 50% 50%; transform: rotate(var(--start)); background-color: var(--color);
                                  clip-path: polygon(50% 50%, 100% 0%, 100% 100%, 0% 100%, 0% 0%, 100% 0%); }}
                    .pie-legend {{ display: flex; flex-direction: column; justify-content: center; }}
                    .legend-item {{ display: flex; align-items: center; margin-bottom: 8px; }}
                    .color-box {{ width: 15px; height: 15px; margin-right: 8px; }}
                    
                    /* Предупреждения */
                    .warning {{ background-color: rgba(255, 193, 7, 0.1); border-left: 4px solid #ffc107; padding: 15px; border-radius: 4px; margin: 20px 0; }}
                    .warning p {{ margin: 0; color: #856404; }}
                    
                    /* Адаптивная верстка */
                    @media (max-width: 768px) {{
                        .stats, .changes-categories {{ grid-template-columns: 1fr; }}
                        .analysis-details {{ grid-template-columns: 1fr; }}
                        .pie-chart-container {{ flex-direction: column; }}
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Отчет по {report_data['type']}</h1>
                    <p>Период: {report_data['date_from'].strftime('%d.%m.%Y')} - {report_data['date_to'].strftime('%d.%m.%Y')}</p>
                    <p>Дата создания: {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
            """
            
            # Добавляем содержимое в зависимости от типа отчета
            if report_data['type'] == 'sites':
                html += self._format_sites_report_html(report_data)
            elif report_data['type'] == 'changes':
                html += self._format_changes_report_html(report_data)
            elif report_data['type'] == 'errors':
                html += self._format_errors_report_html(report_data)
            elif report_data['type'] == 'stats':
                html += self._format_stats_report_html(report_data)
            
            html += """
                    <div class="footer" style="margin-top: 40px; text-align: center; color: #777; font-size: 14px; border-top: 1px solid #ddd; padding-top: 20px;">
                        <p>Отчет создан с помощью Web Data Monitor V12 © 2025 AT-Consulting</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            return html
            
        except Exception as e:
            self.logger.error(f"Ошибка при форматировании отчета в HTML: {e}")
            log_exception(self.logger, "Ошибка форматирования отчета в HTML")
            raise
    
    def _format_sites_report_html(self, report_data: Dict[str, Any]) -> str:
        """Форматирование отчета по сайтам в HTML"""
        html = f"""
        <div class="stats">
            <div class="stat-card">
                <h3>Всего сайтов</h3>
                <p>{report_data['total_sites']}</p>
            </div>
            <div class="stat-card">
                <h3>Активных сайтов</h3>
                <p>{report_data['active_sites']}</p>
            </div>
            <div class="stat-card">
                <h3>Изменений за период</h3>
                <p>{report_data['total_changes']}</p>
            </div>
            <div class="stat-card">
                <h3>Ошибок за период</h3>
                <p>{report_data['total_errors']}</p>
            </div>
        </div>
        """
        
        # Добавляем таблицу сайтов по группам
        for group, sites in report_data['sites_by_group'].items():
            html += f"""
            <h2>Группа: {group}</h2>
            <table>
                <tr>
                    <th>Название</th>
                    <th>URL</th>
                    <th>Статус</th>
                    <th>Последняя проверка</th>
                    <th>Последнее изменение</th>
                    <th>Изменений</th>
                    <th>Ошибок</th>
                </tr>
            """
            
            for site in sites:
                html += f"""
                <tr>
                    <td>{site['name']}</td>
                    <td>{site['url']}</td>
                    <td>{site['status']}</td>
                    <td>{site['last_check'].strftime('%d.%m.%Y %H:%M') if site['last_check'] else '-'}</td>
                    <td>{site['last_change'].strftime('%d.%m.%Y %H:%M') if site['last_change'] else '-'}</td>
                    <td>{site['changes_count']}</td>
                    <td>{site['errors_count']}</td>
                </tr>
                """
            
            html += "</table>"
        
        return html
    
    def _format_changes_report_html(self, report_data: Dict[str, Any]) -> str:
        """Форматирование отчета по изменениям в HTML"""
        html = f"""
        <div class="stats">
            <div class="stat-card">
                <h3>Всего изменений</h3>
                <p>{report_data['total_changes']}</p>
            </div>
            <div class="stat-card">
                <h3>Сайтов с изменениями</h3>
                <p>{report_data['sites_with_changes']}</p>
            </div>
            <div class="stat-card">
                <h3>Средний процент изменений</h3>
                <p>{report_data['avg_diff_percent']:.2f}%</p>
            </div>
        </div>
        
        <h2>Категоризация изменений</h2>
        <div class="changes-categories">
            <div class="category critical">
                <h3>Критические изменения ({len(report_data['categorized_changes']['critical'])})</h3>
                <div class="progress-bar">
                    <div class="progress" style="width: {len(report_data['categorized_changes']['critical']) / max(1, report_data['total_changes']) * 100}%"></div>
                </div>
                <p>Изменения более {self.CRITICAL_CHANGE_THRESHOLD}%</p>
            </div>
            <div class="category normal">
                <h3>Значимые изменения ({len(report_data['categorized_changes']['normal'])})</h3>
                <div class="progress-bar">
                    <div class="progress" style="width: {len(report_data['categorized_changes']['normal']) / max(1, report_data['total_changes']) * 100}%"></div>
                </div>
                <p>Изменения от {self.NORMAL_CHANGE_THRESHOLD}% до {self.CRITICAL_CHANGE_THRESHOLD}%</p>
            </div>
            <div class="category minor">
                <h3>Незначительные изменения ({len(report_data['categorized_changes']['minor'])})</h3>
                <div class="progress-bar">
                    <div class="progress" style="width: {len(report_data['categorized_changes']['minor']) / max(1, report_data['total_changes']) * 100}%"></div>
                </div>
                <p>Изменения менее {self.NORMAL_CHANGE_THRESHOLD}%</p>
            </div>
        </div>
        
        <h2>Детальный анализ изменений</h2>
        <div class="detailed-changes">
        """
        
        # Добавляем детальный анализ изменений, если он есть
        if report_data.get('detailed_analysis'):
            for analysis_item in report_data['detailed_analysis']:
                analysis = analysis_item['analysis']
                if isinstance(analysis, dict) and 'error' not in analysis:
                    change_type_class = analysis.get('changes_type', 'minor')
                    title_changed = analysis.get('metadata_changes', {}).get('title_changed', False)
                    description_changed = analysis.get('metadata_changes', {}).get('description_changed', False)
                    keywords_changed = analysis.get('metadata_changes', {}).get('keywords_changed', False)
                    
                    html += f"""
                    <div class="change-analysis {change_type_class}">
                        <h3>Изменение для сайта: {analysis_item['site_name']}</h3>
                        <p>Дата: {analysis_item['timestamp'].strftime('%d.%m.%Y %H:%M')}</p>
                        <div class="analysis-details">
                            <div class="metadata-changes">
                                <h4>Изменения в метаданных:</h4>
                                <ul>
                                    <li>Заголовок: {'<span class="changed">Изменен</span>' if title_changed else 'Без изменений'}</li>
                                    <li>Описание: {'<span class="changed">Изменено</span>' if description_changed else 'Без изменений'}</li>
                                    <li>Ключевые слова: {'<span class="changed">Изменены</span>' if keywords_changed else 'Без изменений'}</li>
                                </ul>
                            </div>
                            <div class="content-changes">
                                <h4>Изменения контента:</h4>
                                <p>Изменение размера: <span class="{change_type_class}">{analysis.get('size_diff', 0)} байт ({analysis.get('size_change_percent', 0):.2f}%)</span></p>
                            </div>
                        </div>
                    </div>
                    """
        else:
            html += """
            <p>Детальный анализ изменений недоступен для данного отчета.</p>
            """
        
        html += """
        </div>
        """
        
        # Добавляем таблицу изменений по категориям
        categories = [
            ('critical', 'Критические изменения'),
            ('normal', 'Значимые изменения'),
            ('minor', 'Незначительные изменения')
        ]
        
        for category_id, category_name in categories:
            changes_list = report_data['categorized_changes'].get(category_id, [])
            if changes_list:
                html += f"""
                <h2>{category_name}</h2>
                <table class="changes-table {category_id}">
                    <tr>
                        <th>Сайт</th>
                        <th>Дата</th>
                        <th>Процент изменений</th>
                        <th>Статус</th>
                        <th>Проверил</th>
                        <th>Комментарий</th>
                    </tr>
                """
                
                for change in changes_list:
                    html += f"""
                    <tr>
                        <td>{change['site_name']}</td>
                        <td>{change['timestamp'].strftime('%d.%m.%Y %H:%M')}</td>
                        <td><span class="{category_id}">{change['diff_percent']:.2f}%</span></td>
                        <td>{change['status']}</td>
                        <td>{change['reviewed_by'] if change['reviewed_by'] else '-'}</td>
                        <td>{change['notes'] if change['notes'] else '-'}</td>
                    </tr>
                    """
                
                html += "</table>"
        
        # Если результаты ограничены, добавляем предупреждение
        if report_data.get('limited_results', False):
            html += f"""
            <div class="warning">
                <p>Внимание: Отчет содержит только {report_data['total_changes']} изменений из {report_data['total_available']} доступных. 
                Для просмотра всех изменений уточните период отчета.</p>
            </div>
            """
        
        return html
    
    def _format_errors_report_html(self, report_data: Dict[str, Any]) -> str:
        """Форматирование отчета по ошибкам в HTML"""
        html = f"""
        <div class="stats">
            <div class="stat-card">
                <h3>Всего ошибок</h3>
                <p>{report_data['total_errors']}</p>
            </div>
            <div class="stat-card">
                <h3>Сайтов с ошибками</h3>
                <p>{report_data['sites_with_errors']}</p>
            </div>
        </div>
        
        <h2>Категоризация ошибок</h2>
        <div class="errors-categories">
        """
        
        # Добавляем категории ошибок и их количество
        errors_by_type = report_data.get('errors_by_type', {})
        if errors_by_type:
            # Создаем круговую диаграмму ошибок с помощью CSS
            html += """
            <div class="pie-chart-container">
                <div class="pie-chart">
            """
            
            # Определяем цвета для категорий ошибок
            colors = [
                "#FF5252", "#FF7043", "#FFCA28", "#66BB6A", 
                "#26C6DA", "#5C6BC0", "#AB47BC", "#EC407A"
            ]
            
            # Создаем сегменты диаграммы
            total_errors = report_data['total_errors']
            start_angle = 0
            
            error_types = list(errors_by_type.keys())
            for i, error_type in enumerate(error_types):
                errors = errors_by_type[error_type]
                percent = (len(errors) / total_errors) * 100
                color = colors[i % len(colors)]
                
                # Добавляем сегмент диаграммы
                if percent > 0:
                    end_angle = start_angle + (percent * 3.6)  # 3.6 = 360 / 100
                    html += f"""
                    <div class="pie-segment" style="--start: {start_angle}deg; --end: {end_angle}deg; --color: {color};" 
                        title="{error_type}: {len(errors)} ({percent:.1f}%)">
                    </div>
                    """
                    start_angle = end_angle
            
            html += """
                </div>
                <div class="pie-legend">
            """
            
            # Добавляем легенду
            for i, error_type in enumerate(error_types):
                errors = errors_by_type[error_type]
                percent = (len(errors) / total_errors) * 100
                color = colors[i % len(colors)]
                
                html += f"""
                <div class="legend-item">
                    <span class="color-box" style="background-color: {color};"></span>
                    <span class="legend-text">{error_type}: {len(errors)} ({percent:.1f}%)</span>
                </div>
                """
            
            html += """
                </div>
            </div>
            """
        else:
            html += "<p>Нет данных для категоризации ошибок.</p>"
        
        html += """
        </div>
        """
        
        # Добавляем таблицы ошибок по категориям
        if errors_by_type:
            for error_type, errors in errors_by_type.items():
                html += f"""
                <h2>Категория: {error_type}</h2>
                <table class="errors-table">
                    <tr>
                        <th>Сайт</th>
                        <th>URL</th>
                        <th>Дата</th>
                        <th>Сообщение об ошибке</th>
                        <th>Группа</th>
                    </tr>
                """
                
                for error in errors:
                    html += f"""
                    <tr>
                        <td>{error['name']}</td>
                        <td>{error['url']}</td>
                        <td>{error['error_time'].strftime('%d.%m.%Y %H:%M')}</td>
                        <td>{error['error_message']}</td>
                        <td>{error['group_name'] if error['group_name'] else '-'}</td>
                    </tr>
                    """
                
                html += "</table>"
        
        # Если результаты ограничены, добавляем предупреждение
        if report_data.get('limited_results', False):
            html += f"""
            <div class="warning">
                <p>Внимание: Отчет содержит только {report_data['total_errors']} ошибок из {report_data['total_available']} доступных. 
                Для просмотра всех ошибок уточните период отчета.</p>
            </div>
            """
        
        return html
    
    def _format_stats_report_html(self, report_data: Dict[str, Any]) -> str:
        """Форматирование статистического отчета в HTML"""
        sites_stats = report_data['sites_stats']
        changes_stats = report_data['changes_stats']
        errors_stats = report_data['errors_stats']
        
        html = f"""
        <div class="stats">
            <div class="stat-card">
                <h3>Всего сайтов</h3>
                <p>{sites_stats['total_sites']}</p>
            </div>
            <div class="stat-card">
                <h3>Активных сайтов</h3>
                <p>{sites_stats['active_sites']}</p>
            </div>
            <div class="stat-card">
                <h3>Средний интервал проверки</h3>
                <p>{sites_stats['avg_check_interval'] / 60:.1f} мин</p>
            </div>
        </div>
        
        <h2>Статистика изменений</h2>
        <div class="stats">
            <div class="stat-card">
                <h3>Всего изменений</h3>
                <p>{changes_stats['total_changes']}</p>
            </div>
            <div class="stat-card">
                <h3>Сайтов с изменениями</h3>
                <p>{changes_stats['sites_with_changes']}</p>
            </div>
            <div class="stat-card">
                <h3>Средний процент изменений</h3>
                <p>{changes_stats['avg_diff_percent']:.2f}%</p>
            </div>
            <div class="stat-card">
                <h3>Максимальный процент изменений</h3>
                <p>{changes_stats['max_diff_percent']:.2f}%</p>
            </div>
        </div>
        
        <h2>Статистика ошибок</h2>
        <div class="stats">
            <div class="stat-card">
                <h3>Всего ошибок</h3>
                <p>{errors_stats['total_errors']}</p>
            </div>
            <div class="stat-card">
                <h3>Сайтов с ошибками</h3>
                <p>{errors_stats['sites_with_errors']}</p>
            </div>
        </div>
        
        <h2>Распределение по группам</h2>
        <table>
            <tr>
                <th>Группа</th>
                <th>Количество сайтов</th>
            </tr>
        """
        
        for group in report_data['groups_stats']:
            html += f"""
            <tr>
                <td>{group['name'] if group['name'] else 'Без группы'}</td>
                <td>{group['sites_count']}</td>
            </tr>
            """
        
        html += "</table>"
        return html 