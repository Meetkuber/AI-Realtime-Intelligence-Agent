/**
 * VoiceOrb.jsx — Animated orb that reacts to audio level
 * States: idle, listening, thinking, speaking
 */
import { useRef, useEffect } from 'react'

const STATE_STYLES = {
  idle:      { color1: '#4f8ef7', color2: '#a855f7', pulseScale: 1.04, speed: 3000 },
  listening: { color1: '#22d3ee', color2: '#4f8ef7', pulseScale: 1.15, speed: 800 },
  thinking:  { color1: '#a855f7', color2: '#f59e0b', pulseScale: 1.08, speed: 1200 },
  speaking:  { color1: '#34d399', color2: '#22d3ee', pulseScale: 1.12, speed: 600 },
}

export default function VoiceOrb({ state = 'idle', audioLevel = 0 }) {
  const canvasRef = useRef(null)
  const frameRef = useRef(null)
  const timeRef = useRef(0)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const size = 220
    canvas.width = size
    canvas.height = size
    const cx = size / 2
    const cy = size / 2

    const draw = (ts) => {
      timeRef.current = ts
      ctx.clearRect(0, 0, size, size)
      const s = STATE_STYLES[state]
      const t = ts / s.speed
      const pulse = 1 + (s.pulseScale - 1) * (0.5 + 0.5 * Math.sin(t * Math.PI * 2))
      const boost = 1 + audioLevel * 0.35
      const r = 72 * pulse * boost

      // Outer glow rings
      for (let i = 3; i >= 1; i--) {
        const grd = ctx.createRadialGradient(cx, cy, r * 0.4 * i, cx, cy, r * 1.4 * i)
        grd.addColorStop(0, `${s.color1}${Math.round(8 / i).toString(16).padStart(2,'0')}`)
        grd.addColorStop(1, 'transparent')
        ctx.beginPath()
        ctx.arc(cx, cy, r * 1.4 * i * 0.6, 0, Math.PI * 2)
        ctx.fillStyle = grd
        ctx.fill()
      }

      // Main orb body
      const grad = ctx.createRadialGradient(cx - r * 0.25, cy - r * 0.25, 0, cx, cy, r)
      grad.addColorStop(0, '#ffffff30')
      grad.addColorStop(0.4, s.color1 + 'cc')
      grad.addColorStop(1, s.color2 + '99')
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.fillStyle = grad
      ctx.fill()

      // Inner shimmer
      const shimmer = ctx.createRadialGradient(cx - r * 0.3, cy - r * 0.35, 0, cx, cy, r * 0.7)
      shimmer.addColorStop(0, '#ffffff25')
      shimmer.addColorStop(1, 'transparent')
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.fillStyle = shimmer
      ctx.fill()

      // Waveform bars when speaking/listening
      if (state === 'speaking' || state === 'listening') {
        const bars = 12
        ctx.save()
        ctx.translate(cx, cy)
        for (let i = 0; i < bars; i++) {
          const angle = (i / bars) * Math.PI * 2
          const barH = (r * 0.3) * (0.4 + 0.6 * Math.abs(Math.sin(t * Math.PI * 3 + i * 0.8)))
          ctx.save()
          ctx.rotate(angle)
          ctx.fillStyle = '#ffffff60'
          ctx.beginPath()
          ctx.roundRect(r + 6, -2, barH, 4, 2)
          ctx.fill()
          ctx.restore()
        }
        ctx.restore()
      }

      // Thinking spinner
      if (state === 'thinking') {
        ctx.save()
        ctx.translate(cx, cy)
        ctx.rotate(t * Math.PI * 2)
        for (let i = 0; i < 8; i++) {
          const a = (i / 8) * Math.PI * 2
          const dot_r = r + 14
          ctx.beginPath()
          ctx.arc(Math.cos(a) * dot_r, Math.sin(a) * dot_r, 3, 0, Math.PI * 2)
          ctx.fillStyle = `rgba(168,85,247,${(i + 1) / 8})`
          ctx.fill()
        }
        ctx.restore()
      }

      frameRef.current = requestAnimationFrame(draw)
    }

    frameRef.current = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(frameRef.current)
  }, [state, audioLevel])

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <canvas ref={canvasRef} style={{ imageRendering: 'crisp-edges' }} />
    </div>
  )
}
