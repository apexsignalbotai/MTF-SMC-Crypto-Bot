import requests
from datetime import datetime, timezone

def get_currencies_for_symbol(symbol: str):
    """Extract currency names from pair name. e.g. GBP/USDT:USDT -> ['GBP', 'USD']"""
    symbol_upper = symbol.upper()
    # Split by / and :
    clean = symbol_upper.replace(":", "/").split("/")
    currencies = []
    for c in clean:
        if c in ["USDT", "USDC"]:
            currencies.append("USD")
        elif c in ["GOLD", "XAU"]:
            currencies.append("USD")
            currencies.append("XAU")
        elif c in ["CL", "CRUDE"]:
            currencies.append("USD")
            currencies.append("CL")
        else:
            currencies.append(c)
    return list(set(currencies))

def is_news_time(symbol: str) -> bool:
    """
    Check if there is high impact news for the symbol's currencies within +-30 minutes.
    Fail-safe: returns False on any connection/parsing errors to avoid blocking scans.
    """
    currencies = get_currencies_for_symbol(symbol)
    now = datetime.now(timezone.utc)
    
    # 1. EODHD API Check (Demo token allows free public economic events)
    try:
        today_str = now.strftime("%Y-%m-%d")
        url = f"https://eodhd.com/api/economic-calendar?api_token=demo&from={today_str}&to={today_str}&fmt=json"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            events = res.json()
            for event in events:
                impact = event.get("impact", "")
                event_currency = event.get("currency", "")
                
                # Check for High Impact news matching our currencies
                if impact and impact.upper() == "HIGH" and event_currency in currencies:
                    event_date_str = event.get("date", "")
                    if event_date_str:
                        # EODHD date format: "YYYY-MM-DD HH:MM:SS" (UTC)
                        event_time = datetime.strptime(event_date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        time_diff = abs((now - event_time).total_seconds())
                        if time_diff <= 1800:  # 30 minutes in seconds
                            print(f"[NEWS FILTER] Blocking setup for {symbol}: High impact news '{event.get('event')}' ({event_currency}) at {event_date_str} UTC.")
                            return True
    except Exception as e:
        print(f"[NEWS FILTER] Warning: EODHD economic calendar fetch failed: {e}")
        
    # 2. Dual-fallback: DailyFX calendar
    try:
        url = "https://calendar-api.dailyfx.com/calendar"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            events = res.json()
            for event in events:
                importance = event.get("importance", "")
                event_currency = event.get("currency", "")
                
                if importance and importance.upper() == "HIGH" and event_currency.upper() in currencies:
                    event_date_str = event.get("date", "")
                    if event_date_str:
                        # DailyFX date format: ISO string "2026-07-09T14:30:00Z"
                        event_date_str = event_date_str.replace("Z", "+00:00")
                        event_time = datetime.fromisoformat(event_date_str)
                        time_diff = abs((now - event_time).total_seconds())
                        if time_diff <= 1800:  # 30 minutes
                            print(f"[NEWS FILTER] Blocking setup for {symbol}: High impact news '{event.get('title')}' ({event_currency}) at {event_date_str}.")
                            return True
    except Exception as e:
        print(f"[NEWS FILTER] Warning: DailyFX calendar fetch failed: {e}")
        
    return False
