import logging
from telethon import TelegramClient, events
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, MONITORED_CHANNELS
from signal_parser import SignalParser
from trading_api import TradingAPI
from notifier import Notifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('../logs/telegram_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TelegramMonitor:
    def __init__(self):
        self.client = TelegramClient('session_name', TELEGRAM_API_ID, TELEGRAM_API_HASH)
        
    async def start(self):
        await self.client.start(TELEGRAM_PHONE)
        logger.info("Telegram client started successfully")
        
        @self.client.on(events.NewMessage(chats=MONITORED_CHANNELS))
        async def handler(event):
            message = event.message.text
            logger.info(f"New message received: {message}")
            
            try:
                signal = SignalParser.parse_signal(message)
                if signal:
                    logger.info(f"Signal parsed successfully: {signal}")
                    trading_api = TradingAPI()
                    trade_result = await trading_api.execute_trade(signal)
                    if trade_result:
                        await Notifier.send_notification(f"Trade executed: {signal}")
                    else:
                        await Notifier.send_notification(f"Trade Failed: {signal}")
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                await Notifier.send_notification(f"Error processing message: {str(e)}")
        
        logger.info("Monitoring Telegram channels...")
        await self.client.run_until_disconnected()