import os
import json
import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

import supabase_client as db
import telegram_bot as tg

load_dotenv()

WATCHLIST_FILE = "watchlist_state.json"
SYMBOLS_CACHE_FILE = "watched_symbols_cache.json"

def get_watched_symbols():
    """Retrieve symbols to scan, dynamically updating the top 25 volume pairs on Bybit on Mondays."""
    now = datetime.now(timezone.utc)
    
    # Load cached symbols if exists
    if os.path.exists(SYMBOLS_CACHE_FILE):
        try:
            with open(SYMBOLS_CACHE_FILE, 'r') as f:
                cache = json.load(f)
            cache_time = datetime.fromisoformat(cache["updated_at"])
            days_old = (now - cache_time).days
            # Monday is weekday() == 0. If not Monday, or it's same week, reuse cache
            if days_old < 7 and (now.weekday() != 0 or cache_time.weekday() == 0):
                return cache["symbols"]
        except Exception as e:
            print(f"Error reading symbols cache, refetching: {e}")
            
    # Refetch from exchange
    print("Fetching top 25 USDT swap pairs by 24h volume from Bybit...")
    try:
        exchange.load_markets()
        tickers = exchange.fetch_tickers()
        
        usdt_swaps = []
        for symbol, ticker in tickers.items():
            # Filter for USDT linear swaps, e.g. "BTC/USDT" or "BTC/USDT:USDT"
            # quoteVolume represents volume in USDT
            if ("/USDT" in symbol) and ticker.get("quoteVolume"):
                usdt_swaps.append({
                    "symbol": symbol,
                    "volume": float(ticker["quoteVolume"])
                })
                
        # Sort by volume descending
        usdt_swaps.sort(key=lambda x: x["volume"], reverse=True)
        top_symbols = [item["symbol"] for item in usdt_swaps[:25]]
        
        # Fallback if empty
        if not top_symbols:
            top_symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "LINK/USDT"]
            
        # Cache results
        cache_data = {
            "updated_at": now.isoformat(),
            "symbols": top_symbols
        }
        with open(SYMBOLS_CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=4)
            
        return top_symbols
    except Exception as e:
        print(f"Failed to fetch dynamic symbols: {e}")
        # Default fallback
        return ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "ADA/USDT", "XRP/USDT", "DOT/USDT", "LINK/USDT", "DOGE/USDT", "AVAX/USDT", "POL/USDT", "LTC/USDT", "UNI/USDT", "NEAR/USDT", "ATOM/USDT"]

WATCHLIST_FILE = "watchlist_state.json"

LATEST_WATCHLIST = []

# Initialize CCXT exchange client
exchange = ccxt.bybit({
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'} # Bybit swaps/futures have high liquidity and no aggressive shared IP bans
})

def load_local_watchlist():
    """Load local watchlist of pairs currently being monitored for SMC setups."""
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading local watchlist: {e}")
    return {}

def save_local_watchlist(watchlist):
    """Save local watchlist state."""
    try:
        with open(WATCHLIST_FILE, 'w') as f:
            json.dump(watchlist, f, indent=4)
    except Exception as e:
        print(f"Error saving local watchlist: {e}")

def fetch_candles(symbol: str, timeframe: str, limit: int = 100):
    """Fetch candles from exchange."""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df
    except Exception as e:
        print(f"Error fetching candles for {symbol} on {timeframe}: {e}")
        return None

def get_weekly_high_low(symbol: str):
    """Get high and low of the previous weekly closed candle."""
    df = fetch_candles(symbol, "1w", limit=3)
    if df is None or len(df) < 2:
        return None, None
    # Last candle (index -1) is current open week, second to last (index -2) is previous closed week
    prev_week = df.iloc[-2]
    return float(prev_week["high"]), float(prev_week["low"])

def find_swings(df: pd.DataFrame, window: int = 2):
    """
    Find Swing Highs and Swing Lows using a fractal window.
    Default window of 2 means a candle must be higher/lower than 2 candles before and 2 after.
    """
    df = df.copy()
    df["swing_high"] = np.nan
    df["swing_low"] = np.nan
    
    for i in range(window, len(df) - window):
        # Swing High
        is_high = True
        for j in range(1, window + 1):
            if df.iloc[i]["high"] <= df.iloc[i-j]["high"] or df.iloc[i]["high"] <= df.iloc[i+j]["high"]:
                is_high = False
                break
        if is_high:
            df.at[df.index[i], "swing_high"] = df.iloc[i]["high"]
            
        # Swing Low
        is_low = True
        for j in range(1, window + 1):
            if df.iloc[i]["low"] >= df.iloc[i-j]["low"] or df.iloc[i]["low"] >= df.iloc[i+j]["low"]:
                is_low = False
                break
        if is_low:
            df.at[df.index[i], "swing_low"] = df.iloc[i]["low"]
            
    return df

def scan_all_markets():
    """Main scan function executed every hour (completely stateless)."""
    start_time = time.time()
    print(f"[{datetime.now().isoformat()}] Starting hourly market scan (stateless)...")
    
    symbols_to_scan = get_watched_symbols()
    scanned_count = 0
    errors_count = 0
    current_watchlist = []
    
    for symbol in symbols_to_scan:
        try:
            # 1. Prevent duplicate signals if pair has an active/pending trade in DB
            db_signal = db.get_signal_by_pair(symbol)
            if db_signal:
                print(f"Skipping {symbol}: Active/Pending signal already exists in Database.")
                continue
            
            # 2. Get Weekly High/Low
            w_high, w_low = get_weekly_high_low(symbol)
            if w_high is None or w_low is None:
                continue
                
            time.sleep(0.3) # Sleep to respect Bybit rate limit
            
            # 3. Fetch 1H candles
            df = fetch_candles(symbol, "1h", limit=100)
            if df is None or len(df) < 20:
                continue
                
            # Look back up to 48 closed candles before the last completed candle (index -2)
            lookback_depth = min(48, len(df) - 3)
            
            trigger_found = False
            trigger_type = None # "HIGH" or "LOW"
            trigger_index = -1
            
            # Search for the oldest weekly high/low touch/break in the lookback window
            for i in range(len(df) - 2 - lookback_depth, len(df) - 1):
                candle = df.iloc[i]
                if candle["high"] >= w_high:
                    trigger_found = True
                    trigger_type = "HIGH"
                    trigger_index = i
                    break
                elif candle["low"] <= w_low:
                    trigger_found = True
                    trigger_type = "LOW"
                    trigger_index = i
                    break
                    
            if not trigger_found:
                scanned_count += 1
                time.sleep(1.0)
                continue
                
            # Add to dynamic cached watchlist
            current_watchlist.append({
                "pair": symbol,
                "trigger": trigger_type,
                "level": w_high if trigger_type == "HIGH" else w_low,
                "time": df.iloc[trigger_index]["datetime"].isoformat()
            })
                
            # 4. Check if the last completed candle (index -2) triggered a BOS or CHOCH
            # Swing points must be calculated from historical data
            df_swings = find_swings(df, window=2)
            
            # Last completed candle
            last_candle = df.iloc[-2]
            close_price = float(last_candle["close"])
            
            signal_direction = None
            setup_type = None
            leg_start = None
            leg_end = None
            
            if trigger_type == "HIGH":
                # Find the breakout peak (highest high) since the weekly high breakout trigger
                # We search from trigger_index to len(df)-2 (completed candles)
                sub_df = df.iloc[trigger_index:len(df)-1]
                breakout_peak = float(sub_df["high"].max())
                peak_idx = sub_df["high"].idxmax()
                
                # Find the most recent confirmed swing low BEFORE or AT peak_idx
                swing_low_rows = df_swings.loc[:peak_idx].dropna(subset=["swing_low"])
                
                if len(swing_low_rows) > 0:
                    recent_swing_low = float(swing_low_rows.iloc[-1]["swing_low"])
                    
                    # Bearish CHOCH (Reversal): price closes below recent swing low
                    if close_price < recent_swing_low:
                        signal_direction = "SELL"
                        setup_type = "CHOCH"
                        leg_start = breakout_peak
                        leg_end = float(last_candle["low"])
                
                # Bullish BOS (Continuation): price closes above breakout_peak
                if close_price > breakout_peak:
                    signal_direction = "BUY"
                    setup_type = "BOS"
                    leg_end = float(last_candle["high"])
                    # leg_start is the lowest low (retracement) between the peak and the breakout candle
                    retracement_df = df.iloc[peak_idx:len(df)-1]
                    leg_start = float(retracement_df["low"].min())
                    
            elif trigger_type == "LOW":
                # Find the breakout valley (lowest low) since the weekly low breakout trigger
                sub_df = df.iloc[trigger_index:len(df)-1]
                breakout_valley = float(sub_df["low"].min())
                valley_idx = sub_df["low"].idxmin()
                
                # Find the most recent confirmed swing high BEFORE or AT valley_idx
                swing_high_rows = df_swings.loc[:valley_idx].dropna(subset=["swing_high"])
                
                if len(swing_high_rows) > 0:
                    recent_swing_high = float(swing_high_rows.iloc[-1]["swing_high"])
                    
                    # Bullish CHOCH (Reversal): price closes above recent swing high
                    if close_price > recent_swing_high:
                        signal_direction = "BUY"
                        setup_type = "CHOCH"
                        leg_start = breakout_valley
                        leg_end = float(last_candle["high"])
                
                # Bearish BOS (Continuation): price closes below breakout_valley
                if close_price < breakout_valley:
                    signal_direction = "SELL"
                    setup_type = "BOS"
                    leg_end = float(last_candle["low"])
                    # leg_start is the highest high (retracement) between the valley and the breakout candle
                    retracement_df = df.iloc[valley_idx:len(df)-1]
                    leg_start = float(retracement_df["high"].max())

            if signal_direction and leg_start is not None and leg_end is not None:
                fib_range = abs(leg_end - leg_start)
                
                if signal_direction == "BUY":
                    # Entry at 0.5 Fib, SL at 0.89 Fib (as requested by user)
                    entry_price = leg_end - (0.5 * fib_range)
                    sl_price = leg_end - (0.89 * fib_range)
                    risk = entry_price - sl_price
                    tp_price = entry_price + (2 * risk) # 1:2 R:R
                else:
                    # Entry at 0.5 Fib, SL at 0.89 Fib
                    entry_price = leg_end + (0.5 * fib_range)
                    sl_price = leg_end + (0.89 * fib_range)
                    risk = sl_price - entry_price
                    tp_price = entry_price - (2 * risk) # 1:2 R:R
                    
                new_signal = db.create_signal(
                    pair=symbol,
                    direction=signal_direction,
                    trigger_type=setup_type,
                    entry=entry_price,
                    sl=sl_price,
                    tp=tp_price
                )
                
                if new_signal:
                    print(f"SUCCESS STATELESS: Generated {setup_type} signal for {symbol}!")
                    tg.alert_new_signal(new_signal)
            
            scanned_count += 1
            time.sleep(1.0) # Delay to respect rate limit
            
        except Exception as e:
            errors_count += 1
            print(f"Error scanning {symbol}: {e}")
            time.sleep(1.0)
            
    execution_time = time.time() - start_time
    
    # Save to global cache variable for API endpoints
    global LATEST_WATCHLIST
    LATEST_WATCHLIST = current_watchlist
    
    # Write audit log to database
    if errors_count == 0:
        db.create_system_log(
            status="SUCCESS",
            message=f"Scan completed successfully. Scanned {scanned_count} symbols.",
            execution_time=round(execution_time, 2)
        )
    else:
        db.create_system_log(
            status="ERROR",
            message=f"Scan completed with {errors_count} errors. Scanned {scanned_count} symbols.",
            execution_time=round(execution_time, 2)
        )

def update_live_trades():
    """Check active and pending signals to see if they hit Entry, SL, or TP."""
    print("Checking status of active/pending trades...")
    active_signals = db.get_active_signals()
    
    for signal in active_signals:
        symbol = signal["pair"]
        try:
            # Fetch current ticker price
            ticker = exchange.fetch_ticker(symbol)
            current_price = float(ticker["last"])
            
            entry = float(signal["entry_price"])
            sl = float(signal["sl_price"])
            tp = float(signal["tp_price"])
            status = signal["status"]
            direction = signal["direction"]
            
            if status == "PENDING":
                is_triggered = False
                
                # Check if it has breached Stop Loss first
                if direction == "BUY" and current_price < sl:
                    db.update_signal_status(signal["id"], "EXPIRED")
                    db.create_system_log("INFO", f"Signal {symbol} EXPIRED: Price {current_price} breached SL {sl} before 15m trigger.")
                    print(f"Signal {symbol} EXPIRED (hit SL before entry)")
                    continue
                elif direction == "SELL" and current_price > sl:
                    db.update_signal_status(signal["id"], "EXPIRED")
                    db.create_system_log("INFO", f"Signal {symbol} EXPIRED: Price {current_price} breached SL {sl} before 15m trigger.")
                    print(f"Signal {symbol} EXPIRED (hit SL before entry)")
                    continue
                
                # Check if price is within the 1H Fib 0.5 - 0.89 entry retracement zone
                in_entry_zone = False
                if direction == "BUY" and current_price <= entry and current_price >= sl:
                    in_entry_zone = True
                elif direction == "SELL" and current_price >= entry and current_price <= sl:
                    in_entry_zone = True
                    
                if in_entry_zone:
                    # Fetch 15m candles to look for micro-structure reversal (15m CHOCH)
                    df_15 = fetch_candles(symbol, "15m", limit=30)
                    time.sleep(0.3) # Respect API rate limits
                    
                    if df_15 is not None and len(df_15) >= 5:
                        df_swings_15 = find_swings(df_15, window=2)
                        
                        if direction == "BUY":
                            swing_high_rows = df_swings_15.iloc[:-1].dropna(subset=["swing_high"])
                            if len(swing_high_rows) > 0:
                                recent_15m_swing_high = float(swing_high_rows.iloc[-1]["swing_high"])
                                last_15m_candle = df_15.iloc[-2]
                                # Check if 15m candle closed above recent swing high
                                if float(last_15m_candle["close"]) > recent_15m_swing_high:
                                    is_triggered = True
                        else: # SELL
                            swing_low_rows = df_swings_15.iloc[:-1].dropna(subset=["swing_low"])
                            if len(swing_low_rows) > 0:
                                recent_15m_swing_low = float(swing_low_rows.iloc[-1]["swing_low"])
                                last_15m_candle = df_15.iloc[-2]
                                # Check if 15m candle closed below recent swing low
                                if float(last_15m_candle["close"]) < recent_15m_swing_low:
                                    is_triggered = True
                                    
                if is_triggered:
                    updated_sig = db.update_signal_status(signal["id"], "ACTIVE")
                    if updated_sig:
                        tg.alert_signal_active(updated_sig)
                        print(f"Signal {symbol} is now ACTIVE (Confirmed by 15m Reversal)")
                        
            elif status == "ACTIVE":
                # Check if TP or SL is hit
                is_tp = False
                is_sl = False
                
                if direction == "BUY":
                    if current_price >= tp:
                        is_tp = True
                    elif current_price <= sl:
                        is_sl = True
                else: # SELL
                    if current_price <= tp:
                        is_tp = True
                    elif current_price >= sl:
                        is_sl = True
                        
                if is_tp:
                    updated_sig = db.update_signal_status(signal["id"], "TP_HIT", current_price)
                    if updated_sig:
                        tg.alert_signal_closed(updated_sig, "TP_HIT")
                        print(f"Signal {symbol} hit TAKE PROFIT (TP)")
                elif is_sl:
                    updated_sig = db.update_signal_status(signal["id"], "SL_HIT", current_price)
                    if updated_sig:
                        tg.alert_signal_closed(updated_sig, "SL_HIT")
                        print(f"Signal {symbol} hit STOP LOSS (SL)")
                        
        except Exception as e:
            print(f"Error updating active trade for {symbol}: {e}")

def get_current_watchlist():
    """Retrieve the cached watchlist collected in the last scan."""
    global LATEST_WATCHLIST
    return LATEST_WATCHLIST
