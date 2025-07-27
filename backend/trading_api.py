import MetaTrader5 as mt5
import logging
from typing import Dict, Optional, Tuple
import asyncio
from config import MT5_SERVER, MT5_LOGIN, MT5_PASSWORD, DEFAULT_LOT_SIZE, MAX_SLIPPAGE, CHANNEL_NAMES, MONITORED_CHANNELS

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
        logging.FileHandler('../logs/trading_api.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TradingAPI:
    VOLATILITY_SYMBOLS = ['BOOM500', 'CRASH500']
    MAX_COMMENT_LENGTH = 32  # MT5 typically has a limit on comment length
    FULL_MARGIN_CHANNELS = ['Tau Core']  
    
    def __init__(self):
        self.connected = False
        self.last_position_id = None
        self.full_margin_enabled = True

    def _normalize_symbol(self, symbol: str) -> str:
        """Convert Gold → XAUUSD, handle Boom/Crash variants"""
        symbol = symbol.upper().strip()
        if 'GOLD' in symbol:
            return 'XAUUSD'
        elif 'BOOM' in symbol:
            return 'BOOM500'
        elif 'CRASH' in symbol:
            return 'CRASH500'
        return symbol

    def _sanitize_comment(self, comment: str) -> str:
        """Ensure comment meets MT5 requirements"""
        # Remove any non-ASCII characters
        comment = comment.encode('ascii', 'ignore').decode('ascii')
        # Trim to maximum allowed length
        return comment[:self.MAX_COMMENT_LENGTH]

    async def connect(self) -> bool:
        """Establish connection to MT5"""
        try:
            if not mt5.initialize():
                logger.error(f"MT5 initialization failed: {mt5.last_error()}")
                return False
                
            authorized = mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER)
            if not authorized:
                logger.error(f"Login failed: {mt5.last_error()}")
                mt5.shutdown()
                return False
                
            self.connected = True
            logger.info("Connected to MT5")
            return True
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            return False

    async def execute_trade(self, signal: Dict, channel_name: str = None) -> Tuple[bool, str]:
        """Execute trade with comprehensive error handling"""
        symbol = None
        try:
            # Validate connection
            if not self.connected and not await self.connect():
                return False, "MT5 connection failed"

            # Prepare symbol
            symbol = self._normalize_symbol(signal['symbol'])
            if not await self._validate_symbol(symbol):
                return False, f"Invalid symbol: {signal['symbol']}"

            # Get current market prices
            price_info = await self._get_current_prices(symbol, signal['action'])
            if not price_info:
                return False, "Failed to get market prices"

            # Calculate entry price
            entry_price = self._calculate_entry(
                signal.get('entry_min'),
                signal.get('entry_max'),
                price_info,
                signal['action']
            )

            # Validate stops
            if not await self._validate_stops(symbol, entry_price, signal['sl'], signal['tp1']):
                return False, "Invalid stop levels"

            # Check if this is a full margin channel
            use_full_margin = self.full_margin_enabled and channel_name in self.FULL_MARGIN_CHANNELS
            
            if use_full_margin:
                return await self._execute_full_margin_trades(symbol, signal, entry_price, channel_name)
            else:
                return await self._execute_single_trade(symbol, signal, entry_price)

        except Exception as e:
            error_msg = f"Trade execution error for {symbol if symbol else 'unknown symbol'}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    async def _execute_full_margin_trades(self, symbol: str, signal: Dict, entry_price: float, channel_name: str) -> Tuple[bool, str]:
        """Execute trades using full margin until no funds left"""
        results = []
        total_lots = 0
        last_ticket = None
        
        while True:
            # Get account balance to check available margin
            balance = mt5.account_info().balance
            margin_required = await self._calculate_margin_required(symbol, DEFAULT_LOT_SIZE)
            
            if margin_required > balance:
                if not results:
                    return False, "Insufficient margin for initial trade"
                break  # No more margin available
                
            # Execute single trade
            success, result = await self._execute_single_trade(symbol, signal, entry_price)
            
            if not success:
                if not results:
                    return False, result  # First trade failed
                break  # Subsequent trade failed
            
            results.append(result)
            total_lots += DEFAULT_LOT_SIZE
            last_ticket = result.split(":")[-1].strip() if ":" in result else None
            
            # Small delay between trades
            await asyncio.sleep(0.5)
        
        if not results:
            return False, "No trades executed with full margin"
            
        return True, f"Executed {len(results)} trades ({total_lots} lots) from {channel_name}. Last ticket: {last_ticket}"

    async def _execute_single_trade(self, symbol: str, signal: Dict, entry_price: float) -> Tuple[bool, str]:
        """Execute a single trade with standard lot size"""
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": DEFAULT_LOT_SIZE,
            "type": mt5.ORDER_TYPE_BUY if signal['action'].upper() == 'BUY' else mt5.ORDER_TYPE_SELL,
            "price": entry_price,
            "sl": signal['sl'],
            "tp": signal['tp1'],
            "deviation": self._calculate_deviation(symbol),
            "magic": 123456,
            "comment": "Tau Core System",
            "type_time": mt5.ORDER_TIME_GTC,
        }

        success, result = await self._send_trade(request)
        if not success:
            return False, result

        await asyncio.sleep(1)  # Give MT5 time to process
        if not await self.verify_position(result.order):
            return False, "Trade appeared successful but position not found"

        return True, f"Trade executed successfully. Ticket: {result.order}"

    async def _calculate_margin_required(self, symbol: str, volume: float) -> float:
        """Calculate margin required for a trade"""
        try:
            margin = mt5.order_calc_margin(
                mt5.ORDER_TYPE_BUY if volume > 0 else mt5.ORDER_TYPE_SELL,
                symbol,
                volume,
                mt5.symbol_info(symbol).ask if volume > 0 else mt5.symbol_info(symbol).bid
            )
            return margin if margin != None else float('inf')
        except Exception as e:
            logger.error(f"Margin calculation error: {str(e)}")
            return float('inf')

    def _calculate_deviation(self, symbol: str) -> int:
        """Calculate appropriate slippage tolerance"""
        base_deviation = MAX_SLIPPAGE
        if symbol in self.VOLATILITY_SYMBOLS:
            return base_deviation * 10
        return base_deviation

    async def _validate_symbol(self, symbol: str) -> bool:
        """Check if symbol exists and is visible"""
        try:
            if not mt5.symbol_select(symbol, True):
                logger.error(f"Symbol {symbol} not available: {mt5.last_error()}")
                return False
            return True
        except Exception as e:
            logger.error(f"Symbol validation error: {str(e)}")
            return False

    def _calculate_entry(self, entry_min: float, entry_max: float, prices: Dict, action: str) -> float:
        """Calculate optimal entry price"""
        if entry_min and entry_max:
            return (entry_min + entry_max) / 2
        return prices['ask'] if action.upper() == 'BUY' else prices['bid']

    async def _get_current_prices(self, symbol: str, action: str) -> Optional[Dict]:
        """Get current market prices with validation"""
        try:
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                logger.error(f"No tick data for {symbol}: {mt5.last_error()}")
                return None
                
            return {
                'ask': tick.ask,
                'bid': tick.bid,
                'spread': tick.ask - tick.bid
            }
        except Exception as e:
            logger.error(f"Price check error: {str(e)}")
            return None

    async def _validate_stops(self, symbol: str, price: float, sl: float, tp: float) -> bool:
        """Validate stop levels against broker requirements"""
        try:
            point = mt5.symbol_info(symbol).point
            min_distance = 10 * point
            return True
        except Exception as e:
            logger.error(f"Stop validation error: {str(e)}")
            return False

    async def _send_trade(self, request: Dict) -> Tuple[bool, any]:
        """Execute trade with multiple filling mode fallbacks"""
        try:
            symbol_info = mt5.symbol_info(request['symbol'])
            if not symbol_info:
                return False, "Cannot get symbol info"
            
            # Log the request for debugging
            logger.info(f"Sending trade request: {request}")
            
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                return True, result
                
            error_msg = result.comment if result else str(mt5.last_error())
            logger.warning(f"Trade failed: {error_msg}")
            return False, error_msg
        except Exception as e:
            logger.error(f"Trade execution exception: {str(e)}")
            return False, str(e)

    async def verify_position(self, position_id: int) -> bool:
        """Verify a position actually exists"""
        try:
            positions = mt5.positions_get(ticket=position_id)
            return len(positions) > 0
        except Exception as e:
            logger.error(f"Position verification error: {str(e)}")
            return False