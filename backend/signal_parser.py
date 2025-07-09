import re
import logging
from typing import Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('../logs/signal_parser.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SignalParser:
    SYMBOL_MAP = {
        'GOLD': 'XAUUSD',
        'XAUUSD': 'XAUUSD',
        'GOLD/USD': 'XAUUSD',
        'BOOM': 'BOOM500',
        'CRASH': 'CRASH500'
    }

    @staticmethod
    def parse_signal(message: str) -> Optional[Dict]:
        try:
            # Normalize message
            clean_msg = re.sub(r'[^\w\s\.-]', ' ', message.upper())
            
            # Extract symbol
            symbol_match = re.search(r'(GOLD|XAUUSD|BOOM\d*|CRASH\d*)', clean_msg)
            if not symbol_match:
                return None
            symbol = SignalParser.SYMBOL_MAP.get(symbol_match.group(1), symbol_match.group(1))

            # Extract action
            action_match = re.search(r'\b(BUY|SELL|LONG|SHORT)\b', clean_msg)
            if not action_match:
                return None
            action = 'BUY' if action_match.group(1) in ['BUY', 'LONG'] else 'SELL'

            # Extract entry prices (handles both ranges and single prices)
            entry_prices = re.findall(r'(\d+\.?\d*)', clean_msg.split(action_match.group(1))[-1])
            if len(entry_prices) >= 2:
                entry_min, entry_max = float(entry_prices[0]), float(entry_prices[1])
            elif entry_prices:
                entry_min = entry_max = float(entry_prices[0])
            else:
                return None

            # Extract SL (more robust pattern)
            sl_match = re.search(r'(?:SL|STOP\s*LOSS)[\s:]*(\d+\.?\d*)', clean_msg)
            sl = float(sl_match.group(1)) if sl_match else None

            # Extract TPs (gets all TP values)
            tp_matches = re.finditer(r'(?:TP\d*|TAKE\s*PROFIT)[\s:]*(\d+\.?\d*)', clean_msg)
            tps = [float(m.group(1)) for m in tp_matches]

            if not all([symbol, action, sl, tps]):
                return None

            return {
                'symbol': symbol,
                'action': action,
                'entry_min': min(entry_min, entry_max),
                'entry_max': max(entry_min, entry_max),
                'sl': sl,
                'tp1': tps[0],
                'tp2': tps[1] if len(tps) > 1 else None
            }

        except Exception as e:
            logger.error(f"Parse error: {str(e)}")
            return None