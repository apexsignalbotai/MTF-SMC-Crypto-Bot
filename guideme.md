# MTF SMC Crypto Bot Setup & Deployment Guide

This guide details the step-by-step instructions to set up the database (Supabase), run the bot locally, and deploy it to production (Vercel & Render).

---

## 1. Supabase Database Setup

Create a free project on [Supabase](https://supabase.com/). Go to the **SQL Editor** in your Supabase dashboard and run the following script to create the necessary tables, indexes, and automatic database cleaning trigger:

```sql
-- 1. Create Signals Table
CREATE TABLE IF NOT EXISTS public.signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pair TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    trigger_type TEXT NOT NULL CHECK (trigger_type IN ('BOS', 'CHOCH')),
    entry_price NUMERIC NOT NULL,
    sl_price NUMERIC NOT NULL,
    tp_price NUMERIC NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'ACTIVE', 'TP_HIT', 'SL_HIT', 'EXPIRED')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    closed_at TIMESTAMP WITH TIME ZONE,
    holding_time INTEGER -- Duration in seconds
);

-- Indexing for performance
CREATE INDEX IF NOT EXISTS idx_signals_pair ON public.signals(pair);
CREATE INDEX IF NOT EXISTS idx_signals_status ON public.signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_created_at ON public.signals(created_at);

-- 2. Create automatic history cleanup function (keeps only current month and last month)
CREATE OR REPLACE FUNCTION clean_old_signals_history() 
RETURNS trigger AS $$
BEGIN
    -- Delete records older than the first day of the previous month
    DELETE FROM public.signals
    WHERE created_at < date_trunc('month', current_date - interval '1 month');
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- 3. Create Trigger to run cleanup on insert
CREATE OR REPLACE TRIGGER trigger_clean_old_signals
AFTER INSERT ON public.signals
FOR EACH STATEMENT
EXECUTE FUNCTION clean_old_signals_history();

-- 4. Create System Audit Logs Table
CREATE TABLE IF NOT EXISTS public.system_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status TEXT NOT NULL CHECK (status IN ('SUCCESS', 'ERROR')),
    message TEXT NOT NULL,
    execution_time NUMERIC, -- in seconds
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_logs_created_at ON public.system_logs(created_at);

-- 5. Create automatic logs cleanup trigger (keeps logs for 14 days)
CREATE OR REPLACE FUNCTION clean_old_logs() 
RETURNS trigger AS $$
BEGIN
    DELETE FROM public.system_logs
    WHERE created_at < now() - interval '14 days';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trigger_clean_old_logs
AFTER INSERT ON public.system_logs
FOR EACH STATEMENT
EXECUTE FUNCTION clean_old_logs();

-- 6. Disable Row Level Security (RLS) to allow inserts via API Key
ALTER TABLE public.signals DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_logs DISABLE ROW LEVEL SECURITY;
```

---

## 2. Environment Variables Configuration

Both the frontend and backend require setup via environment variables.

### Backend `.env` (Render / Local)
Create a `.env` file inside the `backend/` directory:
```env
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-supabase-service-role-key-or-anon-key
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_CHAT_ID=-1001234567890
PORT=8000
```

### Frontend `.env` (Vercel / Local)
Create a `.env` file inside the `frontend/` directory (Vite requires variables to start with `VITE_`):
```env
VITE_SUPABASE_URL=https://your-project-id.supabase.co
VITE_SUPABASE_KEY=your-supabase-anon-key
VITE_BACKEND_URL=https://your-backend-app.onrender.com
```

---

## 3. Local Development

### Running the Backend (Python)
1. Navigate to the `backend/` directory.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the FastAPI server:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

### Running the Frontend (React + Vite)
1. Navigate to the `frontend/` directory.
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the Vite dev server:
   ```bash
   npm run dev
   ```

---

## 4. Production Deployment

### Backend (Render)
1. Connect your Github repository to [Render](https://render.com/).
2. Create a new **Web Service**.
3. Select **Python** runtime environment.
4. Set the **Build Command**:
   ```bash
   pip install -r backend/requirements.txt
   ```
5. Set the **Start Command**:
   ```bash
   uvicorn backend.main:app --host 0.0.0.0 --port $PORT
   ```
6. Add the environment variables from the Backend `.env` section in the Render "Environment" settings.

### Frontend (Vercel)
1. Connect your Github repository to [Vercel](https://vercel.com/).
2. Select the `frontend/` directory as the root of the project.
3. Vercel will automatically detect **Vite** and configure the build settings.
4. Add the environment variables from the Frontend `.env` section in the Vercel project settings.
5. Deploy!
