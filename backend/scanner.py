import os
import json
import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timezone, timedelta
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
            # Filter for USDT linear swaps, e.g. "BTC/USDT:USDT"
            # quoteVolume represents volume in USDT
            if (":USDT" in symbol) and ticker.get("quoteVolume"):
                usdt_swaps.append({
                    "symbol": symbol,
                    "volume": float(ticker["quoteVolume"])
                })
                
        # Sort by volume descending
        usdt_swaps.sort(key=lambda x: x["volume"], reverse=True)
        top_symbols = [item["symbol"] for item in usdt_swaps[:25]]
        
        # Force Gold 'XAU/USDT:USDT' to be in the list
        gold_symbol = "XAU/USDT:USDT"
        if gold_symbol not in top_symbols:
            top_symbols.append(gold_symbol)
            
        # Fallback if empty
        if not top_symbols:
            top_symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XAU/USDT:USDT"]
            
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
        return ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XAU/USDT:USDT"]

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
    """Fetch candles from Bybit exchange."""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df
    except Exception as e:
        print(f"Error fetching candles for {symbol} on {timeframe}: {e}")
        return None

def get_monday_range(symbol: str, current_week_start: datetime) -> tuple[float, float]:
    """Get Monday's High and Low for the current week (Monday 00:00 to Tuesday 00:00 UTC)."""
    try:
        # Fetch 1H candles to cover the last 7 days (limit=200)
        df = fetch_candles(symbol, "1h", limit=200)
        if df is None or len(df) == 0:
            return None, None
            
        # Monday ends at current_week_start + 24 hours
        monday_end = current_week_start + timedelta(hours=24)
        
        # Filter candles within Monday
        monday_candles = df[(df["datetime"] >= current_week_start) & (df["datetime"] < monday_end)]
        if len(monday_candles) == 0:
            return None, None
            
        monday_high = float(monday_candles["high"].max())
        monday_low = float(monday_candles["low"].min())
        return monday_high, monday_low
    except Exception as e:
        print(f"Error getting Monday range for {symbol}: {e}")
        return None, None

WEEKLY_STATE_FILE = "weekly_state.json"

def check_weekly_reset():
    """Check if a new week has started and close all pending/active signals from the previous week."""
    now_utc = datetime.now(timezone.utc)
    current_week_start = now_utc - timedelta(days=now_utc.weekday())
    current_week_start = current_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    current_week_str = current_week_start.isoformat()
    
    # Load last processed week start
    last_week_str = None
    if os.path.exists(WEEKLY_STATE_FILE):
        try:
            with open(WEEKLY_STATE_FILE, 'r') as f:
                state = json.load(f)
                last_week_str = state.get("last_processed_week_start")
        except Exception as e:
            print(f"Error loading weekly state: {e}")
            
    # First time initialization: write current week and return
    if last_week_str is None:
        try:
            with open(WEEKLY_STATE_FILE, 'w') as f:
                json.dump({"last_processed_week_start": current_week_str}, f)
        except Exception as e:
            print(f"Error saving initial weekly state: {e}")
        return

    # If the week has changed, perform the reset!
    if current_week_str != last_week_str:
        print(f"[{datetime.now().isoformat()}] New weekly candle open detected ({current_week_str}). Closing previous week's trades...")
        
        # 1. Fetch all pending and active signals
        active_signals = db.get_active_signals()
        
        closed_count = 0
        for signal in active_signals:
            symbol = signal["pair"]
            try:
                # Fetch current price to close active trades at current market rate
                current_price = None
                try:
                    ticker = exchange.fetch_ticker(symbol)
                    current_price = float(ticker["last"])
                except Exception as ticker_err:
                    print(f"Error getting exit price for {symbol} during reset: {ticker_err}")
                
                # Update status to EXPIRED
                db.update_signal_status(signal["id"], "EXPIRED", close_price=current_price)
                closed_count += 1
                print(f"Weekly Reset: Closed trade {symbol} at {current_price}")
            except Exception as e:
                print(f"Error closing trade {symbol} during weekly reset: {e}")
                
        # Send Telegram notification
        msg = (
            f"🔄 **WEEKLY CANDLE OPEN RESET**\n\n"
            f"• **New Week Start**: `{current_week_start.strftime('%Y-%m-%d %H:%M')} UTC`\n"
            f"• **Closed Signals**: `{closed_count}`\n\n"
            f"All pending setups and active positions from the previous weekly candle have been closed. A new weekly scanning cycle is now active! 📈"
        )
        tg.send_telegram_message(msg)
        db.create_system_log(
            status="SUCCESS",
            message=f"Weekly candle open reset completed. Closed {closed_count} signals from previous week."
        )
        
        # Update state file
        try:
            with open(WEEKLY_STATE_FILE, 'w') as f:
                json.dump({"last_processed_week_start": current_week_str}, f)
        except Exception as e:
            print(f"Error saving weekly state: {e}")

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
    """Main scan function executed every hour (Monday Range PO3 model)."""
    check_weekly_reset()
    start_time = time.time()
    
    # Check if today is Monday (Accumulation Phase)
    now_utc = datetime.now(timezone.utc)
    if now_utc.weekday() == 0:
        print(f"[{datetime.now().isoformat()}] Today is Monday (Accumulation Phase). Skipping scan for sweeps.")
        return
        
    print(f"[{datetime.now().isoformat()}] Starting hourly Monday Range PO3 market scan...")
    
    symbols_to_scan = get_watched_symbols()
    scanned_count = 0
    errors_count = 0
    current_watchlist = []
    
    # Calculate current week start (Monday 00:00 UTC)
    current_week_start = now_utc - timedelta(days=now_utc.weekday())
    current_week_start = current_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    
    for symbol in symbols_to_scan:
        try:
            # 1. Prevent duplicate active/pending signals
            db_signal = db.get_signal_by_pair(symbol)
            if db_signal:
                print(f"Skipping {symbol}: Active/Pending signal already exists in Database.")
                continue
                
            if db.has_signal_since(symbol, current_week_start):
                print(f"Skipping {symbol}: A signal was already generated this week for the current weekly candle.")
                continue
                
            time.sleep(0.3) # Sleep to respect Bybit rate limit
            
            # 2. Get Monday High & Low
            m_high, m_low = get_monday_range(symbol, current_week_start)
            if m_high is None or m_low is None:
                print(f"Skipping {symbol}: Monday range not fully established yet.")
                continue
                
            # Add to watchlist cache for frontend
            current_watchlist.append({
                "pair": symbol,
                "trigger": "PO3_RANGE",
                "level": f"MH: {m_high} | ML: {m_low}",
                "time": now_utc.isoformat()
            })
            
            # 3. Fetch current price
            ticker = exchange.fetch_ticker(symbol)
            current_price = float(ticker["last"])
            
            # 4. Check for sweeps
            signal_direction = None
            
            # Find the lowest/highest price of the current week up to now (for SL calculation)
            df_1h = fetch_candles(symbol, "1h", limit=200)
            if df_1h is None or len(df_1h) == 0:
                continue
            week_candles = df_1h[df_1h["datetime"] >= current_week_start]
            week_low = float(week_candles["low"].min()) if len(week_candles) > 0 else current_price
            week_high = float(week_candles["high"].max()) if len(week_candles) > 0 else current_price
            
            if current_price < m_low:
                # Bullish Sweep (Monday Low swept)
                signal_direction = "BUY"
                sl_price = week_low * 0.9995 # 0.05% safety buffer
                tp_price = current_price + 2.0 * (current_price - sl_price) # 1:2 R:R
                entry_price = current_price
                
            elif current_price > m_high:
                # Bearish Sweep (Monday High swept)
                signal_direction = "SELL"
                sl_price = week_high * 1.0005 # 0.05% safety buffer
                tp_price = current_price - 2.0 * (sl_price - current_price) # 1:2 R:R
                entry_price = current_price
                
            if signal_direction:
                # Create PENDING signal
                new_sig = db.create_signal(
                    pair=symbol,
                    direction=signal_direction,
                    trigger_type="BOS",
                    entry=entry_price,
                    sl=sl_price,
                    tp=tp_price
                )
                if new_sig:
                    print(f"Created PENDING signal for {symbol} ({signal_direction} PO3 sweep of Monday range)")
                    tg.alert_new_signal(new_sig)
                    db.create_system_log(
                        status="SUCCESS",
                        message=f"Created PENDING signal for {symbol} ({signal_direction} PO3 sweep of Monday range)."
                    )
                    
            scanned_count += 1
            time.sleep(1.0)
            
        except Exception as e:
            print(f"Error scanning {symbol}: {e}")
            errors_count += 1
            time.sleep(1.0)
            
    execution_time = time.time() - start_time
    
    global LATEST_WATCHLIST
    LATEST_WATCHLIST = current_watchlist
    
    if errors_count == 0:
        db.create_system_log(
            status="SUCCESS",
            message=f"PO3 Scan completed successfully. Scanned {scanned_count} symbols.",
            execution_time=round(execution_time, 2)
        )
    else:
        db.create_system_log(
            status="WARNING" if errors_count < 3 else "ERROR",
            message=f"PO3 Scan completed with {errors_count} errors. Scanned {scanned_count} symbols.",
            execution_time=round(execution_time, 2)
        )

def update_live_trades():
    """Check active and pending signals to see if they hit Entry, SL, or TP."""
    check_weekly_reset()
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
                    db.create_system_log(
                        status="SUCCESS",
                        message=f"Signal {symbol} EXPIRED: Price {current_price} breached SL {sl} before 15m trigger."
                    )
                    print(f"Signal {symbol} EXPIRED (hit SL before entry)")
                    continue
                elif direction == "SELL" and current_price > sl:
                    db.update_signal_status(signal["id"], "EXPIRED")
                    db.create_system_log(
                        status="SUCCESS",
                        message=f"Signal {symbol} EXPIRED: Price {current_price} breached SL {sl} before 15m trigger."
                    )
                    print(f"Signal {symbol} EXPIRED (hit SL before entry)")
                    continue
                
                # Fetch 15m candles to look for external structure reversal (15m CHOCH)
                df_15 = fetch_candles(symbol, "15m", limit=60)
                time.sleep(0.3) # Respect API rate limits
                
                if df_15 is not None and len(df_15) >= 15:
                    df_15_completed = df_15.iloc[:-1].copy()
                    df_swings_15 = find_swings(df_15_completed, window=5)
                    
                    if direction == "BUY":
                        swing_high_rows = df_swings_15.dropna(subset=["swing_high"])
                        if len(swing_high_rows) > 0:
                            recent_15m_swing_high = float(swing_high_rows.iloc[-1]["swing_high"])
                            last_15m_candle = df_15.iloc[-2]
                            if float(last_15m_candle["close"]) > recent_15m_swing_high:
                                is_triggered = True
                    else: # SELL
                        swing_low_rows = df_swings_15.dropna(subset=["swing_low"])
                        if len(swing_low_rows) > 0:
                            recent_15m_swing_low = float(swing_low_rows.iloc[-1]["swing_low"])
                            last_15m_candle = df_15.iloc[-2]
                            if float(last_15m_candle["close"]) < recent_15m_swing_low:
                                is_triggered = True
                                
                if is_triggered:
                    actual_entry = current_price
                    # Fetch 1H candles to find the weekly extreme high/low
                    now_utc = datetime.now(timezone.utc)
                    current_week_start = now_utc - timedelta(days=now_utc.weekday())
                    current_week_start = current_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
                    
                    df_1h = fetch_candles(symbol, "1h", limit=200)
                    week_candles = df_1h[df_1h["datetime"] >= current_week_start] if df_1h is not None else []
                    
                    if direction == "BUY":
                        actual_sl = float(week_candles["low"].min()) if len(week_candles) > 0 else sl
                        actual_sl = actual_sl * 0.9995 # 0.05% buffer
                        actual_risk = actual_entry - actual_sl
                        actual_tp = actual_entry + (2.0 * actual_risk)
                    else: # SELL
                        actual_sl = float(week_candles["high"].max()) if len(week_candles) > 0 else sl
                        actual_sl = actual_sl * 1.0005 # 0.05% buffer
                        actual_risk = actual_sl - actual_entry
                        actual_tp = actual_entry - (2.0 * actual_risk)
                        
                    updated_sig = db.update_signal_status(
                        signal["id"], 
                        "ACTIVE", 
                        actual_entry=actual_entry, 
                        actual_tp=actual_tp
                    )
                    if updated_sig:
                        db.update_signal_sl(signal["id"], actual_sl)
                        # Fetch updated signal for alert
                        full_sig = db.get_signal_by_pair(symbol)
                        tg.alert_signal_active(full_sig)
                        print(f"Signal {symbol} is now ACTIVE (Confirmed by 15m Reversal at entry {actual_entry}, TP {actual_tp}, SL {actual_sl})")
                        db.create_system_log(
                            status="SUCCESS",
                            message=f"Signal {symbol} is now ACTIVE (Confirmed by 15m Reversal at entry {actual_entry}, TP {actual_tp}, SL {actual_sl})."
                        )
                        
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
                        db.create_system_log(
                            status="SUCCESS",
                            message=f"Signal {symbol} hit TAKE PROFIT (TP) at {current_price}."
                        )
                elif is_sl:
                    updated_sig = db.update_signal_status(signal["id"], "SL_HIT", current_price)
                    if updated_sig:
                        tg.alert_signal_closed(updated_sig, "SL_HIT")
                        print(f"Signal {symbol} hit STOP LOSS (SL)")
                        db.create_system_log(
                            status="SUCCESS",
                            message=f"Signal {symbol} hit STOP LOSS (SL) at {current_price}."
                        )
                        
        except Exception as e:
            print(f"Error updating active trade for {symbol}: {e}")

def get_current_watchlist():
    """Retrieve the cached watchlist collected in the last scan."""
    global LATEST_WATCHLIST
    return LATEST_WATCHLIST
