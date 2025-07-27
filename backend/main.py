import asyncio
import logging
from telegram_monitor import TelegramMonitor
from trading_api import TradingAPI
from notifier import Notifier
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

class SafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            stream.write(msg.encode('utf-8', errors='replace').decode('utf-8') + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('../logs/trading.log', encoding='utf-8'),
        SafeStreamHandler()
    ]
)

logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting Telegram Trading Assistant...")
    
    # Initialize components
    trading_api = TradingAPI()
    notifier = Notifier()
    
    # Connect to MT5
    if not await trading_api.connect():
        await notifier.send_notification("Failed to connect to MT5. Exiting...")
        return
        
    # Start Telegram monitoring
    monitor = TelegramMonitor()
    await notifier.send_notification("Telegram Trading Assistant started successfully")
    #winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    await monitor.start()


if __name__ == "__main__":
    asyncio.run(main())
    
