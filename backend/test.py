import logging
from telethon import TelegramClient, events
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, MONITORED_CHANNELS, CHANNEL_NAMES, DEFAULT_LOT_SIZE
from signal_parser import SignalParser
from trading_api import TradingAPI
from notifier import Notifier
from logging.handlers import RotatingFileHandler
import winsound
import sys
import requests
from trade_tracker import TradeTracker
from pushover import send_pushover_notification
import asyncio

if __name__ == "__main__":
    test_messages = [
        """BUY XAUUSD
        Entry: 3372.48-3372.88
        SL: 3371.53
        TP1: 3373.62
        TP2: 3375.12""",
        
        """GOLD SELL @2365
        Stop Loss: 2370
        Take Profit: 2355""",
        
        """XAU/USD BUY NOW
        SL 2345
        TP 2360"""
    ]

    parser = SignalParser(use_ai=True)
    
    for msg in test_messages:
        print("\nTesting message:")
        print(msg)
        print("\nAI Result:")
        print(parser._parse_with_ai(msg))
        print("\nRegex Result:")
        print(parser._parse_with_regex(msg))
        