import { useEffect, useState } from 'react'
import {
  evaluate,
  getHealth,
  getHistory,
  getLastGate,
  getReport,
} from './api.js'

const ATTACKS = [
  'pod-kill',
  'pod-failure',
  'network-latency',
  'network-loss',
  'network-partition',
  'cpu-stress',
  'memory-stress',
]

const DEFAULTS = {
  attack: 'network-latency',
  target: 'payment-service',
  duration: 20,
  threshold: 70,
  settle: 30,
  version: 'v1.0.4',
}

function Verdict({ decision }) {
  if (!decision) {
    return <span className="pill pill-muted">No battle recorded yet</span>
  }
  const promoted = decision.verdict === 'PROMOTE'
  return (
    <span className={promoted ? 'pill pill-good' : 'pill pill-bad'}>
      {decision.verdict}
    </span>
  )
}

function Score({ score, grade }) {
  return (
    <div className="score">
      <div className="score-number">{score ?? '--'}</div>
      <div className="score-label">/ 100 · grade {grade ?? '--'}</div>
    </div>
  )
}

export default function App() {
  const [health, setHealth] = useState(null)
  const [last, setLast] = useState(null)
  const [history, setHistory] = useState([])
  const [report, setReport] = useState(null)
  const [form, setForm] = useState(DEFAULTS)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [lastBattle, setLastBattle] = useState(null)

  async function load() {
    setError('')
    try {
      const [h, g, hist, rep] = await Promise.all([
        getHealth(),
        getLastGate(),
        getHistory(8),
        getReport(),
      ])
      setHealth(h)
      setLast(g.decision)
      setHistory(hist.decisions || [])
      setReport(rep.text)
    } catch (err) {
      setError(`Cannot reach the gate API: ${err.message}`)
    }
  }

  useEffect(() => {
    load()
  }, [])

  function update(key, value) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  async function runBattle(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const result = await evaluate({
        attack: form.attack,
        target: form.target,
        duration: Number(form.duration),
        threshold: Number(form.threshold),
        settle: Number(form.settle),
        version: form.version,
      })
      setLastBattle(result.battle)
      setLast(result.decision)
      setHistory((current) => [result.decision, ...current].slice(0, 8))
      if (result.decision?.verdict === 'PROMOTE') {
        const rep = await getReport()
        setReport(rep.text)
      }
    } catch (err) {
      setError(`Battle failed: ${err.message}`)
    } finally {
      setBusy(false)
    }
  }

  const online = health?.status === 'ok'

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>ChaosArena</h1>
          <p className="subtitle">Resilience-gated releases · local demo</p>
        </div>
        <div className="topbar-actions">
          <span className={online ? 'pill pill-good' : 'pill pill-bad'}>
            {online ? 'API online' : 'API offline'}
          </span>
          <button className="button button-ghost" onClick={load} disabled={busy}>
            Refresh
          </button>
        </div>
      </header>

      {error && <div className="alert">{error}</div>}

      <main className="grid">
        <section className="card gate-card">
          <div className="card-head">
            <div>
              <h2>Release gate</h2>
              <p className="muted">Latest decision from the Arena Controller</p>
            </div>
            <Verdict decision={last} />
          </div>

          <Score score={last?.score} grade={last?.grade} />

          <dl className="facts">
            <div><dt>Version</dt><dd>{last?.version || '--'}</dd></div>
            <div><dt>Attack</dt><dd>{last?.attack || '--'}</dd></div>
            <div><dt>Target</dt><dd>{last?.target || '--'}</dd></div>
            <div><dt>Threshold</dt><dd>{last?.threshold ?? '--'}</dd></div>
            <div><dt>Evaluated</dt><dd>{last?.evaluated_at || '--'}</dd></div>
          </dl>

          <h3>Why</h3>
          <ul className="reasons">
            {(last?.reasons || []).map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </section>

        <section className="card">
          <div className="card-head">
            <div>
              <h2>Run a battle</h2>
              <p className="muted">Calls the allowlisted attacker, then the Defender</p>
            </div>
          </div>

          <form onSubmit={runBattle} className="form">
            <label>
              Attack
              <select value={form.attack} onChange={(e) => update('attack', e.target.value)}>
                {ATTACKS.map((attack) => (
                  <option key={attack} value={attack}>{attack}</option>
                ))}
              </select>
            </label>

            <label>
              Target service
              <input
                value={form.target}
                onChange={(e) => update('target', e.target.value)}
                placeholder="payment-service"
              />
            </label>

            <div className="form-row">
              <label>
                Duration (s)
                <input
                  type="number"
                  min="1"
                  max="300"
                  value={form.duration}
                  onChange={(e) => update('duration', e.target.value)}
                />
              </label>
              <label>
                Settle (s)
                <input
                  type="number"
                  min="0"
                  max="180"
                  value={form.settle}
                  onChange={(e) => update('settle', e.target.value)}
                />
              </label>
            </div>

            <div className="form-row">
              <label>
                Threshold
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={form.threshold}
                  onChange={(e) => update('threshold', e.target.value)}
                />
              </label>
              <label>
                Version
                <input
                  value={form.version}
                  onChange={(e) => update('version', e.target.value)}
                  placeholder="v1.0.4"
                />
              </label>
            </div>

            <button className="button button-primary" type="submit" disabled={busy}>
              {busy ? 'Battling…' : 'Run battle'}
            </button>
            <p className="muted small">
              Safety: only <code>shop-test</code> services are allowed. Chaos cleanup is enforced.
            </p>
          </form>

          {lastBattle && (
            <div className="last-battle">
              <strong>Last battle:</strong> detected={String(lastBattle.detected)} ·
              recovered={String(lastBattle.recovered)} ·
              cleanup={String(lastBattle.cleanup_ok)} ·
              objects left={lastBattle.chaos_objects_remaining}
            </div>
          )}
        </section>

        <section className="card card-wide">
          <div className="card-head">
            <h2>Decision history</h2>
            <span className="muted">newest first</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Time</th><th>Version</th><th>Attack</th><th>Target</th>
                  <th>Score</th><th>Grade</th><th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {history.map((decision, index) => (
                  <tr key={`${decision.evaluated_at}-${index}`}>
                    <td>{decision.evaluated_at}</td>
                    <td>{decision.version}</td>
                    <td>{decision.attack}</td>
                    <td>{decision.target}</td>
                    <td>{decision.score}</td>
                    <td>{decision.grade}</td>
                    <td><Verdict decision={decision} /></td>
                  </tr>
                ))}
                {history.length === 0 && (
                  <tr><td colSpan="7" className="muted">No decisions yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card card-wide">
          <div className="card-head">
            <h2>Incident report</h2>
            <span className="muted">facts only · offline template</span>
          </div>
          <pre className="report">{report || 'No report yet. Run a battle to generate one.'}</pre>
        </section>
      </main>

      <footer>
        ChaosArena · React + Vite · local and free · no external UI kit
      </footer>
    </div>
  )
}
