import logging
from telethon import TelegramClient, events
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, MONITORED_CHANNELS, CHANNEL_NAMES, DEFAULT_LOT_SIZE
from signal_parser import SignalParser
from trading_api import TradingAPI
from notifier import Notifier
from logging.handlers import RotatingFileHandler
import winsound
import sys
import requests
from trade_tracker import TradeTracker
from pushover import send_pushover_notification
import asyncio

PUSHOVER_USER_KEY = "uig46b9ik8eqy5fefzbzt8ttri1k6z"
PUSHOVER_APP_TOKEN = "admg7efo3yqp4pwmbi6v92opmpnzov"

parser = SignalParser(use_ai=True) 

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
        UTF8StreamHandler(sys.stdout) 
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

logging.getLogger("telethon").setLevel(logging.WARNING)

class TelegramMonitor:
    def __init__(self):
        self.client = TelegramClient('session_name', TELEGRAM_API_ID, TELEGRAM_API_HASH)
        self.trade_tracker = TradeTracker()
        
    async def _log_channels(self):
        """Log monitored channels at startup"""
        logger.info("=== Monitored Channels ===")
        for channel_id in MONITORED_CHANNELS:
            name = CHANNEL_NAMES.get(channel_id, f"Unknown Channel ({channel_id})")
            logger.info(f" • {name} (ID: {channel_id})")
        logger.info("==========================")
        
    async def start(self):
        await self.client.start(TELEGRAM_PHONE)
        asyncio.create_task(self.trade_tracker.monitor_trades())
        logger.info("Telegram client started successfully")
        
        # Log all monitored channels
        await self._log_channels()
        
        @self.client.on(events.NewMessage(chats=MONITORED_CHANNELS))
        async def handler(event):
            channel_name = CHANNEL_NAMES.get(event.chat_id, f"Unknown Channel ({event.chat_id})")
            message = event.message.text
            
            logger.info(f"New message from [{channel_name}]: {message}")
            #winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            
            def send_pushover_notification(message: str, title: str = "Tau Core System"):
                payload = {
                    "token": PUSHOVER_APP_TOKEN,
                    "user": PUSHOVER_USER_KEY,
                    "message": message,
                    "title": title,
                    "priority": 1,
                }
                try:
                    response = requests.post("https://api.pushover.net/1/messages.json", data=payload)
                    if response.status_code == 200:
                        print("✅ Pushover notification sent")
                    else:
                        print(f"❌ Failed to send Pushover notification: {response.text}")
                except Exception as e:
                    print(f"Error sending pushover: {str(e)}")

            
            try:
                signal = SignalParser.parse_signal_static(message)
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
                        send_pushover_notification(
                            message=f"Trade executed from {channel_name}\n"
                                    f"Symbol: {signal['symbol']} {signal['action']}\n"
                                    f"Entry: {signal.get('entry_min', 'N/A')}-{signal.get('entry_max', 'N/A')}\n"
                                    f"SL: {signal['sl']} | TP: {signal['tp1']}",
                            title="📈 Tau Core Trade Executed!"
                        )
                        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                        
                        # In your handler function, update the trade tracking part:
                        if trade_result[0]:
                            try:
                                # Extract ticket number safely
                                ticket = int(trade_result[1].split(":")[-1].strip()) if ":" in trade_result[1] else None
                                if ticket:
                                    entry_price = (signal.get('entry_min', 0) + signal.get('entry_max', 0)) / 2 if \
                                                signal.get('entry_min') and signal.get('entry_max') else \
                                                signal.get('entry_min', 0)
                                    
                                    self.trade_tracker.add_trade(
                                        ticket=ticket,
                                        symbol=signal["symbol"],
                                        sl=signal["sl"],
                                        tp=signal["tp1"],
                                        volume=DEFAULT_LOT_SIZE,
                                        entry_price=entry_price,
                                        action=signal["action"]
                                    )
                            except Exception as e:
                                logger.error(f"Error adding trade to tracker: {str(e)}")

                    else:
                        await Notifier.send_notification(f"Trade FAILED from {channel_name} - Reason: {trade_result[1]}")
                        

            except Exception as e:
                error_msg = f"Error processing message from {channel_name}: {str(e)}"
                logger.error(error_msg)
                await Notifier.send_notification(error_msg)
        
        logger.info("Active monitoring started...")
        await self.client.run_until_disconnected()