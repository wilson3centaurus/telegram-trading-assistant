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
        """Robust regex parsing that handles all signal formats"""
        try:
            clean_msg = self._clean_message(message)
            logger.info(f"Parsing with regex: {clean_msg[:100]}...")
            
            # Extract symbol (with more flexible matching)
            symbol = self._extract_symbol(clean_msg)
            if not symbol:
                logger.warning("No symbol found")
                return None

            # Extract action (more flexible patterns)
            action = self._extract_action(clean_msg)
            if not action:
                logger.warning("No action found")
                return None

            # Extract entry prices (handles all formats)
            entry_min, entry_max = self._extract_entry_prices(clean_msg)
            
            # Extract stop loss (with better patterns)
            sl = self._extract_stop_loss(clean_msg)
            
            # Extract take profits (limit to first 2, handle OPEN/OPN)
            tps = self._extract_take_profits(clean_msg)
            
            # Calculate defaults if missing
            if not sl:
                if entry_min:
                    sl = entry_min - (5 if action == 'BUY' else -5)  # 5 USD SL
                else:
                    logger.warning("No SL found and cannot calculate")
                    return None
                    
            if not tps:
                if entry_min:
                    tps = [entry_min + (10 if action == 'BUY' else -10)]  # 10 USD TP
                else:
                    logger.warning("No TP found and cannot calculate")
                    return None
                    
            # If no entry prices, calculate reasonable ones
            if not entry_min:
                if action == 'BUY':
                    entry_min = sl + 1.0
                    entry_max = entry_min + 3.0
                else:
                    entry_min = sl - 1.0
                    entry_max = entry_min - 3.0
                    
            # Process TPs (limit to first 2, replace OPEN with calculated)
            processed_tps = []
            for i, tp in enumerate(tps[:2]):  # Only take first two TPs
                if isinstance(tp, str) and 'OPEN' in tp.upper():
                    # Calculate 5 USD TP from entry
                    avg_entry = (entry_min + entry_max) / 2 if entry_max else entry_min
                    tp_value = avg_entry + (5 if action == 'BUY' else -5)
                    processed_tps.append(tp_value)
                else:
                    try:
                        processed_tps.append(float(tp))
                    except (ValueError, TypeError):
                        continue

            # Ensure we have at least one TP
            if not processed_tps:
                avg_entry = (entry_min + entry_max) / 2 if entry_max else entry_min
                processed_tps.append(avg_entry + (10 if action == 'BUY' else -10))

            signal = {
                'symbol': symbol,
                'action': action,
                'entry_min': min(entry_min, entry_max) if entry_max else entry_min,
                'entry_max': max(entry_min, entry_max) if entry_max else entry_min,
                'sl': sl,
                'tp1': processed_tps[0],
                'tp2': processed_tps[1] if len(processed_tps) > 1 else None
            }

            logger.info(f"Regex parsed successfully: {signal}")
            return signal
                
        except Exception as e:
            logger.error(f"Regex parsing error: {e}")
            return None

    def _extract_entry_prices(self, message: str) -> tuple:
        """Enhanced entry price extraction"""
        # Try different patterns in order of preference
        patterns = [
            # Zone patterns: "BUY ZONE : 3345-3342"
            r'(?:ZONE|RANGE|ENTRY)\s*[:@]?\s*(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)',
            # Standard range: "3345-3342"
            r'(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)',
            # After action: "BUY 3345" or "BUY NOW 3345"
            r'(?:BUY|SELL)\s+(?:NOW\s+)?(\d+\.?\d*)',
            # With @ symbol: "@3345" or "BUY @3345"
            r'@\s*(\d+\.?\d*)',
            # After symbol: "XAUUSD 3345"
            r'(?:XAUUSD|GOLD)\s+(\d+\.?\d*)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                try:
                    if len(match.groups()) > 1:
                        price1 = float(match.group(1))
                        price2 = float(match.group(2))
                        return min(price1, price2), max(price1, price2)
                    else:
                        price = float(match.group(1))
                        return price, price
                except ValueError:
                    continue
                    
        return None, None

    def _extract_take_profits(self, message: str) -> list:
        """Enhanced TP extraction with OPEN handling"""
        tp_patterns = [
            r'(?:TP|TAKE\s*PROFIT|TARGET)\s*\d?\s*[:@]?\s*(\d+\.?\d*|OPEN|OPN)',
            r'✅\s*(\d+\.?\d*)',  # TP with checkmark
            r'🎯\s*(\d+\.?\d*)'   # TP with target emoji
        ]
        
        tps = []
        for pattern in tp_patterns:
            matches = re.finditer(pattern, message, re.IGNORECASE)
            for match in matches:
                val = match.group(1).upper()
                if val in ['OPEN', 'OPN']:
                    tps.append('OPEN')
                else:
                    try:
                        tps.append(float(val))
                    except ValueError:
                        continue
        
        # Remove duplicates and sort
        unique_tps = []
        seen = set()
        for tp in tps:
            if isinstance(tp, float) and tp not in seen:
                seen.add(tp)
                unique_tps.append(tp)
            elif isinstance(tp, str) and tp not in seen:
                seen.add(tp)
                unique_tps.append(tp)
        
        return sorted(unique_tps)

    def _extract_stop_loss(self, message: str) -> Optional[float]:
        """Enhanced SL extraction"""
        sl_patterns = [
            r'(?:SL|STOP\s*LOSS?|STOP|❌|🛑)\s*[:@]?\s*(\d+\.?\d*)',
            r'RISK\s*[:@]?\s*(\d+\.?\d*)',
            r'LOSS?\s*[:@]?\s*(\d+\.?\d*)'
        ]
        
        for pattern in sl_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
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
