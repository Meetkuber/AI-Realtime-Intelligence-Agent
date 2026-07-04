/**
 * MetricsPanel.jsx — Live observability dashboard
 * Polls /api/metrics every 5 seconds and displays:
 *   - Request count + error rate
 *   - Latency p50/p95/p99
 *   - Per-tool call bar chart
 */
import { useEffect, useState } from 'react'

const BAR_COLORS = {
  lookup_order: '#4f8ef7',
  trigger_refund: '#f59e0b',
  create_support_ticket: '#a855f7',
  check_loyalty_points: '#22d3ee',
  escalate_to_human: '#f87171',
}

function MiniBar({ label, count, maxCount, color }) {
  const pct = maxCount > 0 ? (count / maxCount) * 100 : 0
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
        <span style={{ fontSize: 11, color: '#64748b', fontFamily: 'monospace' }}>{label}</span>
        <span style={{ fontSize: 11, fontWeight: 600, color }}>×{count}</span>
      </div>
      <div style={{ height: 5, background: 'rgba(255,255,255,0.06)', borderRadius: 99, overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${pct}%`, background: color,
          borderRadius: 99, transition: 'width 0.5s ease',
          boxShadow: `0 0 8px ${color}60`,
        }} />
      </div>
    </div>
  )
}

function Stat({ label, value, unit = '', color = '#e2e8f0', sub = '' }) {
  return (
    <div style={{ textAlign: 'center', flex: 1 }}>
      <div style={{ fontSize: 20, fontWeight: 700, color, fontFamily: 'Space Grotesk, sans-serif' }}>
        {value}{unit}
      </div>
      <div style={{ fontSize: 10, color: '#475569', marginTop: 2 }}>{label}</div>
      {sub && <div style={{ fontSize: 9, color: '#334155', marginTop: 1 }}>{sub}</div>}
    </div>
  )
}

export default function MetricsPanel() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    const fetch_ = () => {
      fetch('/api/metrics')
        .then(r => r.json())
        .then(d => { setData(d); setError(false) })
        .catch(() => setError(true))
    }
    fetch_()
    const interval = setInterval(fetch_, 5000)
    return () => clearInterval(interval)
  }, [])

  const s = {
    panel: { padding: '14px 16px', height: '100%', overflowY: 'auto' },
    section: { marginBottom: 18 },
    sectionTitle: {
      fontSize: 10, fontWeight: 700, color: '#334155',
      textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10,
    },
    statsRow: { display: 'flex', gap: 4, marginBottom: 14 },
    divider: { height: 1, background: 'rgba(255,255,255,0.05)', margin: '14px 0' },
  }

  if (error) return (
    <div style={{ ...s.panel, color: '#475569', fontSize: 12, paddingTop: 40, textAlign: 'center' }}>
      ⚠️ Backend offline
    </div>
  )

  if (!data) return (
    <div style={{ ...s.panel, color: '#334155', fontSize: 12, paddingTop: 40, textAlign: 'center' }}>
      Loading metrics…
    </div>
  )

  const tools = data.tool_calls || {}
  const maxCount = Math.max(...Object.values(tools).map(t => t.count), 1)
  const errorRate = data.error_rate_pct ?? 0
  const errorColor = errorRate > 10 ? '#f87171' : errorRate > 5 ? '#fbbf24' : '#34d399'

  return (
    <div style={s.panel}>
      {/* Request summary */}
      <div style={s.sectionTitle}>📊 Request Stats</div>
      <div style={s.statsRow}>
        <Stat label="Total Reqs" value={data.requests_total} color="#4f8ef7" />
        <Stat label="Errors" value={data.errors_total} color={errorColor} />
        <Stat label="Error Rate" value={errorRate} unit="%" color={errorColor} />
      </div>

      <div style={s.divider} />

      {/* Latency */}
      <div style={s.sectionTitle}>⚡ Latency</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14 }}>
        {[
          { k: 'p50_ms', label: 'p50' },
          { k: 'p75_ms', label: 'p75' },
          { k: 'p95_ms', label: 'p95' },
          { k: 'p99_ms', label: 'p99' },
        ].map(({ k, label }) => (
          <div key={k} style={{
            background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 8, padding: '8px 10px', textAlign: 'center',
          }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#4f8ef7', fontFamily: 'Space Grotesk, sans-serif' }}>
              {data.latency?.[k] ?? '—'}<span style={{ fontSize: 10, color: '#475569' }}>ms</span>
            </div>
            <div style={{ fontSize: 10, color: '#475569', marginTop: 2 }}>{label}</div>
          </div>
        ))}
      </div>

      <div style={s.divider} />

      {/* Tool calls */}
      <div style={s.sectionTitle}>⚙️ Tool Calls</div>
      {Object.keys(tools).length === 0 ? (
        <div style={{ color: '#1e293b', fontSize: 12, textAlign: 'center', padding: '10px 0' }}>
          No tool calls yet
        </div>
      ) : (
        Object.entries(tools).map(([name, stats]) => (
          <MiniBar
            key={name}
            label={name}
            count={stats.count}
            maxCount={maxCount}
            color={BAR_COLORS[name] || '#64748b'}
          />
        ))
      )}

      <div style={{ fontSize: 9, color: '#1e293b', marginTop: 12, textAlign: 'right' }}>
        Auto-refreshes every 5s
      </div>
    </div>
  )
}
