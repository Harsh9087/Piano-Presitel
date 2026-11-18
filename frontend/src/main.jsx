import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Activity, CalendarClock, Cpu, KeyRound, Plus, RefreshCw, Save, Trash2, Wifi, WifiOff, X } from 'lucide-react'
import './style.css'

const API = '/api'
const DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
const emptyForm = { day: 0, start_time: '05:00', seconds: 120, enabled: true }

function App() {
  const [key, setKey] = useState(localStorage.getItem('relay_dashboard_key') || '')
  const [keyInput, setKeyInput] = useState(key)
  const [rows, setRows] = useState([])
  const [version, setVersion] = useState(0)
  const [devices, setDevices] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [editing, setEditing] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function request(path, options={}) {
    const res = await fetch(API + path, { ...options, headers: { 'Content-Type':'application/json', 'X-API-Key': key, ...(options.headers || {}) } })
    if (res.status === 401) throw new Error('Dashboard API key is incorrect.')
    if (!res.ok) { let msg = `Request failed (${res.status})`; try { const d=await res.json(); msg=d.detail || JSON.stringify(d) } catch {} throw new Error(msg) }
    if (res.status === 204) return null
    return res.json()
  }
  async function load() {
    if (!key) return
    setBusy(true); setError('')
    try {
      const [s, d] = await Promise.all([request('/schedules/'), request('/dashboard/status/')])
      setRows(s.schedules); setVersion(s.version); setDevices(d.devices || [])
      localStorage.setItem('relay_dashboard_key', key)
    } catch(e) { setError(e.message) } finally { setBusy(false) }
  }
  useEffect(() => { if (key) load() }, [key])
  const sorted = useMemo(() => [...rows].sort((a,b)=>a.day-b.day || a.start_time.localeCompare(b.start_time)), [rows])
  function startAdd() { setEditing(null); setForm(emptyForm); setShowForm(true) }
  function startEdit(row) { setEditing(row.id); setForm({day:row.day,start_time:row.start_time,seconds:row.seconds,enabled:row.enabled}); setShowForm(true) }
  async function save(e) {
    e.preventDefault(); setError(''); setNotice('')
    const payload = {...form, day:Number(form.day), seconds:Number(form.seconds)}
    try {
      await request(editing ? `/schedules/${editing}/` : '/schedules/', {method: editing?'PUT':'POST', body:JSON.stringify(payload)})
      setShowForm(false); setNotice('Schedule saved and published. Pico will fetch the new version on its next sync.'); await load()
    } catch(e) { setError(e.message) }
  }
  async function remove(row) {
    if (!confirm(`Delete ${DAYS[row.day]} at ${row.start_time}?`)) return
    try { await request(`/schedules/${row.id}/`, {method:'DELETE'}); setNotice('Schedule deleted and published.'); await load() } catch(e) { setError(e.message) }
  }
  async function toggle(row) {
    try { await request(`/schedules/${row.id}/`, {method:'PUT', body:JSON.stringify({day:row.day,start_time:row.start_time,seconds:row.seconds,enabled:!row.enabled})}); await load(); setNotice('Schedule status updated.') } catch(e) { setError(e.message) }
  }
  const lastSeen = devices[0]?.last_seen ? new Date(devices[0].last_seen) : null
  const online = lastSeen && (Date.now()-lastSeen.getTime() < 3*60*1000)

  if (!key) return <main className="login-wrap"><section className="login-card"><div className="brand-icon"><CalendarClock/></div><h1>Relay Schedule Manager</h1><p>Connect to your controller schedule dashboard.</p><form onSubmit={e=>{e.preventDefault(); const v=keyInput.trim(); if(v){setKey(v);localStorage.setItem('relay_dashboard_key',v)}}}><label>Dashboard API key</label><input type="password" value={keyInput} onChange={e=>setKeyInput(e.target.value)} placeholder="Enter dashboard key" autoComplete="current-password"/><button className="primary full"><KeyRound size={17}/> Connect dashboard</button></form><small>Your key is stored in this browser only.</small></section></main>

  return <div className="app-shell">
    <header className="topbar"><div className="brand"><div className="brand-icon"><CalendarClock/></div><div><strong>Relay Schedule Manager</strong><span>Weekly automation controller</span></div></div><div className="top-actions"><span className="version-pill">Schedule v{version}</span><button className="icon-button" onClick={load} title="Refresh" disabled={busy}><RefreshCw size={18}/></button><button className="text-button" onClick={()=>{localStorage.removeItem('relay_dashboard_key');setKey('');setRows([])}}>Disconnect</button></div></header>
    <main className="content">
      <div className="page-heading"><div><div className="eyebrow">CONTROL PANEL</div><h1>Weekly schedules</h1><p>Configure when your Pico W runs the six-relay sequence.</p></div><button className="primary" onClick={startAdd}><Plus size={18}/> Add schedule</button></div>
      {error && <div className="alert error"><X size={17}/>{error}</div>}{notice && <div className="alert success">{notice}<button onClick={()=>setNotice('')}><X size={15}/></button></div>}
      <section className="stats-grid"><div className="stat-card"><div className="stat-icon blue"><CalendarClock/></div><div><span>Configured schedules</span><strong>{rows.length}</strong></div></div><div className="stat-card"><div className="stat-icon purple"><Activity/></div><div><span>Enabled schedules</span><strong>{rows.filter(x=>x.enabled).length}</strong></div></div><div className="stat-card"><div className={`stat-icon ${online?'green':'orange'}`}>{online?<Wifi/>:<WifiOff/>}</div><div><span>Pico W connection</span><strong className="status-text">{online?'Online':'Waiting for device'}</strong></div></div></section>
      <section className="panel"><div className="panel-head"><div><h2>Schedule list</h2><p>Duration is applied separately to each relay from 1 through 6.</p></div><span className="muted-label">LOCAL TIME · IST</span></div>
        {sorted.length===0 ? <div className="empty"><CalendarClock size={34}/><strong>No schedules yet</strong><span>Add your first weekly relay schedule.</span><button className="secondary" onClick={startAdd}><Plus size={16}/> Add schedule</button></div> : <div className="table-wrap"><table><thead><tr><th>DAY</th><th>START TIME</th><th>SECONDS / RELAY</th><th>STATUS</th><th></th></tr></thead><tbody>{sorted.map(row=><tr key={row.id}><td><strong>{row.day_name}</strong></td><td className="time-cell">{row.start_time.slice(0,5)}</td><td>{row.seconds} sec <span className="muted">each</span></td><td><button className={`toggle ${row.enabled?'on':''}`} onClick={()=>toggle(row)}><span/>{row.enabled?'Enabled':'Disabled'}</button></td><td className="row-actions"><button className="icon-button" title="Edit" onClick={()=>startEdit(row)}>Edit</button><button className="icon-button danger" title="Delete" onClick={()=>remove(row)}><Trash2 size={16}/></button></td></tr>)}</tbody></table></div>}
      </section>
      <section className="panel device-panel"><div className="device-title"><div className="stat-icon blue"><Cpu/></div><div><h2>Device status</h2><p>Last contact reported by the Pico W.</p></div></div><div className="device-details"><div><span>Device</span><strong>{devices[0]?.name || 'Pico W relay controller'}</strong></div><div><span>Connection</span><strong className={online?'green-text':'orange-text'}>{online?'Online':lastSeen?'Offline / stale':'Not connected yet'}</strong></div><div><span>Last sync report</span><strong>{lastSeen?lastSeen.toLocaleString():'No heartbeat received'}</strong></div><div><span>Device schedule version</span><strong>{devices[0]?.reported_version ?? '—'}</strong></div></div></section>
      <div className="info-note"><strong>Offline operation:</strong> The Pico keeps its last valid local <code>schedule.csv</code> and uses the DS3231 RTC. Internet is needed only to fetch updates and report device status.</div>
    </main>
    {showForm && <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setShowForm(false)}}><form className="modal" onSubmit={save}><div className="modal-head"><div><h2>{editing?'Edit schedule':'Add schedule'}</h2><p>One event starts the complete Relay 7 + Relay 1–6 sequence.</p></div><button type="button" className="icon-button" onClick={()=>setShowForm(false)}><X/></button></div><label>Day of week<select value={form.day} onChange={e=>setForm({...form,day:e.target.value})}>{DAYS.map((d,i)=><option value={i} key={d}>{d}</option>)}</select></label><label>Start time<input type="time" value={form.start_time} onChange={e=>setForm({...form,start_time:e.target.value})} required/></label><label>ON duration for each relay (seconds)<input type="number" min="1" max="86400" value={form.seconds} onChange={e=>setForm({...form,seconds:e.target.value})} required/><small>Example: 120 means Relay 1 = 120 sec, Relay 2 = 120 sec, continuing through Relay 6.</small></label><label className="check-label"><input type="checkbox" checked={form.enabled} onChange={e=>setForm({...form,enabled:e.target.checked})}/> Enable this schedule</label><div className="modal-actions"><button type="button" className="secondary" onClick={()=>setShowForm(false)}>Cancel</button><button className="primary"><Save size={17}/> Save schedule</button></div></form></div>}
  </div>
}

createRoot(document.getElementById('root')).render(<App />)
