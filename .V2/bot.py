import asyncio
import logging
import os
import re
import pandas as pd
import MetaTrader5 as mt5
from telethon import TelegramClient, events
from datetime import datetime, timedelta
import json
import csv
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class TradingSignal:
    channel_name: str
    pair: str
    action: str  # BUY or SELL
    entry_price: float
    stop_loss: float
    take_profit: List[float]
    timestamp: datetime
    raw_message: str
    confidence: float = 0.0

@dataclass
class TradeResult:
    signal: TradingSignal
    ticket: int
    open_time: datetime
    close_time: Optional[datetime]
    open_price: float
    close_price: Optional[float]
    profit: Optional[float]
    status: str  # OPEN, CLOSED, FAILED
    volume: float

class TelegramSignalParser:
    def __init__(self):
        self.signal_patterns = {
            'buy_sell': r'(?:^|\s)(BUY|SELL)\s*([A-Z]{6})',
            'entry': r'(?:ENTRY|ENTER|EP)[:\s]*([0-9]*\.?[0-9]+)',
            'stop_loss': r'(?:SL|STOP\s*LOSS|STOPLOSS)[:\s]*([0-9]*\.?[0-9]+)',
            'take_profit': r'(?:TP|TAKE\s*PROFIT|TARGET)[:\s]*([0-9]*\.?[0-9]+)',
            'multiple_tp': r'(?:TP\s*[1-9]|TARGET\s*[1-9])[:\s]*([0-9]*\.?[0-9]+)'
        }
        
    def parse_signal(self, message: str, channel_name: str) -> Optional[TradingSignal]:
        """Parse a trading signal from telegram message"""
        message = message.upper().replace('\n', ' ')
        
        # Extract action and pair
        buy_sell_match = re.search(self.signal_patterns['buy_sell'], message)
        if not buy_sell_match:
            return None
            
        action = buy_sell_match.group(1)
        pair = buy_sell_match.group(2)
        
        # Only process our target pairs
        if pair not in ['EURUSD', 'GBPUSD', 'XAUUSD']:
            return None
            
        # Extract entry price
        entry_match = re.search(self.signal_patterns['entry'], message)
        if not entry_match:
            return None
        entry_price = float(entry_match.group(1))
        
        # Extract stop loss
        sl_match = re.search(self.signal_patterns['stop_loss'], message)
        if not sl_match:
            return None
        stop_loss = float(sl_match.group(1))
        
        # Extract take profits
        tp_matches = re.findall(self.signal_patterns['take_profit'], message)
        multiple_tp_matches = re.findall(self.signal_patterns['multiple_tp'], message)
        
        take_profits = []
        for match in tp_matches + multiple_tp_matches:
            try:
                tp_value = float(match)
                if tp_value not in take_profits:
                    take_profits.append(tp_value)
            except ValueError:
                continue
                
        if not take_profits:
            return None
            
        # Sort take profits
        take_profits.sort()
        if action == 'SELL':
            take_profits.sort(reverse=True)
            
        return TradingSignal(
            channel_name=channel_name,
            pair=pair,
            action=action,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profits,
            timestamp=datetime.now(),
            raw_message=message,
            confidence=self._calculate_confidence(message)
        )
    
    def _calculate_confidence(self, message: str) -> float:
        """Calculate signal confidence based on message quality"""
        confidence = 0.5
        
        # Boost confidence for messages with multiple TPs
        tp_count = len(re.findall(r'TP\s*[1-9]', message))
        confidence += min(tp_count * 0.1, 0.3)
        
        # Boost for channels with track record
        if any(keyword in message for keyword in ['VERIFIED', 'CONFIRMED', 'HIGH PROBABILITY']):
            confidence += 0.2
            
        return min(confidence, 1.0)

class MT5TradingEngine:
    def __init__(self):
        self.account = int(os.getenv('MT5_LOGIN'))
        self.password = os.getenv('MT5_PASSWORD')
        self.server = os.getenv('MT5_SERVER')
        self.connected = False
        self.base_volume = float(os.getenv('BASE_VOLUME', '0.01'))
        
    def connect(self) -> bool:
        """Connect to MT5"""
        try:
            if not mt5.initialize():
                logger.error("MT5 initialization failed")
                return False
                
            if not mt5.login(self.account, self.password, self.server):
                logger.error(f"MT5 login failed: {mt5.last_error()}")
                return False
                
            self.connected = True
            logger.info("Successfully connected to MT5")
            return True
            
        except Exception as e:
            logger.error(f"MT5 connection error: {e}")
            return False
    
    def execute_trade(self, signal: TradingSignal) -> Optional[TradeResult]:
        """Execute a trade based on signal"""
        if not self.connected:
            logger.error("MT5 not connected")
            return None
            
        try:
            symbol = signal.pair
            
            # Get symbol info
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logger.error(f"Symbol {symbol} not found")
                return None
                
            if not symbol_info.visible:
                if not mt5.symbol_select(symbol, True):
                    logger.error(f"Failed to select symbol {symbol}")
                    return None
            
            # Prepare trade request
            action_type = mt5.ORDER_TYPE_BUY if signal.action == 'BUY' else mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(symbol).ask if signal.action == 'BUY' else mt5.symbol_info_tick(symbol).bid
            
            # Calculate volume based on risk
            volume = self._calculate_volume(signal, symbol_info)
            
            # Use first TP only (as requested)
            tp_price = signal.take_profit[0] if signal.take_profit else None
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": action_type,
                "price": price,
                "sl": signal.stop_loss,
                "tp": tp_price,
                "deviation": 20,
                "magic": 234000,
                "comment": f"TG_Signal_{signal.channel_name}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"Trade failed: {result.retcode}")
                return TradeResult(
                    signal=signal,
                    ticket=0,
                    open_time=datetime.now(),
                    close_time=None,
                    open_price=price,
                    close_price=None,
                    profit=None,
                    status="FAILED",
                    volume=volume
                )
            
            logger.info(f"Trade executed successfully: Ticket {result.order}")
            
            return TradeResult(
                signal=signal,
                ticket=result.order,
                open_time=datetime.now(),
                close_time=None,
                open_price=result.price,
                close_price=None,
                profit=None,
                status="OPEN",
                volume=result.volume
            )
            
        except Exception as e:
            logger.error(f"Trade execution error: {e}")
            return None
    
    def _calculate_volume(self, signal: TradingSignal, symbol_info) -> float:
        """Calculate position volume based on risk management"""
        account_info = mt5.account_info()
        if not account_info:
            return self.base_volume
            
        # Risk 2% of account per trade
        risk_amount = account_info.balance * 0.02
        
        # Calculate pip value and risk
        pip_size = symbol_info.point * 10 if 'JPY' in signal.pair else symbol_info.point
        stop_loss_pips = abs(signal.entry_price - signal.stop_loss) / pip_size
        
        if stop_loss_pips > 0:
            volume = risk_amount / (stop_loss_pips * symbol_info.trade_contract_size * pip_size)
            volume = max(symbol_info.volume_min, min(volume, symbol_info.volume_max))
            return round(volume, 2)
        
        return self.base_volume
    
    def get_account_info(self) -> Dict:
        """Get current account information"""
        if not self.connected:
            return {}
            
        account_info = mt5.account_info()
        if account_info:
            return {
                'balance': account_info.balance,
                'equity': account_info.equity,
                'profit': account_info.profit,
                'margin': account_info.margin,
                'free_margin': account_info.margin_free
            }
        return {}
    
    def update_trade_status(self, trade_result: TradeResult) -> TradeResult:
        """Update trade status and profit"""
        if trade_result.status == "FAILED" or not self.connected:
            return trade_result
            
        try:
            positions = mt5.positions_get(ticket=trade_result.ticket)
            if positions:
                # Trade is still open
                position = positions[0]
                trade_result.profit = position.profit
                return trade_result
            else:
                # Trade is closed, get from history
                history = mt5.history_deals_get(ticket=trade_result.ticket)
                if history and len(history) >= 2:
                    close_deal = history[-1]
                    trade_result.close_time = datetime.fromtimestamp(close_deal.time)
                    trade_result.close_price = close_deal.price
                    trade_result.profit = close_deal.profit
                    trade_result.status = "CLOSED"
                    
        except Exception as e:
            logger.error(f"Error updating trade status: {e}")
            
        return trade_result

class TradingReporter:
    def __init__(self, output_dir: str = "reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
    def log_signal(self, signal: TradingSignal, trade_result: Optional[TradeResult] = None):
        """Log signal to CSV"""
        csv_file = self.output_dir / "signals_log.csv"
        
        data = {
            'timestamp': signal.timestamp,
            'channel': signal.channel_name,
            'pair': signal.pair,
            'action': signal.action,
            'entry_price': signal.entry_price,
            'stop_loss': signal.stop_loss,
            'take_profit': ','.join(map(str, signal.take_profit)),
            'confidence': signal.confidence,
            'trade_executed': trade_result is not None,
            'ticket': trade_result.ticket if trade_result else 0,
            'status': trade_result.status if trade_result else 'NO_TRADE',
            'profit': trade_result.profit if trade_result else 0
        }
        
        # Write to CSV
        file_exists = csv_file.exists()
        with open(csv_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=data.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(data)
    
    def generate_performance_report(self, trades: List[TradeResult], account_info: Dict):
        """Generate comprehensive performance report"""
        if not trades:
            return
            
        df = pd.DataFrame([{
            'channel': trade.signal.channel_name,
            'pair': trade.signal.pair,
            'action': trade.signal.action,
            'open_time': trade.open_time,
            'close_time': trade.close_time,
            'profit': trade.profit or 0,
            'status': trade.status,
            'volume': trade.volume
        } for trade in trades])
        
        # Performance metrics
        total_trades = len(df)
        winning_trades = len(df[df['profit'] > 0])
        losing_trades = len(df[df['profit'] < 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        total_profit = df['profit'].sum()
        avg_profit = df['profit'].mean()
        
        # Generate report
        report = f"""
TRADING PERFORMANCE REPORT
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

ACCOUNT SUMMARY:
Balance: ${account_info.get('balance', 0):.2f}
Equity: ${account_info.get('equity', 0):.2f}
Profit: ${account_info.get('profit', 0):.2f}
Free Margin: ${account_info.get('free_margin', 0):.2f}

TRADING STATISTICS:
Total Trades: {total_trades}
Winning Trades: {winning_trades}
Losing Trades: {losing_trades}
Win Rate: {win_rate:.2f}%
Total Profit: ${total_profit:.2f}
Average Profit per Trade: ${avg_profit:.2f}

PERFORMANCE BY CHANNEL:
"""
        
        # Channel performance
        channel_stats = df.groupby('channel').agg({
            'profit': ['sum', 'mean', 'count'],
            'status': lambda x: (x == 'CLOSED').sum()
        }).round(2)
        
        for channel in channel_stats.index:
            report += f"\n{channel}:\n"
            report += f"  Total Profit: ${channel_stats.loc[channel, ('profit', 'sum')]:.2f}\n"
            report += f"  Avg Profit: ${channel_stats.loc[channel, ('profit', 'mean')]:.2f}\n"
            report += f"  Total Trades: {channel_stats.loc[channel, ('profit', 'count')]}\n"
        
        # Save report
        with open(self.output_dir / "performance_report.txt", 'w') as f:
            f.write(report)
            
        # Generate charts
        self._generate_charts(df, account_info)
        
        logger.info(f"Performance report generated in {self.output_dir}")
    
    def _generate_charts(self, df: pd.DataFrame, account_info: Dict):
        """Generate performance charts"""
        if df.empty:
            return
            
        plt.style.use('seaborn-v0_8')
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('Trading Performance Dashboard', fontsize=16)
        
        # Profit by channel
        channel_profit = df.groupby('channel')['profit'].sum()
        axes[0, 0].bar(channel_profit.index, channel_profit.values)
        axes[0, 0].set_title('Profit by Channel')
        axes[0, 0].set_ylabel('Profit ($)')
        axes[0, 0].tick_params(axis='x', rotation=45)
        
        # Profit distribution
        axes[0, 1].hist(df['profit'], bins=20, alpha=0.7)
        axes[0, 1].set_title('Profit Distribution')
        axes[0, 1].set_xlabel('Profit ($)')
        axes[0, 1].set_ylabel('Frequency')
        
        # Performance by pair
        pair_stats = df.groupby('pair')['profit'].agg(['sum', 'count'])
        axes[1, 0].bar(pair_stats.index, pair_stats['sum'])
        axes[1, 0].set_title('Profit by Currency Pair')
        axes[1, 0].set_ylabel('Total Profit ($)')
        
        # Cumulative profit over time
        df_sorted = df.sort_values('open_time')
        df_sorted['cumulative_profit'] = df_sorted['profit'].cumsum()
        axes[1, 1].plot(df_sorted['open_time'], df_sorted['cumulative_profit'])
        axes[1, 1].set_title('Cumulative Profit Over Time')
        axes[1, 1].set_ylabel('Cumulative Profit ($)')
        axes[1, 1].tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'performance_charts.png', dpi=300, bbox_inches='tight')
        plt.close()

class TelegramTradingBot:
    def __init__(self):
        self.api_id = int(os.getenv('TELEGRAM_API_ID'))
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        self.phone = os.getenv('TELEGRAM_PHONE')
        
        self.client = TelegramClient('trading_session', self.api_id, self.api_hash)
        self.parser = TelegramSignalParser()
        self.trading_engine = MT5TradingEngine()
        self.reporter = TradingReporter()
        
        self.active_trades: List[TradeResult] = []
        self.processed_signals: List[TradingSignal] = []
        self.channel_status: Dict[str, bool] = {}
        
        # Target channels
        self.target_channels = [
            '1000pip_builder',
            'united_signals',
            'forexfactorysignals01',
            'eurusdforexsignalss',
            'gbpusdforexsignals02',
            'signalprovider_free',
            'topsignals_fx',
            'prosignals_fx',
            'unitedkings_signals',
            'gold_eur_gbp_signals'
        ]
        
        self.is_trading = True
        self.max_concurrent_trades = 2  # Max 2 trades as requested
        
    async def start(self):
        """Start the trading bot"""
        logger.info("Starting Telegram Trading Bot...")
        
        # Connect to MT5
        if not self.trading_engine.connect():
            logger.error("Failed to connect to MT5. Exiting...")
            return
            
        # Connect to Telegram
        await self.client.start(phone=self.phone)
        logger.info("Connected to Telegram")
        
        # Setup event handlers
        @self.client.on(events.NewMessage)
        async def handle_new_message(event):
            await self.process_message(event)
        
        # Start monitoring loop
        await self.monitoring_loop()
    
    async def process_message(self, event):
        """Process incoming telegram messages"""
        try:
            sender = await event.get_sender()
            if not sender or not hasattr(sender, 'username'):
                return
                
            channel_name = sender.username
            if channel_name not in self.target_channels:
                return
                
            message_text = event.message.message
            if not message_text:
                return
                
            # Parse signal
            signal = self.parser.parse_signal(message_text, channel_name)
            if not signal:
                return
                
            logger.info(f"Signal received from {channel_name}: {signal.pair} {signal.action}")
            
            # Check if we should trade
            if not self.should_execute_trade():
                logger.info("Trade execution paused or max trades reached")
                self.reporter.log_signal(signal, None)
                return
                
            # Execute trade
            trade_result = self.trading_engine.execute_trade(signal)
            if trade_result:
                self.active_trades.append(trade_result)
                logger.info(f"Trade executed: Ticket {trade_result.ticket}")
            
            # Log signal and result
            self.reporter.log_signal(signal, trade_result)
            self.processed_signals.append(signal)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def should_execute_trade(self) -> bool:
        """Check if we should execute a trade"""
        if not self.is_trading:
            return False
            
        # Count open trades
        open_trades = len([t for t in self.active_trades if t.status == "OPEN"])
        return open_trades < self.max_concurrent_trades
    
    async def monitoring_loop(self):
        """Main monitoring and reporting loop"""
        logger.info("Starting monitoring loop...")
        
        while True:
            try:
                # Update trade statuses
                for i, trade in enumerate(self.active_trades):
                    if trade.status == "OPEN":
                        self.active_trades[i] = self.trading_engine.update_trade_status(trade)
                
                # Generate reports every hour
                if datetime.now().minute == 0:
                    account_info = self.trading_engine.get_account_info()
                    self.reporter.generate_performance_report(self.active_trades, account_info)
                    
                    # Log status
                    self.log_system_status()
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)
    
    def log_system_status(self):
        """Log current system status"""
        open_trades = len([t for t in self.active_trades if t.status == "OPEN"])
        total_signals = len(self.processed_signals)
        
        status = f"""
SYSTEM STATUS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Trading Active: {self.is_trading}
Open Trades: {open_trades}/{self.max_concurrent_trades}
Total Signals Processed: {total_signals}
Channels Monitored: {len(self.target_channels)}
MT5 Connected: {self.trading_engine.connected}
"""
        
        logger.info(status)
        
        # Save status to file
        with open("system_status.txt", "w") as f:
            f.write(status)

# CLI Interface
def main():
    """Main function to run the trading bot"""
    print("Telegram Trading Bot")
    print("===================")
    
    # Check environment variables
    required_vars = [
        'TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_PHONE',
        'MT5_LOGIN', 'MT5_PASSWORD', 'MT5_SERVER'
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"Missing environment variables: {', '.join(missing_vars)}")
        print("Please set these in your .env file")
        return
    
    # Start the bot
    bot = TelegramTradingBot()
    
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Bot error: {e}")

if __name__ == "__main__":
    main()