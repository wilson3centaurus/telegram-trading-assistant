import requests
import json
import logging
from typing import Dict, Optional
import re

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
    def __init__(self, use_ai: bool = True, ollama_url: str = "http://localhost:11434", model: str = "deepseek-r1:8b"):
        self.use_ai = use_ai
        self.ollama_url = ollama_url
        self.model = model
        
        # Symbol mapping
        self.SYMBOL_MAP = {
            'GOLD': 'XAUUSD',
            'XAUUSD': 'XAUUSD',
            'XAU/USD': 'XAUUSD',
            'GOLD/USD': 'XAUUSD',
            'XAU': 'XAUUSD',
            'GOLDSPOT': 'XAUUSD',
        }
    
    def parse_signal(self, message: str) -> Optional[Dict]:
        """Parse trading signal"""
        try:
            if self.use_ai:
                logger.info("Attempting AI parsing...")
                ai_result = self._parse_with_ai(message)
                if ai_result:
                    logger.info("AI parsing successful")
                    return ai_result
                logger.warning("AI parsing failed, falling back to regex")
            
            # Fallback to regex
            logger.info("Using regex parsing")
            return self._parse_with_regex(message)
            
        except Exception as e:
            logger.error(f"Parse error: {str(e)}", exc_info=True)
            return None
        
    @staticmethod
    def parse_signal_static(message: str) -> Optional[Dict]:
        """Static method version for backward compatibility"""
        parser = SignalParser(use_ai=False)  # Use regex for static method
        return parser.parse_signal(message)
    
    def _parse_with_ai(self, message: str) -> Optional[Dict]:
        """Parse using local LLM with better error handling"""
        try:
            # Clean the message first
            clean_msg = self._clean_message(message)
            
            prompt = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a trading signal parser. Extract:
    - symbol (convert GOLD/XAU to XAUUSD)
    - action (BUY/SELL)
    - entry_min (number)
    - entry_max (number, same as min if single price)
    - sl (stop loss number)
    - tp1 (take profit 1 number)
    - tp2 (take profit 2 number or null)

    Return ONLY valid JSON with these fields."""
                    },
                    {
                        "role": "user",
                        "content": clean_msg
                    }
                ],
                "format": "json",
                "options": {
                    "temperature": 0.1,
                    "num_ctx": 2048
                }
            }

            response = requests.post(
                f"{self.ollama_url}/api/chat",
                json=prompt,
                timeout=15
            )

            if response.status_code == 200:
                try:
                    result = response.json()
                    if 'message' in result and 'content' in result['message']:
                        ai_response = result['message']['content']
                        logger.info(f"AI raw response: {ai_response}")
                        
                        # Extract JSON from response
                        json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
                        if json_match:
                            parsed = json.loads(json_match.group(0))
                            if self._validate_required_fields(parsed):
                                normalized = self._normalize_data(parsed)
                                if self._validate_signal_logic(normalized):
                                    logger.info("AI parsing successful")
                                    return normalized
                except Exception as e:
                    logger.error(f"AI response parsing failed: {str(e)}")
            
            logger.warning(f"AI request failed with status {response.status_code}")
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"AI connection error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"AI parsing error: {str(e)}")
            return None
        
    def _extract_json_from_ai_response(self, response: str) -> Optional[Dict]:
        """Extract and validate JSON from AI response"""
        try:
            # Find JSON in response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                return None
            
            parsed = json.loads(json_match.group(0))
            
            # Validate and normalize
            if self._validate_required_fields(parsed):
                normalized = self._normalize_data(parsed)
                if self._validate_signal_logic(normalized):
                    logger.info(f"AI parsed successfully: {normalized}")
                    return normalized
            
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"AI response parsing error: {e}")
        return None
    
    def _parse_with_regex(self, message: str) -> Optional[Dict]:
        """Improved regex parsing"""
        try:
            clean_msg = self._clean_message(message)
            logger.info(f"Parsing with regex: {clean_msg[:100]}...")
            
            # Extract components
            symbol = self._extract_symbol(clean_msg)
            action = self._extract_action(clean_msg)
            entry_min, entry_max = self._extract_entry_prices(clean_msg)
            sl = self._extract_stop_loss(clean_msg)
            tps = self._extract_take_profits(clean_msg)
            
            # Validate we have minimum required data
            if not all([symbol, action, sl, tps]):
                missing = []
                if not symbol: missing.append("symbol")
                if not action: missing.append("action")
                if not sl: missing.append("stop loss")
                if not tps: missing.append("take profit")
                logger.warning(f"Missing: {', '.join(missing)}")
                return None
            
            # Handle entry prices - if missing, estimate from SL and TP
            if not entry_min:
                entry_min = self._estimate_entry_price(action, sl, tps[0] if tps else None)
                if not entry_min:
                    logger.warning("Could not determine entry price")
                    return None
            
            # Build signal
            signal = {
                'symbol': symbol,
                'action': action,
                'entry_min': entry_min,
                'entry_max': entry_max if entry_max else entry_min,
                'sl': sl,
                'tp1': tps[0] if len(tps) > 0 else None,
                'tp2': tps[1] if len(tps) > 1 else None
            }
            
            if self._validate_signal_logic(signal):
                logger.info(f"Regex parsed successfully: {signal}")
                return signal
            else:
                logger.warning(f"Signal failed validation: {signal}")
                return None
                
        except Exception as e:
            logger.error(f"Regex parsing error: {e}")
            return None
    
    def _clean_message(self, message: str) -> str:
        """Clean message for parsing"""
        # Remove HTML tags and normalize
        clean = re.sub(r'<[^>]+>', '', message)
        clean = clean.replace('–', '-').replace('—', '-')
        clean = re.sub(r'[^\w\s@:.\-/,*]', ' ', clean, flags=re.UNICODE)
        clean = clean.upper().strip()
        clean = re.sub(r'\s+', ' ', clean)
        return clean
    
    def _extract_symbol(self, message: str) -> Optional[str]:
        """Extract trading symbol"""
        patterns = [
            r'\b(XAUUSD|XAU\s*[/\\]\s*USD|GOLD)\b',
            r'\b(BOOM\d*|CRASH\d*)\b',
            r'\b([A-Z]{3}\s*[/\\]\s*[A-Z]{3})\b'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                symbol = re.sub(r'\s+', '', match.group(1))
                return self.SYMBOL_MAP.get(symbol, symbol)
        return 'XAUUSD'  # Default for gold-related messages
    
    def _extract_action(self, message: str) -> Optional[str]:
        """Extract BUY/SELL action"""
        if re.search(r'\b(SELL|SHORT)\b', message):
            return 'SELL'
        elif re.search(r'\b(BUY|LONG)\b', message):
            return 'BUY'
        return None
    
    def _extract_entry_prices(self, message: str) -> tuple:
        """Extract entry price range"""
        # Look for price ranges like "3370.54-3371.14"
        range_match = re.search(r'(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)', message)
        if range_match:
            price1 = float(range_match.group(1))
            price2 = float(range_match.group(2))
            return min(price1, price2), max(price1, price2)
        
        # Look for single entry price
        entry_patterns = [
            r'(?:NOW|@)\s*(\d+\.?\d*)',
            r'ENTRY\s*[:@]?\s*(\d+\.?\d*)',
            r'(?:BUY|SELL)\s+(?:NOW\s+)?(\d+\.?\d*)'
        ]
        
        for pattern in entry_patterns:
            match = re.search(pattern, message)
            if match:
                price = float(match.group(1))
                return price, price
        
        return None, None
    
    def _extract_stop_loss(self, message: str) -> Optional[float]:
        """Extract stop loss price"""
        sl_patterns = [
            r'SL\s*[:@]?\s*(\d+\.?\d*)',
            r'STOP\s*LOSS?\s*[:@]?\s*(\d+\.?\d*)',
            r'STOP\s*[:@]?\s*(\d+\.?\d*)'
        ]
        
        for pattern in sl_patterns:
            match = re.search(pattern, message)
            if match:
                return float(match.group(1))
        return None
    
    def _extract_take_profits(self, message: str) -> list:
        """Extract take profit levels"""
        tp_patterns = [
            r'TP\d?\s*[:@]?\s*(\d+\.?\d*)',
            r'TARGET\s*\d?\s*[:@]?\s*(\d+\.?\d*)',
            r'TAKE\s*PROFIT\s*\d?\s*[:@]?\s*(\d+\.?\d*)'
        ]
        
        tps = []
        for pattern in tp_patterns:
            matches = re.finditer(pattern, message)
            for match in matches:
                try:
                    tp = float(match.group(1))
                    if tp not in tps:
                        tps.append(tp)
                except ValueError:
                    continue
        
        return sorted(tps)
    
    def _estimate_entry_price(self, action: str, sl: float, tp1: float) -> Optional[float]:
        """Estimate entry price if not provided"""
        if not sl or not tp1:
            return None
        
        if action == 'BUY':
            # Entry should be between SL and TP1, closer to SL
            return sl + (tp1 - sl) * 0.1
        else:  # SELL
            # Entry should be between TP1 and SL, closer to SL  
            return sl - (sl - tp1) * 0.1
    
    def _validate_required_fields(self, data: dict) -> bool:
        """Check if required fields exist"""
        required = ['symbol', 'action', 'sl', 'tp1']
        return all(field in data and data[field] is not None for field in required)
    
    def _normalize_data(self, data: dict) -> dict:
        """Normalize parsed data"""
        try:
            symbol = self.SYMBOL_MAP.get(str(data.get('symbol', '')).upper(), 'XAUUSD')
            action = str(data.get('action', '')).upper()
            
            return {
                'symbol': symbol,
                'action': action,
                'entry_min': float(data.get('entry_min', 0)),
                'entry_max': float(data.get('entry_max', data.get('entry_min', 0))),
                'sl': float(data.get('sl', 0)),
                'tp1': float(data.get('tp1', 0)),
                'tp2': float(data.get('tp2')) if data.get('tp2') else None
            }
        except (ValueError, TypeError) as e:
            logger.error(f"Data normalization error: {e}")
            return data
    
    def _validate_signal_logic(self, signal: dict) -> bool:
        """Validate signal makes logical sense"""
        try:
            entry = signal.get('entry_min', 0)
            sl = signal.get('sl', 0)
            tp1 = signal.get('tp1', 0)
            action = signal.get('action', '')
            
            # Check all prices are positive
            if not all(x > 0 for x in [entry, sl, tp1]):
                return False
            
            # Check price logic based on action
            if action == 'BUY':
                return sl < entry < tp1
            elif action == 'SELL':
                return tp1 < entry < sl
            
            return False
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False

# Test with your actual signal
if __name__ == "__main__":
    # Test signal from your log
    test_message = """**XAUUSD sell now 3370.54-3371.1400000000003**        
Sl: 3371.84
TP1: 3369.65
TP2: 3368.15
TP3: 3366.65"""
    
    print("Testing with your actual signal:")
    print(f"Message: {test_message}")
    print()
    
    # Test with AI (if available)
    try:
        parser_ai = SignalParser(use_ai=True)
        result_ai = parser_ai.parse_signal(test_message)
        print(f"AI Result: {result_ai}")
    except Exception as e:
        print(f"AI parsing failed: {e}")
    
    # Test with regex
    parser_regex = SignalParser(use_ai=False)
    result_regex = parser_regex.parse_signal(test_message)
    print(f"Regex Result: {result_regex}")
    
    # Test static method (for backward compatibility)
    result_static = SignalParser.parse_signal_static(test_message)
    print(f"Static Result: {result_static}")