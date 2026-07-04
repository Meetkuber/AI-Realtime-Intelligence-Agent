/**
 * TranscriptPanel.jsx — Live scrolling conversation transcript
 */
import { useEffect, useRef } from 'react'

const styles = {
  panel: {
    display: 'flex', flexDirection: 'column', gap: 0, height: '100%',
    overflow: 'hidden',
  },
  header: {
    padding: '14px 18px', borderBottom: '1px solid rgba(255,255,255,0.07)',
    display: 'flex', alignItems: 'center', gap: 8,
    fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600, fontSize: 13,
    color: '#94a3b8', letterSpacing: '0.06em', textTransform: 'uppercase',
    flexShrink: 0,
  },
  dot: { width: 7, height: 7, borderRadius: '50%', background: '#34d399' },
  body: {
    flex: 1, overflowY: 'auto', padding: '14px 16px',
    display: 'flex', flexDirection: 'column', gap: 12,
  },
  empty: {
    flex: 1, display: 'flex', flexDirection: 'column',
    alignItems: 'center', justifyContent: 'center',
    color: '#334155', fontSize: 13, gap: 8, textAlign: 'center',
  },
  emptyIcon: { fontSize: 32, marginBottom: 4 },
  roleLine: (role) => ({
    fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
    color: role === 'user' ? '#60a5fa' : '#34d399',
    marginBottom: 6,
  }),
  text: { fontSize: 13, lineHeight: 1.6, color: '#e2e8f0' },
  ts: { fontSize: 10, color: '#475569', marginTop: 4, textAlign: 'right' },
}

export default function TranscriptPanel({ messages }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="glass" style={styles.panel}>
      <div style={styles.header}>
        <div style={styles.dot} />
        Live Transcript
      </div>
      <div style={styles.body}>
        {messages.length === 0 ? (
          <div style={styles.empty}>
            <div style={styles.emptyIcon}>🎙️</div>
            <div>Transcript will appear here</div>
            <div style={{ color: '#1e293b', fontSize: 11 }}>Start speaking to begin</div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '85%', alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
              <div className={`chat-bubble animate-fade-in ${msg.role}`}>
                <div style={styles.roleLine(msg.role)}>
                  {msg.role === 'user' ? 'You' : 'ARIA'}
                </div>
                <div style={styles.text}>{msg.text}</div>
                <div style={styles.ts}>{msg.time}</div>
              </div>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
