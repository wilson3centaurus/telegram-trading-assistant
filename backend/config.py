import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Configuration
TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID'))
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
TELEGRAM_PHONE = os.getenv('TELEGRAM_PHONE')

# Telegram connection settings
TELEGRAM_CONNECTION_RETRIES = 5
TELEGRAM_RETRY_DELAY = 1
TELEGRAM_TIMEOUT = 10

# Full margin configuration
FULL_MARGIN_SETTINGS = {
    'ENABLED': True,  # Master switch for full margin feature
    'CHANNELS': ['Adam Trader'],  # Channels that should use full margin
    'MULTIPLIER': 1.0  # Risk multiplier for full margin (1.0 = full margin)
}

# Trading Configuration
MT5_SERVER = os.getenv('MT5_SERVER')
MT5_LOGIN = int(os.getenv('MT5_LOGIN'))
MT5_PASSWORD = os.getenv('MT5_PASSWORD')
MT5_DEMO_ACCOUNT = True
DEFAULT_LOT_SIZE = 0.01
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
    -1002310471028,      # Tau Core 
    -1001727095970,      # Wicked Pips
    -1001678550622,
    -1001680297592,
    -1001348564602,
    -1001348564602,
    -1001230054900,
    -1002176701424,
    -1001584939836,
    -1001588519179,
    -1001853260470,
    -1001649102395,
    -1001765226347,
    -1001727095970,
    -1001604309645,
    -1001780474473,
    -1001920020352,
    -1002070456268,
    -1001774783341,
    -1001927294039,
    -1002144761347,
    -1001897903474,
    -1001949888064,
    -1001548697299,
    -1002109688314,
    -1002266711958
]

# channel names for logging
CHANNEL_NAMES = {
    -1002553705628: "Land of Heros",
    -1001979633557: "Adam Trader",
    -1001454616797: "Bluebull Trader",
    -1001313672961: "Golder Snipers",
    -1002310471028: "Tau Core",
    -1001727095970: "Wicked Pips",
    -1001678550622: "Day Trading Academy",
    -1001680297592: "Gold Empire",
    -1001348564602: "Rio Traders",
    -1001230054900: "Market Makers",
    -1002176701424: "United Kings",
    -1001584939836: "Gold Snipers Signals",
    -1001588519179: "Sure Shot Gold",
    -1001853260470: "Mafia Markerts",
    -1001649102395: "Trader's Circle",
    -1001765226347: "Ben GT",
    -1001727095970: "Farooq Gold Master",
    -1001604309645: "James Gold Master",
    -1001780474473: "Novatrades Int.",
    -1001920020352: "Grow Trading",
    -1002070456268: "Henry Gold Digger",
    -1001774783341: "Gary Gold Trader",
    -1001927294039: "Vincent Gold Trader",
    -1002144761347: "Top 1% Trades",
    -1001897903474: "Chief Pablo Trader",
    -1001949888064: "Arixander X Signals",
    -1001548697299: "Fabio GT",
    -1002109688314: "Project 7",
    -1002266711958: "Gold Pipstar",
}

# Database
DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'trades.db')

