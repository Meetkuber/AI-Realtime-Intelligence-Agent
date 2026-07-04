/**
 * ToolCallLog.jsx — Real-time log of function calls made by the agent
 */
import { useState } from 'react'

const TOOL_ICONS = {
  lookup_order: '📦',
  trigger_refund: '💸',
  create_support_ticket: '🎫',
  check_loyalty_points: '⭐',
  escalate_to_human: '👤',
}

const TOOL_COLORS = {
  lookup_order: '#4f8ef7',
  trigger_refund: '#f59e0b',
  create_support_ticket: '#a855f7',
  check_loyalty_points: '#22d3ee',
  escalate_to_human: '#f87171',
}

const s = {
  panel: { display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' },
  header: {
    padding: '14px 18px', borderBottom: '1px solid rgba(255,255,255,0.07)',
    display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
    fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600, fontSize: 13,
    color: '#94a3b8', letterSpacing: '0.06em', textTransform: 'uppercase',
  },
  body: { flex: 1, overflowY: 'auto', padding: '12px' },
  empty: {
    display: 'flex', flexDirection: 'column',
    alignItems: 'center', justifyContent: 'center', height: '100%',
    color: '#1e293b', fontSize: 12, gap: 6, paddingTop: 40,
  },
}

function ToolEntry({ call, index }) {
  const [open, setOpen] = useState(false)
  const color = TOOL_COLORS[call.name] || '#4f8ef7'
  const icon = TOOL_ICONS[call.name] || '🔧'
  const success = call.result?.success !== false

  return (
    <div
      style={{
        border: `1px solid ${color}30`,
        borderLeft: `3px solid ${color}`,
        borderRadius: 10, marginBottom: 8,
        background: `${color}08`, overflow: 'hidden',
        cursor: 'pointer',
        transition: 'background 0.2s',
      }}
      onClick={() => setOpen(o => !o)}
    >
      <div style={{ padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 16 }}>{icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color, fontFamily: 'monospace' }}>
            {call.name}
          </div>
          <div style={{ fontSize: 10, color: '#475569', marginTop: 1 }}>
            {call.time} · {call.duration_ms?.toFixed(0) ?? '—'}ms
          </div>
        </div>
        <div style={{
          fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 99,
          background: success ? '#34d39920' : '#f8717120',
          color: success ? '#34d399' : '#f87171',
        }}>
          {success ? 'OK' : 'ERR'}
        </div>
        <span style={{ fontSize: 10, color: '#475569' }}>{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div style={{ borderTop: `1px solid ${color}20`, padding: '10px 12px' }}>
          <div style={{ fontSize: 10, color: '#64748b', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Args
          </div>
          <pre style={{
            fontSize: 11, color: '#94a3b8', background: 'rgba(0,0,0,0.3)',
            padding: 8, borderRadius: 6, overflow: 'auto', marginBottom: 8,
            fontFamily: 'monospace', lineHeight: 1.5,
          }}>
            {JSON.stringify(call.args, null, 2)}
          </pre>
          <div style={{ fontSize: 10, color: '#64748b', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Result
          </div>
          <pre style={{
            fontSize: 11, color: success ? '#86efac' : '#fca5a5',
            background: 'rgba(0,0,0,0.3)',
            padding: 8, borderRadius: 6, overflow: 'auto', fontFamily: 'monospace', lineHeight: 1.5,
          }}>
            {JSON.stringify(call.result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

export default function ToolCallLog({ toolCalls }) {
  return (
    <div className="glass" style={s.panel}>
      <div style={s.header}>
        <span>⚡</span> Tool Calls
        {toolCalls.length > 0 && (
          <span style={{
            marginLeft: 'auto', fontSize: 11, background: '#4f8ef720',
            color: '#4f8ef7', padding: '2px 8px', borderRadius: 99,
          }}>
            {toolCalls.length}
          </span>
        )}
      </div>
      <div style={s.body}>
        {toolCalls.length === 0 ? (
          <div style={s.empty}>
            <span style={{ fontSize: 28 }}>⚡</span>
            <span>Function calls appear here</span>
          </div>
        ) : (
          [...toolCalls].reverse().map((call, i) => (
            <ToolEntry key={i} call={call} index={i} />
          ))
        )}
      </div>
    </div>
  )
}
