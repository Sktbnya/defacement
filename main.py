# main.py
import sys
import asyncio
import threading
import yaml
import logging
import logging.config
from gui.main_window import MainWindow
from PyQt5.QtWidgets import QApplication
from async_tasks.worker import process_all_sites

def setup_logging():
    try:
        logging.config.fileConfig("config/logging.conf", disable_existing_loggers=False)
    except Exception as e:
        logging.basicConfig(level=logging.INFO)
        logging.error("Ошибка загрузки конфигурации логирования: " + str(e))

def load_config() -> dict:
    with open("config/config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def start_monitoring_loop(sites: list, interval: int):
    asyncio.run(process_all_sites(sites, interval))

def start_async_monitoring(sites: list, interval: int):
    thread = threading.Thread(target=start_monitoring_loop, args=(sites, interval), daemon=True)
    thread.start()
    logging.info("Асинхронный мониторинг запущен в отдельном потоке.")

def main():
    setup_logging()
    config = load_config()
    sites = config.get("sites", [])
    interval = config.get("monitoring_interval", 300)
    
    # Можно запускать фоновый мониторинг до запуска GUI (если требуется)
    start_async_monitoring(sites, interval)
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
