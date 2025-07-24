import asyncio
import logging
import pandas as pd
import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import csv
from pathlib import Path

# Third-party imports (install with pip)
from telethon import TelegramClient, events
import MetaTrader5 as mt5
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import seaborn as sns
from flask import Flask, render_template, jsonify, request
import plotly.graph_objs as go
import plotly.express as px
from plotly.utils import PlotlyJSONEncoder

# Load environment variables
load_dotenv()

@dataclass
class Signal:
    channel: str
    pair: str
    action: str  # BUY/SELL
    entry_price: float
    stop_loss: float
    take_profit: float
    timestamp: datetime
    processed: bool = False
    trade_id: Optional[int] = None
    result: Optional[str] = None  # WIN/LOSS/PENDING
    profit_loss: float = 0.0

@dataclass
class TradeResult:
    signal_id: str
    trade_id: int
    pair: str
    action: str
    entry_price: float
    exit_price: float
    profit_loss: float
    timestamp: datetime
    channel: str

class TelegramSignalBot:
    def __init__(self):
        # Telegram credentials from .env
        self.api_id = os.getenv('TELEGRAM_API_ID')
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        self.phone = os.getenv('TELEGRAM_PHONE')
        
        # MT5 credentials from .env
        self.mt5_login = int(os.getenv('MT5_LOGIN'))
        self.mt5_password = os.getenv('MT5_PASSWORD')
        self.mt5_server = os.getenv('MT5_SERVER')
        
        # Trading settings
        self.lot_size = float(os.getenv('LOT_SIZE', '0.01'))
        self.max_trades_per_channel = int(os.getenv('MAX_TRADES_PER_CHANNEL', '2'))
        
        # Channels to monitor
        self.channels = [
            '@forexfactorysignals01',
            '@eurusdforexsignalss',
            '@gbpusdforexsignals02',
            'United Signals',
            '1000pip Builder',
            'SignalProvider',
            'TopTradingSignals',
            'ProSignalsFX',
            'United Kings',
            'GOLD XAU/USD EUR/USD GBP/USD SIGNALS'
        ]
        
        self.target_pairs = ['EURUSD', 'GBPUSD', 'XAUUSD']
        
        # Data storage
        self.signals: List[Signal] = []
        self.trades: List[TradeResult] = []
        self.channel_stats = {}
        
        # Initialize logging
        self.setup_logging()
        
        # Initialize Telegram client
        self.client = TelegramClient('trading_session', self.api_id, self.api_hash)
        
        # Flask app for dashboard
        self.app = Flask(__name__)
        self.setup_routes()
        
    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('trading_bot.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def connect_mt5(self) -> bool:
        """Connect to MetaTrader 5"""
        try:
            if not mt5.initialize():
                self.logger.error(f"MT5 initialize failed: {mt5.last_error()}")
                return False
            
            authorized = mt5.login(self.mt5_login, password=self.mt5_password, server=self.mt5_server)
            if not authorized:
                self.logger.error(f"MT5 login failed: {mt5.last_error()}")
                return False
            
            self.logger.info("Successfully connected to MT5")
            return True
        except Exception as e:
            self.logger.error(f"MT5 connection error: {e}")
            return False

    def parse_signal(self, message: str, channel: str) -> Optional[Signal]:
        """Parse trading signal from message"""
        try:
            message = message.upper()
            
            # Check if message contains target pairs
            pair_found = None
            for pair in self.target_pairs:
                if pair in message:
                    pair_found = pair
                    break
            
            if not pair_found:
                return None
            
            # Extract action (BUY/SELL)
            action = None
            if 'BUY' in message:
                action = 'BUY'
            elif 'SELL' in message:
                action = 'SELL'
            
            if not action:
                return None
            
            # Extract prices using regex
            price_patterns = [
                r'ENTRY[:\s]*(\d+\.?\d*)',
                r'PRICE[:\s]*(\d+\.?\d*)',
                r'AT[:\s]*(\d+\.?\d*)',
                r'(\d+\.\d{4,5})'  # General price pattern
            ]
            
            sl_patterns = [
                r'SL[:\s]*(\d+\.?\d*)',
                r'STOP\s*LOSS[:\s]*(\d+\.?\d*)',
                r'STOPLOSS[:\s]*(\d+\.?\d*)'
            ]
            
            tp_patterns = [
                r'TP[:\s]*(\d+\.?\d*)',
                r'TAKE\s*PROFIT[:\s]*(\d+\.?\d*)',
                r'TAKEPROFIT[:\s]*(\d+\.?\d*)',
                r'TARGET[:\s]*(\d+\.?\d*)'
            ]
            
            # Extract entry price
            entry_price = None
            for pattern in price_patterns:
                match = re.search(pattern, message)
                if match:
                    entry_price = float(match.group(1))
                    break
            
            # Extract stop loss
            stop_loss = None
            for pattern in sl_patterns:
                match = re.search(pattern, message)
                if match:
                    stop_loss = float(match.group(1))
                    break
            
            # Extract take profit
            take_profit = None
            for pattern in tp_patterns:
                matches = re.findall(pattern, message)
                if matches:
                    take_profit = float(matches[0])  # Take first TP
                    break
            
            if entry_price and stop_loss and take_profit:
                return Signal(
                    channel=channel,
                    pair=pair_found,
                    action=action,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    timestamp=datetime.now()
                )
            
        except Exception as e:
            self.logger.error(f"Error parsing signal: {e}")
        
        return None

    def execute_trade(self, signal: Signal) -> Optional[int]:
        """Execute trade in MT5"""
        try:
            symbol = signal.pair
            action = mt5.ORDER_TYPE_BUY if signal.action == 'BUY' else mt5.ORDER_TYPE_SELL
            
            # Get current price
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                self.logger.error(f"Failed to get tick for {symbol}")
                return None
            
            current_price = tick.ask if signal.action == 'BUY' else tick.bid
            
            # Prepare trade request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": self.lot_size,
                "type": action,
                "price": current_price,
                "sl": signal.stop_loss,
                "tp": signal.take_profit,
                "deviation": 20,
                "magic": 234000,
                "comment": f"Signal from {signal.channel}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            # Send trade request
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                self.logger.error(f"Trade failed: {result.retcode}")
                return None
            
            self.logger.info(f"Trade executed: {symbol} {signal.action} at {current_price}")
            return result.order
            
        except Exception as e:
            self.logger.error(f"Error executing trade: {e}")
            return None

    def check_active_trades(self):
        """Check status of active trades"""
        try:
            positions = mt5.positions_get()
            if positions:
                for position in positions:
                    # Update trade results
                    for signal in self.signals:
                        if signal.trade_id == position.ticket:
                            signal.profit_loss = position.profit
                            if position.profit > 0:
                                signal.result = "WIN"
                            elif position.profit < 0:
                                signal.result = "LOSS"
                            else:
                                signal.result = "PENDING"
        except Exception as e:
            self.logger.error(f"Error checking trades: {e}")

    def save_to_csv(self):
        """Save signals and trades to CSV files"""
        try:
            # Save signals
            signals_data = []
            for signal in self.signals:
                signals_data.append({
                    'Date': signal.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'Channel': signal.channel,
                    'Pair': signal.pair,
                    'Action': signal.action,
                    'Entry Price': signal.entry_price,
                    'Stop Loss': signal.stop_loss,
                    'Take Profit': signal.take_profit,
                    'Trade ID': signal.trade_id,
                    'Result': signal.result,
                    'Profit/Loss': signal.profit_loss,
                    'Processed': signal.processed
                })
            
            df_signals = pd.DataFrame(signals_data)
            df_signals.to_csv('trading_signals.csv', index=False)
            
            # Save trades
            trades_data = []
            for trade in self.trades:
                trades_data.append(asdict(trade))
            
            df_trades = pd.DataFrame(trades_data)
            df_trades.to_csv('trading_results.csv', index=False)
            
            self.logger.info("Data saved to CSV files")
            
        except Exception as e:
            self.logger.error(f"Error saving to CSV: {e}")

    def generate_report(self):
        """Generate trading performance report"""
        try:
            if not self.signals:
                return
            
            # Create performance charts
            df = pd.DataFrame([asdict(signal) for signal in self.signals])
            
            # Channel performance
            plt.figure(figsize=(12, 8))
            
            plt.subplot(2, 2, 1)
            channel_performance = df.groupby('channel')['profit_loss'].sum()
            channel_performance.plot(kind='bar')
            plt.title('Profit/Loss by Channel')
            plt.xticks(rotation=45)
            
            plt.subplot(2, 2, 2)
            pair_performance = df.groupby('pair')['profit_loss'].sum()
            pair_performance.plot(kind='pie', autopct='%1.1f%%')
            plt.title('Profit Distribution by Pair')
            
            plt.subplot(2, 2, 3)
            df['date'] = pd.to_datetime(df['timestamp']).dt.date
            daily_pnl = df.groupby('date')['profit_loss'].sum().cumsum()
            daily_pnl.plot()
            plt.title('Cumulative P&L')
            plt.xticks(rotation=45)
            
            plt.subplot(2, 2, 4)
            win_rate = df[df['result'].isin(['WIN', 'LOSS'])].groupby('channel')['result'].apply(
                lambda x: (x == 'WIN').sum() / len(x) * 100
            )
            win_rate.plot(kind='bar')
            plt.title('Win Rate by Channel (%)')
            plt.xticks(rotation=45)
            
            plt.tight_layout()
            plt.savefig('trading_report.png', dpi=300, bbox_inches='tight')
            plt.close()
            
            self.logger.info("Trading report generated")
            
        except Exception as e:
            self.logger.error(f"Error generating report: {e}")

    def setup_routes(self):
        """Setup Flask routes for dashboard"""
        
        @self.app.route('/')
        def dashboard():
            return render_template('dashboard.html')
        
        @self.app.route('/api/stats')
        def get_stats():
            try:
                account_info = mt5.account_info()
                
                stats = {
                    'account_balance': account_info.balance if account_info else 0,
                    'account_equity': account_info.equity if account_info else 0,
                    'total_signals': len(self.signals),
                    'active_trades': len([s for s in self.signals if s.result == 'PENDING']),
                    'total_profit': sum([s.profit_loss for s in self.signals]),
                    'win_rate': self.calculate_win_rate(),
                    'channel_status': self.get_channel_status()
                }
                
                return jsonify(stats)
            except Exception as e:
                return jsonify({'error': str(e)})
        
        @self.app.route('/api/signals')
        def get_signals():
            try:
                signals_data = []
                for signal in self.signals[-50:]:  # Last 50 signals
                    signals_data.append({
                        'timestamp': signal.timestamp.isoformat(),
                        'channel': signal.channel,
                        'pair': signal.pair,
                        'action': signal.action,
                        'entry_price': signal.entry_price,
                        'stop_loss': signal.stop_loss,
                        'take_profit': signal.take_profit,
                        'result': signal.result,
                        'profit_loss': signal.profit_loss
                    })
                
                return jsonify(signals_data)
            except Exception as e:
                return jsonify({'error': str(e)})
        
        @self.app.route('/api/chart')
        def get_chart_data():
            try:
                if not self.signals:
                    return jsonify({'data': []})
                
                df = pd.DataFrame([asdict(signal) for signal in self.signals])
                df['date'] = pd.to_datetime(df['timestamp']).dt.date
                daily_pnl = df.groupby('date')['profit_loss'].sum().cumsum()
                
                chart_data = {
                    'dates': [str(date) for date in daily_pnl.index],
                    'cumulative_pnl': daily_pnl.values.tolist()
                }
                
                return jsonify(chart_data)
            except Exception as e:
                return jsonify({'error': str(e)})

    def calculate_win_rate(self) -> float:
        """Calculate overall win rate"""
        closed_signals = [s for s in self.signals if s.result in ['WIN', 'LOSS']]
        if not closed_signals:
            return 0.0
        
        wins = len([s for s in closed_signals if s.result == 'WIN'])
        return (wins / len(closed_signals)) * 100

    def get_channel_status(self) -> Dict:
        """Get status of each channel"""
        status = {}
        for channel in self.channels:
            channel_signals = [s for s in self.signals if s.channel == channel]
            status[channel] = {
                'total_signals': len(channel_signals),
                'active_trades': len([s for s in channel_signals if s.result == 'PENDING']),
                'profit': sum([s.profit_loss for s in channel_signals])
            }
        return status

    async def message_handler(self, event):
        """Handle incoming Telegram messages"""
        try:
            sender = await event.get_sender()
            channel_name = sender.username if hasattr(sender, 'username') else sender.title
            
            if channel_name in self.channels or any(ch in channel_name for ch in self.channels):
                message_text = event.message.message
                
                signal = self.parse_signal(message_text, channel_name)
                if signal:
                    self.logger.info(f"Signal detected from {channel_name}: {signal.pair} {signal.action}")
                    
                    # Check if we haven't exceeded max trades for this channel
                    channel_active_trades = len([s for s in self.signals 
                                                if s.channel == channel_name and s.result == 'PENDING'])
                    
                    if channel_active_trades < self.max_trades_per_channel:
                        trade_id = self.execute_trade(signal)
                        if trade_id:
                            signal.trade_id = trade_id
                            signal.processed = True
                            signal.result = 'PENDING'
                            
                        self.signals.append(signal)
                        self.save_to_csv()
                    else:
                        self.logger.info(f"Max trades reached for {channel_name}")
                        
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")

    async def start_monitoring(self):
        """Start monitoring Telegram channels"""
        try:
            await self.client.start(phone=self.phone)
            self.logger.info("Telegram client started")
            
            # Register message handler
            self.client.add_event_handler(self.message_handler, events.NewMessage)
            
            self.logger.info("Started monitoring channels...")
            
            # Keep the client running
            while True:
                self.check_active_trades()
                self.save_to_csv()
                self.generate_report()
                await asyncio.sleep(60)  # Check every minute
                
        except Exception as e:
            self.logger.error(f"Error in monitoring: {e}")

    def run_dashboard(self):
        """Run Flask dashboard"""
        self.app.run(host='0.0.0.0', port=5000, debug=False)

    async def main(self):
        """Main function"""
        # Connect to MT5
        if not self.connect_mt5():
            self.logger.error("Failed to connect to MT5")
            return
        
        # Start monitoring in background
        monitoring_task = asyncio.create_task(self.start_monitoring())
        
        # Start dashboard in a separate thread
        import threading
        dashboard_thread = threading.Thread(target=self.run_dashboard)
        dashboard_thread.daemon = True
        dashboard_thread.start()
        
        # Wait for monitoring task
        await monitoring_task

if __name__ == "__main__":
    bot = TelegramSignalBot()
    
    # Create dashboard template directory
    os.makedirs('templates', exist_ok=True)
    
    # Run the bot
    asyncio.run(bot.main())