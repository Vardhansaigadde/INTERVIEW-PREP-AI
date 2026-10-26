import { useEffect, useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, Search, TriangleAlert, UserRound, Users } from 'lucide-react'
import { api } from '../api'
import { Alert, Empty } from '../components/ui'
import { pct } from '../lib'

const COLUMNS = [
  { key: 'username', label: 'Student' },
  { key: 'attempts', label: 'Questions' },
  { key: 'accuracy', label: 'Accuracy' },
]

export default function Teacher() {
  const [students, setStudents] = useState(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState({ key: 'accuracy', dir: 'asc' })

  useEffect(() => { api('/teacher/students').then(setStudents).catch(e => setError(e.message)) }, [])

  const rows = useMemo(() => {
    if (!students) return []
    const q = query.trim().toLowerCase()
    const filtered = students.filter(s => !q || s.username.toLowerCase().includes(q))
    const val = s => s[sort.key] ?? (sort.dir === 'asc' ? Infinity : -Infinity)
    return [...filtered].sort((a, b) => {
      const x = val(a), y = val(b)
      const c = typeof x === 'string' ? x.localeCompare(y) : x - y
      return sort.dir === 'asc' ? c : -c
    })
  }, [students, query, sort])

  if (error) return <Alert>{error}</Alert>
  if (!students) return <div className="skeleton" style={{ height: 360 }} aria-busy="true" aria-label="Loading students" />

  const active = students.filter(s => s.attempts)
  const avg = active.length ? active.reduce((a, s) => a + s.accuracy, 0) / active.length : null
  const atRisk = students.filter(s => (s.accuracy != null && s.accuracy < 0.5) || s.struggling_topics.length).length

  const toggleSort = (key) => setSort(s => ({ key, dir: s.key === key && s.dir === 'asc' ? 'desc' : 'asc' }))

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Class overview</h1>
          <p className="muted">See who needs help and which topics they find hardest.</p>
        </div>
      </header>

      <section className="kpis" aria-label="Class stats">
        <div className="card kpi"><span className="kpi-icon" style={{ background: 'var(--color-primary-soft)', color: 'var(--color-primary)' }}><Users size={22} aria-hidden="true" /></span>
          <div><div className="kpi-value">{students.length}</div><div className="small muted">Students</div></div></div>
        <div className="card kpi"><span className="kpi-icon" style={{ background: 'var(--color-accent-soft)', color: 'var(--color-accent)' }}><UserRound size={22} aria-hidden="true" /></span>
          <div><div className="kpi-value">{active.length}</div><div className="small muted">Active learners</div></div></div>
        <div className="card kpi"><span className="kpi-icon" style={{ background: 'var(--color-success-soft)', color: 'var(--color-success)' }}><ArrowUp size={22} aria-hidden="true" /></span>
          <div><div className="kpi-value">{avg == null ? '—' : pct(avg)}</div><div className="small muted">Average accuracy</div></div></div>
        <div className="card kpi"><span className="kpi-icon" style={{ background: 'var(--color-danger-soft)', color: 'var(--color-danger)' }}><TriangleAlert size={22} aria-hidden="true" /></span>
          <div><div className="kpi-value">{atRisk}</div><div className="small muted">Need attention</div></div></div>
      </section>

      <section className="card" aria-labelledby="students-title">
        <div className="card-header">
          <h2 className="card-title" id="students-title"><Users size={20} aria-hidden="true" />Students</h2>
          <div className="search">
            <Search size={16} aria-hidden="true" />
            <label htmlFor="student-search" className="sr-only">Search students</label>
            <input id="student-search" className="input" type="search" placeholder="Search by name" value={query} onChange={e => setQuery(e.target.value)} />
          </div>
        </div>
        {students.length === 0 ? (
          <Empty icon={Users} title="No students yet">Students show up here once they sign up and start practising.</Empty>
        ) : rows.length === 0 ? (
          <Empty icon={Search} title="No matches">No student matches “{query}”.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <caption className="sr-only">Student progress. Select a column heading to sort.</caption>
              <thead>
                <tr>
                  {COLUMNS.map(c => {
                    const activeCol = sort.key === c.key
                    const Icon = !activeCol ? ArrowUpDown : sort.dir === 'asc' ? ArrowUp : ArrowDown
                    return (
                      <th key={c.key} aria-sort={activeCol ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                        <button onClick={() => toggleSort(c.key)}>{c.label}<Icon size={14} aria-hidden="true" /></button>
                      </th>
                    )
                  })}
                  <th>Weak topics</th>
                  <th>Looked confused on</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(s => (
                  <tr key={s.id}>
                    <td><span className="student"><span className="avatar" aria-hidden="true">{s.username.slice(0, 2)}</span>{s.username}</span></td>
                    <td className="mono-num">{s.attempts}</td>
                    <td>{s.accuracy == null ? <span className="muted">—</span> : (
                      <span className={`badge ${s.accuracy >= 0.75 ? 'badge-success' : s.accuracy >= 0.5 ? 'badge-warning' : 'badge-danger'}`}>{pct(s.accuracy)}</span>
                    )}</td>
                    <td><div className="tags">{s.weak_topics.length ? s.weak_topics.map(t => <span key={t} className="badge">{t}</span>) : <span className="muted">—</span>}</div></td>
                    <td><div className="tags">{s.struggling_topics.length ? s.struggling_topics.map(t => <span key={t} className="badge badge-warning">{t}</span>) : <span className="muted">—</span>}</div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}
