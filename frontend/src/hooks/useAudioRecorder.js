/**
 * useAudioRecorder.js
 * Push-to-talk audio recording hook using MediaRecorder API.
 * Returns audio as a Blob when recording stops.
 */
import { useState, useRef, useCallback } from 'react'

export function useAudioRecorder() {
  const [isRecording, setIsRecording] = useState(false)
  const [audioLevel, setAudioLevel] = useState(0)
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])
  const streamRef = useRef(null)
  const analyserRef = useRef(null)
  const animFrameRef = useRef(null)

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      streamRef.current = stream

      // Audio level analyser for visualisation
      const ctx = new AudioContext()
      const source = ctx.createMediaStreamSource(stream)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 256
      source.connect(analyser)
      analyserRef.current = analyser

      const trackLevel = () => {
        const data = new Uint8Array(analyser.frequencyBinCount)
        analyser.getByteFrequencyData(data)
        const avg = data.reduce((a, b) => a + b, 0) / data.length
        setAudioLevel(avg / 128) // 0-1 normalised
        animFrameRef.current = requestAnimationFrame(trackLevel)
      }
      trackLevel()

      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
      mediaRecorderRef.current = recorder
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.start(100) // collect data every 100ms
      setIsRecording(true)
    } catch (err) {
      console.error('Microphone access error:', err)
      alert('Microphone access denied. Please allow mic permissions and try again.')
    }
  }, [])

  const stopRecording = useCallback(() => {
    return new Promise((resolve) => {
      const recorder = mediaRecorderRef.current
      if (!recorder || recorder.state === 'inactive') { resolve(null); return }

      cancelAnimationFrame(animFrameRef.current)
      setAudioLevel(0)

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        chunksRef.current = []
        streamRef.current?.getTracks().forEach(t => t.stop())
        setIsRecording(false)
        resolve(blob)
      }

      recorder.stop()
    })
  }, [])

  return { isRecording, audioLevel, startRecording, stopRecording }
}
