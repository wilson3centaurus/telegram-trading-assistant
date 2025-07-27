import logging
from telethon import TelegramClient, events, errors
from telethon.network import ConnectionTcpFull
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, MONITORED_CHANNELS, CHANNEL_NAMES, DEFAULT_LOT_SIZE
from signal_parser import SignalParser
from trading_api import TradingAPI
from notifier import Notifier
from logging.handlers import RotatingFileHandler
import winsound
import sys
import requests
from trade_tracker import TradeTracker
import asyncio
import time
from functools import wraps

PUSHOVER_USER_KEY = "uig46b9ik8eqy5fefzbzt8ttri1k6z"
PUSHOVER_APP_TOKEN = "admg7efo3yqp4pwmbi6v92opmpnzov"

logger = logging.getLogger(__name__)

class TelegramMonitor:
    def __init__(self):
        self.client = None
        self.trade_tracker = TradeTracker()
        self._is_running = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._last_message_time = time.time()
        self._connection_task = None
        self.trading_api = TradingAPI()
        
    async def initialize_client(self):
        """Initialize Telegram client with robust connection settings"""
        self.client = TelegramClient(
            'session_name', 
            TELEGRAM_API_ID, 
            TELEGRAM_API_HASH,
            connection=ConnectionTcpFull,
            timeout=10,
            connection_retries=5,
            auto_reconnect=True,
            retry_delay=1,
            flood_sleep_threshold=60
        )
        
        # Add message handler
        self.client.add_event_handler(self._message_handler, events.NewMessage(chats=MONITORED_CHANNELS))
        
    async def _handle_disconnect(self):
        """Handle disconnections manually"""
        while self._is_running:
            if not self.client.is_connected():
                logger.warning("Connection lost, attempting to reconnect...")
                await self._safe_reconnect()
            await asyncio.sleep(5)  # Check connection every 5 seconds
            
    async def _safe_reconnect(self):
        """Handle reconnection with backoff"""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error("Max reconnection attempts reached. Shutting down...")
            await Notifier.send_notification("Telegram monitor failed to reconnect after multiple attempts!")
            self._is_running = False
            return
            
        self._reconnect_attempts += 1
        reconnect_delay = min(2 ** self._reconnect_attempts, 30)  # Exponential backoff with max 30s
        
        try:
            await asyncio.sleep(reconnect_delay)
            if self.client.is_connected():
                await self.client.disconnect()
                
            await self.client.connect()
            self._reconnect_attempts = 0  # Reset on successful reconnect
            logger.info("Successfully reconnected to Telegram")
        except Exception as e:
            logger.error(f"Reconnection attempt {self._reconnect_attempts} failed: {str(e)}")
            await self._safe_reconnect()
            
    async def _log_channels(self):
        """Log monitored channels at startup"""
        logger.info("=== Monitored Channels ===")
        for channel_id in MONITORED_CHANNELS:
            name = CHANNEL_NAMES.get(channel_id, f"Unknown Channel ({channel_id})")
            logger.info(f" • {name} (ID: {channel_id})")
        logger.info("==========================")
        
    async def _send_pushover_notification(self, message: str, title: str = "Tau Core System"):
        """Robust notification sender"""
        payload = {
            "token": PUSHOVER_APP_TOKEN,
            "user": PUSHOVER_USER_KEY,
            "message": message,
            "title": title,
            "priority": 1,
        }
        try:
            response = requests.post("https://api.pushover.net/1/messages.json", data=payload, timeout=5)
            response.raise_for_status()
            logger.info("Pushover notification sent successfully")
        except Exception as e:
            logger.error(f"Failed to send Pushover notification: {str(e)}")
            raise
            
    async def _process_signal(self, channel_name, message):
        """Process trading signal with error handling"""
        try:
            signal = SignalParser.parse_signal_static(message)
            if not signal:
                return
                
            logger.info(f"[{channel_name}] Signal parsed: {signal}")
            
            # Execute trade with channel name context
            trade_result = await self.trading_api.execute_trade(signal, channel_name)
            
            notification_msg = (
                f"Trade executed from {channel_name}\n"
                f"Symbol: {signal['symbol']} {signal['action']}\n"
                f"Entry: {signal.get('entry_min', 'N/A')}-{signal.get('entry_max', 'N/A')}\n"
                f"SL: {signal['sl']} | TP: {signal['tp1']}"
            )
            
            if trade_result[0]:
                await Notifier.send_notification(f"Trade executed from {channel_name} ...")
                await self._send_pushover_notification(
                    message=notification_msg,
                    title="📈 Tau Core Trade Executed!"
                )
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                
                # Handle trade tracking (only track the last trade in full margin mode)
                if ":" in trade_result[1]:
                    try:
                        ticket_part = trade_result[1].split("Last ticket: ")[-1] if "Last ticket:" in trade_result[1] else trade_result[1]
                        ticket = int(ticket_part.split(":")[-1].strip()) if ":" in ticket_part else None
                        
                        if ticket:
                            entry_price = (signal.get('entry_min', 0) + signal.get('entry_max', 0)) / 2 if \
                                        signal.get('entry_min') and signal.get('entry_max') else \
                                        signal.get('entry_min', 0)
                            
                            self.trade_tracker.add_trade(
                                ticket=ticket,
                                symbol=signal["symbol"],
                                sl=signal["sl"],
                                tp=signal["tp1"],
                                volume=DEFAULT_LOT_SIZE,
                                entry_price=entry_price,
                                action=signal["action"]
                            )
                    except Exception as e:
                        logger.error(f"Error adding trade to tracker: {str(e)}")
            else:
                await Notifier.send_notification(f"Trade FAILED from {channel_name} - Reason: {trade_result[1]}")
                
        except Exception as e:
            error_msg = f"Error processing message from {channel_name}: {str(e)}"
            logger.error(error_msg)
            await Notifier.send_notification(error_msg)
                      
    async def _message_handler(self, event):
        """Handle incoming messages"""
        self._last_message_time = time.time()
        channel_name = CHANNEL_NAMES.get(event.chat_id, f"Unknown Channel ({event.chat_id})")
        message = event.message.text
        
        logger.info(f"New message from [{channel_name}]: {message}")
        await self._process_signal(channel_name, message)
        
    async def start(self):
        """Start the monitor with robust connection handling"""
        self._is_running = True
        
        await self.initialize_client()
        try:
            await self.client.start(TELEGRAM_PHONE)
            self._connection_task = asyncio.create_task(self._handle_disconnect())
            asyncio.create_task(self.trade_tracker.monitor_trades())
            
            logger.info("Telegram client started successfully")
            await self._log_channels()
            await Notifier.send_notification("Telegram monitor started successfully")
            
            while self._is_running:
                try:
                    await self.client.run_until_disconnected()
                except Exception as e:
                    logger.error(f"Connection error: {str(e)}")
                    if self._is_running:
                        await self._safe_reconnect()
                        
        except Exception as e:
            logger.error(f"Fatal error in monitor: {str(e)}")
            await Notifier.send_notification(f"Telegram monitor crashed: {str(e)}")
        finally:
            self._is_running = False
            if self._connection_task:
                self._connection_task.cancel()
            if self.client and self.client.is_connected():
                await self.client.disconnect()
                
    async def stop(self):
        """Gracefully stop the monitor"""
        self._is_running = False
        if self.client and self.client.is_connected():
            await self.client.disconnect()