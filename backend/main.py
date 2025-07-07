import asyncio
import logging
from telegram_monitor import TelegramMonitor
from trading_api import TradingAPI
from notifier import Notifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('../logs/main.log'),
        logging.StreamHandler()
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
    await monitor.start()

if __name__ == "__main__":
    asyncio.run(main())