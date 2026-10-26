import { useState } from 'react'
import { Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import { BookOpenCheck, LayoutDashboard, LogOut, Users, Video } from 'lucide-react'
import { getStoredUser, storeAuth } from './api'
import { Logo, ThemeToggle } from './components/ui'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Study from './pages/Study'
import Teacher from './pages/Teacher'
import Interview from './pages/Interview'

export default function App() {
  const [user, setUser] = useState(getStoredUser())
  const navigate = useNavigate()

  const onLogin = (token, u) => {
    storeAuth(token, u)
    setUser(u)
    navigate(u.role === 'teacher' ? '/teacher' : '/')
  }
  const logout = () => {
    storeAuth(null)
    setUser(null)
    navigate('/login')
  }

  if (!user) {
    return (
      <Routes>
        <Route path="*" element={<Login onLogin={onLogin} />} />
      </Routes>
    )
  }

  const links = user.role === 'teacher'
    ? [{ to: '/teacher', label: 'Students', icon: Users }]
    : [{ to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true }, { to: '/study', label: 'Practice', icon: BookOpenCheck }, { to: '/interview', label: 'Mock interview', icon: Video }]

  return (
    <div className="shell">
      <aside className="sidebar" aria-label="Main navigation">
        <Logo />
        <nav className="nav">
          <div className="nav-label">Menu</div>
          {links.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end}><Icon size={20} aria-hidden="true" />{label}</NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <ThemeToggle />
          <div className="user-card">
            <span className="avatar" aria-hidden="true">{user.username.slice(0, 2)}</span>
            <div className="who"><strong>{user.username}</strong><span>{user.role}</span></div>
            <button className="btn btn-ghost btn-icon btn-sm" onClick={logout} aria-label="Log out" title="Log out">
              <LogOut size={18} aria-hidden="true" />
            </button>
          </div>
        </div>
      </aside>

      <header className="mobile-bar">
        <Logo sub={false} />
        <button className="btn btn-ghost btn-icon" onClick={logout} aria-label="Log out"><LogOut size={20} aria-hidden="true" /></button>
      </header>

      <main className="content" id="main">
        <Routes>
          {user.role === 'teacher' ? (
            <>
              <Route path="/teacher" element={<Teacher />} />
              <Route path="*" element={<Navigate to="/teacher" replace />} />
            </>
          ) : (
            <>
              <Route path="/" element={<Dashboard user={user} />} />
              <Route path="/study" element={<Study />} />
              <Route path="/interview" element={<Interview />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </>
          )}
        </Routes>
      </main>

      <nav className="bottom-nav" aria-label="Main navigation">
        {links.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end}><Icon size={22} aria-hidden="true" />{label === 'Mock interview' ? 'Interview' : label.split(' ')[0]}</NavLink>
        ))}
      </nav>
    </div>
  )
}
