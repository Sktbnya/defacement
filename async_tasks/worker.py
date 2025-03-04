# async_tasks/worker.py
import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, List
from monitor import fetcher, parser, diff_analyzer, ml_analyzer, notifier

previous_contents: Dict[str, str] = {}

async def process_site(url: str) -> Dict[str, any]:
    """
    Обрабатывает один сайт и возвращает результаты мониторинга.
    Возвращаемый словарь содержит:
      - "structure": % изменений структуры,
      - "content": % изменений видимого текста,
      - "metadata": % изменений метаданных,
      - "overall": общий базовый риск,
      - "updated": время последней проверки,
      - "status": статус сайта,
      - "ml_score": ML-оценка (в процентах).
    """
    logging.info(f"Обработка сайта: {url}")
    content = await fetcher.fetch_page(url)
    available = content is not None
    result = {}
    if not available:
        logging.error(f"Сайт недоступен: {url}")
        notifier.send_telegram_notification(f"Сайт {url} недоступен!")
        result = {
            "structure": "",
            "content": "",
            "metadata": "",
            "overall": "",
            "updated": datetime.now().isoformat(timespec='seconds'),
            "status": "Недоступен",
            "ml_score": ""
        }
        return result

    parsed_new = parser.parse_html(content)
    text_new = parsed_new.get("text", "")
    ml_score = await asyncio.to_thread(ml_analyzer.evaluate_defacement, text_new)
    ml_percentage = round(ml_score * 100, 2)
    
    if url in previous_contents:
        old_content = previous_contents[url]
        basic_changes = diff_analyzer.calculate_changes(parser.parse_html(old_content), parsed_new, None)
        status_text = "Доступен"
        reports_dir = "reports"
        os.makedirs(reports_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sanitized_url = url.replace("https://", "").replace("http://", "").replace("/", "_")
        diff_filename = os.path.join(reports_dir, f"diff_{sanitized_url}_{timestamp}.html")
        try:
            diff_html = diff_analyzer.generate_report({"html": old_content}, {"html": content}, basic_changes, url)
            with open(diff_filename, "w", encoding="utf-8") as f:
                f.write(diff_html)
            logging.info(f"Дифф-отчет для {url} сохранён в {diff_filename}")
        except Exception as e:
            logging.error(f"Ошибка сохранения отчета для {url}: {e}")
        result = {
            "structure": basic_changes.get("visual_changes", {}).get("structure"),
            "content": basic_changes.get("visual_changes", {}).get("content"),
            "metadata": basic_changes.get("visual_changes", {}).get("metadata"),
            "overall": basic_changes.get("visual_changes", {}).get("structure"),  # Можно объединить категории
            "updated": datetime.now().isoformat(timespec='seconds'),
            "status": status_text,
            "ml_score": ml_percentage,
            "html": content,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    else:
        logging.info(f"Первая версия для {url} сохранена.")
        result = {
            "structure": 0,
            "content": 0,
            "metadata": 0,
            "overall": 0,
            "updated": datetime.now().isoformat(timespec='seconds'),
            "status": "Первый сбор",
            "ml_score": ml_percentage,
            "html": content,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    previous_contents[url] = content
    if ml_score > 0.5:
        notifier.send_telegram_notification(f"Обнаружены подозрительные изменения на сайте {url} (ML оценка: {ml_percentage}%)")
    return result

async def process_all_sites(urls: List[str], interval: int = 300) -> List[Dict[str, any]]:
    """
    Периодически обрабатывает список сайтов и возвращает список результатов.
    :param urls: Список URL.
    :param interval: Интервал в секундах.
    :return: Список словарей с результатами для каждого сайта.
    """
    results = []
    for url in urls:
        try:
            res = await process_site(url)
            res["url"] = url  # Добавляем ключ, чтобы можно было обновить нужную строку в UI
            results.append(res)
        except Exception as e:
            logging.error(f"Ошибка обработки сайта {url}: {e}")
    return results
