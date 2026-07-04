/**
 * useRealtimeSession.js
 * Manages the WebSocket connection to the Gemini Live API proxy.
 * Sends PCM audio chunks and plays back streamed audio responses.
 */
import { useState, useRef, useCallback, useEffect } from 'react'

const WS_URL = `ws://${window.location.host}/ws/realtime`

export function useRealtimeSession({ onTranscript, onAgentText, onToolCall, onTurnComplete }) {
  const [status, setStatus] = useState('disconnected') // disconnected | connecting | ready | error
  const wsRef = useRef(null)
  const audioCtxRef = useRef(null)
  const audioQueueRef = useRef([])
  const isPlayingRef = useRef(false)
  const mediaRecorderRef = useRef(null)
  const streamRef = useRef(null)

  // ── Audio playback (PCM 24kHz from Gemini) ──────────────────
  const ensureAudioCtx = () => {
    if (!audioCtxRef.current || audioCtxRef.current.state === 'closed') {
      audioCtxRef.current = new AudioContext({ sampleRate: 24000 })
    }
    if (audioCtxRef.current.state === 'suspended') {
      audioCtxRef.current.resume()
    }
    return audioCtxRef.current
  }

  const playPCMChunk = useCallback(async (pcmBytes) => {
    const ctx = ensureAudioCtx()
    // Convert raw PCM16 bytes → Float32
    const int16 = new Int16Array(pcmBytes)
    const float32 = new Float32Array(int16.length)
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768
    const buffer = ctx.createBuffer(1, float32.length, 24000)
    buffer.copyToChannel(float32, 0)
    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.connect(ctx.destination)
    source.start()
  }, [])

  // ── Connect ──────────────────────────────────────────────────
  const connect = useCallback(() => {
    if (wsRef.current) wsRef.current.close()
    setStatus('connecting')

    const ws = new WebSocket(WS_URL)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    ws.onopen = () => console.log('[WS] Connected to proxy')

    ws.onmessage = async (event) => {
      if (event.data instanceof ArrayBuffer) {
        // Raw PCM audio from Gemini → play it
        await playPCMChunk(event.data)
        return
      }
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'session_ready') {
          setStatus('ready')
        } else if (msg.type === 'user_transcript') {
          onTranscript?.(msg.text, 'user')
        } else if (msg.type === 'agent_transcript') {
          onTranscript?.(msg.text, 'agent')
        } else if (msg.type === 'agent_text') {
          onAgentText?.(msg.text)
        } else if (msg.type === 'tool_call') {
          onToolCall?.(msg)
        } else if (msg.type === 'turn_complete') {
          onTurnComplete?.()
        } else if (msg.type === 'error') {
          console.error('[WS] Server error:', msg.message)
          setStatus('error')
        }
      } catch { /* binary data handled above */ }
    }

    ws.onerror = (e) => { console.error('[WS] error', e); setStatus('error') }
    ws.onclose = () => { setStatus('disconnected'); console.log('[WS] Disconnected') }
  }, [playPCMChunk, onTranscript, onAgentText, onToolCall, onTurnComplete])

  const disconnect = useCallback(() => {
    wsRef.current?.close()
    stopMic()
  }, [])

  // ── Mic streaming ────────────────────────────────────────────
  const startMic = useCallback(async () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return

    const stream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 16000 }, video: false })
    streamRef.current = stream

    // Use ScriptProcessor to get raw PCM16 at 16kHz
    const ctx = new AudioContext({ sampleRate: 16000 })
    const source = ctx.createMediaStreamSource(stream)
    const processor = ctx.createScriptProcessor(4096, 1, 1)

    processor.onaudioprocess = (e) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
      const f32 = e.inputBuffer.getChannelData(0)
      const i16 = new Int16Array(f32.length)
      for (let i = 0; i < f32.length; i++) i16[i] = Math.max(-32768, Math.min(32767, f32[i] * 32768))
      wsRef.current.send(i16.buffer)
    }

    source.connect(processor)
    processor.connect(ctx.destination)
    mediaRecorderRef.current = { ctx, processor, source }
  }, [])

  const stopMic = useCallback(() => {
    streamRef.current?.getTracks().forEach(t => t.stop())
    streamRef.current = null
    const rec = mediaRecorderRef.current
    if (rec) {
      try { rec.source.disconnect(); rec.processor.disconnect() } catch {}
      rec.ctx.close()
      mediaRecorderRef.current = null
    }
    // Signal end of turn
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'end_of_turn' }))
    }
  }, [])

  // Send text input (for demo chips)
  const sendText = useCallback((text) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'text_input', text }))
    }
  }, [])

  useEffect(() => () => disconnect(), [disconnect])

  return { status, connect, disconnect, startMic, stopMic, sendText }
}
