# monitor/diff_analyzer.py
import difflib
from datetime import datetime

def calculate_changes(old_data: dict, new_data: dict, analyzer) -> dict:
    """
    Вычисляет процент изменений между двумя версиями HTML-контента.
    
    Если предыдущий контент пустой, а новый не пустой, возвращает 100% изменений.
    В противном случае использует difflib для оценки схожести.
    
    :param old_data: Словарь с ключом 'html' для старой версии.
    :param new_data: Словарь с ключом 'html' для новой версии.
    :param analyzer: Объект анализатора (пока не используется – placeholder).
    :return: Словарь с изменениями, например, {"visual_changes": {"structure": value, ...}}
    """
    old_html = old_data.get("html", "")
    new_html = new_data.get("html", "")
    # Если предыдущий контент пустой, а новый не пустой – возвращаем 100%
    if not old_html and new_html:
        change_ratio = 100.0
        return {"visual_changes": {"structure": change_ratio, "content": change_ratio, "metadata": change_ratio}}
    if not old_html and not new_html:
        return {"visual_changes": {"structure": 0.0, "content": 0.0, "metadata": 0.0}}
    
    matcher = difflib.SequenceMatcher(None, old_html, new_html)
    change_ratio = (1 - matcher.ratio()) * 100
    return {"visual_changes": {"structure": change_ratio, "content": change_ratio, "metadata": change_ratio}}

def generate_report(old_content: dict, new_content: dict, changes: dict, url: str) -> str:
    """
    Генерирует HTML-отчет по изменениям между двумя версиями контента.
    
    :param old_content: Словарь с ключом 'html' для старой версии.
    :param new_content: Словарь с ключом 'html' для новой версии.
    :param changes: Словарь с рассчитанными изменениями.
    :param url: URL сайта.
    :return: HTML-строка с отчетом, где проценты отображаются с символом '%'.
    """
    report = f"""
    <html>
    <head>
      <meta charset="utf-8">
      <title>Отчет по сайту {url}</title>
      <style>
        body {{
          font-family: Arial, sans-serif;
          margin: 20px;
        }}
        h1 {{
          color: #004080;
        }}
        table {{
          border-collapse: collapse;
          width: 100%;
        }}
        th, td {{
          border: 1px solid #ddd;
          padding: 8px;
          text-align: left;
        }}
        th {{
          background-color: #f2f2f2;
        }}
      </style>
    </head>
    <body>
      <h1>Отчет по сайту: {url}</h1>
      <p>Дата отчета: {datetime.now().strftime("%H:%M:%S %d.%m.%Y")}</p>
      <h2>Сводка изменений</h2>
      <table>
        <tr>
          <th>Категория</th>
          <th>Процент изменений</th>
        </tr>
        <tr>
          <td>Структура</td>
          <td>{changes['visual_changes'].get('structure', 0):.2f}%</td>
        </tr>
        <tr>
          <td>Контент</td>
          <td>{changes['visual_changes'].get('content', 0):.2f}%</td>
        </tr>
        <tr>
          <td>Метаданные</td>
          <td>{changes['visual_changes'].get('metadata', 0):.2f}%</td>
        </tr>
      </table>
    </body>
    </html>
    """
    return report
