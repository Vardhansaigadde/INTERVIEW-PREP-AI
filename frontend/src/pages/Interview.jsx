import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ArrowRight, CameraOff, Circle, CircleCheck, Eye, EyeOff, Gauge, History, Lightbulb, Mic, MessageSquareText,
  Play, RotateCcw, Shuffle, Sparkles, Square, Timer, TrendingUp, Video,
} from 'lucide-react'
import { api } from '../api'
import { speakAndWait, useAudioMeter, useDictation, useWebcam } from '../hooks'
import { Alert, Empty, Ring, Spinner } from '../components/ui'

const CATEGORIES = ['All', 'HR', 'Behavioural', 'Technical']
const FRAME_MS = 1500
const MAX_ANSWER_SEC = 180
const COUNTDOWN = 3
const FILLER_RE = /\b(um+|uh+m?|er+m?|ah|hmm+|mm|you know|i mean|kind of|sort of|basically|actually|literally|like i said)\b/gi

const fmtTime = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
const countWords = (t) => (t.match(/[A-Za-z0-9']+/g) || []).length

function Highlighted({ text }) {
  if (!text) return null
  // split() with a capture group alternates plain text (even indexes) and fillers (odd indexes)
  return text.split(FILLER_RE).map((p, i) => i % 2
    ? <mark key={i} className="filler" title="Filler word">{p}</mark>
    : <span key={i}>{p}</span>)
}

export default function Interview() {
  const [questions, setQuestions] = useState([])
  const [category, setCategory] = useState('All')
  const [question, setQuestion] = useState(null)
  const [phase, setPhase] = useState('ready') // ready | countdown | answering | processing | report
  const [count, setCount] = useState(COUNTDOWN)
  const [elapsed, setElapsed] = useState(0)
  const [live, setLive] = useState(null)
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState([])
  const [readAloud, setReadAloud] = useState(true)
  const [error, setError] = useState('')

  const cam = useWebcam()
  const audio = useAudioMeter()
  const dict = useDictation()
  const { stop: stopCam, capture } = cam
  const { stop: stopAudio } = audio
  const { stop: stopDict, start: startDict } = dict
  const attemptRef = useRef(null)
  const startRef = useRef(0)
  const runRef = useRef(0)          // bumps on every start/cancel so a cancelled start can't carry on
  const finishingRef = useRef(false)
  const phaseRef = useRef(phase)
  phaseRef.current = phase

  const loadHistory = useCallback(() => api('/interview/attempts').then(setHistory).catch(e => setError(e.message)), [])

  const pickQuestion = useCallback((list, cat, avoidId) => {
    const pool = list.filter(q => (cat === 'All' || q.category === cat) && q.id !== avoidId)
    return pool[Math.floor(Math.random() * pool.length)] || list[0] || null
  }, [])

  useEffect(() => {
    api('/interview/questions').then(qs => { setQuestions(qs); setQuestion(pickQuestion(qs, 'All')) }).catch(e => setError(e.message))
    loadHistory()
  }, [pickQuestion, loadHistory])

  const stopAll = useCallback(() => {
    stopCam()
    const audioStats = stopAudio()
    const transcript = stopDict()
    window.speechSynthesis?.cancel()
    return { audioStats, transcript }
  }, [stopCam, stopAudio, stopDict])

  useEffect(() => () => { stopAll() }, [stopAll])

  // ---------- start: create attempt, turn on camera + mic, read the question, count down ----------
  const startAnswer = async () => {
    if (!question) return
    const run = ++runRef.current
    setError('')
    setResult(null)
    finishingRef.current = false
    try {
      const { attempt_id } = await api('/interview/attempts', { method: 'POST', body: { question_id: question.id } })
      attemptRef.current = attempt_id
      const camOk = await cam.start()
      if (run !== runRef.current) return
      // Read the question BEFORE the mic starts, so the computer's voice isn't transcribed as the answer
      // or mistaken for background noise.
      if (readAloud) {
        setPhase('asking')
        await speakAndWait(question.text)
        if (run !== runRef.current) return
      }
      const micOk = await audio.start() // the countdown doubles as the time to measure background noise
      if (run !== runRef.current) { stopAll(); return }
      if (!camOk && !micOk) {
        stopAll()
        setPhase('ready')
        setError('Allow camera and microphone access in your browser to start a mock interview.')
        return
      }
      setLive(null)
      setCount(COUNTDOWN)
      setPhase('countdown')
    } catch (e) { setError(e.message); stopAll(); setPhase('ready') }
  }

  useEffect(() => {
    if (phase !== 'countdown') return
    if (count === 0) {
      startRef.current = Date.now()
      setElapsed(0)
      startDict()
      setPhase('answering')
      return
    }
    const t = setTimeout(() => setCount(c => c - 1), 1000)
    return () => clearTimeout(t)
  }, [phase, count, startDict])

  // ---------- finish: stop devices, send transcript + audio stats, get report ----------
  const finishAnswer = useCallback(async () => {
    if (finishingRef.current) return  // the auto-stop timer and the button can both fire
    finishingRef.current = true
    const duration = (Date.now() - startRef.current) / 1000
    setPhase('processing')
    const { audioStats, transcript } = stopAll()
    try {
      const res = await api(`/interview/attempts/${attemptRef.current}/finish`, {
        method: 'POST', body: { transcript, duration_sec: Math.max(1, duration), audio: audioStats },
      })
      setResult(res)
      setPhase('report')
      loadHistory()
    } catch (e) { setError(e.message); setPhase('ready') }
  }, [stopAll, loadHistory])

  const cancel = () => { runRef.current++; stopAll(); setPhase('ready') }

  // timer + auto-stop
  useEffect(() => {
    if (phase !== 'answering') return
    const t = setInterval(() => {
      const s = (Date.now() - startRef.current) / 1000
      setElapsed(s)
      if (s >= MAX_ANSWER_SEC) finishAnswer()
    }, 250)
    return () => clearInterval(t)
  }, [phase, finishAnswer])

  // webcam frames for body language
  useEffect(() => {
    if (phase !== 'answering' || !cam.on) return
    let busy = false
    const t = setInterval(async () => {
      if (busy) return
      busy = true
      try {
        const blob = await capture()
        if (!blob) return
        const form = new FormData()
        form.append('file', blob, 'frame.jpg')
        const res = await api(`/interview/attempts/${attemptRef.current}/frame`, { method: 'POST', form })
        if (phaseRef.current === 'answering') setLive(res)
      } catch (e) {
        if (phaseRef.current === 'answering') setError(e.message)  // a frame still in flight after "Finish" is fine
      } finally { busy = false }
    }, FRAME_MS)
    return () => clearInterval(t)
  }, [phase, cam.on, capture])

  const newQuestion = (cat = category) => { setResult(null); setPhase('ready'); setQuestion(pickQuestion(questions, cat, question?.id)) }

  const openAttempt = async (id) => {
    try {
      const a = await api(`/interview/attempts/${id}`)
      const q = questions.find(x => x.id === a.question_id)
      if (q) setQuestion(q)
      setResult(a)
      setPhase('report')
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) { setError(e.message) }
  }

  const liveText = `${dict.finalText} ${dict.interim}`.trim()
  const liveWords = countWords(liveText)
  const liveWpm = elapsed >= 10 && liveWords >= 5 ? Math.round(liveWords / (elapsed / 60)) : null
  const liveFillers = (liveText.match(FILLER_RE) || []).length
  const busy = ['asking', 'countdown', 'answering', 'processing'].includes(phase)

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Mock interview</h1>
          <p className="muted">Answer out loud on camera. You’ll get a report on eye contact, pace, filler words, posture and content.</p>
        </div>
      </header>

      {error && <div style={{ marginBottom: 'var(--space-4)' }}><Alert onClose={() => setError('')}>{error}</Alert></div>}

      <div className="iv-grid">
        <div className="stack" style={{ gap: 'var(--space-6)' }}>
          <section className="card iv-question" aria-labelledby="iv-q">
            <div className="card-header">
              <div className="segmented" role="group" aria-label="Question category">
                {CATEGORIES.map(c => (
                  <button key={c} aria-pressed={category === c} disabled={busy}
                    onClick={() => { setCategory(c); newQuestion(c) }}>{c}</button>
                ))}
              </div>
              <button className="btn btn-sm btn-ghost" onClick={() => newQuestion()} disabled={busy}><Shuffle size={16} aria-hidden="true" />Another question</button>
            </div>
            {question ? (
              <>
                <span className="badge badge-primary">{question.category}</span>
                <h2 id="iv-q" className="iv-q-text">{question.text}</h2>
                <p className="small muted iv-tip"><Lightbulb size={16} aria-hidden="true" />{question.tip}</p>
                <p className="xs muted">Aim for {question.ideal_seconds[0]}–{question.ideal_seconds[1]} seconds.</p>
              </>
            ) : <div className="skeleton" style={{ height: 120 }} />}
          </section>

          {phase === 'report' && result?.report ? (
            <Report result={result} onRetry={() => { setResult(null); setPhase('ready') }} onNext={() => newQuestion()} />
          ) : (
            <section className="card" aria-labelledby="iv-stage">
              <h2 id="iv-stage" className="sr-only">Answer</h2>
              <div className="iv-stage">
                <div className="camera iv-camera">
                  <video ref={cam.videoRef} autoPlay playsInline muted hidden={!cam.on} aria-label="Your webcam preview" />
                  {!cam.on && (
                    <div className="camera-off">
                      {phase === 'processing' ? <Spinner label="Building your report" /> : <Video size={30} aria-hidden="true" />}
                      <span>{phase === 'processing' ? 'Building your report…' : cam.error || 'Your camera and microphone turn on when you start.'}</span>
                    </div>
                  )}
                  {phase === 'asking' && <div className="iv-countdown iv-asking" aria-live="polite">The interviewer is asking the question…</div>}
                  {phase === 'countdown' && <div className="iv-countdown" aria-live="assertive">{count || 'Go'}</div>}
                  {phase === 'answering' && (
                    <>
                      <span className="iv-rec"><span className="live-dot" aria-hidden="true" />REC {fmtTime(elapsed)}</span>
                      <span className={`state-chip ${live?.facing ? 'ok' : ''}`} role="status">
                        {live == null ? <><Eye size={14} aria-hidden="true" />Checking…</>
                          : live.facing ? <><Eye size={14} aria-hidden="true" />Good eye contact</>
                          : <><EyeOff size={14} aria-hidden="true" />{live.has_face ? 'Look at the camera' : 'Face not visible'}</>}
                      </span>
                    </>
                  )}
                </div>

                {(phase === 'answering' || phase === 'countdown') && (
                  <div className="iv-meters" aria-label="Live feedback">
                    <Meter icon={Eye} label="Eye contact" value={live?.eye_contact_so_far == null ? '—' : `${Math.round(live.eye_contact_so_far * 100)}%`} />
                    <Meter icon={Gauge} label="Pace" value={liveWpm ? `${liveWpm} wpm` : '—'}
                      tone={liveWpm ? (liveWpm < 110 || liveWpm > 170 ? 'warn' : 'good') : undefined} />
                    <Meter icon={MessageSquareText} label="Fillers" value={liveFillers} tone={liveFillers > 4 ? 'warn' : undefined} />
                    <div className="iv-meter">
                      <span className="xs muted"><Mic size={14} aria-hidden="true" />Mic</span>
                      <div className="level" aria-hidden="true"><div style={{ width: `${Math.round(audio.level * 100)}%`, background: audio.speaking ? 'var(--state-engaged)' : 'var(--color-border-strong)' }} /></div>
                    </div>
                  </div>
                )}

                {phase === 'answering' && (
                  <div className="iv-transcript" aria-live="off">
                    {dict.supported
                      ? (liveText ? <Highlighted text={liveText} /> : <span className="muted">Start speaking… your words will appear here.</span>)
                      : <span className="muted">Speech-to-text needs Chrome or Edge, so pace, filler words and content won’t be scored. Eye contact and posture still will be.</span>}
                  </div>
                )}

                {(audio.error || dict.error) && <Alert>{audio.error || dict.error}</Alert>}

                <div className="row iv-actions">
                  {phase === 'ready' && (
                    <>
                      <button className="btn btn-primary" onClick={startAnswer} disabled={!question}><Play size={18} aria-hidden="true" />Start answer</button>
                      <label className="checkbox"><input type="checkbox" checked={readAloud} onChange={e => setReadAloud(e.target.checked)} />Read the question aloud</label>
                    </>
                  )}
                  {(phase === 'countdown' || phase === 'asking') && <button className="btn" onClick={cancel}>Cancel</button>}
                  {phase === 'answering' && (
                    <>
                      <button className="btn btn-danger" onClick={finishAnswer}><Square size={16} aria-hidden="true" />Finish answer</button>
                      <span className="xs muted"><Timer size={14} aria-hidden="true" style={{ verticalAlign: '-2px' }} /> Stops automatically at {fmtTime(MAX_ANSWER_SEC)}</span>
                    </>
                  )}
                </div>
              </div>
            </section>
          )}
        </div>

        <aside className="stack" style={{ gap: 'var(--space-6)' }} aria-label="Your progress">
          <section className="card" aria-labelledby="trend-title">
            <div className="card-header"><h2 className="card-title" id="trend-title"><TrendingUp size={20} aria-hidden="true" />Confidence trend</h2></div>
            {history.length < 2 ? <p className="small muted">Answer at least two questions to see your trend.</p> : (
              <div className="trend" role="img" aria-label={`Last scores: ${history.slice(0, 10).reverse().map(h => h.overall ?? 'n/a').join(', ')}`}>
                {history.slice(0, 10).reverse().map(h => (
                  <div key={h.id} className="trend-col" title={`${h.question}: ${h.overall ?? '—'}`}>
                    <span className="xs mono-num">{h.overall ?? '—'}</span>
                    <div className="trend-bar"><div style={{ height: `${h.overall ?? 0}%` }} className={`tone-${scoreTone(h.overall)}`} /></div>
                  </div>
                ))}
              </div>
            )}
          </section>
          <section className="card" aria-labelledby="hist-title">
            <div className="card-header"><h2 className="card-title" id="hist-title"><History size={20} aria-hidden="true" />Past answers</h2></div>
            {history.length === 0 ? <Empty icon={Video} title="No answers yet">Your reports will be saved here.</Empty> : (
              <ul className="iv-history">
                {history.map(h => (
                  <li key={h.id}>
                    <button onClick={() => openAttempt(h.id)} disabled={busy}>
                      <span className={`score-pill tone-${scoreTone(h.overall)}`}>{h.overall ?? '—'}</span>
                      <span className="iv-h-body"><strong>{h.question}</strong><span className="xs muted">{h.category} · {new Date(h.started_at).toLocaleDateString()}</span></span>
                      <ArrowRight size={16} aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>
      </div>
    </>
  )
}

function scoreTone(s) {
  if (s == null) return 'new'
  return s >= 75 ? 'good' : s >= 50 ? 'mid' : 'low'
}

function Meter({ icon: Icon, label, value, tone }) {
  return (
    <div className="iv-meter">
      <span className="xs muted"><Icon size={14} aria-hidden="true" />{label}</span>
      <strong className={`mono-num ${tone === 'warn' ? 'text-warn' : tone === 'good' ? 'text-good' : ''}`}>{value}</strong>
    </div>
  )
}

const STATUS_BADGE = { good: ['badge-success', 'Good'], ok: ['badge-warning', 'Okay'], work: ['badge-danger', 'Work on this'], na: ['', 'Not measured'] }

function Report({ result, onRetry, onNext }) {
  const r = result.report
  return (
    <section className="card" aria-labelledby="report-title">
      <div className="card-header">
        <h2 className="card-title" id="report-title"><Sparkles size={20} aria-hidden="true" />Your confidence report</h2>
        <div className="row">
          <button className="btn btn-sm" onClick={onRetry}><RotateCcw size={16} aria-hidden="true" />Try again</button>
          <button className="btn btn-sm btn-primary" onClick={onNext}>Next question<ArrowRight size={16} aria-hidden="true" /></button>
        </div>
      </div>

      <div className="report-top">
        <Ring value={r.overall == null ? null : r.overall / 100} label="Overall confidence score" sub="confidence" size={132} />
        <div className="report-summary">
          <p className="small muted">{Math.round(r.duration_sec)}s answer · {r.word_count} words · {r.frames_analyzed} camera frames</p>
          {r.strengths.length > 0 && (
            <ul className="tips good">{r.strengths.map(t => <li key={t}><CircleCheck size={16} aria-hidden="true" />{t}</li>)}</ul>
          )}
          {r.improvements.length > 0 && (
            <ul className="tips work">{r.improvements.map(t => <li key={t}><Lightbulb size={16} aria-hidden="true" />{t}</li>)}</ul>
          )}
          {r.overall == null && <p className="small muted">Not enough was captured to score this answer. Check that the camera and microphone are allowed, then try again.</p>}
        </div>
      </div>

      <div className="metric-grid">
        {r.metrics.map(m => {
          const [cls, text] = STATUS_BADGE[m.status]
          return (
            <div key={m.key} className="metric">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="small muted">{m.label}</span>
                <span className={`badge ${cls}`}>{text}</span>
              </div>
              <strong className="metric-value">{m.display}</strong>
              <div className="meter" aria-hidden="true"><div className={`tone-${scoreTone(m.score)}`} style={{ width: `${m.score ?? 0}%` }} /></div>
              <span className="xs muted">Target: {m.ideal}</span>
            </div>
          )
        })}
      </div>

      {r.coverage.length > 0 && (
        <div className="report-block">
          <h3>Key points</h3>
          <ul className="checklist">
            {r.coverage.map(c => (
              <li key={c.label} className={c.covered ? 'done' : ''}>
                {c.covered ? <CircleCheck size={18} aria-hidden="true" /> : <Circle size={18} aria-hidden="true" />}
                {c.label}<span className="sr-only">{c.covered ? ' (covered)' : ' (missing)'}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="report-block">
        <h3>What you said</h3>
        {result.transcript
          ? <p className="iv-transcript static"><Highlighted text={result.transcript} /></p>
          : <p className="small muted">No speech was captured.</p>}
        {r.fillers.length > 0 && <p className="xs muted">Filler words are highlighted.</p>}
      </div>

      <p className="xs muted privacy"><CameraOff size={14} aria-hidden="true" />“Eye contact” means facing the camera (head position), not exact gaze. No video or audio is stored, only these measurements and your transcript.</p>
    </section>
  )
}
