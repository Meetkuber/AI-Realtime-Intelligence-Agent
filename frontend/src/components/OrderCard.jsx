/**
 * OrderCard.jsx — Mock order database sidebar cards
 */

const STATUS_STYLE = {
  Delivered:  { label: '✓ Delivered',  cls: 'status-delivered' },
  'In Transit': { label: '→ In Transit', cls: 'status-in-transit' },
  Processing: { label: '◌ Processing', cls: 'status-processing' },
  Cancelled:  { label: '✕ Cancelled',  cls: 'status-cancelled' },
}

export default function OrderCard({ order, onSelect }) {
  const st = STATUS_STYLE[order.status] || { label: order.status, cls: '' }

  return (
    <div
      onClick={() => onSelect(order.id)}
      style={{
        background: 'rgba(255,255,255,0.03)',
        border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: 12, padding: '11px 13px',
        cursor: 'pointer', transition: 'all 0.18s ease',
        marginBottom: 8,
      }}
      onMouseEnter={e => { e.currentTarget.style.background = 'rgba(79,142,247,0.08)'; e.currentTarget.style.borderColor = 'rgba(79,142,247,0.25)' }}
      onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.03)'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.07)' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
        <span style={{ fontFamily: 'monospace', fontSize: 12, fontWeight: 700, color: '#4f8ef7' }}>
          {order.id}
        </span>
        <span className={`pill ${st.cls}`} style={{ fontSize: 9 }}>
          {st.label}
        </span>
      </div>

      <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {order.item_names?.join(', ')}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 11, color: '#475569' }}>{order.placed_at}</span>
        <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>${order.total?.toFixed(2)}</span>
      </div>
    </div>
  )
}
