# WDM V12

Web Data Monitor - профессиональная система мониторинга веб-сайтов и управления данными.

## Описание

WDM V12 - это профессиональное программное обеспечение для мониторинга веб-сайтов, которое позволяет:
- Отслеживать изменения на веб-сайтах
- Создавать снимки состояния сайтов
- Управлять большими объемами данных
- Получать уведомления об изменениях
- Генерировать подробные отчеты

## Установка

Для установки необходимых зависимостей выполните следующую команду:

```bash
pip install -r requirements.txt
```

## Использование

Для запуска системы мониторинга выполните:

```bash
python main.py
```


## Лицензия

WDM V12 распространяется под лицензией MIT. Подробности смотрите в файле LICENSE.

## Основные компоненты
- **Ядро мониторинга**: Получение контента и сравнение снимков
- **Управление задачами**: Менеджер потоков с автоматической перезапусковой стратегией
- **Современный UI/UX**: Интуитивно понятный интерфейс с вкладками и уведомлениями
- **Гибкая система отчетности**: Возможность экспорта в различные форматы (HTML, CSV)
- **Бизнес-логика**: Централизованный метод проверки сайтов с фолбэками

## Системные требования

- Windows 10/11 или Linux
- Python 3.8+
- SQLite 3
- 2 ГБ оперативной памяти
- 500 МБ свободного места на диске

## Структура проекта
- `core/` - Основная бизнес-логика и ядро мониторинга
- `ui/` - Компоненты пользовательского интерфейса
- `database/` - Модули для работы с базой данных SQLite
- `utils/` - Вспомогательные утилиты
- `workers/` - Управление асинхронными задачами и потоками
- `tests/` - Модульные тесты
- `resources/` - Ресурсы (изображения, CSS, шаблоны)
- `reports/` - Модули для генерации отчетов
- `config/` - Конфигурационные файлы

## Правовая информация

Copyright © 2025 AT-Consulting. Все права защищены.

Несанкционированное копирование, распространение и использование программы запрещено. 