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
    @staticmethod
    def parse_signal(message: str) -> Optional[Dict]:
        try:
            # Pattern for signals like: "Gold Sell Now: 3343 - 3346 SL: 3348 TP1: 3341 TP2: 3339"
            pattern = r"""
                (?P<symbol>[A-Za-z]+)\s+          # Symbol (e.g., Gold, BTCUSD)
                (?P<action>Buy|Sell)\s+           # Action (Buy/Sell)
                (?:Now|Entry)\s*:\s*              # Optional "Now" or "Entry" keyword
                (?P<entry_min>\d+\.?\d*)\s*-\s*  # Entry min price
                (?P<entry_max>\d+\.?\d*)\s+       # Entry max price
                SL\s*:\s*(?P<sl>\d+\.?\d*)\s+    # Stop Loss
                TP1\s*:\s*(?P<tp1>\d+\.?\d*)\s+  # Take Profit 1
                (?:TP2\s*:\s*(?P<tp2>\d+\.?\d*)\s*)?  # Optional Take Profit 2
            """
            
            match = re.search(pattern, message, re.VERBOSE | re.IGNORECASE)
            if not match:
                logger.warning(f"No signal pattern found in message: {message}")
                return None
                
            signal = {
                'symbol': match.group('symbol').upper(),
                'action': match.group('action').upper(),
                'entry_min': float(match.group('entry_min')),
                'entry_max': float(match.group('entry_max')),
                'sl': float(match.group('sl')),
                'tp1': float(match.group('tp1')),
                'tp2': float(match.group('tp2')) if match.group('tp2') else None
            }
            
            logger.info(f"Successfully parsed signal: {signal}")
            return signal
            
        except Exception as e:
            logger.error(f"Error parsing signal: {str(e)}")
            return None