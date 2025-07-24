import MetaTrader5 as mt5
import asyncio
import logging
from notifier import Notifier
from typing import Dict, List
from datetime import datetime
import winsound
from pushover import send_pushover_notification
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class TradeTracker:
    def __init__(self):
        self.active_trades: List[Dict] = []
        self.closed_trades: List[Dict] = []
        self.last_check_time = datetime.now()

    def add_trade(self, ticket: int, symbol: str, sl: float, tp: float, 
                 volume: float, entry_price: float, action: str):
        """Add a new trade to tracking"""
        self.active_trades.append({
            "ticket": ticket,
            "symbol": symbol,
            "sl": sl,
            "tp": tp,
            "volume": volume,
            "entry_price": entry_price,
            "action": action.upper(),
            "opened_at": datetime.now()
        })
        logger.info(f"Added trade to tracking: {self.active_trades[-1]}")

    async def monitor_trades(self):
        """Continuously monitor active trades"""
        while True:
            try:
                await self._check_trades()
                await asyncio.sleep(10)  # Check every 10 seconds
            except Exception as e:
                logger.error(f"Trade monitoring error: {str(e)}")
                await asyncio.sleep(30)  # Wait longer if error occurs

    async def _check_trades(self):
        """Check all active trades for closures or hits"""
        if not mt5.initialize():
            logger.warning("MT5 not initialized for trade checking")
            return

        try:
            positions = mt5.positions_get()
            if positions is None:
                logger.warning("No positions returned from MT5")
                return

            
            await self._check_tp_sl_hits(positions)
            await self._check_manual_closures(positions)

        finally:
            mt5.shutdown()

    async def _check_manual_closures(self, current_positions):
        """Check for trades that were manually closed"""
        current_tickets = {p.ticket for p in current_positions}
        
        for trade in self.active_trades[:]:  # Iterate over copy
            if trade["ticket"] not in current_tickets:
                # Trade was closed
                profit = await self._get_trade_profit(trade["ticket"]) 

                if profit is not None:
                    msg = (
                        f"ℹ️ Trade Manually Closed\n"
                        f"Symbol: {trade['symbol']} {trade['action']}\n"
                        f"Profit/Loss: ${profit:.2f}\n"
                        f"Duration: {datetime.now() - trade['opened_at']}"
                    )
                    await self._send_notification(msg, "ℹ️ Trade Closed")
                    self.closed_trades.append(trade)
                    self.active_trades.remove(trade)
                    logger.info(f"Trade {trade['ticket']} manually closed")

    async def _check_tp_sl_hits(self, current_positions):
        """Check for TP/SL hits on active trades"""
        for trade in self.active_trades[:]:
            pos = next((p for p in current_positions if p.ticket == trade["ticket"]), None)
            if not pos:
                continue

            current_price = pos.price_current
            profit = pos.profit

            # Check TP hit
            if ((trade["action"] == "BUY" and current_price >= trade["tp"]) or
                (trade["action"] == "SELL" and current_price <= trade["tp"])):
                
                msg = (
                    f"🎯 TP Hit on {trade['symbol']}\n"
                    f"Entry: {trade['entry_price']}\n"
                    f"Exit: {current_price:.5f}\n"
                    f"Profit: ${profit:.2f}"
                )
                await self._send_notification(msg, "✅ TP Hit")
                self.closed_trades.append(trade)
                self.active_trades.remove(trade)
                logger.info(f"TP hit for trade {trade['ticket']}")

            # Check SL hit
            elif ((trade["action"] == "BUY" and current_price <= trade["sl"]) or
                  (trade["action"] == "SELL" and current_price >= trade["sl"])):
                
                msg = (
                    f"🛑 SL Hit on {trade['symbol']}\n"
                    f"Entry: {trade['entry_price']}\n"
                    f"Exit: {current_price:.5f}\n"
                    f"Loss: ${abs(profit):.2f}"
                )
                await self._send_notification(msg, "❌ SL Hit")
                self.closed_trades.append(trade)
                self.active_trades.remove(trade)
                logger.info(f"SL hit for trade {trade['ticket']}")

    async def _get_trade_profit(self, position_id: int) -> float:
        if not mt5.initialize():
            return 0.0

        try:
            from_time = datetime.now() - timedelta(days=7)
            to_time = datetime.now()
            deals = mt5.history_deals_get(from_time, to_time)

            if not deals:
                return 0.0

            # Filter by position_id
            profit = sum(d.profit for d in deals if d.position_id == position_id)
            return profit
        finally:
            mt5.shutdown()

    async def _send_notification(self, message: str, title: str):
        """Send notification through all channels"""
        try:
            await Notifier.send_notification(message)
            send_pushover_notification(message, title)
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception as e:
            logger.error(f"Notification error: {str(e)}")