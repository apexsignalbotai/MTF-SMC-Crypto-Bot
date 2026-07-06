import os
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message: str):
    """Send a formatted telegram alert to the specified chat group/user."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram configuration is incomplete. Message not sent.")
        print(f"[DEBUG TELEGRAM]: {message}")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True
        else:
            print(f"Telegram API error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")
        return False

def format_holding_time(seconds: int) -> str:
    """Format seconds into human-readable duration."""
    if not seconds:
        return "N/A"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}h {minutes}m"

def alert_new_signal(signal: dict):
    """Format and send a Telegram alert for a newly detected signal."""
    direction_emoji = "🟢 *BUY (LONG)*" if signal["direction"] == "BUY" else "🔴 *SELL (SHORT)*"
    
    message = (
        f"📊 *NEW SMC SIGNAL DETECTED* 📊\n\n"
        f"🪙 *Pair:* {signal['pair']}\n"
        f"⚡ *Direction:* {direction_emoji}\n"
        f"⚙️ *Setup:* {signal['trigger_type']}\n\n"
        f"📥 *Entry Zone:* {signal['entry_price']}\n"
        f"🛡️ *Stop Loss:* {signal['sl_price']}\n"
        f"🎯 *Take Profit (1:2):* {signal['tp_price']}\n\n"
        f"🕒 _Status: Pending Entry. Monitor card on web dashboard._"
    )
    send_telegram_message(message)

def alert_signal_active(signal: dict):
    """Send alert when price hits the entry zone and position becomes ACTIVE."""
    message = (
        f"🚀 *TRADE ACTIVATED* 🚀\n\n"
        f"🪙 *Pair:* {signal['pair']}\n"
        f"⚡ *Direction:* {'LONG 🟢' if signal['direction'] == 'BUY' else 'SHORT 🔴'}\n"
        f"📥 *Entry Price:* {signal['entry_price']}\n"
        f"🎯 *TP:* {signal['tp_price']} | 🛡️ *SL:* {signal['sl_price']}\n\n"
        f"📈 _Trade is now live! Monitor performance on the dashboard._"
    )
    send_telegram_message(message)

def alert_signal_closed(signal: dict, outcome: str):
    """Send alert when position hits TP or SL."""
    emoji = "🏆" if outcome == "TP_HIT" else "❌"
    result_text = "🎉 *TAKE PROFIT HIT (TP)*" if outcome == "TP_HIT" else "📉 *STOP LOSS HIT (SL)*"
    holding = format_holding_time(signal.get("holding_time", 0))
    
    message = (
        f"{emoji} *TRADE CLOSED* {emoji}\n\n"
        f"🪙 *Pair:* {signal['pair']}\n"
        f"⚡ *Direction:* {'LONG' if signal['direction'] == 'BUY' else 'SHORT'}\n"
        f"📊 *Outcome:* {result_text}\n"
        f"📥 *Entry Price:* {signal['entry_price']}\n"
        f"🎯 *Target Price:* {signal['tp_price'] if outcome == 'TP_HIT' else signal['sl_price']}\n"
        f"⏱️ *Holding Duration:* {holding}\n\n"
        f"💹 _Dashboard has been updated._"
    )
    send_telegram_message(message)
