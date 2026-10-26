import { useCallback, useEffect, useRef, useState } from 'react'

/** Webcam stream + a helper to grab the current frame as a JPEG blob. */
export function useWebcam() {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const canvasRef = useRef(document.createElement('canvas'))
  const [on, setOn] = useState(false)
  const [error, setError] = useState('')

  const start = useCallback(async () => {
    setError('')
    streamRef.current?.getTracks().forEach(t => t.stop())
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false })
      streamRef.current = stream
      if (videoRef.current) videoRef.current.srcObject = stream
      setOn(true)
      return true
    } catch (e) {
      setError(e.name === 'NotAllowedError' ? 'Camera permission was denied.' : `Camera error: ${e.message}`)
      return false
    }
  }, [])

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach(t => t.stop())
    streamRef.current = null
    setOn(false)
  }, [])

  const capture = useCallback(() => new Promise(resolve => {
    const v = videoRef.current
    if (!v || !v.videoWidth) return resolve(null)
    const c = canvasRef.current
    c.width = 320
    c.height = Math.round(320 * v.videoHeight / v.videoWidth)
    c.getContext('2d').drawImage(v, 0, 0, c.width, c.height)
    c.toBlob(resolve, 'image/jpeg', 0.8)
  }), [])

  useEffect(() => stop, [stop])
  return { videoRef, on, error, start, stop, capture }
}

const Recognition = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition)

/** Browser speech-to-text (Chrome/Edge). Calls onText with the final transcript. */
export function useSpeech(onText) {
  const [listening, setListening] = useState(false)
  const [error, setError] = useState('')
  const recRef = useRef(null)
  const cbRef = useRef(onText)
  cbRef.current = onText

  const listen = useCallback(() => {
    if (!Recognition) return
    setError('')
    const rec = new Recognition()
    rec.lang = 'en-US'
    rec.interimResults = false
    rec.maxAlternatives = 1
    rec.onresult = e => cbRef.current(e.results[0][0].transcript)
    rec.onerror = e => setError(e.error === 'not-allowed' ? 'Microphone permission was denied.' : `Speech error: ${e.error}`)
    rec.onend = () => setListening(false)
    recRef.current = rec
    rec.start()
    setListening(true)
  }, [])

  useEffect(() => () => recRef.current?.abort(), [])
  return { supported: Boolean(Recognition), listening, error, listen }
}

/** Read text aloud and resolve when finished (or after a safety timeout, since some browsers never fire 'end'). */
export function speakAndWait(text, maxMs = 15000) {
  return new Promise(resolve => {
    if (!window.speechSynthesis || !text) return resolve()
    window.speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(text)
    const timer = setTimeout(resolve, maxMs)
    const done = () => { clearTimeout(timer); resolve() }
    u.onend = done
    u.onerror = done
    window.speechSynthesis.speak(u)
  })
}

export function speak(text) {
  if (!window.speechSynthesis || !text) return
  window.speechSynthesis.cancel()
  window.speechSynthesis.speak(new SpeechSynthesisUtterance(text))
}

const LONG_PAUSE_MS = 2500

/**
 * Microphone level meter. Measures how long the student actually speaks and counts long pauses
 * (silence over 2.5 s between bits of speech). The first second sets the room's noise floor.
 */
export function useAudioMeter() {
  const [level, setLevel] = useState(0)
  const [speaking, setSpeaking] = useState(false)
  const [error, setError] = useState('')
  const ref = useRef(null)

  const stop = useCallback(() => {
    const s = ref.current
    if (!s) return null
    clearInterval(s.timer)
    s.stream.getTracks().forEach(t => t.stop())
    s.ctx.close().catch(() => {})
    ref.current = null
    setLevel(0)
    setSpeaking(false)
    return { speaking_sec: Math.round(s.speakingMs / 100) / 10, long_pauses: s.longPauses, longest_pause_sec: Math.round(s.longest / 100) / 10 }
  }, [])

  const start = useCallback(async () => {
    setError('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      const ctx = new (window.AudioContext || window.webkitAudioContext)()
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 1024
      ctx.createMediaStreamSource(stream).connect(analyser)
      const buf = new Float32Array(analyser.fftSize)
      const s = { stream, ctx, speakingMs: 0, longPauses: 0, longest: 0, silenceMs: 0, heardSpeech: false, floor: [], threshold: 0.02 }
      s.timer = setInterval(() => {
        analyser.getFloatTimeDomainData(buf)
        let sum = 0
        for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i]
        const rms = Math.sqrt(sum / buf.length)
        if (s.floor.length < 10) {            // first second: learn the background noise level
          s.floor.push(rms)
          s.threshold = Math.max(0.012, (s.floor.reduce((a, b) => a + b, 0) / s.floor.length) * 2.5)
        }
        const isSpeech = rms > s.threshold
        if (isSpeech) {
          if (s.heardSpeech && s.silenceMs >= LONG_PAUSE_MS) s.longPauses += 1
          s.longest = Math.max(s.longest, s.heardSpeech ? s.silenceMs : 0)
          s.silenceMs = 0
          s.heardSpeech = true
          s.speakingMs += 100
        } else if (s.heardSpeech) {
          s.silenceMs += 100
        }
        setLevel(Math.min(1, rms / (s.threshold * 4)))
        setSpeaking(isSpeech)
      }, 100)
      ref.current = s
      return true
    } catch (e) {
      setError(e.name === 'NotAllowedError' ? 'Microphone permission was denied.' : `Microphone error: ${e.message}`)
      return false
    }
  }, [])

  useEffect(() => () => { stop() }, [stop])
  return { level, speaking, error, start, stop }
}

const FATAL_SPEECH_ERRORS = {
  'not-allowed': 'Microphone permission was denied.',
  'service-not-allowed': 'Speech recognition is blocked in this browser. Use Chrome or Edge.',
  'audio-capture': 'No microphone was found.',
  'network': 'Speech-to-text needs an internet connection in Chrome.',
}

/** Continuous speech-to-text for a whole answer. Restarts itself when the browser stops after a silence. */
export function useDictation() {
  const [finalText, setFinalText] = useState('')
  const [interim, setInterim] = useState('')
  const [error, setError] = useState('')
  const recRef = useRef(null)
  const activeRef = useRef(false)
  const finalRef = useRef('')
  const liveRef = useRef('')  // last interim words, kept so they aren't lost when the answer ends mid-sentence
  const restartsRef = useRef([])

  const start = useCallback(() => {
    if (!Recognition) return false
    setError('')
    finalRef.current = ''
    liveRef.current = ''
    restartsRef.current = []
    setFinalText('')
    setInterim('')
    activeRef.current = true
    const begin = () => {
      const rec = new Recognition()
      rec.lang = 'en-US'
      rec.continuous = true
      rec.interimResults = true
      rec.onresult = (e) => {
        let live = ''
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const t = e.results[i][0].transcript
          if (e.results[i].isFinal) finalRef.current = `${finalRef.current} ${t}`.trim()
          else live += t
        }
        liveRef.current = live
        setFinalText(finalRef.current)
        setInterim(live)
      }
      rec.onerror = (e) => {
        if (FATAL_SPEECH_ERRORS[e.error]) { activeRef.current = false; setError(FATAL_SPEECH_ERRORS[e.error]) }
        else if (e.error !== 'no-speech' && e.error !== 'aborted') setError(`Speech error: ${e.error}`)
      }
      rec.onend = () => {
        if (!activeRef.current) return
        // Chrome ends recognition after a silence; restart it, but give up if it keeps ending straight away
        const now = Date.now()
        restartsRef.current = restartsRef.current.filter(t => now - t < 10000).concat(now)
        if (restartsRef.current.length > 6) {
          activeRef.current = false
          setError('Speech recognition keeps stopping. Check your internet connection (Chrome needs it for speech-to-text).')
          return
        }
        try { begin() } catch { /* already running */ }
      }
      recRef.current = rec
      rec.start()
    }
    begin()
    return true
  }, [])

  const stop = useCallback(() => {
    activeRef.current = false
    recRef.current?.stop()
    const text = `${finalRef.current} ${liveRef.current}`.trim()
    setInterim('')
    return text
  }, [])

  useEffect(() => () => { activeRef.current = false; recRef.current?.abort() }, [])
  return { supported: Boolean(Recognition), finalText, interim, error, start, stop }
}
