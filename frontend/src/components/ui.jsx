import { useEffect, useId, useState } from 'react'
import { AlertCircle, Layers, Monitor, Moon, Sun, X } from 'lucide-react'
import { pct } from '../lib'

export function Spinner({ label = 'Loading' }) {
  return <span className="spinner" role="status" aria-label={label} />
}

export function Alert({ children, onClose, tone = 'danger' }) {
  return (
    <div className={`alert alert-${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>
      <AlertCircle size={18} aria-hidden="true" />
      <div>{children}</div>
      {onClose && (
        <button className="btn btn-ghost btn-icon btn-sm" onClick={onClose} aria-label="Dismiss message">
          <X size={16} aria-hidden="true" />
        </button>
      )}
    </div>
  )
}

export function Empty({ icon: Icon, title, children, action }) {
  return (
    <div className="empty">
      <div className="empty-icon"><Icon size={22} aria-hidden="true" /></div>
      <strong>{title}</strong>
      {children && <p className="small">{children}</p>}
      {action}
    </div>
  )
}

export function Ring({ value, size = 120, stroke = 10, label, sub }) {
  const gradId = useId()  // unique per ring, so several rings on one page don't share an SVG id
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const v = value == null ? 0 : Math.max(0, Math.min(1, value))
  return (
    <div className="ring" style={{ width: size, height: size }} role="img" aria-label={`${label}: ${value == null ? 'no data' : pct(v)}`}>
      <svg width={size} height={size} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-muted)" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={`url(#${CSS.escape(gradId)})`} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - v)} style={{ transition: 'stroke-dashoffset 700ms var(--ease-out)' }} />
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#0e7490" /><stop offset="100%" stopColor="#10a37f" />
          </linearGradient>
        </defs>
      </svg>
      <div className="ring-label" aria-hidden="true">
        <strong>{value == null ? '—' : pct(v)}</strong>
        {sub && <span className="xs muted">{sub}</span>}
      </div>
    </div>
  )
}

export function Difficulty({ level }) {
  return (
    <span className="difficulty" aria-label={`Difficulty ${level} of 3`} title={`Difficulty ${level} of 3`}>
      {[1, 2, 3].map(i => <i key={i} className={i <= level ? 'on' : ''} />)}
    </span>
  )
}

/** Renders the plain-text study notes: "- " lines become bullets, "1. " lines become numbered steps. */
export function Notes({ text }) {
  const blocks = []
  for (const line of text.split('\n')) {
    const bullet = line.match(/^\s*-\s+(.*)/)
    const num = line.match(/^\s*\d+\.\s+(.*)/)
    const kind = bullet ? 'ul' : num ? 'ol' : 'p'
    const content = bullet?.[1] ?? num?.[1] ?? line.trim()
    if (!content) { blocks.push(null); continue }
    const last = blocks[blocks.length - 1]
    if (kind !== 'p' && last && last.kind === kind) last.items.push(content)
    else blocks.push({ kind, items: [content] })
  }
  return (
    <div className="notes">
      {blocks.filter(Boolean).map((b, i) => {
        if (b.kind === 'p') return <p key={i}>{b.items[0]}</p>
        const List = b.kind
        return <List key={i}>{b.items.map((it, j) => <li key={j}>{it}</li>)}</List>
      })}
    </div>
  )
}

const THEME_KEY = 'examprep.theme'
const THEMES = [
  { id: 'light', icon: Sun, label: 'Light theme' },
  { id: 'dark', icon: Moon, label: 'Dark theme' },
  { id: 'system', icon: Monitor, label: 'Use system theme' },
]

export function ThemeToggle() {
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem(THEME_KEY) || 'system' } catch { return 'system' }
  })
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') delete root.dataset.theme
    else root.dataset.theme = theme
    try {
      if (theme === 'system') localStorage.removeItem(THEME_KEY)
      else localStorage.setItem(THEME_KEY, theme)
    } catch { /* storage unavailable */ }
  }, [theme])
  return (
    <div className="segmented" role="group" aria-label="Colour theme">
      {THEMES.map(({ id, icon: Icon, label }) => (
        <button key={id} type="button" aria-pressed={theme === id} aria-label={label} title={label} onClick={() => setTheme(id)}>
          <Icon size={16} aria-hidden="true" />
        </button>
      ))}
    </div>
  )
}

export function Logo({ sub = true }) {
  return (
    <span className="logo">
      <span className="logo-mark"><Layers size={20} aria-hidden="true" /></span>
      <span>InterviewPrep AI{sub && <small>Adaptive interview coach</small>}</span>
    </span>
  )
}
