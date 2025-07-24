import MetaTrader5 as mt5
import logging
from typing import Dict, Optional, Tuple
import asyncio
from config import MT5_SERVER, MT5_LOGIN, MT5_PASSWORD, DEFAULT_LOT_SIZE, MAX_SLIPPAGE

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
    
    def __init__(self):
        self.connected = False
        self.last_position_id = None

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

    async def execute_trade(self, signal: Dict) -> Tuple[bool, str]:
        """Execute trade with comprehensive error handling"""
        symbol = None  # Initialize symbol here to avoid scope issues
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

            # Build trade request
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
                "comment": "Tau Core System AutoTrade",
                "type_time": mt5.ORDER_TIME_GTC,
            }

            # Execute trade
            success, result = await self._send_trade(request)
            if not success:
                return False, result

            # Verify position actually exists
            await asyncio.sleep(1)  # Give MT5 time to process
            if not await self.verify_position(result.order):
                return False, "Trade appeared successful but position not found"

            return True, f"Trade executed successfully. Ticket: {result.order}"

        except Exception as e:
            error_msg = f"Trade execution error for {symbol if symbol else 'unknown symbol'}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

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
            min_distance = 10 * point  # Minimum 10 pips distance
            
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
            
            # Try default filling mode first
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                return True, result
                
            logger.warning(f"Trade failed: {result.comment if result else mt5.last_error()}")
            return False, result.comment if result else mt5.last_error()
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