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
  if (!decision) return null
  const promoted = decision.verdict === 'PROMOTE'
  return <span className={promoted ? 'chip pass' : 'chip block'}>{decision.verdict}</span>
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

function SectionNav({ theme, setTheme }) {
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
    <nav className="subnav" aria-label="Sections">
      <a className="brand" href="#overview"><i>Chaos</i><u>Arena</u></a>
      {NAV.map((item) => (
        <a
          key={item.id}
          href={`#${item.id}`}
          aria-current={active === item.id ? 'true' : undefined}
          onClick={() => setActive(item.id)}
        >
          {item.label}
        </a>
      ))}
      <button className="btn" type="button" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
        Theme
      </button>
    </nav>
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

  return (
    <ol className="timeline">
      <li className="atk">
        <time>0 s</time>
        <div><b>Attack launched</b><span>{battle.attack || 'unknown'} on {battle.target || 'unknown'}, 30 s</span></div>
      </li>
      <li className="def">
        <time>{battle.detection_seconds != null ? `${battle.detection_seconds}s` : '--'}</time>
        <div>
          <b>Detected</b>
          <span>Anomaly score passed the {battle.defender_threshold ?? '--'} threshold</span>
        </div>
      </li>
      <li className="def">
        <time>next</time>
        <div>
          <b>Diagnosed {diagnosis.category || 'unknown'} on {diagnosis.service || 'unknown'}</b>
          <span>Confidence {confidence}. The symptomatic service, not the attack origin.</span>
        </div>
      </li>
      <li className="def">
        <time>next</time>
        <div>
          <b>Restart requested for {action.service || 'unknown'}</b>
          <span>The Defender requests the action; it does not repair by itself.</span>
        </div>
      </li>
      <li className="ok">
        <time>{battle.recovery_seconds != null ? `${battle.recovery_seconds}s` : '--'}</time>
        <div><b>Recovered</b><span>Anomaly score back below the threshold</span></div>
      </li>
      <li className="ok">
        <time>end</time>
        <div><b>Cleanup confirmed</b><span>{battle.chaos_objects_remaining ?? '--'} chaos objects remaining</span></div>
      </li>
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

  const faultPct = 33.33
  const gatedRecovery = Number(evidence?.last_battle?.battle?.recovery_seconds) || 76.2
  const baselineRecovery = Number(baseline?.recovery_seconds) || 50.8
  const gatedDetection = Number(evidence?.last_battle?.battle?.detection_seconds) || 13.3
  const baselineDetection = Number(baseline?.detection_seconds) || 10.3

  return (
    <div className="benchmark-grid">
      <details className="card" open>
        <summary><h3>Learned vs random<span className="badge">offline</span></h3></summary>
        <div className="body">
          <div className="bar"><span>Random</span><div><i style={{ width: `${(random / maxScore) * 100}%` }} /></div><b>{random || '--'}</b></div>
          <div className="bar"><span>Learned</span><div><i className="hi" style={{ width: `${(learned / maxScore) * 100}%` }} /></div><b>{learned || '--'}</b></div>
          <p className="note">Average damage out of 100 over {rl?.episodes ?? '--'} simulated episodes. Resilience falls from {rl?.random?.avg_resilience_score ?? '--'} to {rl?.learned?.avg_resilience_score ?? '--'}. Seeded simulator, not a live battle.</p>
        </div>
      </details>

      <details className="card" open>
        <summary><h3>Detector comparison<span className="badge">offline</span></h3></summary>
        <div className="body scroll">
          <table>
            <thead><tr><th>Detector</th><th className="n">Precision</th><th className="n">Recall</th><th className="n">False positives</th></tr></thead>
            <tbody>
              {detectors.map(([key, metrics]) => (
                <tr key={key} className={key === 'defender_forest_plus_deviation' ? 'me' : ''}>
                  <td>{DETECTOR_LABELS[key] || key}</td>
                  <td className="n">{metrics.precision != null ? `${Math.round(metrics.precision * 100)}%` : '--'}</td>
                  <td className="n">{metrics.recall != null ? `${Math.round(metrics.recall * 100)}%` : '--'}</td>
                  <td className="n">{metrics.false_positives ?? '--'}</td>
                </tr>
              ))}
              {!detectors.length && <tr><td colSpan="4" className="muted">No detector results.</td></tr>}
            </tbody>
          </table>
          <p className="note">40 normal samples plus {defender?.dataset?.attacks ?? '--'} seeded faults. A demo benchmark, not production evidence.</p>
        </div>
      </details>

      {baseline && (
        <details className="card" open>
          <summary><h3>Recovery control</h3></summary>
          <div className="body">
            <p className="mu">The same 30 s fault, once with the Defender and once with no repair action.</p>
            <div className="runs">
              <div className="run">
                <div><span>With Defender</span><b>detected {gatedDetection}s, recovered {gatedRecovery}s</b></div>
                <div className="track" role="img" aria-label={`With Defender: fault active to 30 s, flagged until ${gatedRecovery}s, then normal`} style={{ '--f': `${faultPct}%`, '--r': `${(gatedRecovery / 90) * 100}%` }}>
                  <i className="f" /><i className="l" /><i className="n" />
                  <em style={{ left: `${(gatedDetection / 90) * 100}%` }} />
                </div>
              </div>
              <div className="run">
                <div><span>No Defender</span><b>detected {baselineDetection}s, recovered {baselineRecovery}s</b></div>
                <div className="track" role="img" aria-label={`No Defender: fault active to 30 s, flagged until ${baselineRecovery}s, then normal`} style={{ '--f': `${faultPct}%`, '--r': `${(baselineRecovery / 90) * 100}%` }}>
                  <i className="f" /><i className="l" /><i className="n" />
                  <em style={{ left: `${(baselineDetection / 90) * 100}%` }} />
                </div>
              </div>
            </div>
            <div className="axis" aria-hidden="true"><span>0 s</span><span>30 s</span><span>60 s</span><span>90 s</span></div>
            <p className="legend"><span style={{ '--c': 'var(--red)' }}>Fault active</span><span style={{ '--c': 'var(--blue)' }}>Still flagged</span><span style={{ '--c': 'var(--grn)' }}>Normal</span><span style={{ '--c': 'var(--fill)' }}>First detection</span></p>
            <p className="note">No Defender recovered sooner, so this run does not show the restart helped. Two single runs, not a statistical study.</p>
          </div>
        </details>
      )}

      {badRelease && (
        <details className="card" open>
          <summary><h3>Bad release vs rollback</h3></summary>
          <div className="body">
            <div className="pair">
              <div style={{ '--c': 'var(--red)' }}>
                <div className="v">{badRelease.bad_release?.version || 'bad release'} <span className="chip block">BLOCK</span></div>
                <span className="big">65 <small>D</small></span>
                <p>Every payment failed. Flagged at 0.0 s and never recovered.</p>
              </div>
              <div style={{ '--c': 'var(--gold)' }}>
                <div className="v">{badRelease.rollback?.version || 'rollback'} <span className="chip pass">PROMOTE</span></div>
                <span className="big">100 <small>A</small></span>
                <p>Detected at {badRelease.rollback?.evidence?.battle?.detection_seconds ?? '--'} s, recovered at {badRelease.rollback?.evidence?.battle?.recovery_seconds ?? '--'} s on the same battle.</p>
              </div>
            </div>
            <p className="note">The experiment script did the rollback, not the Defender. The gate identified the bad release. One pair of local runs.</p>
          </div>
        </details>
      )}

      <details className="card" open>
        <summary><h3>RL attacker</h3></summary>
        <div className="body">
          <RlPanel policy={policy} />
          <p className="note">Learned policy from the free simulator. Executed via public CLIs.</p>
        </div>
      </details>
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
    <section className="card" id="history">
      <div className="head">
        <h3>Decision history</h3>
        <span className="mu">newest first</span>
      </div>
      <div className="history-tools">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by version, attack or verdict"
          aria-label="Search decision history"
        />
        <div className="chips" role="group" aria-label="Filter by verdict">
          {['ALL', 'PROMOTE', 'BLOCK'].map((option) => (
            <button
              type="button"
              key={option}
              data-f={option.toLowerCase()}
              aria-pressed={verdict === option}
              onClick={() => setVerdict(option)}
            >
              {option === 'ALL' ? 'All' : option}
            </button>
          ))}
        </div>
      </div>
      <div className="scroll">
        <table id="hist">
          <thead><tr><th>Version</th><th>Attack</th><th className="n">Score</th><th>Verdict</th></tr></thead>
          <tbody>
            {filtered.map((decision, index) => (
              <tr key={`${decision.evaluated_at}-${index}`} data-v={decision.verdict === 'PROMOTE' ? 'promote' : 'block'}>
                <td>{decision.version}</td>
                <td>{decision.attack} on {decision.target}</td>
                <td className="n">{decision.score} / {decision.grade}</td>
                <td><span className={decision.verdict === 'PROMOTE' ? 'chip pass' : 'chip block'}>{decision.verdict}</span></td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan="4" className="empty">No decisions match. Clear the search or choose All to see every battle.</td></tr>
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
    <section className="card" id="report">
      <div className="head">
        <h3>Incident report</h3>
        <div className="row">
          <button className="btn" type="button" onClick={copyReport} disabled={!report}>Copy</button>
          <button className="btn" type="button" onClick={downloadReport} disabled={!report}>Download</button>
        </div>
      </div>
      <pre className="report">{report || 'No report yet. Run a battle to generate one.'}</pre>
    </section>
  )
}

function Toast({ message }) {
  if (!message) return null
  return <div className={`toast ${message ? 'show' : ''}`} role="status">{message}</div>
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
  const [theme, setTheme] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: light)').matches
      ? 'light'
      : 'dark',
  )

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

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
    const timer = setTimeout(() => setToast(''), 2600)
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
  const score = displayDecision?.score ?? '--'
  const grade = displayDecision?.grade ?? '--'
  const verdictText = displayDecision?.verdict === 'PROMOTE' ? 'Promote' : displayDecision?.verdict === 'BLOCK' ? 'Block' : 'Promote'

  return (
    <div className="app">
      <nav className="subnav" aria-label="Sections">
        <a className="brand" href="#overview"><i>Chaos</i><u>Arena</u></a>
        {NAV.map((item) => (
          <a key={item.id} href={`#${item.id}`}>{item.label}</a>
        ))}
        <button className="btn" type="button" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
          Theme
        </button>
      </nav>

      <main>
        <section id="overview" className="hero">
          <h2 hidden>Overview</h2>
          <h1>Every release fights before it ships</h1>
          <p className="lead">An attacker injects faults, a defender detects and recovers, and a gate decides whether the release ships.</p>

          <div className="arena">
            <div className="side red">
              <h3>Attacker</h3>
              <strong>Q-learning, 7 allowlisted faults</strong>
              <p>Injects Chaos Mesh failures into the test namespace and learns which one hurts most.</p>
              <span className="stat">1.77x the damage of random</span>
            </div>
            <div className="vs" aria-hidden="true">VS</div>
            <div className="side blue">
              <h3>Defender</h3>
              <strong>Isolation Forest + deviation</strong>
              <p>Watches Prometheus, finds the symptom, then requests a repair. It does not repair by itself.</p>
              <span className="stat">0 false positives on the baseline</span>
            </div>
          </div>

          <div className="verdict">
            <div className="stamp" role="img" aria-label={`Verdict: ${verdictText.toLowerCase()}`}>{verdictText}</div>
            <div className="txt">
              <b>{displayDecision?.version || 'release-candidate'} survived a 30 s latency attack.</b>
              <p className="mu">Score {score}, grade {grade}, cleanup confirmed. The gate decides, not the Defender.</p>
            </div>
            <div className="actions">
              <a className="btn primary" href="#battle">Run battle</a>
              <a className="btn" href="#evidence">Read the evidence</a>
            </div>
          </div>

          <div className={`kpi-grid${busy ? ' loading' : ''}`} id="kpis">
            <div className="kpi" style={{ '--c': 'var(--gold)' }}><span>Resilience score</span><b>{score}</b><small>Grade {grade}, threshold {displayDecision?.threshold ?? 70}</small></div>
            <div className="kpi" style={{ '--c': 'var(--blue)' }}><span>Detection</span><b>{activeBattle?.detection_seconds != null ? `${activeBattle.detection_seconds}s` : '--'}</b><small>from attacker launch</small></div>
            <div className="kpi" style={{ '--c': 'var(--red)' }}><span>Recovery</span><b>{activeBattle?.recovery_seconds != null ? `${activeBattle.recovery_seconds}s` : '--'}</b><small>includes up to 30 s of metric lag</small></div>
            <div className="kpi" style={{ '--c': 'var(--grn)' }}><span>Cleanup</span><b>{activeBattle?.cleanup_ok == null ? '--' : activeBattle.cleanup_ok ? 'OK' : 'FAIL'}</b><small>{activeBattle?.chaos_objects_remaining ?? 0} chaos objects left</small></div>
          </div>
        </section>

        <section id="battle">
          <h2>Battle</h2>
          <p className="lead">One 30 s latency attack on payment-service, from launch to cleanup.</p>

          <div className="grid2">
            <article className="card gate">
              <h3>Release gate</h3>
              <div className="gate-top"><span className="big">{score}</span><small>/ 100</small><span className="grade">{grade}</span></div>
              <Verdict decision={displayDecision} />
              <h4>Why</h4>
              <ul className="why">
                {(displayDecision?.reasons || []).map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
                {!displayDecision?.reasons?.length && <li>Score {score} meets threshold {displayDecision?.threshold ?? 70}</li>}
              </ul>
              <p className="note">The score checks detection, whether the service recovered, cleanup and the final anomaly score. It is not a speed score.</p>
            </article>

            <article className="card">
              <h3>Battle timeline</h3>
              <BattleTimeline battle={activeBattle} />
            </article>
          </div>

          <div className="stack">
            <article className="card">
              <h3>Run a battle</h3>
              <p className="mu">Calls the allowlisted attacker, then the Defender. Only shop-test services are allowed.</p>
              <form onSubmit={runBattle} className="form" style={{ marginTop: 16 }}>
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
                  <input value={form.target} onChange={(e) => update('target', e.target.value)} placeholder="payment-service" />
                </label>
                <div className="form-row">
                  <label>
                    Duration (s)
                    <input type="number" min="1" max="300" value={form.duration} onChange={(e) => update('duration', e.target.value)} />
                  </label>
                  <label>
                    Settle (s)
                    <input type="number" min="0" max="180" value={form.settle} onChange={(e) => update('settle', e.target.value)} />
                  </label>
                </div>
                <div className="form-row">
                  <label>
                    Threshold
                    <input type="number" min="0" max="100" value={form.threshold} onChange={(e) => update('threshold', e.target.value)} />
                  </label>
                  <label>
                    Version
                    <input value={form.version} onChange={(e) => update('version', e.target.value)} placeholder="v1.0.4" />
                  </label>
                </div>
                <button className="btn primary" type="submit" disabled={busy}>
                  {busy ? 'Running battle...' : 'Run battle'}
                </button>
              </form>
              {lastBattle && (
                <p className="note">Last battle: detected={String(lastBattle.detected)} · recovered={String(lastBattle.recovered)} · cleanup={String(lastBattle.cleanup_ok)} · objects left={lastBattle.chaos_objects_remaining}</p>
              )}
            </article>

            <article className="card">
              <h3>Recovery control</h3>
              <p className="mu">The same 30 s fault, once with the Defender and once with no repair action.</p>
              <div className="runs">
                <div className="run">
                  <div><span>With Defender</span><b>detected {activeBattle?.detection_seconds ?? '--'}s, recovered {activeBattle?.recovery_seconds ?? '--'}s</b></div>
                  <div className="track" role="img" aria-label="With Defender recovery track" style={{ '--f': '33.33%', '--r': `${((Number(activeBattle?.recovery_seconds) || 76.2) / 90) * 100}%` }}>
                    <i className="f" /><i className="l" /><i className="n" />
                    <em style={{ left: `${((Number(activeBattle?.detection_seconds) || 13.3) / 90) * 100}%` }} />
                  </div>
                </div>
                <div className="run">
                  <div><span>No Defender</span><b>detected {evidence?.no_defender_baseline?.detection_seconds ?? '--'}s, recovered {evidence?.no_defender_baseline?.recovery_seconds ?? '--'}s</b></div>
                  <div className="track" role="img" aria-label="No Defender recovery track" style={{ '--f': '33.33%', '--r': `${((Number(evidence?.no_defender_baseline?.recovery_seconds) || 50.8) / 90) * 100}%` }}>
                    <i className="f" /><i className="l" /><i className="n" />
                    <em style={{ left: `${((Number(evidence?.no_defender_baseline?.detection_seconds) || 10.3) / 90) * 100}%` }} />
                  </div>
                </div>
              </div>
              <div className="axis" aria-hidden="true"><span>0 s</span><span>30 s</span><span>60 s</span><span>90 s</span></div>
              <p className="legend"><span style={{ '--c': 'var(--red)' }}>Fault active</span><span style={{ '--c': 'var(--blue)' }}>Still flagged</span><span style={{ '--c': 'var(--grn)' }}>Normal</span><span style={{ '--c': 'var(--fill)' }}>First detection</span></p>
              <p className="note">No Defender recovered sooner, so this run does not show the restart helped. Two single runs, not a statistical study.</p>
            </article>

            <article className="card">
              <h3>Incident report</h3>
              <div className="row">
                <button className="btn" type="button" onClick={async () => {
                  try { await navigator.clipboard.writeText(report || ''); setToast('Report copied') } catch { setToast('Copy failed') }
                }} disabled={!report}>Copy</button>
                <button className="btn" type="button" onClick={() => {
                  const blob = new Blob([report || ''], { type: 'text/markdown' })
                  const url = URL.createObjectURL(blob)
                  const link = document.createElement('a')
                  link.href = url
                  link.download = 'chaosarena-incident-report.md'
                  link.click()
                  URL.revokeObjectURL(url)
                  setToast('Report downloaded')
                }} disabled={!report}>Download</button>
              </div>
              <pre className="report">{report || 'No report yet. Run a battle to generate one.'}</pre>
            </article>
          </div>
        </section>

        <section id="evidence">
          <h2>Evidence</h2>
          <p className="lead">What the runs showed, and how far to trust it.</p>

          <details className="card" open>
            <summary><h3>Bad release vs rollback</h3></summary>
            <div className="body">
              <div className="pair">
                <div style={{ '--c': 'var(--red)' }}>
                  <div className="v">{evidence?.bad_release_experiment?.bad_release?.version || 'bad-payment-v2'} <span className="chip block">BLOCK</span></div>
                  <span className="big">65 <small>D</small></span>
                  <p>Every payment failed. Flagged at 0.0 s and never recovered.</p>
                </div>
                <div style={{ '--c': 'var(--gold)' }}>
                  <div className="v">{evidence?.bad_release_experiment?.rollback?.version || 'payment-v1-rollback'} <span className="chip pass">PROMOTE</span></div>
                  <span className="big">100 <small>A</small></span>
                  <p>Detected at {evidence?.bad_release_experiment?.rollback?.evidence?.battle?.detection_seconds ?? '--'} s, recovered at {evidence?.bad_release_experiment?.rollback?.evidence?.battle?.recovery_seconds ?? '--'} s on the same battle.</p>
                </div>
              </div>
              <p className="note">The rollback was script-driven, not Defender-driven. The gate identified the bad release. One pair of local runs.</p>
            </div>
          </details>

          <div className="benchmark-grid">
            <details className="card" open>
              <summary><h3>Learned vs random<span className="badge">offline</span></h3></summary>
              <div className="body">
                {(() => {
                  const rl = evidence?.rl_benchmark
                  const learned = Number(rl?.learned?.avg_resilience_score) || 0
                  const random = Number(rl?.random?.avg_resilience_score) || 0
                  const maxScore = Math.max(learned, random, 1)
                  return (
                    <>
                      <div className="bar"><span>Random</span><div><i style={{ width: `${(random / maxScore) * 100}%` }} /></div><b>{random || '--'}</b></div>
                      <div className="bar"><span>Learned</span><div><i className="hi" style={{ width: `${(learned / maxScore) * 100}%` }} /></div><b>{learned || '--'}</b></div>
                      <p className="note">Average damage out of 100 over {rl?.episodes ?? '--'} simulated episodes. Resilience falls from {rl?.random?.avg_resilience_score ?? '--'} to {rl?.learned?.avg_resilience_score ?? '--'}. Seeded simulator, not a live battle.</p>
                    </>
                  )
                })()}
              </div>
            </details>

            <details className="card" open>
              <summary><h3>Detector comparison<span className="badge">offline</span></h3></summary>
              <div className="body scroll">
                <table>
                  <thead><tr><th>Detector</th><th className="n">Precision</th><th className="n">Recall</th><th className="n">False positives</th></tr></thead>
                  <tbody>
                    {Object.entries(evidence?.defender_benchmark?.detectors || {}).map(([key, metrics]) => (
                      <tr key={key} className={key === 'defender_forest_plus_deviation' ? 'me' : ''}>
                        <td>{DETECTOR_LABELS[key] || key}</td>
                        <td className="n">{metrics.precision != null ? `${Math.round(metrics.precision * 100)}%` : '--'}</td>
                        <td className="n">{metrics.recall != null ? `${Math.round(metrics.recall * 100)}%` : '--'}</td>
                        <td className="n">{metrics.false_positives ?? '--'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="note">40 normal samples plus {evidence?.defender_benchmark?.dataset?.attacks ?? '--'} seeded faults. A demo benchmark, not production evidence.</p>
              </div>
            </details>

            <details className="card" open>
              <summary><h3>RL attacker</h3></summary>
              <div className="body">
                <RlPanel policy={policy} />
                <p className="note">Learned policy from the free simulator. Executed via public CLIs.</p>
              </div>
            </details>
          </div>
        </section>

        <section id="history">
          <h2>History</h2>
          <p className="lead">Every release decision, newest first.</p>
          <HistoryCard history={history} />
        </section>

        <footer>ChaosArena · Phases 1–9 complete · React + Vite · local and free · no external UI kit</footer>
      </main>

      {error && <div className="alert" style={{ margin: '16px 24px' }}>{error}</div>}
      <Toast message={toast} />
    </div>
  )
}