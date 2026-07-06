import os
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager

import scanner as sc
import supabase_client as db

# Initialize scheduler
scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: start scheduler
    print("Starting background scheduler...")
    
    # Run active trades checker every 1 minute
    scheduler.add_job(sc.update_live_trades, 'interval', minutes=1, id='update_trades_job')
    
    # Run market scanner every 1 hour (on the hour)
    scheduler.add_job(sc.scan_all_markets, 'cron', hour='*', minute='0', id='market_scan_job')
    
    # Start scheduler
    scheduler.start()
    
    # Trigger scan immediately on startup to populate watchlist/signals cache
    from fastapi.concurrency import run_in_threadpool
    import asyncio
    asyncio.create_task(run_in_threadpool(sc.scan_all_markets))
    
    yield
    # Shutdown: stop scheduler
    print("Shutting down background scheduler...")
    scheduler.shutdown()

app = FastAPI(
    title="MTF SMC Crypto Bot API",
    description="Backend API for scanning SMC market structures and alerting via Telegram",
    lifespan=lifespan
)

# CORS Setup for Frontend integration (Vercel deployment)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace with Vercel frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "scheduler_running": scheduler.running}

@app.get("/api/signals/active")
def get_active_signals():
    """Endpoint for frontend to retrieve active and pending signal cards."""
    return db.get_active_signals()

@app.get("/api/watchlist")
def get_watchlist():
    """Endpoint for frontend to retrieve symbols currently monitored for setups."""
    return sc.get_current_watchlist()

@app.get("/api/signals/history")
def get_signals_history():
    """Endpoint for frontend to retrieve past closed trades."""
    return db.get_monthly_history()

@app.get("/api/signals/stats")
def get_signals_stats():
    """Calculate and return monthly P&L, win rate, and total trades metrics."""
    history = db.get_monthly_history()
    
    total_trades = len(history)
    tp_hits = sum(1 for t in history if t["status"] == "TP_HIT")
    sl_hits = sum(1 for t in history if t["status"] == "SL_HIT")
    expired = sum(1 for t in history if t["status"] == "EXPIRED")
    
    # Calculate P&L in terms of 'R' (Risk units)
    # TP is 1:2 R:R, so TP_HIT = +2R, SL_HIT = -1R
    net_r = (tp_hits * 2.0) - (sl_hits * 1.0)
    
    win_rate = 0.0
    completed_trades = tp_hits + sl_hits
    if completed_trades > 0:
        win_rate = round((tp_hits / completed_trades) * 100, 2)
        
    return {
        "total_trades": total_trades,
        "completed_trades": completed_trades,
        "tp_hits": tp_hits,
        "sl_hits": sl_hits,
        "expired": expired,
        "win_rate_percent": win_rate,
        "net_pnl_r": round(net_r, 2)
    }

@app.get("/api/logs")
def get_system_logs(limit: int = 50):
    """Endpoint for frontend to retrieve recent system audit logs."""
    return db.get_system_logs(limit)

@app.post("/api/scan")
def trigger_manual_scan(background_tasks: BackgroundTasks):
    """Endpoint to manually trigger a market scan (for manual testing/UI refresh)."""
    background_tasks.add_task(sc.scan_all_markets)
    return {"status": "Scan initiated in background"}

@app.post("/api/update-trades")
def trigger_manual_trade_update(background_tasks: BackgroundTasks):
    """Endpoint to manually trigger active trades check."""
    background_tasks.add_task(sc.update_live_trades)
    return {"status": "Trade updates initiated in background"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
