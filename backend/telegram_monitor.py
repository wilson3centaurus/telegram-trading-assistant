import logging
from telethon import TelegramClient, events
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, MONITORED_CHANNELS, CHANNEL_NAMES
from signal_parser import SignalParser
from trading_api import TradingAPI
from notifier import Notifier
from logging.handlers import RotatingFileHandler
import sys

# Create a custom StreamHandler that forces UTF-8 encoding
class UTF8StreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            stream.write(msg.encode('utf-8').decode('utf-8') + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('../logs/telegram_monitor.log', encoding='utf-8'),
        UTF8StreamHandler(sys.stdout)  # Use our custom handler instead
    ]
)
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
        
    async def _log_channels(self):
        """Log monitored channels at startup"""
        logger.info("=== Monitored Channels ===")
        for channel_id in MONITORED_CHANNELS:
            name = CHANNEL_NAMES.get(channel_id, f"Unknown Channel ({channel_id})")
            logger.info(f" • {name} (ID: {channel_id})")
        logger.info("==========================")
        
    async def start(self):
        await self.client.start(TELEGRAM_PHONE)
        logger.info("Telegram client started successfully")
        
        # Log all monitored channels
        await self._log_channels()
        
        @self.client.on(events.NewMessage(chats=MONITORED_CHANNELS))
        async def handler(event):
            channel_name = CHANNEL_NAMES.get(event.chat_id, f"Unknown Channel ({event.chat_id})")
            message = event.message.text
            
            logger.info(f"New message from [{channel_name}]: {message}")
            
            try:
                signal = SignalParser.parse_signal(message)
                if signal:
                    logger.info(f"[{channel_name}] Signal parsed: {signal}")
                    trading_api = TradingAPI()
                    trade_result = await trading_api.execute_trade(signal)
                    
                    notification_msg = (
                        f"Trade executed from {channel_name}\n"
                        f"Symbol: {signal['symbol']} {signal['action']}\n"
                        f"Entry: {signal.get('entry_min', 'N/A')}-{signal.get('entry_max', 'N/A')}\n"
                        f"SL: {signal['sl']} | TP: {signal['tp1']}"
                    )
                    
                    if trade_result[0]:
                        await Notifier.send_notification(f"Trade executed from {channel_name} ...")
                    else:
                        await Notifier.send_notification(f"Trade FAILED from {channel_name} - Reason: {trade_result[1]}")

            except Exception as e:
                error_msg = f"Error processing message from {channel_name}: {str(e)}"
                logger.error(error_msg)
                await Notifier.send_notification(error_msg)
        
        logger.info("Active monitoring started...")
        await self.client.run_until_disconnected()