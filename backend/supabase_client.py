import os
from datetime import datetime, timezone
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase_client: Client = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Error initializing Supabase client: {e}")
else:
    print("WARNING: Supabase environment variables missing.")

def get_active_signals():
    """Fetch signals that are PENDING or ACTIVE."""
    if not supabase_client:
        return []
    try:
        response = supabase_client.table("signals")\
            .select("*")\
            .in_("status", ["PENDING", "ACTIVE"])\
            .execute()
        return response.data
    except Exception as e:
        print(f"Error getting active signals: {e}")
        return []

def get_signal_by_pair(pair: str):
    """Fetch the latest pending/active signal for a specific pair to prevent duplicates."""
    if not supabase_client:
        return None
    try:
        response = supabase_client.table("signals")\
            .select("*")\
            .eq("pair", pair)\
            .in_("status", ["PENDING", "ACTIVE"])\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error getting signal by pair: {e}")
        return None

def create_signal(pair: str, direction: str, trigger_type: str, entry: float, sl: float, tp: float):
    """Create a new trading signal."""
    if not supabase_client:
        return None
    try:
        data = {
            "pair": pair,
            "direction": direction,
            "trigger_type": trigger_type,
            "entry_price": entry,
            "sl_price": sl,
            "tp_price": tp,
            "status": "PENDING",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        response = supabase_client.table("signals").insert(data).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error creating signal: {e}")
        return None

def update_signal_status(signal_id: str, status: str, close_price: float = None):
    """Update active/pending signal status (e.g. TP_HIT, SL_HIT, ACTIVE, EXPIRED)."""
    if not supabase_client:
        return None
    try:
        now = datetime.now(timezone.utc)
        
        # First, fetch signal to calculate holding time
        sig_resp = supabase_client.table("signals").select("*").eq("id", signal_id).execute()
        if not sig_resp.data:
            return None
        signal = sig_resp.data[0]
        
        data = {
            "status": status,
        }
        
        if status in ["TP_HIT", "SL_HIT", "EXPIRED"]:
            data["closed_at"] = now.isoformat()
            
            # Calculate holding time in seconds
            created_at = datetime.fromisoformat(signal["created_at"].replace("Z", "+00:00"))
            holding_seconds = int((now - created_at).total_seconds())
            data["holding_time"] = holding_seconds
            
        response = supabase_client.table("signals").update(data).eq("id", signal_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error updating signal status: {e}")
        return None

def get_monthly_history():
    """Retrieve closed signal history for the current and previous month."""
    if not supabase_client:
        return []
    try:
        # History is automatically pruned in database trigger, so we can fetch all closed trades
        response = supabase_client.table("signals")\
            .select("*")\
            .in_("status", ["TP_HIT", "SL_HIT", "EXPIRED"])\
            .order("closed_at", desc=True)\
            .execute()
        return response.data
    except Exception as e:
        print(f"Error fetching closed history: {e}")
        return []
