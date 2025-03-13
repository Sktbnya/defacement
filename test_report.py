#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для проверки системы отчетов
"""

from core.app_context import AppContext
from reports.report_generator import ReportGenerator
from datetime import datetime, timedelta
import os

def main():
    print("Инициализация AppContext...")
    app = AppContext()
    app.initialize()
    
    print("Создание ReportGenerator...")
    rg = ReportGenerator(app)
    
    # Период для отчетов - последние 30 дней
    date_from = datetime.now() - timedelta(days=30)
    date_to = datetime.now()
    
    print(f"Создание отчета по сайтам за период {date_from.strftime('%d.%m.%Y')} - {date_to.strftime('%d.%m.%Y')}...")
    sites_report = rg.generate_sites_report(date_from, date_to)
    print(f"Создан отчет по {sites_report['total_sites']} сайтам")
    
    print("\nСоздание отчета по изменениям...")
    changes_report = rg.generate_changes_report(date_from, date_to)
    print("Категоризация изменений:")
    print(f"- Критические: {len(changes_report['categorized_changes']['critical'])}")
    print(f"- Значимые: {len(changes_report['categorized_changes']['normal'])}")
    print(f"- Незначительные: {len(changes_report['categorized_changes']['minor'])}")
    
    if changes_report.get('detailed_analysis'):
        print(f"\nДетальный анализ доступен для {len(changes_report['detailed_analysis'])} изменений")
    
    print("\nСоздание отчета по ошибкам...")
    errors_report = rg.generate_errors_report(date_from, date_to)
    print(f"Всего ошибок: {errors_report['total_errors']}")
    print(f"Сайтов с ошибками: {errors_report['sites_with_errors']}")
    
    if errors_report.get('errors_by_type'):
        print("\nРаспределение ошибок по типам:")
        for error_type, errors in errors_report['errors_by_type'].items():
            print(f"- {error_type}: {len(errors)}")
    
    # Сохраняем HTML отчет
    html_report = rg.format_report_html(changes_report)
    report_path = os.path.join("reports_output", f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_report)
    
    print(f"\nОтчет сохранен в {report_path}")
    print("Тестирование завершено успешно!")

if __name__ == "__main__":
    main() 