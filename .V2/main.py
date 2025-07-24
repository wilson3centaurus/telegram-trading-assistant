import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime
from dotenv import load_dotenv
import os
import talib

# Load config
load_dotenv()
SERVER = os.getenv("MT5_SERVER")
LOGIN = int(os.getenv("MT5_LOGIN"))
PASSWORD = os.getenv("MT5_PASSWORD")
LOT_SIZE = float(os.getenv("LOT_SIZE"))
TP1 = int(os.getenv("TP1_PIPS"))
TP2 = int(os.getenv("TP2_PIPS"))
SL = int(os.getenv("SL_PIPS"))

# Enhanced trading parameters
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
MA_FAST = 9
MA_SLOW = 21

# Pairs to trade
PAIRS = ["GBPUSD", "XAUUSD", "EURUSD"]

# Track recent trades to avoid overtrading
recent_trades = {}

def connect_mt5():
    if not mt5.initialize(server=SERVER, login=LOGIN, password=PASSWORD):
        print("MT5 Login Failed!")
        return False
    print("MT5 Connected!")
    return True

def get_balance():
    return mt5.account_info().balance

def log_trade(pair, ticket, entry_time, entry_price, exit_price, exit_time, pnl, hit_tp_sl, strategy):
    log_data = {
        "Time_Entry": entry_time,
        "Time_Exit": exit_time,
        "Pair": pair,
        "Ticket": ticket,
        "Entry_Price": entry_price,
        "Exit_Price": exit_price,
        "PnL": pnl,
        "TP/SL_Hit": hit_tp_sl,
        "Strategy": strategy,
        "Balance": get_balance()
    }
    df = pd.DataFrame([log_data])
    df.to_csv("trade_log.csv", mode='a', header=not os.path.exists("trade_log.csv"), index=False)

def calculate_indicators(df):
    """Calculate all technical indicators"""
    # RSI
    df['rsi'] = talib.RSI(df['close'].values, timeperiod=RSI_PERIOD)
    
    # MACD
    macd, macd_signal, macd_hist = talib.MACD(df['close'].values, 
                                             fastperiod=MACD_FAST, 
                                             slowperiod=MACD_SLOW, 
                                             signalperiod=MACD_SIGNAL)
    df['macd'] = macd
    df['macd_signal'] = macd_signal
    df['macd_hist'] = macd_hist
    
    # Moving Averages
    df['ma_fast'] = talib.SMA(df['close'].values, timeperiod=MA_FAST)
    df['ma_slow'] = talib.SMA(df['close'].values, timeperiod=MA_SLOW)
    
    # Bollinger Bands
    df['bb_upper'], df['bb_middle'], df['bb_lower'] = talib.BBANDS(df['close'].values, 
                                                                  timeperiod=20, 
                                                                  nbdevup=2, 
                                                                  nbdevdn=2)
    
    return df

def detect_engulfing_pattern(df):
    """Detect bullish/bearish engulfing patterns"""
    if len(df) < 2:
        return None
    
    current = df.iloc[-1]
    previous = df.iloc[-2]
    
    # Bullish engulfing
    if (previous['close'] < previous['open'] and  # Previous candle bearish
        current['close'] > current['open'] and    # Current candle bullish
        current['open'] < previous['close'] and   # Current opens below previous close
        current['close'] > previous['open']):     # Current closes above previous open
        return "bullish_engulfing"
    
    # Bearish engulfing
    if (previous['close'] > previous['open'] and  # Previous candle bullish
        current['close'] < current['open'] and    # Current candle bearish
        current['open'] > previous['close'] and   # Current opens above previous close
        current['close'] < previous['open']):     # Current closes below previous open
        return "bearish_engulfing"
    
    return None

def check_rsi_divergence(df):
    """Check for RSI divergence (simplified)"""
    if len(df) < 10:
        return None
    
    # Get recent highs and lows
    recent_data = df.tail(10)
    price_high = recent_data['high'].max()
    price_low = recent_data['low'].min()
    
    # Find corresponding RSI values
    price_high_idx = recent_data['high'].idxmax()
    price_low_idx = recent_data['low'].idxmin()
    
    current_rsi = df['rsi'].iloc[-1]
    
    # Bullish divergence: Price makes lower low, RSI makes higher low
    if (recent_data['low'].iloc[-1] <= price_low * 1.001 and 
        current_rsi > df.loc[price_low_idx, 'rsi'] and 
        current_rsi < 40):
        return "bullish_divergence"
    
    # Bearish divergence: Price makes higher high, RSI makes lower high
    if (recent_data['high'].iloc[-1] >= price_high * 0.999 and 
        current_rsi < df.loc[price_high_idx, 'rsi'] and 
        current_rsi > 60):
        return "bearish_divergence"
    
    return None

def check_trend_pullback(df):
    """Check for trend + pullback opportunities"""
    if len(df) < 30:
        return None
    
    current = df.iloc[-1]
    
    # Determine trend using longer MA
    ma_50 = talib.SMA(df['close'].values, timeperiod=50)
    if len(ma_50) < 2:
        return None
    
    trend_up = ma_50[-1] > ma_50[-10]  # Trend over last 10 periods
    
    # Check for pullback in uptrend
    if (trend_up and 
        current['ma_fast'] > current['ma_slow'] and  # Short term trend aligned
        current['close'] > current['bb_lower'] and   # Above lower BB
        current['close'] < current['bb_middle'] and  # Below middle BB (pullback)
        current['rsi'] > 40 and current['rsi'] < 60):  # RSI in middle range
        return "trend_pullback_buy"
    
    # Check for pullback in downtrend
    if (not trend_up and 
        current['ma_fast'] < current['ma_slow'] and  # Short term trend aligned
        current['close'] < current['bb_upper'] and   # Below upper BB
        current['close'] > current['bb_middle'] and  # Above middle BB (pullback)
        current['rsi'] > 40 and current['rsi'] < 60):  # RSI in middle range
        return "trend_pullback_sell"
    
    return None

def check_multiple_confirmations(pair):
    """Check multiple strategies for confirmation"""
    # Get more data for better analysis
    bars = mt5.copy_rates_from_pos(pair, mt5.TIMEFRAME_M5, 0, 100)
    if bars is None or len(bars) < 50:
        print(f"[{pair}] ❌ Insufficient data.")
        return None, None
    
    df = pd.DataFrame(bars)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    # Calculate all indicators
    df = calculate_indicators(df)
    
    if len(df) < 30:  # Need enough data for indicators
        return None, None
    
    current = df.iloc[-1]
    signals = []
    strategy_used = []
    
    # 1. RSI Divergence Strategy
    rsi_div = check_rsi_divergence(df)
    if rsi_div == "bullish_divergence":
        signals.append("buy")
        strategy_used.append("RSI_Divergence")
    elif rsi_div == "bearish_divergence":
        signals.append("sell")
        strategy_used.append("RSI_Divergence")
    
    # 2. MACD Cross Strategy
    if (not pd.isna(current['macd']) and not pd.isna(current['macd_signal']) and 
        len(df) > 1):
        prev_macd = df['macd'].iloc[-2]
        prev_signal = df['macd_signal'].iloc[-2]
        
        # Bullish cross
        if (prev_macd <= prev_signal and current['macd'] > current['macd_signal'] and
            current['macd'] < 0):  # Cross above zero line is stronger
            signals.append("buy")
            strategy_used.append("MACD_Cross")
        
        # Bearish cross
        elif (prev_macd >= prev_signal and current['macd'] < current['macd_signal'] and
              current['macd'] > 0):  # Cross below zero line is stronger
            signals.append("sell")
            strategy_used.append("MACD_Cross")
    
    # 3. Moving Average Crossover
    if (not pd.isna(current['ma_fast']) and not pd.isna(current['ma_slow']) and 
        len(df) > 1):
        prev_ma_fast = df['ma_fast'].iloc[-2]
        prev_ma_slow = df['ma_slow'].iloc[-2]
        
        # Bullish cross
        if (prev_ma_fast <= prev_ma_slow and current['ma_fast'] > current['ma_slow'] and
            current['rsi'] < 70):  # Not overbought
            signals.append("buy")
            strategy_used.append("MA_Cross")
        
        # Bearish cross
        elif (prev_ma_fast >= prev_ma_slow and current['ma_fast'] < current['ma_slow'] and
              current['rsi'] > 30):  # Not oversold
            signals.append("sell")
            strategy_used.append("MA_Cross")
    
    # 4. Engulfing Pattern
    engulfing = detect_engulfing_pattern(df)
    if engulfing == "bullish_engulfing" and current['rsi'] < 70:
        signals.append("buy")
        strategy_used.append("Bullish_Engulfing")
    elif engulfing == "bearish_engulfing" and current['rsi'] > 30:
        signals.append("sell")
        strategy_used.append("Bearish_Engulfing")
    
    # 5. Trend + Pullback
    trend_pullback = check_trend_pullback(df)
    if trend_pullback == "trend_pullback_buy":
        signals.append("buy")
        strategy_used.append("Trend_Pullback")
    elif trend_pullback == "trend_pullback_sell":
        signals.append("sell")
        strategy_used.append("Trend_Pullback")
    
    # Require at least 2 confirmations for a trade
    if len(signals) >= 2:
        if signals.count("buy") > signals.count("sell"):
            print(f"[{pair}] 📈 STRONG BUY Signal - Strategies: {', '.join(strategy_used)}")
            print(f"[{pair}] RSI: {current['rsi']:.2f}, MACD: {current['macd']:.5f}, MA_Fast: {current['ma_fast']:.5f}, MA_Slow: {current['ma_slow']:.5f}")
            return "buy", "+".join(strategy_used)
        elif signals.count("sell") > signals.count("buy"):
            print(f"[{pair}] 📉 STRONG SELL Signal - Strategies: {', '.join(strategy_used)}")
            print(f"[{pair}] RSI: {current['rsi']:.2f}, MACD: {current['macd']:.5f}, MA_Fast: {current['ma_fast']:.5f}, MA_Slow: {current['ma_slow']:.5f}")
            return "sell", "+".join(strategy_used)
    
    return None, None

def can_trade_pair(pair):
    """Check if we can trade this pair (avoid overtrading)"""
    current_time = time.time()
    if pair in recent_trades:
        # Don't trade same pair within 30 minutes
        if current_time - recent_trades[pair] < 1800:
            return False
    return True

def place_enhanced_trade(pair, signal, strategy):
    """Place trade with dynamic SL/TP based on volatility"""
    if not can_trade_pair(pair):
        print(f"[{pair}] ⏳ Skipping - recently traded")
        return []
    
    symbol_info = mt5.symbol_info(pair)
    if symbol_info is None:
        print(f"[{pair}] ❌ Symbol info not available")
        return []
    
    tick = mt5.symbol_info_tick(pair)
    if tick is None:
        print(f"[{pair}] ❌ Tick data not available")
        return []
    
    # Get recent volatility to adjust SL/TP
    bars = mt5.copy_rates_from_pos(pair, mt5.TIMEFRAME_M5, 0, 20)
    if bars is None or len(bars) == 0:
        print(f"[{pair}] ❌ No price data for ATR calculation")
        return []
        
    df = pd.DataFrame(bars)
    atr = talib.ATR(df['high'].values, df['low'].values, df['close'].values, timeperiod=14)
    current_atr = atr[-1] if len(atr) > 0 and not np.isnan(atr[-1]) else symbol_info.point * 100
    
    # Ensure minimum ATR value
    min_atr = symbol_info.point * 50  # Minimum 5 pips equivalent
    current_atr = max(current_atr, min_atr)
    
    # Dynamic SL/TP based on ATR
    atr_multiplier_sl = 1.5
    atr_multiplier_tp1 = 2.0
    atr_multiplier_tp2 = 3.0
    
    if signal == "buy":
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
        sl = price - (current_atr * atr_multiplier_sl)
        tp1 = price + (current_atr * atr_multiplier_tp1)
        tp2 = price + (current_atr * atr_multiplier_tp2)
    else:  # sell
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
        sl = price + (current_atr * atr_multiplier_sl)
        tp1 = price - (current_atr * atr_multiplier_tp1)
        tp2 = price - (current_atr * atr_multiplier_tp2)
    
    # Ensure minimum distance from current price (broker requirements)
    min_distance = symbol_info.trade_stops_level * symbol_info.point
    if min_distance > 0:
        if signal == "buy":
            sl = min(sl, price - min_distance)
            tp1 = max(tp1, price + min_distance)
            tp2 = max(tp2, price + min_distance)
        else:
            sl = max(sl, price + min_distance)
            tp1 = min(tp1, price - min_distance)
            tp2 = min(tp2, price - min_distance)
    
    # Reduce lot size for high-risk strategies
    lot_size = LOT_SIZE
    if "Divergence" in strategy or "Engulfing" in strategy:
        lot_size *= 0.7  # Reduce risk for pattern-based trades
    
    # Ensure lot size meets broker requirements
    if lot_size < symbol_info.volume_min:
        lot_size = symbol_info.volume_min
    elif lot_size > symbol_info.volume_max:
        lot_size = symbol_info.volume_max
    
    print(f"[{pair}] 📊 Trade Details:")
    print(f"  Price: {price:.5f} | SL: {sl:.5f} | TP1: {tp1:.5f} | TP2: {tp2:.5f}")
    print(f"  ATR: {current_atr:.5f} | Lot Size: {lot_size}")
    
    tickets = []
    # Open 2 positions: one for TP1, one for TP2
    for i, tp in enumerate([tp1, tp2]):
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pair,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 234567,
            "comment": f"ScalpBot_{strategy}_{i+1}",
        }
        
        try:
            trade = mt5.order_send(request)
            if trade is None:
                print(f"❌ Trade request returned None for {pair}")
                continue
                
            if trade.retcode == mt5.TRADE_RETCODE_DONE:
                tickets.append(trade.order)
                print(f"✅ Opened {signal.upper()} {pair} | Ticket: {trade.order} | TP{i+1}: {tp:.5f} | SL: {sl:.5f}")
            else:
                print(f"❌ Trade failed for {pair}: Code {trade.retcode} - {trade.comment}")
                
        except Exception as e:
            print(f"❌ Exception during trade execution for {pair}: {str(e)}")
    
    # Mark this pair as recently traded only if we actually opened trades
    if tickets:
        recent_trades[pair] = time.time()
    
    return tickets

def track_trades():
    """Enhanced trade tracking with partial closures"""
    open_trades = mt5.positions_get()
    for trade in open_trades:
        symbol_info = mt5.symbol_info(trade.symbol)
        if trade.type == mt5.ORDER_TYPE_BUY:
            current_price = mt5.symbol_info_tick(trade.symbol).bid
        else:
            current_price = mt5.symbol_info_tick(trade.symbol).ask
        
        pnl = trade.profit
        
        # Check for manual trailing stop (move SL to breakeven after 50% of TP1)
        if trade.type == mt5.ORDER_TYPE_BUY:
            halfway_to_tp = trade.price_open + (trade.tp - trade.price_open) * 0.5
            if current_price >= halfway_to_tp and trade.sl < trade.price_open:
                # Move SL to breakeven
                modify_request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "symbol": trade.symbol,
                    "position": trade.ticket,
                    "sl": trade.price_open,
                    "tp": trade.tp
                }
                mt5.order_send(modify_request)
                print(f"📈 Moved SL to breakeven for {trade.symbol} ticket {trade.ticket}")
        
        elif trade.type == mt5.ORDER_TYPE_SELL:
            halfway_to_tp = trade.price_open + (trade.tp - trade.price_open) * 0.5
            if current_price <= halfway_to_tp and trade.sl > trade.price_open:
                # Move SL to breakeven
                modify_request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "symbol": trade.symbol,
                    "position": trade.ticket,
                    "sl": trade.price_open,
                    "tp": trade.tp
                }
                mt5.order_send(modify_request)
                print(f"📉 Moved SL to breakeven for {trade.symbol} ticket {trade.ticket}")

def main():
    if not connect_mt5():
        return
    
    print("=" * 60)
    print("🚀 ADVANCED SCALPING BOT STARTED 🚀")
    print("=" * 60)
    print(f"💰 Starting Balance: ${get_balance():.2f}")
    print(f"📊 Pairs: {', '.join(PAIRS)}")
    print(f"📈 Strategies: RSI Divergence, MACD Cross, MA Cross, Engulfing, Trend Pullback")
    print("=" * 60)
    
    iteration = 0
    while True:
        iteration += 1
        print(f"\n🔄 Scan #{iteration} - {datetime.now().strftime('%H:%M:%S')}")
        
        for pair in PAIRS:
            try:
                signal, strategy = check_multiple_confirmations(pair)
                if signal and strategy:
                    tickets = place_enhanced_trade(pair, signal, strategy)
                    if tickets:
                        print(f"🎯 Trade opened for {pair} using {strategy}")
                else:
                    print(f"[{pair}] ⏸️  No strong signals")
            except Exception as e:
                print(f"[{pair}] ⚠️  Error: {str(e)}")
        
        # Track existing trades
        try:
            track_trades()
        except Exception as e:
            print(f"⚠️ Trade tracking error: {str(e)}")
        
        print(f"💰 Current Balance: ${get_balance():.2f}")
        
        # Wait before next scan
        time.sleep(60)  # Scan every minute for scalping

if __name__ == "__main__":
    main()