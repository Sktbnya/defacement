# monitor/notifier.py
import logging
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import yaml

def load_notification_config() -> dict:
    try:
        with open("config/config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return config.get("notifications", {})
    except Exception as e:
        logging.error(f"Ошибка загрузки конфигурации уведомлений: {e}")
        return {}

def check_configuration() -> bool:
    config = load_notification_config().get("telegram", {})
    return bool(config.get("token") and config.get("chat_id"))

def send_telegram_notification(message: str) -> None:
    config = load_notification_config().get("telegram", {})
    if not config.get("enabled", False):
        logging.info("Telegram уведомления отключены.")
        return
    token = config.get("token")
    chat_id = config.get("chat_id")
    if not token or not chat_id:
        logging.error("Telegram token или chat_id не настроены.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": message}
    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            logging.info("Telegram уведомление отправлено.")
        else:
            logging.error(f"Ошибка отправки Telegram уведомления: {response.text}")
    except Exception as e:
        logging.error(f"Исключение при отправке Telegram уведомления: {e}")

def send_email_notification(subject: str, message: str, recipient: str) -> None:
    config = load_notification_config().get("email", {})
    if not config.get("enabled", False):
        logging.info("Email уведомления отключены.")
        return
    smtp_server = config.get("smtp_server")
    smtp_port = config.get("smtp_port")
    username = config.get("username")
    password = config.get("password")
    if not (smtp_server and smtp_port and username and password):
        logging.error("Email конфигурация неполная.")
        return
    try:
        msg = MIMEMultipart()
        msg['From'] = username
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(username, password)
        server.send_message(msg)
        server.quit()
        logging.info("Email уведомление отправлено.")
    except Exception as e:
        logging.error(f"Ошибка отправки email уведомления: {e}")

def send_desktop_notification(message: str) -> None:
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast("Уведомление", message, duration=10)
        logging.info("Десктоп уведомление отправлено.")
    except ImportError:
        logging.error("Библиотека win10toast не установлена.")
    except Exception as e:
        logging.error(f"Ошибка отправки десктоп уведомления: {e}")
