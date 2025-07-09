import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Configuration
TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID'))
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
TELEGRAM_PHONE = os.getenv('TELEGRAM_PHONE')

# Trading Configuration
MT5_SERVER = os.getenv('MT5_SERVER')
MT5_LOGIN = int(os.getenv('MT5_LOGIN'))
MT5_PASSWORD = os.getenv('MT5_PASSWORD')
MT5_DEMO_ACCOUNT = True
DEFAULT_LOT_SIZE = 0.1
MAX_SLIPPAGE = 10  # in pips

# Notification Configuration
NOTIFICATION_TELEGRAM_BOT_TOKEN = os.getenv('NOTIFICATION_TELEGRAM_BOT_TOKEN')
NOTIFICATION_CHAT_ID = os.getenv('NOTIFICATION_CHAT_ID')
EMAIL_NOTIFICATIONS = False
EMAIL_FROM = os.getenv('EMAIL_FROM')
EMAIL_TO = os.getenv('EMAIL_TO')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')

# Logging Configuration
LOG_FILE = 'logs/trading.log'
LOG_LEVEL = 'INFO'

# Unified channel loading (from .env with fallback)
MONITORED_CHANNELS = [
    int(channel_id.strip()) for channel_id in 
    os.getenv('MONITORED_CHANNELS', '').split(',') 
    if channel_id.strip()
] or [  # Fallback hardcoded channels
    -1002553705628,     # Land of Heros
    -1001979633557,     # Adam Trader
    -1001454616797,     # Bluebull Trader
    -1001313672961,     # Golder Snipers
    -1002310471028      # Tau Core 
]

# channel names for logging
CHANNEL_NAMES = {
    -1002553705628: "Land of Heros",
    -1001979633557: "Adam Trader",
    -1001454616797: "Bluebull Trader",
    -1001313672961: "Golder Snipers",
    -1002310471028: "Tau Core"
}

# Database
DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'trades.db')