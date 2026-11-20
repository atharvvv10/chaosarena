import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getHealth, getLastGate, getHistory, getReport, getRlPolicy, getEvidence, evaluate } from './api'
import arenaSvg from './arena.svg?raw'
import './styles.css'

const ATTACKS=['network-latency','pod-kill','pod-failure','network-loss','network-partition','cpu-stress','memory-stress']
const TARGETS=['payment-service','order-service','cart-service','product-service','user-service','redis','postgres']
const DETECTOR_LABELS={rule_based_3sigma:'Rule-based 3sigma',isolation_forest_only:'Isolation forest only',defender_forest_plus_deviation:'Defender: forest + deviation'}
const DEFAULT_FORM={attack:'network-latency',target:'payment-service',duration:30,settle:45,threshold:70,version:'release-candidate'}
const SECTIONS=['Overview','Battle','Evidence','History']
const SECTION_IDS=SECTIONS.map(n=>n.toLowerCase())
const fmt=(v,unit='')=>v===null||v===undefined||v===''||!Number.isFinite(Number(v))?'Not measured':`${Number(v).toFixed(1)}${unit}`
const show=(v,fallback='Not available')=>v===null||v===undefined||v===''?fallback:String(v)
const grade=n=>n>=90?'A':n>=80?'B':n>=70?'C':n>=50?'D':'F'
const describe=v=>v==null?'Not recorded':typeof v==='string'?v:Array.isArray(v)?v.map(describe).join(', '):typeof v==='object'?Object.entries(v).map(([k,val])=>`${k}: ${describe(val)}`).join(' · '):String(v)
const hasNumber=n=>typeof n==='number'&&Number.isFinite(n)
const cls=v=>v==='PROMOTE'?'promote':v==='BLOCK'?'block':'pending'
function Status({children,tone=''}){return <span className={`status ${tone}`}>{children}</span>}
function Panel({title,subtitle,children,className=''}){return <div className={`panel ${className}`}><div className="panelheader"><h3>{title}</h3><small>{subtitle}</small></div>{children}</div>}
function Field({name,label,form,setForm,options,min,max}){const value=form[name];return <div className="field"><label htmlFor={name}>{label}</label>{options?<select id={name} value={value} onChange={e=>setForm(f=>({...f,[name]:e.target.value}))}>{options.map(x=><option key={x} value={x}>{x}</option>)}</select>:<input id={name} type={name==='version'?'text':'number'} min={min} max={max} required value={value} onChange={e=>setForm(f=>({...f,[name]:name==='version'?e.target.value:e.target.value===''?'':Number(e.target.value)}))}/>}</div>}
function Metric({label,value,sub,tone=''}){return <div className="panel kpi"><div className="overline">{label}</div><div className={`number ${tone}`}>{value}</div><div className="sub">{sub}</div></div>}
function diagnosisSummary(value){
  if(!value)return 'No diagnosis recorded.';
  if(typeof value==='string')return value;
  const category=show(value.category??value.diagnosis_category,'Unclassified');
  const service=show(value.service??value.requested_service,'service not recorded');
  const confidence=hasNumber(value.confidence)?` · ${Math.round(value.confidence*100)}% confidence`:'';
  const signals=Array.isArray(value.evidence)?` · ${value.evidence.length} signals`:'';
  return `${category} · ${service}${confidence}${signals}`;
}
function diagnosisJson(value){
  if(!value)return 'No diagnosis recorded.';
  return typeof value==='string'?value:JSON.stringify(value,null,2);
}
function Timeline({battle}){
  if(!battle)return <div className="state">No battle evidence is available. Start the gate API to inspect a recorded experiment.</div>;
  const objects=battle.chaos_objects_left??battle.chaos_objects_remaining??battle.objects_left;
  const diagnosis=battle.diagnosis??battle.diagnosis_category;
  const action=battle.action_taken??{};
  const actionService=action.service??battle.requested_service;
  const actionDesc=`${show(action.action??battle.requested_action??battle.action,'Not recorded')}${actionService?' · '+actionService:''}${action.status?' · '+action.status:''}`;
  const events=[
    ['T+0s','Fault injected',`${show(battle.attack,'Fault')} on ${show(battle.target,'target')}`,'red'],
    [battle.detected===false?'Not detected':hasNumber(battle.detection_seconds)?`T+${fmt(battle.detection_seconds,'s')}`:'Unmeasured','Defender detected',battle.detected===false?'No detection recorded':'Detection reported by Defender',''],
    ['','Symptom identified',<div className="diagnosis-block"><div className="diagnosis-summary">{diagnosisSummary(diagnosis)}</div><details className="diagnostic-details"><summary>Full diagnosis</summary><pre>{diagnosisJson(diagnosis)}</pre></details></div>,''],
    ['','Repair requested',actionDesc,''],
    [hasNumber(battle.recovery_seconds)?`T+${fmt(battle.recovery_seconds,'s')}`:'Unmeasured','Service recovered',battle.recovered===false?'Recovery not observed':battle.recovered===true?'Recovery observed':'Recovery status not recorded','green'],
    ['Status','Cleanup verified',`${battle.cleanup_ok===true?'OK':battle.cleanup_ok===false?'FAILED':'Not recorded'} · objects left: ${describe(objects)}`,battle.cleanup_ok===true?'green':battle.cleanup_ok===false?'red':'']
  ];
  return <div className="timeline">{events.map(([time,title,description,tone],i)=><div className="event" key={i}><div className={`time ${time.startsWith('T+')?'measured':''}`}>{time}</div><div className={`pin ${tone}`}/><div><b>{title}</b>{typeof description==='string'?<p>{description}</p>:description}</div></div>)}</div>;
}
function Gate({result,threshold}){
  const score=result?.score?.score??result?.decision?.score;
  const verdict=result?.decision?.verdict;
  const g=result?.score?.grade??result?.decision?.grade??(hasNumber(score)?grade(score):null);
  const deductions=result?.score?.deductions;
  const reasons=result?.decision?.reasons;
  const tone=verdict==='BLOCK'?'block':verdict==='PROMOTE'?'promote':'pending';
  return <div className="gategrid"><Panel title="Release gate" subtitle="EVALUATION RESULT"><div className="gatebody">
    <div className={`gateverdict ${tone}`}>
      <div className="gateicon">{verdict==='PROMOTE'?'✓':verdict==='BLOCK'?'×':'·'}</div>
      <div className="gatemain"><h3>{show(verdict,'PENDING')}</h3><p>{verdict?'Release decision recorded':'Waiting for gate evidence'}</p></div>
      <div className="decision-pair">
        <div><span>SCORE</span><strong>{hasNumber(score)?score:'—'}</strong></div>
        <div><span>GRADE</span><strong>{show(g,'—')}</strong></div>
      </div>
    </div>
    <div className="scoreline"><span style={{width:hasNumber(score)?`${Math.max(0,Math.min(100,score))}%`:'0%',background:tone==='block'?'var(--red)':tone==='promote'?'var(--green)':'var(--dim)'}}/></div>
    <div className="gatevalues">
      <div><div className="overline">THRESHOLD</div><strong>{show(result?.decision?.threshold??threshold)}</strong></div>
      <div><div className="overline">DEDUCTIONS</div><strong>{Array.isArray(deductions)?deductions.length:'—'}</strong></div>
      <div><div className="overline">RECOVERY</div><strong>{result?.battle?.recovered===true?'Yes':result?.battle?.recovered===false?'No':'—'}</strong></div>
    </div>
    <p className="recovery-note">Recovery is a yes/no check, not a speed score.</p>
  </div></Panel><Panel title="Gate reasoning" subtitle="AUDIT TRAIL"><div className="checks">{Array.isArray(reasons)&&reasons.length?reasons.map((r,i)=><div className="check" key={i}><span>•</span><div>{describe(r)}</div></div>):<div className="state">No decision reasons recorded.</div>}{Array.isArray(deductions)&&deductions.length>0&&<><div className="overline">PENALTIES</div>{deductions.map((d,i)=><div className="check" key={i}><span style={{color:'var(--red)'}}>−</span><div>{describe(d)}</div></div>)}</>}</div></Panel></div>
}
function inlineText(text){return String(text).split('`').map((part,i)=>i%2?<code key={i}>{part}</code>:part)}
function renderList(items,key){
  const root=[];const stack=[{indent:-1,children:root}];
  for(const item of items){
    while(stack.length>1&&item.indent<=stack[stack.length-1].indent)stack.pop();
    const node={content:item.content,children:[]};
    stack[stack.length-1].children.push(node);
    stack.push({indent:item.indent,children:node.children});
  }
  const render=(nodes,path)=><ul key={path}>{nodes.map((node,i)=><li key={`${path}-${i}`}>{inlineText(node.content)}{node.children.length?render(node.children,`${path}-${i}`):null}</li>)}</ul>;
  return render(root,key);
}
function ReportView({text}){
  if(!text)return <p className="state">No incident report recorded.</p>;
  const lines=String(text).split('\n');
  const blocks=[];
  let list=[];
  const flush=()=>{if(list.length){blocks.push(renderList(list,`list-${blocks.length}`));list=[]}};
  for(const raw of lines){
    const line=raw.trim();
    if(!line){flush();continue}
    if(line.startsWith('# ')){flush();blocks.push(<h3 key={blocks.length}>{inlineText(line.slice(2))}</h3>);continue}
    const heading=line.match(/^\*\*(.+)\*\*$/)||line.match(/^\d+\.\s+(.+)$/);
    if(heading){flush();blocks.push(<h4 key={blocks.length}>{inlineText(heading[1])}</h4>);continue}
    const item=raw.match(/^(\s*)-\s+(.*)$/);
    if(item){list.push({indent:item[1].length,content:item[2]});continue}
    flush();blocks.push(<p key={blocks.length}>{inlineText(line)}</p>);
  }
  flush();
  return <div className="report">{blocks}</div>;
}
function reportSummary(text){if(!text)return 'No incident report recorded.';const lines=String(text).split('\n');const idx=lines.findIndex(line=>/^\d+\.\s*Summary$/i.test(line.trim()));if(idx>=0){for(let i=idx+1;i<lines.length;i++){const line=lines[i].trim();if(line)return line}}const fallback=lines.find(line=>{const t=line.trim();return t && !t.startsWith('#') && !/^\d+\./.test(t)});return fallback?fallback.trim():'No incident report recorded.'}
function Compare({evidence,battle}){const baseline=evidence?.no_defender_baseline;return <div className="recovery-tracks"><p className="metric-group-label">Detection time · seconds · lower is better</p><div className="metric-row"><span>Detection with Defender</span><strong>{fmt(battle?.detection_seconds,'s')}</strong></div><div className="metric-row"><span>Detection without Defender</span><strong>{fmt(baseline?.detection_seconds,'s')}</strong></div><p className="metric-group-label">Recovery time · seconds · lower is better</p><div className="metric-row"><span>With Defender · recovery</span><strong>{fmt(battle?.recovery_seconds,'s')}</strong></div><div className="metric-row"><span>Without Defender · recovery</span><strong>{fmt(baseline?.recovery_seconds,'s')}</strong></div><p className="recovery-note">Measured battle recovery. {baseline?.defender_remediation===false?'No Defender remediation':'Baseline evidence'}</p><p className="recovery-note">Two single runs, not a statistical study. Repair requested, not repaired by itself. Elapsed time has no fixed upper bound, so no bar scale is applied; a longer bar would wrongly imply a better result.</p></div>}
function Evidence({evidence,policy,loading}){
  const bad=evidence?.bad_release_experiment;
  const rl=evidence?.rl_benchmark;
  const detectors=evidence?.defender_benchmark?.detectors;
  const baseline=evidence?.no_defender_baseline;
  const badEvidence=bad?.bad_release?.evidence;
  const rollbackEvidence=bad?.rollback?.evidence;
  const badScore=badEvidence?.score?.score;
  const rollbackScore=rollbackEvidence?.score?.score;
  const badVerdict=badEvidence?.decision?.verdict;
  const rollbackVerdict=rollbackEvidence?.decision?.verdict;
  const badGrade=badEvidence?.score?.grade;
  const rollbackGrade=rollbackEvidence?.score?.grade;
  const withDetection=evidence?.last_battle?.battle?.detection_seconds;
  const withRecovery=evidence?.last_battle?.battle?.recovery_seconds;
  const pct=n=>hasNumber(n)?`${Math.max(0,Math.min(100,Number(n)))}%`:'0%';
  const rate=n=>n===null||n===undefined?'—':`${Math.round(Number(n)*100)}%`;
  const shipped=detectors?.defender_forest_plus_deviation;
  const rule=detectors?.rule_based_3sigma;
  const iso=detectors?.isolation_forest_only;
  const isoText=iso?.recall===0?'isolation forest alone detects none':`isolation forest alone at ${rate(iso?.recall)} recall`;
  const ruleFpText=rule?.false_positives===1?'1 false positive':`${rule?.false_positives??'—'} false positives`;
  return <div className="evidence-groups">
    <section className="evidence-group">
      <div className="evidence-group-head"><h3>Resilience comparisons</h3><p>Recorded gate decisions and observe-only control.</p></div>
      <div className="benchmark-grid">
        <Panel title="Bad release vs rollback" subtitle="RELEASE SAFETY"><div className="cardbody">
          {loading?<div className="state">Loading experiment evidence.</div>:bad?<>
            <p className="metric-group-label">Gate score · 0–100 points · higher is better</p>
            <div className="score-compare">
              <div className="compare-row">
                <div className="metric-row"><span>Bad release · {show(bad.bad_release?.version,'candidate')}</span><strong className="block-text">{show(badVerdict,'—')} · {show(badScore,'—')} / {show(badGrade,'—')}</strong></div>
                <div className="track"><span className="red" style={{width:pct(badScore)}}/></div>
              </div>
              <div className="compare-row">
                <div className="metric-row"><span>Rollback · {show(bad.rollback?.version,'rollback')}</span><strong className="promote-text">{show(rollbackVerdict,'—')} · {show(rollbackScore,'—')} / {show(rollbackGrade,'—')}</strong></div>
                <div className="track"><span className="green" style={{width:pct(rollbackScore)}}/></div>
              </div>
            </div>
            <div className="metric-row"><span>Final anomaly / threshold</span><strong>{fmt(badEvidence?.battle?.final_score)} / {fmt(badEvidence?.battle?.defender_threshold)}</strong></div>
            <div className="metric-row"><span>Gate result</span><strong>{bad.result?.gate_caught_bad_release?'Gate caught bad release':'See decision record'}</strong></div>
            <p className="recovery-note">Main finding: the gate blocked the bad release and promoted the rollback. The experiment script performed the rollback; the Defender did not catch the release.</p>
          </>:<div className="state">No bad-release experiment saved.</div>}
        </div></Panel>
        <Panel title="Defender vs observe-only" subtitle="SAME FAULT CLOCK"><div className="cardbody">
          <p className="metric-group-label">Detection time · seconds · lower is better</p>
          <div className="metric-row"><span>Detection with Defender</span><strong>{fmt(withDetection,'s')}</strong></div>
          <div className="metric-row"><span>Detection observe-only</span><strong>{fmt(baseline?.detection_seconds,'s')}</strong></div>
          <p className="metric-group-label">Recovery time · seconds · lower is better</p>
          <div className="metric-row"><span>Recovery with Defender</span><strong>{fmt(withRecovery,'s')}</strong></div>
          <div className="metric-row"><span>Recovery observe-only</span><strong>{fmt(baseline?.recovery_seconds,'s')}</strong></div>
          <p className="recovery-note">Both runs detected and recovered; recovery timing is not attributable to Defender. Two single runs, not a statistical study.</p>
          <p className="recovery-note">Elapsed time has no fixed upper bound, so no bar scale is applied; a longer bar would wrongly imply a better result.</p>
        </div></Panel>
      </div>
    </section>
    <section className="evidence-group">
      <div className="evidence-group-head"><h3>Detector performance</h3><p>Offline seeded benchmark; detailed metrics remain available.</p></div>
      <Panel title="Detector comparison" subtitle="DEFENDER BENCHMARK"><div className="cardbody">
        <div className="detector-layout">
          <div className="detector-table">
            {loading?<div className="state">Loading detectors.</div>:detectors&&Object.keys(detectors).length?<div className="tablewrap"><table className="compact-table"><colgroup><col style={{width:'42%'}}/><col style={{width:'16%'}}/><col style={{width:'18%'}}/><col style={{width:'24%'}}/></colgroup><thead><tr><th>Detector</th><th className="n">Recall</th><th className="n">Precision</th><th className="n">False positives</th></tr></thead><tbody>{Object.entries(detectors).map(([name,data])=><tr key={name} className={name==='defender_forest_plus_deviation'?'self':''}><td>{DETECTOR_LABELS[name]||name}</td><td className="n">{data.recall!=null?rate(data.recall):'—'}</td><td className="n">{data.precision!=null?rate(data.precision):'—'}</td><td className="n">{data.false_positives??'—'}</td></tr>)}</tbody></table></div>:<div className="state">No detector benchmark available.</div>}
          </div>
          <div className="detector-notes">
            <div className="metric-row"><span>Normal samples</span><strong>{show(evidence?.defender_benchmark?.dataset?.normal,'—')}</strong></div>
            <div className="metric-row"><span>Fault injections</span><strong>{show(evidence?.defender_benchmark?.dataset?.attacks,'—')}</strong></div>
            <div className="metric-row"><span>Features / seed</span><strong>{show(evidence?.defender_benchmark?.dataset?.features,'—')} / {show(evidence?.defender_benchmark?.dataset?.seed,'—')}</strong></div>
            <p className="recovery-note">Offline seeded benchmark: shipped Defender at {rate(shipped?.recall)} recall and {rate(shipped?.precision)} precision with {shipped?.false_positives??'—'} false positives; rule-based 3sigma at {rate(rule?.recall)} recall with {ruleFpText}; {isoText}. Not a live battle.</p>
          </div>
        </div>
      </div></Panel>
    </section>
    <section className="evidence-group">
      <div className="evidence-group-head"><h3>Attacker learning</h3><p>Seeded simulator results and saved policy values.</p></div>
      <div className="benchmark-grid">
        <Panel title="Learned vs random" subtitle="ATTACKER BENCHMARK"><div className="cardbody">
          {loading?<div className="state">Loading benchmark.</div>:rl?<>
            <div className="metric-row"><span>Damage ratio</span><strong>{show(rl.damage_ratio,'—')}</strong></div>
            <div className="metric-row"><span>Resilience score delta</span><strong>{show(rl.score_delta,'—')}</strong></div>
            <div className="metric-row"><span>Learned / random reward</span><strong>{show(rl.learned?.avg_reward,'—')} / {show(rl.random?.avg_reward,'—')}</strong></div>
            <div className="metric-row"><span>Learned / random resilience</span><strong>{show(rl.learned?.avg_resilience_score,'—')} / {show(rl.random?.avg_resilience_score,'—')}</strong></div>
          </>:<div className="state">No RL benchmark available.</div>}
          <p className="recovery-note">Offline seeded simulator: the learned attacker does more damage than random. No statistical significance or live-cluster result is implied.</p>
        </div></Panel>
        <Panel title="RL attacker" subtitle="POLICY INSPECTION" className="rl-panel"><div className="cardbody">
          {loading?<div className="state">Loading policy.</div>:!policy?.available?<div className="state">No saved RL policy available.</div>:<>
            <div className="metric-row"><span>Exploration epsilon</span><strong>{show(policy.epsilon)}</strong></div>
            {Object.entries(policy.states||{}).map(([state,actions])=><div key={state} className="policy-state"><div className="overline">STATE · {state}</div>{Array.isArray(actions)&&actions.length?actions.map((a,i)=><div className="metric-row" key={i}><span>{describe(a.action)}</span><strong>Q {show(a.q)}</strong></div>):<div className="state">No actions recorded.</div>}</div>)}
          </>}
        </div></Panel>
      </div>
    </section>
  </div>
}
function History({items,loading,error}){const [query,setQuery]=useState('');const [filter,setFilter]=useState('ALL');const filtered=useMemo(()=>items.filter(r=>(filter==='ALL'||r.verdict===filter)&&[r.version,r.attack,r.target,r.verdict,r.score].join(' ').toLowerCase().includes(query.toLowerCase())),[items,query,filter]);return <><div className="history-tools"><input className="search" value={query} onChange={e=>setQuery(e.target.value)} aria-label="Search decisions" placeholder="Search version, attack, target…"/><div className="filters">{['ALL','PROMOTE','BLOCK'].map(x=><button type="button" className={filter===x?'active':''} key={x} onClick={()=>setFilter(x)}>{x==='ALL'?'All':x==='PROMOTE'?'Promote':'Block'}</button>)}</div></div><div className="panel tablewrap"><table><thead><tr>{['RELEASE','FAULT','TARGET','SCORE','GRADE','DECISION'].map(x=><th key={x}>{x}</th>)}</tr></thead><tbody>{filtered.map((r,i)=><tr key={`${r.id??r.version??'decision'}-${i}`}><td>{show(r.version,'—')}</td><td>{show(r.attack,'—')}</td><td>{show(r.target,'—')}</td><td className="mono">{show(r.score,'—')}</td><td className="mono">{show(r.grade??(hasNumber(r.score)?grade(r.score):null),'—')}</td><td><span className={`pill ${cls(r.verdict)}`}>{show(r.verdict,'—')}</span></td></tr>)}</tbody></table>{loading?<div className="empty">Loading decision history…</div>:error?<div className="empty error">History unavailable: {error}</div>:!filtered.length?<div className="empty">{items.length?'No matching decisions.':'No decisions recorded.'}</div>:null}</div></>}
function useActiveSection(ids){const [active,setActive]=useState(ids[0]);useEffect(()=>{const update=()=>{const atBottom=window.innerHeight+window.scrollY>=document.documentElement.scrollHeight-2;const next=atBottom?ids[ids.length-1]:([...ids].reverse().find(id=>{const el=document.getElementById(id);return el&&el.getBoundingClientRect().top<=120})??ids[0]);setActive(next)};update();window.addEventListener('scroll',update,{passive:true});window.addEventListener('resize',update);return()=>{window.removeEventListener('scroll',update);window.removeEventListener('resize',update)}},[ids]);return active}
export default function App(){const activeSection=useActiveSection(SECTION_IDS);const [form,setForm]=useState(DEFAULT_FORM);const [data,setData]=useState({});const [pending,setPending]=useState(true);const [running,setRunning]=useState(false);const [errors,setErrors]=useState({});const [toast,setToast]=useState('');const timer=useRef(null);const notify=useCallback(message=>{setToast(message);clearTimeout(timer.current);timer.current=setTimeout(()=>setToast(''),4200)},[]);useEffect(()=>()=>clearTimeout(timer.current),[])
const refresh=useCallback(async()=>{setPending(true);const keys=['health','evidence','last','history','report','policy'];const results=await Promise.allSettled([getHealth(),getEvidence(),getLastGate(),getHistory(10),getReport(),getRlPolicy()]);const values={};const faults={};results.forEach((r,i)=>{if(r.status==='fulfilled')values[keys[i]]=r.value;else faults[keys[i]]=r.reason?.message||'Request failed'});setData(old=>({...old,...values}));setErrors(faults);setPending(false)},[]);useEffect(()=>{refresh()},[refresh]);const result=data.current??data.evidence?.last_battle??(data.last?.decision?{decision:data.last.decision}:null);const battle=result?.battle;const score=result?.score?.score??result?.decision?.score;const verdict=result?.decision?.verdict;const history=data.history?.decisions??[];const online=Boolean(data.health)&&!errors.health;const source=data.current?'NEW EXPERIMENT':data.evidence?.last_battle?'SAVED EXPERIMENT':'NO BATTLE DATA';const run=async e=>{e.preventDefault();if(!form.version.trim()||!Number.isFinite(form.duration)||form.duration<=0||!Number.isFinite(form.settle)||form.settle<0||!Number.isFinite(form.threshold)||form.threshold<0||form.threshold>100){notify('Check battle parameters.');return}setRunning(true);notify('Experiment submitted. Waiting for the gate API.');try{const result=await evaluate({...form,version:form.version.trim()});setData(old=>({...old,current:result}));notify('Gate evaluation completed.');const updates=await Promise.allSettled([getHistory(10),getReport(),getEvidence()]);setData(old=>({...old,...(updates[0].status==='fulfilled'?{history:updates[0].value}:{}),...(updates[1].status==='fulfilled'?{report:updates[1].value}:{}),...(updates[2].status==='fulfilled'?{evidence:updates[2].value}:{})}));}catch(err){notify(`Battle could not run: ${err.message}`)}finally{setRunning(false)}};const copy=async()=>{if(!data.report?.text){notify('No report to copy.');return}try{await navigator.clipboard.writeText(data.report.text);notify('Incident report copied.')}catch{notify('Clipboard unavailable.')}}
const downloadReport=()=>{if(!data.report?.text){notify('No report to download.');return}const blob=new Blob([data.report.text],{type:'text/markdown'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='chaosarena-incident-report.md';link.click();URL.revokeObjectURL(url);notify('Incident report downloaded.')};return <div className="app"><aside className="sidebar"><div className="brand"><div className="brandmark">◇</div><div><div className="brandname">ChaosArena</div><div className="brandcaption">RESILIENCE RELEASE CONTROL</div></div></div><div className="navcap">WORKSPACE</div><nav className="nav" aria-label="Primary navigation">{SECTIONS.map((n,i)=>{const id=n.toLowerCase();const current=activeSection===id;return <a href={`#${id}`} key={n} className={current?'active':''} aria-current={current?'location':undefined}><span className="n">0{i+1}</span>{n}</a>})}</nav><div className="sideend"><div className="env"><div className="envtitle">ENVIRONMENT</div><div className="envline"><span>Gate API</span><strong className={online?'green':'amber'}>{pending?'CHECKING':online?'CONNECTED':'OFFLINE'}</strong></div><div className="envline"><span>Evidence</span><strong>{data.evidence?'LOADED':pending?'LOADING':'UNAVAILABLE'}</strong></div><div className="envline"><span>Execution</span><strong>{running?'RUNNING':'IDLE'}</strong></div><div className="envline"><span>Namespace</span><strong>shop-test</strong></div></div><div className="footnote">KIND · CHAOS MESH · PROMETHEUS</div></div></aside><div className="main"><header className="topbar"><div className="crumb">Platform / <strong>Release resilience</strong></div><div className="topright"><span className="mode">{running?'EXPERIMENT RUNNING':online?'GATE API ONLINE':'GATE API OFFLINE'}</span><span className="address">{import.meta.env.VITE_API_URL||'127.0.0.1:8080'}</span></div></header><main className="container"><section className="section" id="overview"><div className="intro"><div><div className="overline">RELEASE RESILIENCE / ENGINEERING CONSOLE</div><h1>Prove resilience <span>before release.</span></h1><p>Inject a controlled fault, observe detection and recovery, verify cleanup, and use recorded evidence to decide whether a release can ship.</p></div><aside>{source}<div style={{marginTop:8}}>{pending?'Loading…':online?'API connected':'API unavailable'}</div></aside></div><div className="panel arena"><div className="arenahead"><strong>Attacker vs Defender</strong><div className="right"><span className="dot" style={{background:online?'var(--green)':'var(--amber)'}}/> {source}</div></div><div className="arenafigure" dangerouslySetInnerHTML={{__html:arenaSvg}}/><div className="arenacaption"><span className="key"><i className="red"/>Chaos Mesh / fault</span><span className="key"><i/>Prometheus / detection</span><span className="key"><i className="green"/>Defender / recovery</span><span className="last">Technical topology · not a live cluster map</span></div></div><div className="kpi-grid"><Metric label="RELEASE VERDICT" value={show(verdict,pending?'Loading…':'Unavailable')} sub={verdict?'Gate decision':'Awaiting gate evidence'} tone={verdict==='PROMOTE'?'promote':verdict==='BLOCK'?'block':''}/><Metric label="GATE SCORE" value={hasNumber(score)?`${score}/100`:'—'} sub={`Grade ${show(result?.score?.grade??result?.decision?.grade??(hasNumber(score)?grade(score):null),'—')}`}/><Metric label="DETECTION" value={fmt(battle?.detection_seconds,'s')} sub={battle?.detected===false?'Fault not detected':'Measured from injection'}/><Metric label="RECOVERY" value={fmt(battle?.recovery_seconds,'s')} sub={battle?.cleanup_ok===true?'Cleanup verified':battle?.cleanup_ok===false?'Cleanup failed':'Cleanup not recorded'}/></div></section><section className="section" id="battle"><div className="sectionheading"><div><div className="overline">02 / CONTROL & OBSERVATION</div><h2>Battle</h2><p>Configure an experiment and inspect the measured result.</p></div><div className="right">{running?'GATE EVALUATING':`RELEASE · ${show(result?.decision?.version,'AWAITING RELEASE')}`}</div></div><div className="twocol"><Panel title="Run a battle" subtitle="FAULT CONFIGURATION"><form className="cardbody" onSubmit={run}><div className="fields"><Field name="attack" label="Attack" form={form} setForm={setForm} options={ATTACKS}/><Field name="target" label="Target" form={form} setForm={setForm} options={TARGETS}/><div className="field wide"><Field name="version" label="Release version" form={form} setForm={setForm}/></div></div><div className="three"><Field name="duration" label="Duration (s)" form={form} setForm={setForm} min={1}/><Field name="settle" label="Settle (s)" form={form} setForm={setForm} min={0}/><Field name="threshold" label="Threshold" form={form} setForm={setForm} min={0} max={100}/></div><div className="actions"><small>Requires a running gate API and configured Kind environment.</small><button className="btn" type="submit" disabled={running}>{running?'Running experiment…':'Run battle'}</button></div>{errors.health&&<p className="note error">Gate API unavailable. Saved evidence may still be displayed if previously loaded.</p>}</form></Panel><Panel title="Battle timeline" subtitle="MEASURED EVENTS"><Timeline battle={battle}/></Panel></div><Gate result={result} threshold={form.threshold}/><div style={{marginTop:13}}><Panel title="Recovery control" subtitle="COMPARATIVE MEASUREMENTS"><div className="cardbody"><Compare evidence={data.evidence} battle={battle}/></div></Panel></div><details className="panel" open style={{marginTop:13}}><summary className="panelheader"><h3>Incident report</h3><small>{show(data.report?.file,'LATEST REPORT')}</small></summary><div className="cardbody"><p className="report-summary">{inlineText(reportSummary(data.report?.text))}</p><div style={{display:'flex',justifyContent:'flex-end',gap:8,marginBottom:12}}><button className="btnsub" type="button" onClick={copy} disabled={!data.report?.text}>Copy report</button><button className="btnsub" type="button" onClick={downloadReport} disabled={!data.report?.text}>Download</button></div><details className="report-disclosure"><summary>Show full incident report</summary><div className="reportbody">{pending && !data.report?.text ? <p className="state">Loading incident report.</p> : errors.report ? <p className="state">Incident report unavailable.</p> : <ReportView text={data.report?.text} />}</div></details></div></details></section><section className="section" id="evidence"><div className="sectionheading"><div><div className="overline">03 / EXPERIMENT EVIDENCE</div><h2>Evidence</h2><p>Saved benchmark results and supporting observations from recorded runs.</p></div><div className="right">{data.evidence?'EVIDENCE LOADED':pending?'LOADING':'UNAVAILABLE'}</div></div><Evidence evidence={data.evidence} policy={data.policy} loading={pending}/></section><section className="section" id="history"><div className="sectionheading"><div><div className="overline">04 / DECISION RECORD</div><h2>Decision history</h2><p>Search recorded gate decisions by release, fault, or target.</p></div><div className="right">{history.length} RECORDS LOADED</div></div><History items={history} loading={pending} error={errors.history}/></section><footer className="footer"><span>CHAOSARENA · RESILIENCE-GATED RELEASE LAB</span><span>KIND / CHAOS MESH / PROMETHEUS</span></footer></main></div>{toast&&<div className="toast" role="status">{toast}</div>}</div>}
