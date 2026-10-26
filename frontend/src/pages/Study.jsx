import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Bot, BookOpen, Camera, CameraOff, CircleCheck, CircleX, ExternalLink, Lightbulb, Mic, MicOff,
  Send, ShieldCheck, Square, UserRound, Volume2, Zap,
} from 'lucide-react'
import { api } from '../api'
import { speak, useSpeech, useWebcam } from '../hooks'
import { Alert, Difficulty, Empty, Notes, Spinner } from '../components/ui'
import { STATE_META } from '../lib'

const FRAME_INTERVAL_MS = 2500
const FEEDBACK_COOLDOWN_MS = 30000
const KEYS = ['A', 'B', 'C', 'D', 'E']
const QUICK_COMMANDS = ['Explain this', 'Make it easier', 'Quiz me', 'Give me a hint', 'Harder', 'What should I study?']
const ACTION_LABEL = { easier: 'Make it easier', harder: 'Try a harder one', explain: 'Show the notes' }

export default function Study() {
  const [params] = useSearchParams()
  const [subjects, setSubjects] = useState([])
  const [topic, setTopic] = useState(null)
  const [material, setMaterial] = useState(null)
  const [question, setQuestion] = useState(null)
  const [eliminated, setEliminated] = useState([])
  const [result, setResult] = useState(null)
  const [sessionId, setSessionId] = useState(null)
  const [emotion, setEmotion] = useState(null)
  const [feed, setFeed] = useState([])
  const [command, setCommand] = useState('')
  const [thinking, setThinking] = useState(false)
  const [loadingQ, setLoadingQ] = useState(false)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')
  const [voiceOut, setVoiceOut] = useState(true)

  const cam = useWebcam()
  const { stop: stopCam, capture } = cam
  const topicRef = useRef(null)
  const sessionRef = useRef(null)
  const lastFeedback = useRef({ type: null, at: 0 })
  const feedRef = useRef(null)
  topicRef.current = topic?.id ?? null
  sessionRef.current = sessionId

  const say = useCallback((text, kind = 'info', action = null) => {
    setFeed(f => [...f, { id: Date.now() + Math.random(), text, kind, action }].slice(-30))
  }, [])

  // Keep the newest assistant message in view without scrolling the whole page
  useEffect(() => {
    const el = feedRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [feed, thinking])

  // ---------- content ----------
  const loadTopic = useCallback(async (topicId, level = 'basic') => {
    const t = await api(`/topics/${topicId}`)
    setTopic(t)
    topicRef.current = t.id
    setMaterial(t.materials.find(m => m.level === level) || t.materials[0] || null)
    setQuestion(null)
    setResult(null)
    return t
  }, [])

  const loadQuestion = useCallback(async (difficulty) => {
    if (!topicRef.current) return
    setLoadingQ(true)
    try {
      const q = await api(`/topics/${topicRef.current}/question${difficulty ? `?difficulty=${difficulty}` : ''}`)
      setQuestion(q)
      setEliminated([])
      setResult(null)
    } catch (e) { setError(e.message) } finally { setLoadingQ(false) }
  }, [])

  useEffect(() => {
    (async () => {
      try {
        setSubjects(await api('/subjects'))
        let id = Number(params.get('topic'))
        if (!id) id = (await api('/recommendations'))[0]?.topic_id
        if (id) await loadTopic(id)
      } catch (e) { setError(e.message) }
    })()
  }, [params, loadTopic])

  // ---------- session + emotion loop ----------
  const startSession = async () => {
    setError('')
    setStarting(true)
    try {
      const { session_id } = await api('/sessions', { method: 'POST' })
      setSessionId(session_id)
      lastFeedback.current = { type: null, at: 0 }
      await cam.start()
      say('Session started. I’ll watch for signs that you’re stuck or tired and adjust what you study.', 'good')
    } catch (e) { setError(e.message) } finally { setStarting(false) }
  }

  const endSession = useCallback(async () => {
    stopCam()
    const sid = sessionRef.current
    setSessionId(null)
    setEmotion(null)
    if (!sid) return
    try {
      const s = await api(`/sessions/${sid}/end`, { method: 'POST' })
      const total = Object.values(s.states).reduce((a, b) => a + b, 0)
      const focus = total ? Math.round(((s.states.engaged || 0) + (s.states.neutral || 0)) / total * 100) : null
      say(`Session complete. You got ${s.correct} of ${s.questions} questions right${focus != null ? ` and were focused about ${focus}% of the time` : ''}. Nice work!`, 'good')
    } catch (e) { setError(e.message) }
  }, [stopCam, say])

  const applyFeedback = useCallback(async (type) => {
    try {
      if (type === 'easier') { if (topicRef.current) await loadTopic(topicRef.current, 'basic'); await loadQuestion(1) }
      else if (type === 'harder') { if (topicRef.current) await loadTopic(topicRef.current, 'advanced'); await loadQuestion(3) }
      else if (type === 'explain') { if (topicRef.current) await loadTopic(topicRef.current, 'basic') }
    } catch (e) { setError(e.message) }
  }, [loadTopic, loadQuestion])

  useEffect(() => {
    if (!cam.on || !sessionId) return
    let busy = false
    const timer = setInterval(async () => {
      if (busy) return
      busy = true
      try {
        const blob = await capture()
        if (!blob) return
        const form = new FormData()
        form.append('file', blob, 'frame.jpg')
        form.append('session_id', sessionRef.current)
        if (topicRef.current) form.append('topic_id', topicRef.current)
        const r = await api('/emotion/frame', { method: 'POST', form })
        setEmotion(r)
        const fb = r.feedback
        const now = Date.now()
        if (fb && (fb.type !== lastFeedback.current.type || now - lastFeedback.current.at > FEEDBACK_COOLDOWN_MS)) {
          lastFeedback.current = { type: fb.type, at: now }
          say(fb.message, fb.type === 'harder' ? 'good' : fb.type === 'break' ? 'info' : 'warn', fb.type === 'break' ? null : fb.type)
        }
      } catch (e) {
        setError(e.message)
      } finally {
        busy = false
      }
    }, FRAME_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [cam.on, sessionId, capture, say])

  useEffect(() => () => {
    if (sessionRef.current) api(`/sessions/${sessionRef.current}/end`, { method: 'POST' }).catch(() => {})
  }, [])

  // ---------- quiz ----------
  const answer = useCallback(async (option) => {
    if (result || !question || eliminated.includes(option)) return
    try {
      const r = await api('/answer', { method: 'POST', body: { question_id: question.id, selected: option, session_id: sessionId } })
      setResult({ ...r, selected: option })
    } catch (e) { setError(e.message) }
  }, [result, question, eliminated, sessionId])

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.closest?.('input, textarea, select, [contenteditable]') || e.metaKey || e.ctrlKey || e.altKey) return
      if (!question) return
      const k = e.key.toUpperCase()
      const idx = KEYS.indexOf(k) >= 0 ? KEYS.indexOf(k) : Number(k) - 1
      if (idx >= 0 && idx < question.options.length && !result) { e.preventDefault(); answer(question.options[idx]) }
      else if (k === 'N' && result) { e.preventDefault(); loadQuestion() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [question, result, answer, loadQuestion])

  // ---------- voice ----------
  const runCommand = useCallback(async (text) => {
    say(text, 'user')
    setThinking(true)
    try {
      const r = await api('/voice/command', { method: 'POST', body: { text, topic_id: topicRef.current, question_id: question?.id ?? null, eliminated } })
      if (r.topic_id && r.topic_id !== topicRef.current) await loadTopic(r.topic_id)
      if (r.material) setMaterial(r.material)
      if (r.question) { setQuestion(r.question); setEliminated([]); setResult(null) }
      if (r.eliminate) setEliminated(e => [...e, r.eliminate])
      const reply = r.message || {
        explain: 'Here are the notes for this topic.', easier: 'I switched to simpler notes and an easier question.',
        harder: 'Here’s the advanced material and a harder question.', quiz: 'Here’s a question for you.',
        next: 'Next question.', recommend: 'Here’s what I recommend.',
      }[r.intent] || 'Done.'
      say(r.eliminate ? `${reply} I’ve also crossed out one wrong option.` : reply, r.intent === 'unknown' ? 'warn' : 'info')
      if (voiceOut) speak(reply)
    } catch (e) { setError(e.message) } finally { setThinking(false) }
  }, [question, eliminated, loadTopic, say, voiceOut])

  const speech = useSpeech(runCommand)

  const submitCommand = (e) => {
    e.preventDefault()
    if (!command.trim() || thinking) return
    runCommand(command.trim())
    setCommand('')
  }

  // Grouped scores from the server (confused = sad + fear + contempt, etc.) drive the signal bars
  const signal = emotion?.groups ? { ...emotion.groups, neutral: emotion.scores?.neutral ?? 0 } : {}
  const stateMeta = emotion ? STATE_META[emotion.state] : null

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Practice session</h1>
          <p className="muted">Revise the notes, answer interview questions, and talk to your coach.</p>
        </div>
        <div className="row">
          <span className={`live-pill ${sessionId ? 'on' : ''}`} role="status">
            <span className="live-dot" aria-hidden="true" />{sessionId ? 'Live session' : 'Not started'}
          </span>
          {sessionId
            ? <button className="btn btn-danger" onClick={endSession}><Square size={16} aria-hidden="true" />End session</button>
            : <button className="btn btn-primary" onClick={startSession} disabled={starting}>
                {starting ? <Spinner label="Starting" /> : <Camera size={18} aria-hidden="true" />}Start session
              </button>}
        </div>
      </header>

      {error && <div style={{ marginBottom: 'var(--space-4)' }}><Alert onClose={() => setError('')}>{error}</Alert></div>}

      <div className="study-toolbar">
        <div className="field">
          <label className="field-label" htmlFor="topic">Topic</label>
          <select id="topic" className="select" value={topic?.id ?? ''} onChange={e => loadTopic(Number(e.target.value)).catch(err => setError(err.message))}>
            <option value="" disabled>Choose a topic…</option>
            {subjects.map(s => (
              <optgroup key={s.id} label={s.name}>
                {s.topics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </optgroup>
            ))}
          </select>
        </div>
        {topic && (
          <div className="field">
            <span className="field-label" id="level-label">Level</span>
            <div className="segmented" role="group" aria-labelledby="level-label">
              {topic.materials.map(m => (
                <button key={m.id} aria-pressed={material?.id === m.id} onClick={() => setMaterial(m)}>{m.level}</button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="study-grid">
        <div className="stack" style={{ gap: 'var(--space-6)' }}>
          <article className="card" aria-labelledby="notes-title">
            {material ? (
              <>
                <div className="card-header">
                  <h2 className="card-title" id="notes-title"><BookOpen size={20} aria-hidden="true" />{material.title}</h2>
                  <span className={`badge ${material.level === 'advanced' ? 'badge-success' : 'badge-info'}`}>{material.level}</span>
                </div>
                <Notes text={material.body} />
                {material.url && <a className="source-link" href={material.url} target="_blank" rel="noreferrer">Read more<ExternalLink size={14} aria-hidden="true" /><span className="sr-only">(opens in a new tab)</span></a>}
              </>
            ) : <Empty icon={BookOpen} title="Pick a topic">Choose a topic above to load its notes.</Empty>}
          </article>

          <section className="card" aria-labelledby="practice-title">
            <div className="card-header">
              <h2 className="card-title" id="practice-title"><Zap size={20} aria-hidden="true" />Practice</h2>
              <button className="btn btn-sm" onClick={() => loadQuestion()} disabled={!topic || loadingQ}>
                {loadingQ && <Spinner label="Loading question" />}{question ? 'Next question' : 'Start quiz'}
              </button>
            </div>
            {!question ? (
              <Empty icon={Zap} title="Ready when you are">Click “Start quiz” or say “quiz me”. Questions get harder as you improve.</Empty>
            ) : (
              <>
                <div className="q-meta"><Difficulty level={question.difficulty} /><span className="xs muted">Answer with keys <span className="kbd">A</span>–<span className="kbd">{KEYS[question.options.length - 1]}</span></span></div>
                <p className="q-text" id="q-text">{question.text}</p>
                <div className="options" role="group" aria-labelledby="q-text">
                  {question.options.map((o, i) => {
                    const isCorrect = result && o === result.correct_option
                    const isWrong = result && o === result.selected && !result.correct
                    const out = eliminated.includes(o)
                    let cls = 'option'
                    if (isCorrect) cls += ' correct'
                    else if (isWrong) cls += ' wrong'
                    else if (result) cls += ' dim'
                    if (out) cls += ' eliminated'
                    return (
                      <button key={o} className={cls} onClick={() => answer(o)} disabled={!!result || out}
                        aria-label={`${KEYS[i]}: ${o}${isCorrect ? ', correct answer' : ''}${isWrong ? ', your answer, incorrect' : ''}${out ? ', crossed out by hint' : ''}`}>
                        <span className="key" aria-hidden="true">{KEYS[i]}</span>
                        <span>{o}</span>
                        {isCorrect && <CircleCheck className="state-icon" size={20} color="var(--color-success)" aria-hidden="true" />}
                        {isWrong && <CircleX className="state-icon" size={20} color="var(--color-danger)" aria-hidden="true" />}
                      </button>
                    )
                  })}
                </div>
                <div aria-live="polite">
                  {result && (
                    <div className={`result ${result.correct ? 'good' : 'bad'}`}>
                      {result.correct ? <CircleCheck size={22} aria-hidden="true" /> : <CircleX size={22} aria-hidden="true" />}
                      <div>
                        <strong>{result.correct ? 'Correct!' : `Not quite. The answer is ${result.correct_option}.`}</strong>
                        <span className="small">{result.explanation}</span>
                        <div className="row" style={{ marginTop: 'var(--space-3)' }}>
                          <button className="btn btn-sm btn-primary" onClick={() => loadQuestion()}>Next question</button>
                          <span className="xs muted">or press <span className="kbd">N</span></span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}
          </section>
        </div>

        <aside className="study-rail" aria-label="Session tools">
          <section className="card" aria-labelledby="cam-title">
            <div className="card-header" style={{ marginBottom: 'var(--space-3)' }}>
              <h2 className="card-title" id="cam-title"><Camera size={20} aria-hidden="true" />Focus monitor</h2>
              {emotion?.emotion && emotion.emotion !== 'no_face' && <span className="xs muted mono-num">{Math.round(emotion.confidence * 100)}% sure</span>}
            </div>
            <div className="camera">
              <video ref={cam.videoRef} autoPlay playsInline muted hidden={!cam.on} aria-label="Your webcam preview" />
              {!cam.on && (
                <div className="camera-off">
                  <CameraOff size={28} aria-hidden="true" />
                  <span>{cam.error || 'Camera is off. Start a session to turn it on.'}</span>
                </div>
              )}
              {cam.on && stateMeta && (
                <span className="state-chip" role="status" aria-live="polite">
                  <span className="dot" style={{ background: stateMeta.color }} aria-hidden="true" />{stateMeta.label}
                  {emotion.state === 'distracted' && emotion.reason && <small style={{ fontWeight: 500, opacity: .85 }}>· {emotion.reason}</small>}
                </span>
              )}
            </div>
            {cam.on && (
              <div className="signal" aria-hidden="true">
                {['engaged', 'neutral', 'confused', 'frustrated'].map(s => (
                  <div key={s}><div className="bar"><span style={{ height: `${Math.round((signal[s] || 0) * 100)}%`, background: STATE_META[s].color }} /></div>{STATE_META[s].label}</div>
                ))}
                <div><div className="bar"><span style={{ height: emotion?.state === 'distracted' ? '100%' : '0%', background: STATE_META.distracted.color }} /></div>Away</div>
              </div>
            )}
            {cam.on && emotion?.calibrating && (
              <p className="xs muted" role="status" style={{ marginTop: 'var(--space-3)' }}>Getting used to your face… look at the screen normally for a few seconds.</p>
            )}
            <p className="privacy xs muted"><ShieldCheck size={14} aria-hidden="true" />Frames are analysed on the server and thrown away. Only the label is saved.</p>
          </section>

          <section className="card" aria-labelledby="voice-title">
            <div className="voice-head">
              <button className={`mic ${speech.listening ? 'listening' : ''}`} onClick={speech.listen} disabled={!speech.supported || speech.listening || thinking}
                aria-label={speech.listening ? 'Listening' : 'Speak a command'}>
                {speech.supported ? <Mic size={26} aria-hidden="true" /> : <MicOff size={26} aria-hidden="true" />}
              </button>
              <div>
                <h2 id="voice-title">Voice commands</h2>
                <p className="small muted">{!speech.supported ? 'Voice needs Chrome or Edge. You can type instead.' : speech.listening ? 'Listening… go ahead and speak.' : 'Tap the mic and say what you need.'}</p>
              </div>
            </div>
            {speech.error && <div style={{ marginTop: 'var(--space-3)' }}><Alert>{speech.error}</Alert></div>}
            <div className="chips">
              {QUICK_COMMANDS.map(c => <button key={c} className="chip" onClick={() => runCommand(c)} disabled={thinking}>{c}</button>)}
            </div>
            <form onSubmit={submitCommand} className="command-form">
              <label htmlFor="cmd" className="sr-only">Type a command</label>
              <input id="cmd" className="input" value={command} onChange={e => setCommand(e.target.value)} placeholder="Type a command…" autoComplete="off" />
              <button className="btn btn-primary btn-icon" aria-label="Send command" disabled={!command.trim() || thinking}><Send size={18} aria-hidden="true" /></button>
            </form>
            <label className="checkbox" style={{ marginTop: 'var(--space-2)' }}>
              <input type="checkbox" checked={voiceOut} onChange={e => setVoiceOut(e.target.checked)} />
              <Volume2 size={16} aria-hidden="true" />Read replies aloud
            </label>
          </section>

          <section className="card" aria-labelledby="feed-title">
            <div className="card-header" style={{ marginBottom: 'var(--space-3)' }}>
              <h2 className="card-title" id="feed-title"><Bot size={20} aria-hidden="true" />Assistant</h2>
            </div>
            <div className="feed" ref={feedRef} role="log" aria-live="polite" aria-relevant="additions">
              {feed.length === 0 && !thinking && (
                <div className="msg"><span className="msg-avatar" aria-hidden="true"><Bot size={16} /></span>
                  <div className="msg-body">Hi! Start a session, or ask me something like “explain this” or “give me a hint”.</div></div>
              )}
              {feed.map(f => (
                <div key={f.id} className={`msg ${f.kind}`}>
                  <span className="msg-avatar" aria-hidden="true">
                    {f.kind === 'user' ? <UserRound size={16} /> : f.kind === 'warn' ? <Lightbulb size={16} /> : <Bot size={16} />}
                  </span>
                  <div className="msg-body">
                    <span className="sr-only">{f.kind === 'user' ? 'You said:' : 'Assistant:'}</span>{f.text}
                    {f.action && <div><button className="btn btn-sm" onClick={() => applyFeedback(f.action)}>{ACTION_LABEL[f.action]}</button></div>}
                  </div>
                </div>
              ))}
              {thinking && (
                <div className="msg"><span className="msg-avatar" aria-hidden="true"><Bot size={16} /></span>
                  <div className="msg-body"><span className="typing" role="status" aria-label="Assistant is thinking"><i /><i /><i /></span></div></div>
              )}
            </div>
          </section>
        </aside>
      </div>
    </>
  )
}
