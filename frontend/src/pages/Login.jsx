import { useState } from 'react'
import { BrainCircuit, Eye, EyeOff, GraduationCap, Mic, School, ScanFace } from 'lucide-react'
import { api } from '../api'
import { Alert, Logo, Spinner } from '../components/ui'

const FEATURES = [
  { icon: ScanFace, title: 'Reads how you feel', text: 'Your webcam spots when you look confused or distracted, and the practice adjusts.' },
  { icon: Mic, title: 'Hands-free study', text: 'Say “explain this”, “quiz me” or “give me a hint”.' },
  { icon: BrainCircuit, title: 'Covers the whole interview', text: 'DSA, CS fundamentals, aptitude and HR questions in one place.' },
]

export default function Login({ onLogin }) {
  const [mode, setMode] = useState('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [role, setRole] = useState('student')
  const [teacherCode, setTeacherCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const isLogin = mode === 'login'
  const pwTooShort = !isLogin && password.length > 0 && password.length < 6

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const body = isLogin ? { username, password } : { username, password, role, ...(role === 'teacher' && { teacher_code: teacherCode }) }
      const res = await api(`/auth/${isLogin ? 'login' : 'register'}`, { method: 'POST', body })
      onLogin(res.token, res.user)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="auth">
      <section className="auth-hero" aria-label="About InterviewPrep AI">
        <Logo />
        <div>
          <h1>Walk into your next interview prepared.</h1>
          <p className="lead">An AI practice partner for placement and job interviews. It notices when you’re stuck, explains things more simply, and keeps you working on your weakest topics.</p>
        </div>
        <ul className="feature-list">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <li key={title}>
              <span className="fi"><Icon size={20} aria-hidden="true" /></span>
              <div><strong>{title}</strong><span>{text}</span></div>
            </li>
          ))}
        </ul>
      </section>

      <section className="auth-panel">
        <form className="auth-form" onSubmit={submit} noValidate={false}>
          <div>
            <h2 style={{ fontSize: '1.6rem' }}>{isLogin ? 'Welcome back' : 'Create your account'}</h2>
            <p className="muted" style={{ marginTop: 6 }}>{isLogin ? 'Log in to continue where you left off.' : 'It takes less than a minute.'}</p>
          </div>

          <div className="segmented" role="tablist" aria-label="Choose log in or sign up">
            <button type="button" role="tab" aria-selected={isLogin} onClick={() => { setMode('login'); setError('') }}>Log in</button>
            <button type="button" role="tab" aria-selected={!isLogin} onClick={() => { setMode('register'); setError('') }}>Sign up</button>
          </div>

          <div className="field">
            <label className="field-label" htmlFor="username">Username</label>
            <input id="username" className="input" value={username} onChange={e => setUsername(e.target.value)}
              required minLength={3} maxLength={64} autoComplete="username" autoCapitalize="none" spellCheck={false} />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="password">Password</label>
            <div className="input-wrap">
              <input id="password" className="input" type={showPw ? 'text' : 'password'} value={password}
                onChange={e => setPassword(e.target.value)} required minLength={6}
                autoComplete={isLogin ? 'current-password' : 'new-password'}
                aria-invalid={pwTooShort} aria-describedby={!isLogin ? 'pw-hint' : undefined} />
              <button type="button" className="btn btn-ghost btn-icon" onClick={() => setShowPw(s => !s)}
                aria-label={showPw ? 'Hide password' : 'Show password'} aria-pressed={showPw}>
                {showPw ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
              </button>
            </div>
            {!isLogin && <span id="pw-hint" className="field-hint" style={pwTooShort ? { color: 'var(--color-danger)' } : undefined}>At least 6 characters.</span>}
          </div>

          {!isLogin && (
            <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className="field-label" style={{ marginBottom: 6 }}>I am a</legend>
              <div className="role-pick">
                <label><input type="radio" name="role" value="student" checked={role === 'student'} onChange={() => setRole('student')} /><GraduationCap size={18} aria-hidden="true" />Student</label>
                <label><input type="radio" name="role" value="teacher" checked={role === 'teacher'} onChange={() => setRole('teacher')} /><School size={18} aria-hidden="true" />Teacher</label>
              </div>
            </fieldset>
          )}

          {!isLogin && role === 'teacher' && (
            <div className="field">
              <label className="field-label" htmlFor="teacher-code">Teacher code</label>
              <input id="teacher-code" className="input" value={teacherCode} onChange={e => setTeacherCode(e.target.value)}
                required autoComplete="off" aria-describedby="teacher-code-hint" />
              <span id="teacher-code-hint" className="field-hint">Teacher accounts can see every student’s progress, so your institute gives you this code.</span>
            </div>
          )}

          {error && <Alert onClose={() => setError('')}>{error}</Alert>}

          <button className="btn btn-primary btn-block" disabled={busy || pwTooShort} aria-busy={busy}>
            {busy && <Spinner label="Submitting" />}
            {busy ? 'Please wait…' : isLogin ? 'Log in' : 'Create account'}
          </button>
          <p className="xs muted" style={{ textAlign: 'center' }}>
            The camera is only used during practice sessions you start. No images are stored.
          </p>
        </form>
      </section>
    </div>
  )
}
