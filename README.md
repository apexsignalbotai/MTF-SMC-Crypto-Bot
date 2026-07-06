# MTF SMC Crypto Trading Bot

A multi-timeframe (MTF) Smart Money Concepts (SMC) crypto trading bot. It automatically scans top coins, marks weekly key levels, identifies 1-hour BOS (Break of Structure) and CHOCH (Change of Character), and calculates Fibonacci OTE (Optimal Trade Entry) zones.

## Features

- **Weekly High/Low Tracker**: Automatically fetches previous week's candle high and low at candle close.
- **Hourly Scanner**: Scans markets every hour using CCXT to detect 1H sweeps or body breaks of the weekly levels.
- **SMC Setup (BOS/CHOCH)**: Performs 1H swing analysis to identify structural shifts (BOS/CHOCH) on body closes.
- **Fibonacci OTE Entry**: Calculates OTE entry (0.5 to 0.618 Fib zone) with SL at the leg origin and 1:2 Risk-to-Reward TP.
- **Live React Dashboard**: Beautiful glassmorphic UI showcasing active signals, live WebSocket price feeds, holding timers, live signal P&L, monthly history, and total P&L.
- **Telegram Notifications**: Instantly alerts users via Telegram bot when new setups form or positions hit TP/SL.
- **Supabase Integration**: Stores signal data, states, and history automatically.

---

## Directory Structure

```text
├── backend/
│   ├── main.py                 # FastAPI Application Server
│   ├── scanner.py              # SMC Logic, Scanner & CCXT Fetching
│   ├── supabase_client.py      # Supabase database interaction layer
│   ├── telegram_bot.py         # Telegram alerts client
│   └── requirements.txt        # Python backend dependencies
│
├── frontend/                   # React + Vite Dashboard
│   ├── src/
│   ├── package.json            # React/Vite dependencies
│   └── vite.config.js          # Vite configuration
│
├── README.md                   # Project overview
└── guideme.md                  # Detailed deployment and setup guide
```

---

## Technical Details

- **Backend**: Python 3.10+, FastAPI, CCXT, Pandas, Supabase-py.
- **Frontend**: React (Vite), CSS3, Tailwind CSS (optional, default is custom CSS).
- **Database**: Supabase (PostgreSQL).
- **WS API**: Binance Public WebSocket.
- **Deployment**: Vercel (Frontend) and Render (Backend).
