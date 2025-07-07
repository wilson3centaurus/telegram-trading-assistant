import MetaTrader5 as mt5
import logging
from typing import Dict, Optional
from config import MT5_SERVER, MT5_LOGIN, MT5_PASSWORD, MT5_DEMO_ACCOUNT, DEFAULT_LOT_SIZE, MAX_SLIPPAGE

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('../logs/trading_api.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TradingAPI:
    def __init__(self):
        self.connected = False
        
    async def connect(self):
        if not mt5.initialize():
            logger.error("MT5 initialization failed")
            self.connected = False
            return False
            
        authorized = mt5.login(
            login=MT5_LOGIN,
            password=MT5_PASSWORD,
            server=MT5_SERVER
        )
        
        if not authorized:
            logger.error(f"MT5 login failed, error: {mt5.last_error()}")
            self.connected = False
            return False
            
        logger.info("Successfully connected to MT5")
        self.connected = True
        return True
        
    async def execute_trade(self, signal: Dict) -> bool:
        if not self.connected and not await self.connect():
            return False
            
        symbol = signal['symbol']
        action = signal['action']
        entry = (signal['entry_min'] + signal['entry_max']) / 2
        sl = signal['sl']
        tp1 = signal['tp1']
        tp2 = signal.get('tp2')
        
        # Prepare the trade request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": DEFAULT_LOT_SIZE,
            "type": mt5.ORDER_TYPE_BUY if action == 'BUY' else mt5.ORDER_TYPE_SELL,
            "price": entry,
            "sl": sl,
            "tp": tp1,
            "deviation": MAX_SLIPPAGE,
            "magic": 123456,
            "comment": "Auto-trade from Telegram signal",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        try:
            # Send the trade request
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"Trade failed, retcode={result.retcode}, error={result.comment}")
                return False
                
            logger.info(f"Trade executed successfully: {result}")
            
            # If TP2 exists, modify the trade to add TP2
            if tp2:
                position_id = result.order
                modify_request = {
                    "action": mt5.TRADE_ACTION_MODIFY,
                    "position": position_id,
                    "sl": sl,
                    "tp": tp2,
                }
                modify_result = mt5.order_send(modify_request)
                if modify_result.retcode != mt5.TRADE_RETCODE_DONE:
                    logger.warning(f"Failed to modify TP2, but trade is executed: {modify_result.comment}")
                else:
                    logger.info(f"Successfully modified TP2: {modify_result}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error executing trade: {str(e)}")
            return False