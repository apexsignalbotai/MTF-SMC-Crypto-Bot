import requests
from datetime import datetime, timezone

# Module-level cache variables
_cached_events = None
_last_fetch_time = None

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

def fetch_high_impact_news() -> list:
    """
    Fetch and return all high-impact economic news events scheduled for today.
    Fetches from EODHD and DailyFX APIs.
    """
    events_list = []
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    
    # 1. EODHD API Check (Demo token allows free public economic events)
    try:
        url = f"https://eodhd.com/api/economic-calendar?api_token=demo&from={today_str}&to={today_str}&fmt=json"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            for event in data:
                impact = event.get("impact", "")
                currency = event.get("currency", "")
                if impact and impact.upper() == "HIGH" and currency:
                    event_date_str = event.get("date", "")
                    if event_date_str:
                        # EODHD date format: "YYYY-MM-DD HH:MM:SS" (UTC)
                        event_time = datetime.strptime(event_date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        events_list.append({
                            "currency": currency.upper(),
                            "time": event_time,
                            "name": event.get("event", "Economic Event")
                        })
    except Exception as e:
        print(f"[NEWS FILTER] Warning: EODHD economic calendar fetch failed: {e}")
        
    # 2. Dual-fallback: DailyFX calendar
    try:
        url = "https://calendar-api.dailyfx.com/calendar"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            for event in data:
                importance = event.get("importance", "")
                currency = event.get("currency", "")
                if importance and importance.upper() == "HIGH" and currency:
                    event_date_str = event.get("date", "")
                    if event_date_str:
                        # DailyFX date format: ISO string "2026-07-09T14:30:00Z"
                        event_date_str = event_date_str.replace("Z", "+00:00")
                        event_time = datetime.fromisoformat(event_date_str)
                        events_list.append({
                            "currency": currency.upper(),
                            "time": event_time,
                            "name": event.get("title", "Economic Event")
                        })
    except Exception as e:
        print(f"[NEWS FILTER] Warning: DailyFX calendar fetch failed: {e}")
        
    return events_list

def is_news_time(symbol: str) -> bool:
    """
    Check if there is high impact news for the symbol's currencies within +-30 minutes.
    Uses cached events if fetched within the last 5 minutes (300 seconds) to avoid spamming APIs.
    """
    global _cached_events, _last_fetch_time
    now = datetime.now(timezone.utc)
    
    # Refresh cache if missing or older than 5 minutes
    if _cached_events is None or _last_fetch_time is None or (now - _last_fetch_time).total_seconds() > 300:
        print("[NEWS FILTER] Fetching fresh economic calendar events...")
        _cached_events = fetch_high_impact_news()
        _last_fetch_time = now
        print(f"[NEWS FILTER] Successfully cached {len(_cached_events)} high-impact events for today.")
        
    currencies = get_currencies_for_symbol(symbol)
    for event in _cached_events:
        if event["currency"] in currencies:
            time_diff = abs((now - event["time"]).total_seconds())
            if time_diff <= 1800:  # 30 minutes in seconds
                print(f"[NEWS FILTER] Blocking setup for {symbol}: High impact news '{event['name']}' ({event['currency']}) at {event['time']}.")
                return True
                
    return False
