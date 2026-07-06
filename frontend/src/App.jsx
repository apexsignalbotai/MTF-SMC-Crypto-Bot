import React, { useState, useEffect, useRef } from 'react'
import { supabase } from './supabase'
import { 
  TrendingUp, 
  TrendingDown, 
  Activity, 
  History, 
  Clock, 
  DollarSign, 
  Percent, 
  RefreshCw, 
  AlertTriangle,
  Play,
  CheckCircle,
  XCircle,
  HelpCircle
} from 'lucide-react'

// Fallback Mock Data if Supabase is not configured yet
const MOCK_SIGNALS = [
  {
    id: "1",
    pair: "BTC/USDT",
    direction: "BUY",
    trigger_type: "CHOCH",
    entry_price: 58500.0,
    sl_price: 57800.0,
    tp_price: 59900.0,
    status: "ACTIVE",
    created_at: new Date(Date.now() - 3 * 3600 * 1000).toISOString(), // 3 hours ago
    closed_at: null
  },
  {
    id: "2",
    pair: "ETH/USDT",
    direction: "SELL",
    trigger_type: "BOS",
    entry_price: 3120.0,
    sl_price: 3180.0,
    tp_price: 3000.0,
    status: "PENDING",
    created_at: new Date(Date.now() - 1 * 3600 * 1000).toISOString(), // 1 hour ago
    closed_at: null
  }
]

const MOCK_HISTORY = [
  {
    id: "3",
    pair: "SOL/USDT",
    direction: "BUY",
    trigger_type: "CHOCH",
    entry_price: 135.0,
    sl_price: 130.0,
    tp_price: 145.0,
    status: "TP_HIT",
    created_at: new Date(Date.now() - 24 * 3600 * 1000).toISOString(),
    closed_at: new Date(Date.now() - 20 * 3600 * 1000).toISOString(),
    holding_time: 14400
  },
  {
    id: "4",
    pair: "LINK/USDT",
    direction: "SELL",
    trigger_type: "BOS",
    entry_price: 14.5,
    sl_price: 15.0,
    tp_price: 13.5,
    status: "SL_HIT",
    created_at: new Date(Date.now() - 48 * 3600 * 1000).toISOString(),
    closed_at: new Date(Date.now() - 44 * 3600 * 1000).toISOString(),
    holding_time: 14400
  }
]

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000"

export default function App() {
  const [activeSignals, setActiveSignals] = useState([])
  const [history, setHistory] = useState([])
  const [stats, setStats] = useState({
    total_trades: 0,
    completed_trades: 0,
    tp_hits: 0,
    sl_hits: 0,
    expired: 0,
    win_rate_percent: 0,
    net_pnl_r: 0
  })
  const [livePrices, setLivePrices] = useState({})
  const [priceDirections, setPriceDirections] = useState({})
  const [isConfigured, setIsConfigured] = useState(true)
  const [backendAlive, setBackendAlive] = useState(false)
  const [isScanning, setIsScanning] = useState(false)
  const [scanMessage, setScanMessage] = useState("")
  const [elapsedTimes, setElapsedTimes] = useState({})
  
  const wsRef = useRef(null)

  // Fetch signals & stats
  const fetchData = async () => {
    try {
      let activeData = []
      let historyData = []

      // Try fetching from Supabase directly
      if (supabase) {
        setIsConfigured(true)
        
        // Fetch Active
        const { data: active, error: activeErr } = await supabase
          .from('signals')
          .select('*')
          .in('status', ['PENDING', 'ACTIVE'])
          .order('created_at', { ascending: false })
          
        if (!activeErr) activeData = active || []

        // Fetch History
        const { data: hist, error: histErr } = await supabase
          .from('signals')
          .select('*')
          .in('status', ['TP_HIT', 'SL_HIT', 'EXPIRED'])
          .order('closed_at', { ascending: false })
          
        if (!histErr) historyData = hist || []
      } else {
        // Use Mock data
        setIsConfigured(false)
        activeData = MOCK_SIGNALS
        historyData = MOCK_HISTORY
      }

      setActiveSignals(activeData)
      setHistory(historyData)
      calculateMetrics(historyData)

      // Ping Backend to keep Render instance alive
      pingBackend()

    } catch (error) {
      console.error("Error fetching signals/history:", error)
    }
  }

  // Calculate stats on client side as backup or direct database reader
  const calculateMetrics = (histList) => {
    const total = histList.length
    const tp = histList.filter(t => t.status === 'TP_HIT').length
    const sl = histList.filter(t => t.status === 'SL_HIT').length
    const exp = histList.filter(t => t.status === 'EXPIRED').length
    const completed = tp + sl
    const winRate = completed > 0 ? ((tp / completed) * 100).toFixed(2) : 0
    const netPnL = (tp * 2.0) - (sl * 1.0) // 1:2 R:R

    setStats({
      total_trades: total,
      completed_trades: completed,
      tp_hits: tp,
      sl_hits: sl,
      expired: exp,
      win_rate_percent: winRate,
      net_pnl_r: netPnL.toFixed(2)
    })
  }

  // Ping Backend (keeps Render instance awake & updates state)
  const pingBackend = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/health`)
      if (res.ok) {
        setBackendAlive(true)
      } else {
        setBackendAlive(false)
      }
    } catch {
      setBackendAlive(false)
    }
  }

  // Trigger manual scanner
  const triggerScan = async () => {
    setIsScanning(true)
    setScanMessage("Scanning markets...")
    try {
      const res = await fetch(`${BACKEND_URL}/api/scan`, { method: 'POST' })
      if (res.ok) {
        setScanMessage("Scan triggered successfully!")
        setTimeout(() => {
          setScanMessage("")
          fetchData()
        }, 3000)
      } else {
        setScanMessage("Failed to connect to backend.")
      }
    } catch (e) {
      setScanMessage("Backend offline.")
    } finally {
      setIsScanning(false)
    }
  }

  // Effect for 1-minute auto-refresh (heartbeat to keep app active)
  useEffect(() => {
    fetchData()
    const dataInterval = setInterval(() => {
      console.log("Refreshing data (1m auto-refresh)...")
      fetchData()
    }, 60000) // 1 minute auto refresh

    return () => clearInterval(dataInterval)
  }, [])

  // Timer effect for live active/pending cards elapsed time
  useEffect(() => {
    const timerInterval = setInterval(() => {
      const newElapsed = {}
      activeSignals.forEach(sig => {
        const created = new Date(sig.created_at)
        const diffSeconds = Math.floor((new Date() - created) / 1000)
        
        const h = Math.floor(diffSeconds / 3600)
        const m = Math.floor((diffSeconds % 3600) / 60)
        const s = diffSeconds % 60
        
        newElapsed[sig.id] = `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
      })
      setElapsedTimes(newElapsed)
    }, 1000)

    return () => clearInterval(timerInterval)
  }, [activeSignals])

  // Setup WebSocket connection to Binance for active signals live price updates
  useEffect(() => {
    if (activeSignals.length === 0) {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      return
    }

    // Connect to Binance Spot WebSocket API
    const wsUrl = "wss://stream.binance.com:9443/ws"
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      // Subscribing to raw tickers, e.g. "btcusdt@ticker"
      const streams = activeSignals.map(sig => {
        const symbolClean = sig.pair.replace('/', '').toLowerCase()
        return `${symbolClean}@ticker`
      })
      
      const payload = {
        method: "SUBSCRIBE",
        params: streams,
        id: 1
      }
      ws.send(JSON.stringify(payload))
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.e === "24hrTicker") {
        const cleanSymbol = data.s // e.g. BTCUSDT
        const lastPrice = parseFloat(data.c)
        
        // Find matching pair format
        const pair = activeSignals.find(s => s.pair.replace('/', '') === cleanSymbol)?.pair
        
        if (pair) {
          setLivePrices(prev => {
            const oldPrice = prev[pair]
            
            // Set direction indicator (green flash vs red flash)
            if (oldPrice) {
              setPriceDirections(dirPrev => ({
                ...dirPrev,
                [pair]: lastPrice > oldPrice ? "up" : lastPrice < oldPrice ? "down" : dirPrev[pair]
              }))
            }
            return {
              ...prev,
              [pair]: lastPrice
            }
          })
        }
      }
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [activeSignals])

  // Calculate live signal P&L
  const getLivePnL = (sig) => {
    const currentPrice = livePrices[sig.pair]
    if (!currentPrice || sig.status === 'PENDING') return { r: 0, percent: 0, text: "0.00%", class: "neutral" }
    
    const entry = sig.entry_price
    const sl = sig.sl_price
    const direction = sig.direction
    
    let pnlR = 0
    let pnlPercent = 0
    
    if (direction === 'BUY') {
      pnlPercent = ((currentPrice - entry) / entry) * 100
      pnlR = (currentPrice - entry) / (entry - sl)
    } else {
      pnlPercent = ((entry - currentPrice) / entry) * 100
      pnlR = (entry - currentPrice) / (sl - entry)
    }

    // Cap R value estimation or format
    const rFormatted = pnlR.toFixed(2)
    const pnlFormatted = pnlPercent.toFixed(2)
    
    return {
      r: pnlR,
      percent: pnlPercent,
      text: `${pnlPercent >= 0 ? '+' : ''}${pnlFormatted}% (${rFormatted}R)`,
      class: pnlPercent > 0 ? "plus" : pnlPercent < 0 ? "minus" : "neutral"
    }
  }

  return (
    <div className="container">
      {/* Header */}
      <header>
        <div className="logo-section">
          <div className="logo-icon">
            <Activity size={24} color="#fff" />
          </div>
          <div>
            <h1>MTF SMC Crypto Bot</h1>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              1H SMC Retracement (0.5 - 0.618 Fib OTE)
            </div>
          </div>
        </div>
        
        <div style={{ display: 'flex', gap: '15px', alignItems: 'center' }}>
          {/* Heartbeat Status Indicator */}
          <div className="status-badge">
            <div className="status-dot" style={{ backgroundColor: backendAlive ? 'var(--accent-green)' : 'var(--accent-red)', boxShadow: backendAlive ? '0 0 10px var(--accent-green)' : '0 0 10px var(--accent-red)' }} />
            <span>Bot Engine: {backendAlive ? "ONLINE" : "OFFLINE"}</span>
          </div>

          <button 
            className="action-button" 
            onClick={triggerScan} 
            disabled={isScanning}
          >
            <RefreshCw className={isScanning ? "spin" : ""} size={16} />
            Scan Markets
          </button>
        </div>
      </header>

      {scanMessage && (
        <div style={{ 
          background: 'rgba(59, 130, 246, 0.1)', 
          border: '1px solid var(--accent-blue)', 
          borderRadius: '12px', 
          padding: '12px 16px', 
          marginBottom: '2rem',
          fontSize: '0.9rem',
          display: 'flex',
          alignItems: 'center',
          gap: '8px'
        }}>
          <Activity size={16} color="var(--accent-blue)" />
          {scanMessage}
        </div>
      )}

      {!isConfigured && (
        <div style={{ 
          background: 'rgba(245, 158, 11, 0.1)', 
          border: '1px solid var(--accent-yellow)', 
          borderRadius: '12px', 
          padding: '16px', 
          marginBottom: '2.5rem',
          display: 'flex',
          gap: '12px',
          alignItems: 'flex-start'
        }}>
          <AlertTriangle size={20} color="var(--accent-yellow)" style={{ flexShrink: 0 }} />
          <div>
            <h4 style={{ color: '#fff', marginBottom: '4px', fontWeight: 600 }}>Demo Mode (Database variables not set)</h4>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Supabase parameters match key guidelines. Running in Mock Demo Mode. To connect actual live signals, please set your `.env` variables according to the <a href="file:///c:/Users/Waqas%20Zulfiqar/Desktop/MTF%20SMC%20Crypto/guideme.md" style={{ color: 'var(--accent-blue)', textDecoration: 'underline' }}>guideme.md</a> configuration.
            </p>
          </div>
        </div>
      )}

      {/* Stats Summary Panel */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-header">
            <span>Win Rate</span>
            <Percent size={18} color="var(--accent-purple)" />
          </div>
          <div className="stat-value" style={{ color: parseFloat(stats.win_rate_percent) >= 50 ? 'var(--accent-green)' : 'inherit' }}>
            {stats.win_rate_percent}%
          </div>
        </div>

        <div className={`stat-card ${parseFloat(stats.net_pnl_r) > 0 ? 'pnl-positive' : parseFloat(stats.net_pnl_r) < 0 ? 'pnl-negative' : ''}`}>
          <div className="stat-header">
            <span>Monthly Net P&L</span>
            <DollarSign size={18} />
          </div>
          <div className="stat-value">
            {parseFloat(stats.net_pnl_r) >= 0 ? '+' : ''}{stats.net_pnl_r} R
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <span>Total Signals</span>
            <Activity size={18} color="var(--accent-blue)" />
          </div>
          <div className="stat-value">
            {stats.total_trades}
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-header">
            <span>TP Hits / SL Hits</span>
            <CheckCircle size={18} color="var(--accent-green)" />
          </div>
          <div className="stat-value" style={{ fontSize: '1.6rem' }}>
            {stats.tp_hits} <span style={{ color: 'var(--text-muted)', fontSize: '1.2rem' }}>/</span> {stats.sl_hits}
          </div>
        </div>
      </div>

      {/* Main Dashboard Layout */}
      <div className="dashboard-layout">
        {/* Left Column: Active Signals */}
        <div>
          <h2 className="section-title">
            <Activity size={20} color="var(--accent-blue)" />
            Active watchlist & signals
          </h2>
          
          <div className="signals-grid">
            {activeSignals.length > 0 ? (
              activeSignals.map(sig => {
                const livePrice = livePrices[sig.pair]
                const pnl = getLivePnL(sig)
                const priceDir = priceDirections[sig.pair] || ""
                
                return (
                  <div key={sig.id} className={`signal-card ${sig.direction.toLowerCase()}`}>
                    <div className="signal-header">
                      <div>
                        <div className="signal-pair">{sig.pair}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                          Opened: {new Date(sig.created_at).toLocaleTimeString()}
                        </div>
                      </div>
                      <div className="signal-type-badge">
                        {sig.trigger_type}
                      </div>
                    </div>

                    <div className={`direction-row ${sig.direction.toLowerCase()}`}>
                      {sig.direction === 'BUY' ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                      <span>{sig.direction === 'BUY' ? 'BULLISH RETRACEMENT (LONG)' : 'BEARISH RETRACEMENT (SHORT)'}</span>
                    </div>

                    {/* Live price block */}
                    <div className="live-price-box">
                      <span className="live-price-label">Live Price</span>
                      <span className={`live-price-value ${priceDir === 'up' ? 'price-up' : priceDir === 'down' ? 'price-down' : ''}`}>
                        {livePrice ? `$${livePrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}` : 'Waiting for WS...'}
                      </span>
                    </div>

                    {/* Price parameters */}
                    <div className="param-list">
                      <div className="param-item">
                        <span className="param-label">Retracement Entry</span>
                        <span className="param-value">${sig.entry_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</span>
                      </div>
                      <div className="param-item">
                        <span className="param-label">Stop Loss (SL)</span>
                        <span className="param-value" style={{ color: 'var(--accent-red)' }}>${sig.sl_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</span>
                      </div>
                      <div className="param-item">
                        <span className="param-label">Take Profit (TP)</span>
                        <span className="param-value" style={{ color: 'var(--accent-green)' }}>${sig.tp_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</span>
                      </div>
                      <div className="param-item">
                        <span className="param-label">Status</span>
                        <span className="param-value" style={{ 
                          color: sig.status === 'ACTIVE' ? 'var(--accent-green)' : 'var(--accent-yellow)',
                          fontWeight: 'bold',
                          fontSize: '0.8rem',
                          letterSpacing: '0.5px'
                        }}>
                          {sig.status}
                        </span>
                      </div>
                    </div>

                    {/* Card footer details */}
                    <div className="card-footer">
                      <div className="timer-box">
                        <span className="footer-label">Holding Time</span>
                        <span className="timer-value" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <Clock size={12} />
                          {elapsedTimes[sig.id] || "00:00:00"}
                        </span>
                      </div>

                      <div className="pnl-box">
                        <span className="footer-label">Live P&L</span>
                        <span className={`pnl-value ${pnl.class}`}>
                          {sig.status === 'PENDING' ? 'Pending Entry' : pnl.text}
                        </span>
                      </div>
                    </div>
                  </div>
                )
              })
            ) : (
              <div className="empty-state">
                <HelpCircle className="empty-icon" size={40} />
                <h3>No Active Signals</h3>
                <p style={{ fontSize: '0.85rem', marginTop: '6px' }}>
                  Weekly high/low sweeps or breakouts will appear here dynamically.
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Signal History */}
        <div className="history-panel">
          <h2 className="section-title">
            <History size={20} color="var(--accent-purple)" />
            Recent History
          </h2>
          
          <div className="history-list">
            {history.length > 0 ? (
              history.map(item => {
                const isTp = item.status === 'TP_HIT'
                const isSl = item.status === 'SL_HIT'
                const isExpired = item.status === 'EXPIRED'
                
                let pnlText = "0R"
                let pnlClass = ""
                
                if (isTp) {
                  pnlText = "+2.00R"
                  pnlClass = "win"
                } else if (isSl) {
                  pnlText = "-1.00R"
                  pnlClass = "loss"
                }
                
                return (
                  <div key={item.id} className="history-item">
                    <div className="history-meta">
                      <span className="history-pair">{item.pair}</span>
                      <span className="history-type">
                        {item.direction} • {item.trigger_type}
                      </span>
                    </div>

                    <div className="history-outcome">
                      <span className={`outcome-badge ${isTp ? 'tp' : isSl ? 'sl' : 'expired'}`}>
                        {item.status.replace('_', ' ')}
                      </span>
                      {!isExpired && (
                        <span className={`history-pnl ${pnlClass}`}>
                          {pnlText}
                        </span>
                      )}
                    </div>
                  </div>
                )
              })
            ) : (
              <div style={{ textAlign: 'center', padding: '2rem 1rem', color: 'var(--text-muted)' }}>
                No past trade history for current and last month.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
