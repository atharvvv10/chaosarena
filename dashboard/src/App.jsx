import { useEffect, useState } from 'react'
import {
  evaluate,
  getEvidence,
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

const NAV = [
  { id: 'overview', label: 'Overview' },
  { id: 'battle', label: 'Battle' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'history', label: 'History' },
]

const DETECTOR_LABELS = {
  rule_based_3sigma: 'Rule-based 3σ',
  isolation_forest_only: 'Isolation forest only',
  defender_forest_plus_deviation: 'Defender: forest + deviation',
}

function Verdict({ decision }) {
  if (!decision) {
    return <span className="pill pill-muted">No battle recorded yet</span>
  }
  const promoted = decision.verdict === 'PROMOTE'
  return (
    <span className={promoted ? 'pill pill-good' : 'pill pill-bad'}>
      ● {decision.verdict}
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

function SectionNav() {
  const [active, setActive] = useState('overview')

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return undefined
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
        if (visible) setActive(visible.target.id)
      },
      { rootMargin: '-120px 0px -55% 0px', threshold: [0, 0.1, 0.5] },
    )
    NAV.forEach(({ id }) => {
      const node = document.getElementById(id)
      if (node) observer.observe(node)
    })
    return () => observer.disconnect()
  }, [])

  return (
    <nav className="subnav" aria-label="Dashboard sections">
      <span className="subnav-label">Jump to</span>
      {NAV.map((item) => (
        <a
          key={item.id}
          href={`#${item.id}`}
          className={active === item.id ? 'subnav-link active' : 'subnav-link'}
          onClick={() => setActive(item.id)}
        >
          {item.label}
        </a>
      ))}
      <span className="subnav-hint">local · free · evidence-first</span>
    </nav>
  )
}

function KpiStrip({ decision, battle }) {
  const items = [
    {
      label: 'Resilience score',
      value: decision?.score ?? '--',
      suffix: decision ? '/100' : '',
      tone: decision?.verdict === 'BLOCK' ? 'bad' : 'good',
    },
    {
      label: 'Detected in',
      value: battle?.detection_seconds != null ? `${battle.detection_seconds}s` : '--',
    },
    {
      label: 'Recovered in',
      value: battle?.recovery_seconds != null ? `${battle.recovery_seconds}s` : '--',
    },
    {
      label: 'Chaos cleanup',
      value: battle?.cleanup_ok == null ? '--' : battle.cleanup_ok ? 'Verified' : 'Failed',
      tone: battle?.cleanup_ok === false ? 'bad' : 'good',
    },
  ]

  return (
    <div className="kpi-grid" aria-label="Battle key results">
      {items.map((item) => (
        <div className="kpi" key={item.label}>
          <span className="kpi-label">{item.label}</span>
          <strong className={item.tone ? `kpi-value ${item.tone}` : 'kpi-value'}>
            {item.value}{item.suffix && <small>{item.suffix}</small>}
          </strong>
        </div>
      ))}
    </div>
  )
}

function BattleTimeline({ battle }) {
  if (!battle) {
    return <p className="muted">No battle evidence yet. Run a battle to populate this timeline.</p>
  }
  const diagnosis = battle.diagnosis || {}
  const action = battle.action_taken || {}
  const confidence = diagnosis.confidence != null
    ? `${Math.round(Number(diagnosis.confidence) * 100)}% confidence`
    : 'confidence not recorded'

  const steps = [
    {
      title: 'Fault injected',
      detail: `${battle.attack || 'unknown'} → ${battle.target || 'unknown'}`,
      time: 'T+0s',
    },
    {
      title: 'Defender detected',
      detail: `score ${battle.final_score ?? '--'} vs threshold ${battle.defender_threshold ?? '--'}`
        + ` · ${battle.detection_seconds === 0
          ? 'anomaly present on first poll after launch'
          : battle.detection_basis || 'measured from attack start'}`,
      time: battle.detection_seconds != null ? `T+${battle.detection_seconds}s` : '--',
      tone: 'good',
    },
    {
      title: 'Symptom identified',
      detail: `${diagnosis.category || 'unknown'} on ${diagnosis.service || 'unknown'} · ${confidence} (symptomatic, not proven origin)`,
    },
    {
      title: 'Repair requested',
      detail: `${action.action || 'none'} on ${action.service || 'unknown'} (${action.status || 'status unknown'})`,
    },
    {
      title: 'Service recovered',
      detail: 'anomaly score back below threshold after the observation window',
      time: battle.recovery_seconds != null ? `T+${battle.recovery_seconds}s` : '--',
      tone: 'good',
    },
    {
      title: 'Cleanup verified',
      detail: `${battle.chaos_objects_remaining ?? '--'} chaos objects remaining`,
      time: battle.cleanup_ok ? 'OK' : 'FAILED',
      tone: battle.cleanup_ok ? 'good' : 'bad',
    },
  ]

  return (
    <ol className="timeline">
      {steps.map((step, index) => (
        <li className="timeline-item" key={step.title}>
          <span className={step.tone ? `timeline-dot ${step.tone}` : 'timeline-dot'}>
            {index + 1}
          </span>
          <div className="timeline-copy">
            <div className="timeline-title">
              <strong>{step.title}</strong>
              {step.time && <span className="timeline-time">{step.time}</span>}
            </div>
            <p>{step.detail}</p>
          </div>
        </li>
      ))}
    </ol>
  )
}

function Benchmarks({ evidence }) {
  const rl = evidence?.rl_benchmark
  const defender = evidence?.defender_benchmark
  const baseline = evidence?.no_defender_baseline
  const badRelease = evidence?.bad_release_experiment
  if (!rl && !defender && !baseline && !badRelease) {
    return <p className="muted">No benchmark evidence found in the local ml/ folder.</p>
  }

  const learned = Number(rl?.learned?.avg_resilience_score) || 0
  const random = Number(rl?.random?.avg_resilience_score) || 0
  const maxScore = Math.max(learned, random, 1)
  const detectors = Object.entries(defender?.detectors || {})

  return (
    <div className="benchmark-grid">
      <div className="benchmark-block">
        <div className="benchmark-head">
          <span className="eyebrow">Learned vs random</span>
          <span className="tag">offline · {rl?.episodes ?? '--'} episodes</span>
        </div>
        <p className="muted small">Offline seeded simulator; not a live cluster battle.</p>
        <div className="compare-bars">
          {[
            { label: 'Learned attacker', value: learned, tone: 'learned' },
            { label: 'Random attacker', value: random, tone: 'random' },
          ].map((row) => (
            <div className="compare-row" key={row.label}>
              <span className="compare-label">{row.label}</span>
              <div className="compare-track">
                <span
                  className={`compare-fill ${row.tone}`}
                  style={{ width: `${(row.value / maxScore) * 100}%` }}
                />
              </div>
              <strong>{row.value || '--'}</strong>
            </div>
          ))}
        </div>
        <div className="benchmark-metrics">
          <div><span>Damage ratio</span><strong>{rl?.damage_ratio ?? '--'}×</strong></div>
          <div><span>Score delta</span><strong>{rl?.score_delta ?? '--'}</strong></div>
          <div><span>Best action</span><code>{rl?.learned?.best_action || '--'}</code></div>
        </div>
      </div>

      <div className="benchmark-block">
        <div className="benchmark-head">
          <span className="eyebrow">Detector comparison</span>
          <span className="tag">offline · {defender?.dataset?.attacks ?? '--'} attacks</span>
        </div>
        <p className="muted small">40 recorded normal samples + seeded fault injections; not a live battle.</p>
        <div className="table-wrap">
          <table className="compare-table">
            <thead>
              <tr><th>Detector</th><th>Recall</th><th>Precision</th><th>False pos.</th></tr>
            </thead>
            <tbody>
              {detectors.map(([key, metrics]) => (
                <tr key={key} className={key === 'defender_forest_plus_deviation' ? 'highlight' : ''}>
                  <td>{DETECTOR_LABELS[key] || key}</td>
                  <td>{metrics.recall != null ? `${Math.round(metrics.recall * 100)}%` : '--'}</td>
                  <td>{metrics.precision != null ? `${Math.round(metrics.precision * 100)}%` : '--'}</td>
                  <td>{metrics.false_positives ?? '--'}</td>
                </tr>
              ))}
              {!detectors.length && <tr><td colSpan="4" className="muted">No detector results.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {baseline && (
        <div className="benchmark-block">
          <div className="benchmark-head">
            <span className="eyebrow">Recovery control</span>
            <span className="tag">two single local runs</span>
          </div>
          <p className="muted small">Same fault and target, one with Defender repair and one observe-only. Not a statistical study.</p>
          <div className="table-wrap">
            <table className="compare-table">
              <thead>
                <tr><th>Run</th><th>Detected</th><th>Recovered</th></tr>
              </thead>
              <tbody>
                <tr className="highlight">
                  <td>With Defender restart</td>
                  <td>{evidence?.last_battle?.battle?.detection_seconds != null
                    ? `T+${evidence.last_battle.battle.detection_seconds}s` : '--'}</td>
                  <td>{evidence?.last_battle?.battle?.recovery_seconds != null
                    ? `T+${evidence.last_battle.battle.recovery_seconds}s` : '--'}</td>
                </tr>
                <tr>
                  <td>No Defender remediation</td>
                  <td>{baseline.detection_seconds != null ? `T+${baseline.detection_seconds}s` : '--'}</td>
                  <td>{baseline.recovery_seconds != null ? `T+${baseline.recovery_seconds}s` : '--'}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="muted small">The observe-only run also recovered, so in this pair of runs the restart was not required for recovery.</p>
        </div>
      )}

      {badRelease && (
        <div className="benchmark-block">
          <div className="benchmark-head">
            <span className="eyebrow">Bad release vs rollback</span>
            <span className="tag">live gate · two local runs</span>
          </div>
          <p className="muted small">A deliberately bad payment config (100% failures) was gated, rolled back and gated again.</p>
          <div className="table-wrap">
            <table className="compare-table">
              <thead>
                <tr><th>Release</th><th>Score</th><th>Verdict</th></tr>
              </thead>
              <tbody>
                <tr>
                  <td>{badRelease.bad_release?.version || 'bad release'}</td>
                  <td>{badRelease.bad_release?.evidence?.score?.score ?? '--'}</td>
                  <td className="verdict-bad">{badRelease.bad_release?.evidence?.decision?.verdict || '--'}</td>
                </tr>
                <tr className="highlight">
                  <td>{badRelease.rollback?.version || 'rollback'}</td>
                  <td>{badRelease.rollback?.evidence?.score?.score ?? '--'}</td>
                  <td className="verdict-good">{badRelease.rollback?.evidence?.decision?.verdict || '--'}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="muted small">
            {badRelease.result?.gate_caught_bad_release
              ? 'The gate blocked the bad release and promoted the rollback.'
              : 'See the committed JSON for the full result.'}
          </p>
        </div>
      )}
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

function HistoryCard({ history }) {
  const [query, setQuery] = useState('')
  const [verdict, setVerdict] = useState('ALL')

  const filtered = history.filter((decision) => {
    const matchesVerdict = verdict === 'ALL' || decision.verdict === verdict
    const haystack = [decision.version, decision.attack, decision.target, decision.verdict]
      .join(' ')
      .toLowerCase()
    return matchesVerdict && haystack.includes(query.trim().toLowerCase())
  })

  return (
    <section className="card card-wide" id="history">
      <div className="card-head">
        <div>
          <span className="eyebrow">Audit trail</span>
          <h2>Decision history</h2>
        </div>
        <span className="muted">newest first</span>
      </div>

      <div className="history-tools">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search version, attack, target…"
          aria-label="Search decision history"
        />
        <div className="filter-group" role="group" aria-label="Filter by verdict">
          {['ALL', 'PROMOTE', 'BLOCK'].map((option) => (
            <button
              type="button"
              key={option}
              className={verdict === option ? 'filter-btn active' : 'filter-btn'}
              onClick={() => setVerdict(option)}
            >
              {option}
            </button>
          ))}
        </div>
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
            {filtered.map((decision, index) => (
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
            {filtered.length === 0 && (
              <tr><td colSpan="7" className="muted">No decisions match this filter.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function ReportCard({ report }) {
  const [copyState, setCopyState] = useState('Copy')

  async function copyReport() {
    try {
      await navigator.clipboard.writeText(report || '')
      setCopyState('Copied')
    } catch {
      setCopyState('Copy failed')
    }
    setTimeout(() => setCopyState('Copy'), 1800)
  }

  function downloadReport() {
    const blob = new Blob([report || ''], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'chaosarena-incident-report.md'
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="card card-wide">
      <div className="card-head">
        <div>
          <span className="eyebrow">Phase 5</span>
          <h2>Incident report</h2>
        </div>
        <div className="report-actions">
          <button className="button button-ghost small-button" onClick={copyReport} disabled={!report}>
            {copyState}
          </button>
          <button className="button button-ghost small-button" onClick={downloadReport} disabled={!report}>
            Download
          </button>
        </div>
      </div>
      <pre className="report">{report || 'No report yet. Run a battle to generate one.'}</pre>
    </section>
  )
}

function Toast({ message }) {
  if (!message) return null
  return <div className="toast" role="status">{message}</div>
}

export default function App() {
  const [health, setHealth] = useState(null)
  const [last, setLast] = useState(null)
  const [history, setHistory] = useState([])
  const [report, setReport] = useState(null)
  const [policy, setPolicy] = useState(null)
  const [evidence, setEvidence] = useState(null)
  const [form, setForm] = useState(DEFAULTS)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [lastBattle, setLastBattle] = useState(null)
  const [toast, setToast] = useState('')

  async function load() {
    setError('')
    try {
      const [h, g, hist, rep, rl, ev] = await Promise.all([
        getHealth(),
        getLastGate(),
        getHistory(8),
        getReport(),
        getRlPolicy(),
        getEvidence(),
      ])
      setHealth(h)
      setLast(g.decision)
      setHistory(hist.decisions || [])
      setReport(rep.text)
      setPolicy(rl)
      setEvidence(ev)
    } catch (err) {
      setError(`Cannot reach the gate API: ${err.message}`)
    }
  }

  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    if (!toast) return undefined
    const timer = setTimeout(() => setToast(''), 4500)
    return () => clearTimeout(timer)
  }, [toast])

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
      const [rep, rl, ev] = await Promise.all([getReport(), getRlPolicy(), getEvidence()])
      setReport(rep.text)
      setPolicy(rl)
      setEvidence(ev)
      setToast(
        result.decision?.verdict === 'PROMOTE'
          ? `PROMOTE · score ${result.decision.score} · ${result.decision.version}`
          : `BLOCK · score ${result.decision?.score ?? '--'} · review reasons below`,
      )
    } catch (err) {
      setError(`Battle failed: ${err.message}`)
    } finally {
      setBusy(false)
    }
  }

  const online = health?.status === 'ok'
  const displayDecision = last || evidence?.last_battle?.decision
  const activeBattle = lastBattle || evidence?.last_battle?.battle

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

      <SectionNav />

      <div className="phase-strip">
        <span>ShopApp</span><span>Attacks</span><span>Defender</span><span>Gate</span>
        <span>Reporter</span><span>CI</span><span>Dashboard</span><span>RL</span>
        <span className="active">Polish</span>
      </div>

      {error && <div className="alert">{error}</div>}

      <KpiStrip decision={displayDecision} battle={activeBattle} />

      <main className="grid">
        <section className="card gate-card" id="overview">
          <div className="card-head">
            <div>
              <span className="eyebrow">Phase 4</span>
              <h2>Release gate</h2>
              <p className="muted">Latest decision from the Arena Controller</p>
            </div>
            <Verdict decision={displayDecision} />
          </div>

          <ScoreRing score={displayDecision?.score} grade={displayDecision?.grade} />

          <dl className="facts">
            <div><dt>Version</dt><dd>{displayDecision?.version || '--'}</dd></div>
            <div><dt>Attack</dt><dd>{displayDecision?.attack || '--'}</dd></div>
            <div><dt>Target</dt><dd>{displayDecision?.target || '--'}</dd></div>
            <div><dt>Threshold</dt><dd>{displayDecision?.threshold ?? '--'}</dd></div>
            <div><dt>Evaluated</dt><dd>{displayDecision?.evaluated_at || '--'}</dd></div>
          </dl>

          <h3>Why</h3>
          <ul className="reasons">
            {(displayDecision?.reasons || []).map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </section>

        <section className="card battle-card" id="battle">
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

        <section className="card card-wide" id="evidence">
          <div className="card-head">
            <div>
              <span className="eyebrow">Measured evidence</span>
              <h2>Battle timeline &amp; comparisons</h2>
              <p className="muted">Real local runs, plus clearly-labelled offline benchmarks</p>
            </div>
            <span className="tag">local JSON · no cloud</span>
          </div>
          <div className="evidence-grid">
            <div className="evidence-column">
              <h3 className="column-title">Real battle timeline</h3>
              <BattleTimeline battle={activeBattle} />
            </div>
            <div className="evidence-column">
              <h3 className="column-title">Benchmarks</h3>
              <Benchmarks evidence={evidence} />
            </div>
          </div>
        </section>

        <section className="card card-wide" id="rl">
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

        <HistoryCard history={history} />

        <ReportCard report={report} />
      </main>

      <footer>
        ChaosArena · Phases 1–9 complete · React + Vite · local and free · no external UI kit
      </footer>

      <Toast message={toast} />
    </div>
  )
}
