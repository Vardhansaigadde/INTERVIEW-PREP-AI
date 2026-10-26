import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, CalendarClock, CircleCheckBig, Flame, ListChecks, Route as RouteIcon, ScanFace, Sparkles, Target, TriangleAlert, Video } from 'lucide-react'
import { api } from '../api'
import { Alert, Empty, Ring } from '../components/ui'
import { STATE_META, masteryTone, pct } from '../lib'

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

export default function Dashboard({ user }) {
  const [progress, setProgress] = useState(null)
  const [plan, setPlan] = useState([])
  const [interviews, setInterviews] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([api('/progress'), api('/recommendations'), api('/interview/attempts')])
      .then(([p, r, iv]) => { setProgress(p); setPlan(r); setInterviews(iv) })
      .catch(e => setError(e.message))
  }, [])

  if (error) return <Alert>{error}</Alert>
  if (!progress) return <DashboardSkeleton />

  const moodTotal = Object.values(progress.emotion_summary).reduce((a, b) => a + b, 0)
  const focused = moodTotal ? ((progress.emotion_summary.engaged || 0) + (progress.emotion_summary.neutral || 0)) / moodTotal : null
  const practised = progress.topics.filter(t => t.attempts)
  const strong = practised.filter(t => t.mastery >= 0.75).length
  const bySubject = progress.topics.reduce((acc, t) => ((acc[t.subject] ??= []).push(t), acc), {})
  const [next, ...rest] = plan

  return (
    <>
      <header className="page-header">
        <div>
          <h1>{greeting()}, {user.username}</h1>
          <p className="muted">{progress.total_attempts
            ? `You've practised ${practised.length} of ${progress.topics.length} topics. Here's what to do next.`
            : 'Start your first practice session. We’ll learn what you need as you go.'}</p>
        </div>
        <Link to="/study" className="btn btn-primary"><Sparkles size={18} aria-hidden="true" />Start practising</Link>
      </header>

      <section className="kpis" aria-label="Your stats">
        <Kpi icon={ListChecks} tone="primary" label="Questions answered" value={progress.total_attempts} />
        <Kpi icon={Target} tone="accent" label="Overall accuracy" value={progress.accuracy == null ? '—' : pct(progress.accuracy)} />
        <Kpi icon={CircleCheckBig} tone="success" label="Topics mastered" value={`${strong}/${progress.topics.length}`} />
        <Kpi icon={Flame} tone="warning" label="Study sessions" value={progress.sessions} />
      </section>

      <div className="dash-grid">
        <div className="stack" style={{ gap: 'var(--space-6)' }}>
          {next && (
            <section className="card next-up" aria-labelledby="next-up-title">
              <span className="eyebrow"><Sparkles size={14} aria-hidden="true" />Recommended next</span>
              <h2 id="next-up-title">{next.topic}</h2>
              <p>{next.reason}</p>
              <div className="next-up-meta">
                <span className="badge">{next.subject}</span>
                <span className="badge">{next.level} level</span>
                {next.attempts > 0 && <span className="badge">Mastery {pct(next.mastery)}</span>}
              </div>
              <Link className="btn" to={`/study?topic=${next.topic_id}`}>Study this now<ArrowRight size={18} aria-hidden="true" /></Link>
            </section>
          )}

          <section className="card" aria-labelledby="mastery-title">
            <div className="card-header">
              <h2 className="card-title" id="mastery-title"><Target size={20} aria-hidden="true" />Mastery by topic</h2>
              <span className="xs muted">Recent answers count more</span>
            </div>
            {Object.entries(bySubject).map(([subject, topics]) => (
              <div key={subject} className="subject-group">
                <div className="subject-head"><h3>{subject}</h3><span className="xs muted">{topics.filter(t => t.attempts).length}/{topics.length} practised</span></div>
                <ul className="mastery-list" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                  {topics.map(t => {
                    const tone = masteryTone(t)
                    return (
                      <li key={t.topic_id} className="mastery-row">
                        <span className="name">
                          <span>{t.topic}</span>
                          {t.struggle > 0.4 && <span className="badge badge-danger"><TriangleAlert size={12} aria-hidden="true" />Struggling</span>}
                        </span>
                        <span className="value">{t.attempts ? pct(t.mastery) : <span className="badge">New</span>}</span>
                        <div className="meter" role="meter" aria-label={`${t.topic} mastery`} aria-valuemin={0} aria-valuemax={100}
                          aria-valuenow={Math.round(t.mastery * 100)} aria-valuetext={t.attempts ? pct(t.mastery) : 'Not practised yet'}>
                          <div className={`tone-${tone}`} style={{ width: t.attempts ? pct(t.mastery) : '0%' }} />
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}
          </section>
        </div>

        <div className="stack" style={{ gap: 'var(--space-6)' }}>
          <section className="card" aria-labelledby="acc-title">
            <div className="card-header"><h2 className="card-title" id="acc-title"><CalendarClock size={20} aria-hidden="true" />Interview readiness</h2></div>
            <div className="row" style={{ gap: 'var(--space-6)', flexWrap: 'nowrap' }}>
              <Ring value={progress.accuracy} label="Overall accuracy" sub="accuracy" />
              <div className="stack" style={{ gap: 'var(--space-3)' }}>
                <div><div className="kpi-value">{practised.length}<span className="muted small">/{progress.topics.length}</span></div><div className="small muted">topics practised</div></div>
                <div><div className="kpi-value">{focused == null ? '—' : pct(focused)}</div><div className="small muted">time focused on camera</div></div>
              </div>
            </div>
          </section>

          <section className="card" aria-labelledby="iv-title">
            <div className="card-header">
              <h2 className="card-title" id="iv-title"><Video size={20} aria-hidden="true" />Mock interview</h2>
              <Link className="btn btn-sm" to="/interview">{interviews.length ? 'Practise again' : 'Try it'}</Link>
            </div>
            {interviews.length === 0 ? (
              <p className="small muted">Answer a question on camera and get a report on eye contact, pace, filler words and posture.</p>
            ) : (
              <div className="row" style={{ gap: 'var(--space-4)', flexWrap: 'nowrap' }}>
                <Ring value={interviews[0].overall == null ? null : interviews[0].overall / 100} size={84} stroke={8} label="Latest confidence score" />
                <div style={{ minWidth: 0 }}>
                  <div className="small muted">Latest answer</div>
                  <strong className="small" style={{ display: 'block' }}>{interviews[0].question}</strong>
                  <span className="xs muted">{interviews.length} answer{interviews.length === 1 ? '' : 's'} practised
                    {interviews.length > 1 && interviews[0].overall != null && interviews[1].overall != null &&
                      ` · ${interviews[0].overall >= interviews[1].overall ? '+' : ''}${Math.round(interviews[0].overall - interviews[1].overall)} vs previous`}</span>
                </div>
              </div>
            )}
          </section>

          <section className="card" aria-labelledby="path-title">
            <div className="card-header"><h2 className="card-title" id="path-title"><RouteIcon size={20} aria-hidden="true" />Your study path</h2></div>
            {rest.length === 0 ? <p className="muted small">Your path will show up here.</p> : (
              <ol className="path">
                {rest.map((p, i) => (
                  <li key={p.topic_id}>
                    <span className="path-step" aria-hidden="true">{i + 2}</span>
                    <div className="path-body">
                      <strong>{p.topic}</strong>
                      <div className="row"><span className="badge">{p.subject}</span><span className={`badge ${p.level === 'advanced' ? 'badge-success' : 'badge-info'}`}>{p.level}</span></div>
                    </div>
                    <Link className="btn btn-sm" to={`/study?topic=${p.topic_id}`} aria-label={`Study ${p.topic}`}>Study</Link>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section className="card" aria-labelledby="mood-title">
            <div className="card-header"><h2 className="card-title" id="mood-title"><ScanFace size={20} aria-hidden="true" />How you felt while studying</h2></div>
            {moodTotal === 0 ? (
              <Empty icon={ScanFace} title="No webcam data yet">Turn the camera on during a study session to see when you were focused or stuck.</Empty>
            ) : (
              <>
                <div className="mood-bar" role="img" aria-label={Object.entries(progress.emotion_summary).map(([s, n]) => `${STATE_META[s]?.label ?? s} ${pct(n / moodTotal)}`).join(', ')}>
                  {Object.entries(progress.emotion_summary).map(([s, n]) => <div key={s} style={{ flex: n, background: STATE_META[s]?.color }} />)}
                </div>
                <ul className="mood-legend">
                  {Object.entries(progress.emotion_summary).sort((a, b) => b[1] - a[1]).map(([s, n]) => (
                    <li key={s}><span className="dot" style={{ background: STATE_META[s]?.color }} />{STATE_META[s]?.label ?? s}<b>{pct(n / moodTotal)}</b></li>
                  ))}
                </ul>
              </>
            )}
          </section>
        </div>
      </div>
    </>
  )
}

function Kpi({ icon: Icon, tone, label, value }) {
  return (
    <div className="card kpi">
      <span className="kpi-icon" style={{ background: `var(--color-${tone}-soft)`, color: `var(--color-${tone})` }}><Icon size={22} aria-hidden="true" /></span>
      <div><div className="kpi-value">{value}</div><div className="small muted">{label}</div></div>
    </div>
  )
}

function DashboardSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading dashboard">
      <div className="skeleton" style={{ height: 44, width: 320, marginBottom: 24 }} />
      <div className="kpis">{[0, 1, 2, 3].map(i => <div key={i} className="skeleton" style={{ height: 92 }} />)}</div>
      <div className="dash-grid">
        <div className="skeleton" style={{ height: 420 }} />
        <div className="skeleton" style={{ height: 420 }} />
      </div>
    </div>
  )
}
