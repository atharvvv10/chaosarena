import { useEffect, useState } from 'react'
import {
  evaluate,
  getHealth,
  getHistory,
  getLastGate,
  getReport,
  getRlPolicy,
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
      {promoted ? '● ' : '● '}{decision.verdict}
    </span>
  )
}

function ScoreRing({ score, grade }) {
  const value = score ?? 0
  const rotation = `${value * 3.6}deg`
  return (
    <div className="score-block">
      <div className="score-ring" style={{ '--rotation': rotation }}>
        <div className="score-ring-inner">
          <strong>{score ?? '--'}</strong>
          <span>/100</span>
          <em>{grade ?? '--'}</em>
        </div>
      </div>
      <div className="score-copy">
        <span className="eyebrow">Resilience score</span>
        <p>Measured from detection, recovery and cleanup — not a stored opinion.</p>
      </div>
    </div>
  )
}

function Trend({ decisions }) {
  if (!decisions.length) return null
  return (
    <div className="trend" aria-label="Recent score trend">
      {decisions.slice(0, 12).reverse().map((decision, index) => (
        <div
          className={`trend-bar ${decision.verdict === 'PROMOTE' ? 'good' : 'bad'}`}
          key={`${decision.evaluated_at}-${index}`}
          style={{ height: `${Math.max(8, Number(decision.score) || 0)}%` }}
          title={`${decision.score} · ${decision.verdict}`}
        />
      ))}
    </div>
  )
}

function RlPanel({ policy }) {
  if (!policy?.available) {
    return <p className="muted">No trained Q table yet. Run <code>make rl-train</code>.</p>
  }
  return (
    <div className="rl-panel">
      <div className="rl-head">
        <span className="eyebrow">Learned policy</span>
        <span className="tag">epsilon {policy.epsilon ?? '--'}</span>
      </div>
      {['calm', 'alert'].map((state) => (
        <div className="rl-state" key={state}>
          <span className={`state-dot state-${state}`}>{state}</span>
          <div className="rl-actions">
            {(policy.states?.[state] || []).slice(0, 2).map((item) => (
              <div className="rl-action" key={item.action}>
                <code>{item.action}</code>
                <span>Q {item.q}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function App() {
  const [health, setHealth] = useState(null)
  const [last, setLast] = useState(null)
  const [history, setHistory] = useState([])
  const [report, setReport] = useState(null)
  const [policy, setPolicy] = useState(null)
  const [form, setForm] = useState(DEFAULTS)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [lastBattle, setLastBattle] = useState(null)

  async function load() {
    setError('')
    try {
      const [h, g, hist, rep, rl] = await Promise.all([
        getHealth(),
        getLastGate(),
        getHistory(8),
        getReport(),
        getRlPolicy(),
      ])
      setHealth(h)
      setLast(g.decision)
      setHistory(hist.decisions || [])
      setReport(rep.text)
      setPolicy(rl)
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
        const [rep, rl] = await Promise.all([getReport(), getRlPolicy()])
        setReport(rep.text)
        setPolicy(rl)
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
        <div className="brand">
          <div className="brand-mark">CA</div>
          <div>
            <h1>ChaosArena</h1>
            <p className="subtitle">Resilience-gated releases · local demo</p>
          </div>
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

      <div className="phase-strip">
        <span>ShopApp</span><span>Attacks</span><span>Defender</span><span>Gate</span>
        <span>Reporter</span><span>CI</span><span>Dashboard</span><span>RL</span>
        <span className="active">Polish</span>
      </div>

      {error && <div className="alert">{error}</div>}

      <main className="grid">
        <section className="card gate-card">
          <div className="card-head">
            <div>
              <span className="eyebrow">Phase 4</span>
              <h2>Release gate</h2>
              <p className="muted">Latest decision from the Arena Controller</p>
            </div>
            <Verdict decision={last} />
          </div>

          <ScoreRing score={last?.score} grade={last?.grade} />

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

        <section className="card battle-card">
          <div className="card-head">
            <div>
              <span className="eyebrow">Phase 2 + 4</span>
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
            <div>
              <span className="eyebrow">Phase 8</span>
              <h2>RL attacker</h2>
              <p className="muted">Learned from the free simulator, executed via public CLIs</p>
            </div>
            <Trend decisions={history} />
          </div>
          <RlPanel policy={policy} />
        </section>

        <section className="card card-wide">
          <div className="card-head">
            <div>
              <span className="eyebrow">Audit trail</span>
              <h2>Decision history</h2>
            </div>
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
                    <td>
                      <span className="score-cell">
                        <span className="mini-bar" style={{ width: `${Number(decision.score) || 0}%` }} />
                        {decision.score}
                      </span>
                    </td>
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
            <div>
              <span className="eyebrow">Phase 5</span>
              <h2>Incident report</h2>
            </div>
            <span className="muted">facts only · offline template</span>
          </div>
          <pre className="report">{report || 'No report yet. Run a battle to generate one.'}</pre>
        </section>
      </main>

      <footer>
        ChaosArena · Phases 1–9 complete · React + Vite · local and free · no external UI kit
      </footer>
    </div>
  )
}
