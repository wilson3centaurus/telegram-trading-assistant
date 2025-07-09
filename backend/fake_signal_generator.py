# This file is only used for testing real signals, it generates fake signals for testing purposes.

import random
import asyncio
import logging
from datetime import datetime
import MetaTrader5 as mt5
from config import MT5_SERVER, MT5_LOGIN, MT5_PASSWORD

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('signal_generator.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('SignalGenerator')

class SignalGenerator:
    def __init__(self):
        self.symbol = "XAUUSD"
        self.min_lot_size = 0.01
        self.max_lot_size = 1.0
        self.valid_actions = ["BUY", "SELL"]
        self.tp_count_range = (1, 4)  # Between 1-4 TP levels
        self.output_file = "generated_signals.txt"
        self.min_stop_distance = 0.5  # Minimum 50 pips for XAUUSD
        
    async def connect_mt5(self):
        if not mt5.initialize():
            logger.error("MT5 initialization failed")
            return False
            
        if not mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER):
            logger.error(f"Login failed: {mt5.last_error()}")
            return False
            
        logger.info("Connected to MT5 for market data")
        return True

    def get_current_price(self):
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            logger.error("Failed to get current price")
            return None, None
        return tick.ask, tick.bid

    def generate_valid_stops(self, action, current_price):
        """Generate stops that comply with broker rules"""
        point = mt5.symbol_info(self.symbol).point
        min_distance = self.min_stop_distance
        
        if action == "BUY":
            sl = current_price - min_distance * random.uniform(1.5, 3)
            tp = current_price + min_distance * random.uniform(1.5, 3)
        else:  # SELL
            sl = current_price + min_distance * random.uniform(1.5, 3)
            tp = current_price - min_distance * random.uniform(1.5, 3)
            
        return round(sl, 2), round(tp, 2)

    def generate_signal_text(self, action, entry, sl, tp_levels):
        """Create realistically formatted signal text with variations"""
        templates = [
            f"{action} {self.symbol} {entry-0.5}-{entry+0.5}\n\nSL: {sl}\n\n" + "\n".join([f"TP: {tp}" for tp in tp_levels]),
            f"**{self.symbol} {action.lower()} now {entry-0.3}-{entry+0.3}**\n\nSl: {sl}\n\n" + "\n".join([f"TP{i+1}: {tp}" for i, tp in enumerate(tp_levels)]),
            f"{action} Signal for {self.symbol}\nEntry Zone: {entry-0.7}-{entry+0.7}\nStop Loss: {sl}\n" + "\n".join([f"Take Profit {i+1}: {tp}" for i, tp in enumerate(tp_levels)]),
            f"{action} {self.symbol}\nEntry: {entry-0.2}-{entry+0.2}\n\nSL: {sl}\n\n" + "\n".join([f"TP{i+1}: {tp}" for i, tp in enumerate(tp_levels)])
        ]
        
        return random.choice(templates)

    async def generate_and_save_signal(self):
        if not await self.connect_mt5():
            return False

        current_ask, current_bid = self.get_current_price()
        if current_ask is None:
            mt5.shutdown()
            return False

        action = random.choice(self.valid_actions)
        entry_price = current_ask if action == "BUY" else current_bid
        sl, tp1 = self.generate_valid_stops(action, entry_price)
        
        # Generate multiple TP levels
        tp_count = random.randint(*self.tp_count_range)
        tp_levels = [round(tp1 + (i * 1.5), 2) if action == "BUY" else round(tp1 - (i * 1.5), 2) 
                    for i in range(tp_count)]
        
        signal_text = self.generate_signal_text(action, entry_price, sl, tp_levels)
        
        # Save to file with timestamp
        with open(self.output_file, 'a', encoding='utf-8') as f:
            f.write(f"\n\n=== New Signal @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            f.write(signal_text)
            f.write("\n======================")
        
        logger.info(f"Generated new signal:\n{signal_text}")
        mt5.shutdown()
        return True

async def main():
    generator = SignalGenerator()
    while True:
        await generator.generate_and_save_signal()
        await asyncio.sleep(5)  # Generate every 5 seconds

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Fake Signal generator stopped by user")