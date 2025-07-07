import logging
import requests
import smtplib
from email.mime.text import MIMEText
from plyer import notification
from config import (
    NOTIFICATION_TELEGRAM_BOT_TOKEN,
    NOTIFICATION_CHAT_ID,
    EMAIL_NOTIFICATIONS,
    EMAIL_FROM,
    EMAIL_TO,
    EMAIL_PASSWORD
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('../logs/notifier.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class Notifier:
    @staticmethod
    async def send_notification(message: str):
        try:
            # Desktop notification
            notification.notify(
                title='Trading Assistant',
                message=message,
                app_name='Telegram Trading Assistant'
            )
            
            # Telegram notification
            if NOTIFICATION_TELEGRAM_BOT_TOKEN and NOTIFICATION_CHAT_ID:
                url = f"https://api.telegram.org/bot{NOTIFICATION_TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {
                    'chat_id': NOTIFICATION_CHAT_ID,
                    'text': message
                }
                response = requests.post(url, data=payload)
                if response.status_code != 200:
                    logger.error(f"Telegram notification failed: {response.text}")
            
            # Email notification
            if EMAIL_NOTIFICATIONS:
                msg = MIMEText(message)
                msg['Subject'] = 'Trading Assistant Notification'
                msg['From'] = EMAIL_FROM
                msg['To'] = EMAIL_TO
                
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(EMAIL_FROM, EMAIL_PASSWORD)
                    server.send_message(msg)
                    
            logger.info(f"Notification sent: {message}")
            
        except Exception as e:
            logger.error(f"Error sending notification: {str(e)}")