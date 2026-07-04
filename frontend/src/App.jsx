import { useState, useEffect, useCallback } from 'react'
import VoiceOrb from './components/VoiceOrb'
import TranscriptPanel from './components/TranscriptPanel'
import ToolCallLog from './components/ToolCallLog'
import OrderCard from './components/OrderCard'
import MetricsPanel from './components/MetricsPanel'
import { useAudioRecorder } from './hooks/useAudioRecorder'
import { useRealtimeSession } from './hooks/useRealtimeSession'
import './App.css'

const QUICK_CHIPS = [
  { label: '📦 Check order ORD-1234', text: 'What is the status of order ORD-1234?' },
  { label: '💸 Request refund', text: 'I want to request a refund for order ORD-1234' },
  { label: '⭐ My loyalty points', text: 'Check loyalty points for customer CUST-001' },
  { label: '🎫 Create ticket', text: 'Create a support ticket for my damaged item' },
  { label: '👤 Talk to human', text: 'I need to speak with a human agent' },
]

function now() {
  return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function App() {
  const [mode, setMode] = useState('classic') // 'classic' | 'realtime'
  const [orbState, setOrbState] = useState('idle')
  const [messages, setMessages] = useState([])
  const [toolCalls, setToolCalls] = useState([])
  const [orders, setOrders] = useState([])
  const [history, setHistory] = useState([])
  const [statusText, setStatusText] = useState('Ready')
  const [escalated, setEscalated] = useState(false)
  const [latency, setLatency] = useState(null)
  const [rateLimited, setRateLimited] = useState(false)
  const [rightTab, setRightTab] = useState('tools') // 'tools' | 'metrics' | 'orders'

  // ── Classic mode ────────────────────────────────────────────
  const { isRecording, audioLevel, startRecording, stopRecording } = useAudioRecorder()

  // ── Realtime mode ────────────────────────────────────────────
  const addMessage = useCallback((role, text) => {
    setMessages(prev => [...prev, { role, text, time: now() }])
  }, [])

  const addToolCall = useCallback((call) => {
    setToolCalls(prev => [...prev, { ...call, time: now() }])
    if (call.tool_name === 'escalate_to_human') setEscalated(true)
  }, [])

  const { status: wsStatus, connect, disconnect, startMic, stopMic, sendText } = useRealtimeSession({
    onTranscript: (text, role) => { if (text?.trim()) addMessage(role === 'user' ? 'user' : 'agent', text) },
    onAgentText: () => {},
    onToolCall: (msg) => addToolCall({ tool_name: msg.tool_name, name: msg.tool_name, args: msg.args, result: msg.result }),
    onTurnComplete: () => { setOrbState('idle'); setStatusText('Ready') },
  })

  // ── Load orders on mount ─────────────────────────────────────
  useEffect(() => {
    fetch('/api/orders')
      .then(r => r.json())
      .then(d => setOrders(d.orders || []))
      .catch(() => {})
  }, [])

  // ── Orb sync ─────────────────────────────────────────────────
  useEffect(() => {
    if (mode === 'realtime') {
      if (wsStatus === 'connecting') setOrbState('thinking')
      else if (wsStatus === 'ready') setOrbState('idle')
      else setOrbState('idle')
    }
  }, [wsStatus, mode])

  // ── Classic pipeline — send audio ────────────────────────────
  const handleClassicStop = async () => {
    const blob = await stopRecording()
    if (!blob || blob.size < 200) { setOrbState('idle'); setStatusText('Ready'); return }

    setOrbState('thinking')
    setStatusText('Processing…')
    const t0 = Date.now()

    const form = new FormData()
    form.append('audio', blob, 'recording.webm')
    form.append('history', JSON.stringify(history))

    try {
      const res = await fetch('/api/chat', { method: 'POST', body: form })
      if (res.status === 429) {
        setRateLimited(true)
        setTimeout(() => setRateLimited(false), 30000)
        throw new Error('API Rate Limit (429) reached. Please wait a moment.')
      }
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()

      const ms = Date.now() - t0
      setLatency(ms)

      // Add to transcript
      if (data.transcript) addMessage('user', data.transcript)
      if (data.reply) addMessage('agent', data.reply)

      // Log tool calls
      data.tool_calls?.forEach(tc => addToolCall({ ...tc, tool_name: tc.name }))

      // Update history
      setHistory(prev => [
        ...prev,
        { role: 'user', content: data.transcript },
        { role: 'model', content: data.reply },
      ])

      // Play TTS audio
      if (data.audio_b64) {
        setOrbState('speaking')
        setStatusText('Speaking…')
        const audioBytes = Uint8Array.from(atob(data.audio_b64), c => c.charCodeAt(0))
        const audioBlob = new Blob([audioBytes], { type: 'audio/wav' })
        const url = URL.createObjectURL(audioBlob)
        const audio = new Audio(url)
        audio.onended = () => { setOrbState('idle'); setStatusText('Ready'); URL.revokeObjectURL(url) }
        audio.play().catch(() => { setOrbState('idle'); setStatusText('Ready') })
      } else {
        setOrbState('idle'); setStatusText('Ready')
      }
    } catch (err) {
      console.error(err)
      setOrbState('idle')
      setStatusText('Error — try again')
      addMessage('agent', `⚠️ Error: ${err.message}`)
    }
  }

  // ── PTT button ───────────────────────────────────────────────
  const handlePTTDown = () => {
    if (mode === 'classic') {
      startRecording()
      setOrbState('listening')
      setStatusText('Listening…')
    } else {
      if (wsStatus !== 'ready') return
      startMic()
      setOrbState('listening')
      setStatusText('Listening…')
    }
  }

  const handlePTTUp = () => {
    if (mode === 'classic') {
      handleClassicStop()
    } else {
      stopMic()
      setOrbState('thinking')
      setStatusText('Thinking…')
    }
  }

  // ── Realtime connect/disconnect ──────────────────────────────
  const handleRealtimeToggle = () => {
    if (wsStatus === 'disconnected' || wsStatus === 'error') {
      connect()
      setStatusText('Connecting to Live API…')
    } else {
      disconnect()
      setStatusText('Disconnected')
      setOrbState('idle')
    }
  }

  // ── Quick chip ───────────────────────────────────────────────
  const handleChip = async (chip) => {
    if (mode === 'realtime') {
      sendText(chip.text)
      addMessage('user', chip.text)
      setOrbState('thinking')
      setStatusText('Thinking…')
    } else {
      addMessage('user', chip.text)
      setOrbState('thinking')
      setStatusText('Processing…')
      const t0 = Date.now()
      try {
        const res = await fetch('/api/text-chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: chip.text, history }),
        })
        if (res.status === 429) {
          setRateLimited(true)
          setTimeout(() => setRateLimited(false), 30000)
          throw new Error('API Rate Limit (429) reached. Please wait a moment.')
        }
        const data = await res.json()
        setLatency(Date.now() - t0)
        if (data.reply) addMessage('agent', data.reply)
        data.tool_calls?.forEach(tc => addToolCall({ ...tc, tool_name: tc.name }))
        setHistory(prev => [...prev, { role: 'user', content: chip.text }, { role: 'model', content: data.reply }])
        if (data.audio_b64) {
          setOrbState('speaking'); setStatusText('Speaking…')
          const bytes = Uint8Array.from(atob(data.audio_b64), c => c.charCodeAt(0))
          const blob = new Blob([bytes], { type: 'audio/wav' })
          const url = URL.createObjectURL(blob)
          const a = new Audio(url)
          a.onended = () => { setOrbState('idle'); setStatusText('Ready'); URL.revokeObjectURL(url) }
          a.play().catch(() => { setOrbState('idle'); setStatusText('Ready') })
        } else { setOrbState('idle'); setStatusText('Ready') }
      } catch (err) { setOrbState('idle'); setStatusText('Ready'); addMessage('agent', '⚠️ Error: ' + err.message) }
    }
  }

  // ── Order click ──────────────────────────────────────────────
  const handleOrderClick = (orderId) => {
    handleChip({ text: `What is the status of order ${orderId}?` })
  }

  const isPTTDisabled = mode === 'realtime' && wsStatus !== 'ready'
  const wsConnected = wsStatus === 'ready' || wsStatus === 'connecting'

  return (
    <div className="app-shell">
      {/* ── Header ── */}
      <header style={{
        display: 'flex', alignItems: 'center', padding: '0 20px',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        background: 'rgba(5,8,16,0.8)', backdropFilter: 'blur(20px)',
        gap: 16, flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 38, height: 38, borderRadius: 12,
            background: 'linear-gradient(135deg, #00f2fe, #4facfe)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 20, boxShadow: '0 0 25px rgba(0, 242, 254, 0.5)',
          }}>🤖</div>
          <div>
            <div style={{ fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, fontSize: 15, letterSpacing: '-0.02em' }}>
              <span className="grad-text">ARIA</span>
            </div>
            <div style={{ fontSize: 10, color: '#475569', letterSpacing: '0.04em' }}>NOVAMART SUPPORT AI</div>
          </div>
        </div>

        {/* Mode toggle */}
        <div style={{
          marginLeft: 'auto', display: 'flex', alignItems: 'center',
          background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 10, padding: 3, gap: 2,
        }}>
          {['classic', 'realtime'].map(m => (
            <button
              key={m}
              onClick={() => { setMode(m); if (m === 'classic' && wsConnected) disconnect() }}
              style={{
                padding: '5px 14px', borderRadius: 8, fontSize: 12, fontWeight: 600,
                background: mode === m ? 'linear-gradient(135deg, #4f8ef730, #a855f730)' : 'transparent',
                color: mode === m ? '#e2e8f0' : '#475569',
                border: mode === m ? '1px solid rgba(255,255,255,0.1)' : '1px solid transparent',
                transition: 'all 0.2s',
              }}
            >
              {m === 'classic' ? '⚡ Classic' : '🔴 Live API'}
            </button>
          ))}
        </div>

        {/* WS connect button (realtime mode only) */}
        {mode === 'realtime' && (
          <button
            onClick={handleRealtimeToggle}
            style={{
              padding: '6px 16px', borderRadius: 8, fontSize: 12, fontWeight: 600,
              background: wsConnected ? '#f8717120' : '#34d39920',
              color: wsConnected ? '#f87171' : '#34d399',
              border: `1px solid ${wsConnected ? '#f8717140' : '#34d39940'}`,
            }}
          >
            {wsStatus === 'connecting' ? '⟳ Connecting…' : wsConnected ? '⏹ Disconnect' : '▶ Connect'}
          </button>
        )}

        {/* Latency badge */}
        {latency && (
          <div style={{
            padding: '4px 10px', borderRadius: 99, fontSize: 11,
            background: '#4f8ef710', color: '#4f8ef7', border: '1px solid #4f8ef730',
          }}>
            ⚡ {latency}ms
          </div>
        )}
      </header>

      {/* ── Body ── */}
      <div className="app-body">

        {/* ── Left: Transcript ── */}
        <div className="panel-left">
          <TranscriptPanel messages={messages} />
        </div>

        {/* ── Center: Orb + controls ── */}
        <div className="panel-center">

          {/* Escalation banner */}
          {escalated && (
            <div style={{
              padding: '12px 24px', borderRadius: 16, width: '100%', textAlign: 'center',
              background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#ef4444',
              fontSize: 14, fontWeight: 600, animation: 'fadeIn 0.3s ease',
              boxShadow: '0 4px 20px rgba(239, 68, 68, 0.15)', marginBottom: 16
            }}>
              👤 Transferring to a human agent…
            </div>
          )}

          {/* Rate Limit banner */}
          {rateLimited && (
            <div style={{
              padding: '16px 24px', borderRadius: 16, width: '100%', textAlign: 'center',
              background: 'linear-gradient(90deg, rgba(239, 68, 68, 0.15), rgba(245, 158, 11, 0.15))',
              border: '1px solid rgba(245, 158, 11, 0.4)', color: '#fcd34d',
              fontSize: 14, fontWeight: 600, animation: 'fadeIn 0.3s ease',
              boxShadow: '0 4px 30px rgba(245, 158, 11, 0.2)', marginBottom: 16,
              backdropFilter: 'blur(10px)'
            }}>
              ⚠️ API Rate Limit Reached (HTTP 429). Gemini Free Tier allows 15 req/min. Please wait ~1 minute.
            </div>
          )}

          <VoiceOrb state={orbState} audioLevel={isRecording ? audioLevel : 0} />

          {/* Status */}
          <div style={{ textAlign: 'center', marginTop: 16 }}>
            <div style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: 28, fontWeight: 700, letterSpacing: '-0.03em', marginBottom: 6 }}>
              {orbState === 'idle' && 'How can I help you?'}
              {orbState === 'listening' && <span className="grad-text">Listening…</span>}
              {orbState === 'thinking' && <span style={{ color: '#c084fc' }}>Thinking…</span>}
              {orbState === 'speaking' && <span style={{ color: '#34d399' }}>Speaking…</span>}
            </div>
            <div style={{ fontSize: 13, color: '#9ca3af', fontWeight: 500 }}>{statusText}</div>
          </div>

          {/* PTT Button */}
          <button
            id="ptt-btn"
            onMouseDown={handlePTTDown}
            onMouseUp={handlePTTUp}
            onTouchStart={e => { e.preventDefault(); handlePTTDown() }}
            onTouchEnd={e => { e.preventDefault(); handlePTTUp() }}
            disabled={isPTTDisabled}
            style={{
              width: 96, height: 96, borderRadius: '50%', marginTop: 24,
              background: isRecording
                ? 'linear-gradient(135deg, #ff0844, #ffb199)'
                : 'linear-gradient(135deg, #00f2fe, #4facfe)',
              boxShadow: isRecording
                ? '0 0 0 20px rgba(255, 8, 68, 0.15), 0 0 60px rgba(255, 8, 68, 0.5)'
                : '0 0 0 12px rgba(0, 242, 254, 0.15), 0 0 50px rgba(0, 242, 254, 0.5)',
              fontSize: 32, color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
              opacity: isPTTDisabled ? 0.4 : 1,
              transform: isRecording ? 'scale(1.1)' : 'scale(1)',
              userSelect: 'none', WebkitUserSelect: 'none',
            }}
          >
            {isRecording ? '⏹' : '🎙'}
          </button>

          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 16, fontWeight: 500 }}>
            {isPTTDisabled ? 'Connect to Live API first' : 'Hold to speak'}
          </div>

          {/* Quick chips */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'center', maxWidth: 540, marginTop: 24 }}>
            {QUICK_CHIPS.map((chip, i) => (
              <button
                key={i}
                onClick={() => handleChip(chip)}
                disabled={mode === 'realtime' && wsStatus !== 'ready'}
                className="animate-fade-in"
                style={{
                  padding: '8px 16px', borderRadius: 99, fontSize: 13, fontWeight: 500,
                  background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)',
                  color: '#9ca3af', transition: 'all 0.2s', animationDelay: `${i * 50}ms`,
                  opacity: (mode === 'realtime' && wsStatus !== 'ready') ? 0.4 : 1,
                  backdropFilter: 'blur(8px)'
                }}
                onMouseEnter={e => { e.target.style.background = 'rgba(59, 130, 246, 0.1)'; e.target.style.color = '#f9fafb'; e.target.style.borderColor = 'rgba(59, 130, 246, 0.3)'; e.target.style.transform = 'translateY(-2px)' }}
                onMouseLeave={e => { e.target.style.background = 'rgba(255,255,255,0.03)'; e.target.style.color = '#9ca3af'; e.target.style.borderColor = 'rgba(255,255,255,0.08)'; e.target.style.transform = 'translateY(0)' }}
              >
                {chip.label}
              </button>
            ))}
          </div>

          {/* Clear button */}
          {messages.length > 0 && (
            <button
              onClick={() => { setMessages([]); setToolCalls([]); setHistory([]); setEscalated(false); setLatency(null) }}
              style={{
                marginTop: 24, padding: '8px 16px', borderRadius: 12, fontSize: 12, color: '#9ca3af',
                background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255,255,255,0.05)',
                transition: 'all 0.2s'
              }}
              onMouseEnter={e => { e.target.style.background = 'rgba(239, 68, 68, 0.1)'; e.target.style.color = '#ef4444'; e.target.style.borderColor = 'rgba(239, 68, 68, 0.2)' }}
              onMouseLeave={e => { e.target.style.background = 'rgba(255, 255, 255, 0.02)'; e.target.style.color = '#9ca3af'; e.target.style.borderColor = 'rgba(255,255,255,0.05)' }}
            >
              ↺ Clear conversation
            </button>
          )}
        </div>

        {/* ── Right: Tabbed panel ── */}
        <div className="panel-right">
          {/* Tab bar */}
          <div className="glass" style={{
            display: 'flex', gap: 2, padding: 4, marginBottom: 12, flexShrink: 0,
          }}>
            {[['tools','⚡ Tools'], ['metrics','📊 Metrics'], ['orders','📦 Orders']].map(([id, label]) => (
              <button
                key={id}
                onClick={() => setRightTab(id)}
                style={{
                  flex: 1, padding: '6px 0', borderRadius: 8, fontSize: 11, fontWeight: 600,
                  background: rightTab === id ? 'rgba(79,142,247,0.15)' : 'transparent',
                  color: rightTab === id ? '#4f8ef7' : '#475569',
                  border: rightTab === id ? '1px solid rgba(79,142,247,0.25)' : '1px solid transparent',
                  transition: 'all 0.15s',
                }}
              >{label}</button>
            ))}
          </div>

          {/* Tab content */}
          <div style={{ flex: 1, overflow: 'hidden', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            {rightTab === 'tools' && <ToolCallLog toolCalls={toolCalls} />}
            {rightTab === 'metrics' && (
              <div className="glass" style={{ flex: 1, overflow: 'hidden' }}>
                <MetricsPanel />
              </div>
            )}
            {rightTab === 'orders' && (
              <div className="glass" style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                <div style={{
                  padding: '12px 16px', borderBottom: '1px solid rgba(255,255,255,0.07)',
                  fontFamily: 'Space Grotesk, sans-serif', fontSize: 11, fontWeight: 600,
                  color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', flexShrink: 0,
                }}>Live from SQLite · Click to query</div>
                <div style={{ overflowY: 'auto', padding: '10px' }}>
                  {orders.map(o => (
                    <OrderCard key={o.id} order={o} onSelect={handleOrderClick} />
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
