import { Link, Route, Routes } from 'react-router-dom'
import { ComparisonPage } from './pages/ComparisonPage'
import { CooperativePage } from './pages/CooperativePage'
import { Dashboard } from './pages/Dashboard'

export default function App() {
  return (
    <>
      <header className="app-header">
        <div className="app-header-inner">
          <Link to="/" className="brand">
            Boster
          </Link>
          <span className="muted small">Analys av bostadsrätter och föreningar</span>
        </div>
      </header>
      <main className="page">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/foreningar/:id" element={<CooperativePage />} />
          <Route path="/jamfor" element={<ComparisonPage />} />
          <Route path="*" element={<p>Sidan finns inte. <Link to="/">Till startsidan</Link></p>} />
        </Routes>
      </main>
    </>
  )
}
