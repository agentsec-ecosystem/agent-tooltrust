# ruff: noqa: E501  (long HTML template lines)
"""Dashboard HTTP route for the operator console (M7.5 #149).

Serves a single-page web app that lists pending escalations and lets the
operator approve/deny them via the /api/escalations backend. The page
calls the existing escalation API so CLI and web stay in sync.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ToolTrust Operator Console</title>
<style>
  :root{--bg:#0f1117;--card:#1a1d27;--border:#2d3140;--text:#e1e4ea;
         --green:#2ecc71;--red:#e74c3c;--amber:#f39c12;--blue:#3498db;--muted:#8892a4}
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
       background:var(--bg);color:var(--text);line-height:1.5}
  .shell{max-width:960px;margin:0 auto;padding:24px 16px}
  header{border-bottom:1px solid var(--border);padding-bottom:16px;margin-bottom:24px}
  header h1{font-size:1.5rem;font-weight:600}
  header p{color:var(--muted);font-size:.875rem;margin-top:4px}
  nav{display:flex;gap:8px;margin-top:12px}
  nav a{color:var(--blue);text-decoration:none;font-size:.875rem;padding:4px 12px;
         border-radius:6px;border:1px solid var(--border)}
  nav a.active{background:var(--blue);color:#fff;border-color:var(--blue)}
  .section{margin-bottom:32px}
  .section h2{font-size:1.1rem;margin-bottom:12px;color:var(--muted)}
  .card{background:var(--card);border:1px solid var(--border);border-radius:8px;
         padding:16px;margin-bottom:12px}
  .card-row{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
  .card-meta{color:var(--muted);font-size:.8125rem}
  .card-id{font-family:monospace;font-size:.75rem;color:var(--muted)}
  .badge{padding:2px 8px;border-radius:999px;font-size:.75rem;font-weight:600}
  .badge-pending{background:rgba(243,156,18,.15);color:var(--amber)}
  .badge-approved{background:rgba(46,204,113,.15);color:var(--green)}
  .badge-denied{background:rgba(231,76,60,.15);color:var(--red)}
  .badge-pass{background:rgba(46,204,113,.15);color:var(--green)}
  .badge-pending{background:rgba(243,156,18,.15);color:var(--amber)}
  .badge-fail{background:rgba(231,76,60,.15);color:var(--red)}
  .btn{padding:6px 16px;border-radius:6px;border:none;font-size:.875rem;cursor:pointer;font-weight:500}
  .btn-approve{background:var(--green);color:#fff}
  .btn-deny{background:var(--red);color:#fff}
  .btn:disabled{opacity:.5;cursor:not-allowed}
  .empty{text-align:center;padding:48px 16px;color:var(--muted)}
  .toast{position:fixed;bottom:16px;right:16px;padding:12px 20px;border-radius:8px;
          font-size:.875rem;z-index:999;animation:fade .3s}
  .toast-ok{background:var(--green);color:#fff}
  .toast-err{background:var(--red);color:#fff}
  @keyframes fade{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
  .refresh-bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
  .refresh-bar button{background:var(--card);border:1px solid var(--border);color:var(--text);
                       padding:4px 12px;border-radius:6px;cursor:pointer;font-size:.8125rem}
  table{width:100%;border-collapse:collapse}
  th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--border);font-size:.8125rem}
  th{color:var(--muted);font-weight:500}
</style>
</head>
<body>
<div class="shell">
<header>
  <h1>ToolTrust Operator Console</h1>
  <p>Decision point for tool-using AI agents</p>
  <nav>
    <a href="#" class="active" data-tab="escalations">Escalations</a>
    <a href="#" data-tab="audit">Audit</a>
    <a href="#" data-tab="sessions">Sessions</a>
    <a href="#" data-tab="analytics">Analytics</a>
    <a href="#" data-tab="baselines">Baselines</a>
    <a href="/audit/health" target="_blank">Health</a>
  </nav>
</header>
<div id="escalations" class="section">
  <div class="refresh-bar">
    <h2>Pending Escalations</h2>
    <div>
      <span id="status-count" style="color:var(--muted);font-size:.8125rem;margin-right:8px"></span>
      <button onclick="loadEscalations()">Refresh</button>
      <button onclick="toggleView()" id="view-toggle" style="margin-left:4px">Show All</button>
    </div>
  </div>
  <div id="esc-list"></div>
</div>
<div id="audit" class="section" style="display:none">
  <div class="refresh-bar">
    <h2>Audit Trail</h2>
    <button onclick="loadAudit()">Refresh</button>
  </div>
  <div style="overflow-x:auto">
    <table id="audit-table"></table>
  </div>
</div>
<div id="sessions" class="section" style="display:none">
  <div class="refresh-bar">
    <h2>Session Calls</h2>
    <div>
      <input id="session-input" placeholder="session id" style="padding:6px 10px;border-radius:6px;border:1px solid var(--border);background:var(--card);color:var(--text);font-size:.875rem;margin-right:8px">
      <button onclick="loadSession()">Load</button>
    </div>
  </div>
  <p id="session-summary" style="color:var(--muted);font-size:.8125rem;margin-bottom:12px"></p>
  <div id="session-list"></div>
</div>
<div id="analytics" class="section" style="display:none">
  <div class="refresh-bar">
    <h2>Analytics</h2>
    <button onclick="loadAnalytics()">Refresh</button>
  </div>
  <div id="analytics-body"></div>
</div>
<div id="baselines" class="section" style="display:none">
  <div class="refresh-bar">
    <h2>Security Baselines</h2>
    <button onclick="loadBaselines()">Refresh</button>
  </div>
  <div id="baseline-body"></div>
</div>
</div>
<div id="toast"></div>
<script>
let showAll=false,tab='escalations';
document.querySelectorAll('[data-tab]').forEach(a=>{a.onclick=e=>{e.preventDefault();
  tab=e.target.dataset.tab;document.querySelectorAll('[data-tab]').forEach(l=>l.classList.remove('active'));
  e.target.classList.add('active');
  ['escalations','audit','sessions','analytics','baselines'].forEach(t=>{
    document.getElementById(t).style.display=t===tab?'':'none';});
  if(tab==='audit')loadAudit();else if(tab==='sessions')loadSession();else if(tab==='analytics')loadAnalytics();else if(tab==='baselines')loadBaselines();else loadEscalations();}});

function toggleView(){showAll=!showAll;document.getElementById('view-toggle').textContent=showAll?'Pending Only':'Show All';loadEscalations();}

async function loadEscalations(){
  const url='/api/escalations'+(showAll?'?all=true':'');
  try{
    const r=await fetch(url);if(!r.ok)throw new Error(r.status+' '+r.statusText);
    const data=await r.json();
    const list=document.getElementById('esc-list');
    document.getElementById('status-count').textContent=data.length+' record'+(data.length===1?'':'s');
    if(!data.length){list.innerHTML='<div class="empty">No escalations</div>';return;}
    list.innerHTML=data.map(e=>`<div class="card">
      <div class="card-row">
        <div>
          <strong>${e.tool}.${e.action}</strong><br>
          <span class="card-meta">agent=${e.agent_id} env=${e.environment} data=${e.data_class}</span><br>
          <span class="card-id">${e.escalation_id}</span>
        </div>
        <div style="text-align:right">
          <span class="badge badge-${e.status}">${e.status}</span><br>
          <span class="card-meta">expires: ${new Date(e.expires_at).toLocaleTimeString()}</span>
          ${e.status==='pending'?`<div style="margin-top:8px">
            <button class="btn btn-approve" onclick="approve('${e.escalation_id}')">Approve</button>
            <button class="btn btn-deny" onclick="deny('${e.escalation_id}')">Deny</button>
          </div>`:e.approver?`<span class="card-meta">by ${e.approver}</span>`:''}
          ${e.denied_reason?`<br><span class="card-meta">reason: ${e.denied_reason}</span>`:''}
        </div>
      </div>
    </div>`).join('');
  }catch(err){document.getElementById('esc-list').innerHTML='<div class="empty">Error: '+err.message+'</div>';}}

async function loadAudit(){
  try{
    const r=await fetch('/audit');if(!r.ok)throw new Error(r.status);
    const data=await r.json();
    const tbody=data.length?data.slice(0,50).map(e=>`<tr>
      <td>${e.timestamp?e.timestamp.slice(11,19):''}</td><td>${e.tool||''}</td>
      <td>${e.action||''}</td><td><span class="badge badge-${e.decision}">${e.decision}</span></td>
      <td>${e.reason_code||''}</td><td>${e.agent_id||''}</td>
      <td>${e.environment||''}</td><td>${e.approver||''}</td>
    </tr>`).join('') : '<tr><td colspan="8" class="empty">No audit entries</td></tr>';
    document.getElementById('audit-table').innerHTML=
      '<thead><tr><th>Time</th><th>Tool</th><th>Action</th><th>Decision</th><th>Reason</th><th>Agent</th><th>Env</th><th>Approver</th></tr></thead><tbody>'+tbody+'</tbody>';
  }catch(err){document.getElementById('audit-table').innerHTML='<tr><td colspan="8">Error: '+err.message+'</td></tr>';}}

async function loadSession(){
  const sid=document.getElementById('session-input').value.trim();
  if(!sid){document.getElementById('session-list').innerHTML='<div class="empty">Enter a session id</div>';return;}
  try{
    const r=await fetch('/api/sessions/'+encodeURIComponent(sid));if(!r.ok)throw new Error(r.status+' '+r.statusText);
    const data=await r.json();
    document.getElementById('session-summary').textContent='session '+data.session_id+' · '+data.call_count+' call'+(data.call_count===1?'':'s');
    const list=document.getElementById('session-list');
    if(!data.calls||!data.calls.length){list.innerHTML='<div class="empty">No calls for session</div>';return;}
    list.innerHTML=data.calls.map(c=>`<div class="card">
      <div class="card-row">
        <div>
          <strong>${c.tool}.${c.action}</strong><br>
          <span class="card-meta">env=${c.environment} data=${c.data_class} reason=${c.reason_code||''}</span>
        </div>
        <div style="text-align:right">
          <span class="badge badge-${c.decision}">${c.decision}</span><br>
          <span class="card-meta">${c.timestamp||''}</span>
        </div>
      </div>
    </div>`).join('');
  }catch(err){document.getElementById('session-list').innerHTML='<div class="empty">Error: '+err.message+'</div>';}}

function kvTable(headers,rows){
  const head=headers.map(h=>'<th>'+h+'</th>').join('');
  return '<table><thead><tr>'+head+'</tr></thead><tbody>'+rows+'</tbody></table>';}

function statCards(data){
  const s=data.sessions||{};const sCount=Array.isArray(s)?s.length:Object.keys(s).length;
  const cards=[['Total Decisions',data.total_decisions],['Deny Rate',(data.deny_rate*100).toFixed(1)+'%'],['Sessions',sCount]];
  return cards.map(c=>`<div class="card" style="flex:1;min-width:150px">
    <div style="font-size:.8125rem;color:var(--muted)">${c[0]}</div>
    <div style="font-size:1.5rem;font-weight:600">${c[1]}</div>
  </div>`).join('');}

async function loadAnalytics(){
  try{
    const r=await fetch('/api/analytics');if(!r.ok)throw new Error(r.status+' '+r.statusText);
    const data=await r.json();
    const body=document.getElementById('analytics-body');
    const decisionRows=Object.entries(data.by_decision||{}).map(([k,v])=>`<tr><td>${k}</td><td>${v}</td></tr>`).join('');
    const toolRows=Object.entries(data.by_tool||{}).map(([k,v])=>`<tr><td>${k}</td><td>${v}</td></tr>`).join('');
    const topDenied=(data.top_denied_tools||[]).map((t,i)=>`<tr><td>${i+1}</td><td>${typeof t==='object'?t.tool:t}</td></tr>`).join('');
    const sessionRows=(()=>{const s=data.sessions||{};if(Array.isArray(s))return s.map(x=>`<tr><td>${x.session_id||x.id||x}</td><td>${x.call_count||x.count||''}</td></tr>`).join('');return Object.entries(s).map(([k,v])=>`<tr><td>${k}</td><td>${typeof v==='object'?(v.call_count||v.count||''):v}</td></tr>`).join('');})();
    body.innerHTML=`<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:16px">${statCards(data)}</div>
      <div class="card"><h3 style="margin-bottom:8px">By Decision</h3>${kvTable(['Decision','Count'],decisionRows)||'<div class="empty">None</div>'}</div>
      <div class="card"><h3 style="margin-bottom:8px">By Tool</h3>${kvTable(['Tool','Count'],toolRows)||'<div class="empty">None</div>'}</div>
      <div class="card"><h3 style="margin-bottom:8px">Top Denied Tools</h3>${kvTable(['#','Tool'],topDenied)||'<div class="empty">None</div>'}</div>
      <div class="card"><h3 style="margin-bottom:8px">Sessions</h3>${kvTable(['Session','Calls'],sessionRows)||'<div class="empty">None</div>'}</div>`;
  }catch(err){document.getElementById('analytics-body').innerHTML='<div class="empty">Error: '+err.message+'</div>';}}

async function loadBaselines(){
  try{
    const r=await fetch('/api/baselines');if(!r.ok)throw new Error(r.status+' '+r.statusText);
    const data=await r.json();
    const body=document.getElementById('baseline-body');
    const tiers=['essential','hardened','certified'];
    const cards=tiers.map(t=>{
      const tier=data[t]||{status:'pending',checks:[]};
      return `<div class="card">
        <div class="card-row">
          <strong style="text-transform:capitalize">${t}</strong>
          <span class="badge badge-${tier.status}">${tier.status}</span>
        </div>
        <ul style="margin-top:8px;padding-left:20px;color:var(--muted);font-size:.8125rem">
          ${(tier.checks||[]).map(c=>'<li>'+c+'</li>').join('')||'<li>No checks</li>'}
        </ul>
      </div>`;
    }).join('');
    const owasp=((data.owasp||{}).covered||0)+'/'+((data.owasp||{}).total||((data.owasp||{}).covered||0));
    const oss=data.openssf||{};const ossRow=oss.status+((oss.target&&oss.status!==oss.target)?' → '+(oss.target):'');
    body.innerHTML=`${cards}
      <div class="card card-row">
        <strong>OWASP ASVS</strong><span class="card-meta">${owasp}</span>
      </div>
      <div class="card card-row">
        <strong>OpenSSF</strong><span class="card-meta">${ossRow}</span>
      </div>`;
  }catch(err){document.getElementById('baseline-body').innerHTML='<div class="empty">Error: '+err.message+'</div>';}}

async function approve(id){
  try{
    const r=await fetch('/api/escalations/'+id+'/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:'{"approver":"operator"}'});
    if(!r.ok){const e=await r.json();toast(e.error||'Failed','err');}else{toast('Approved','ok');loadEscalations();}
  }catch(err){toast(err.message,'err');}}

async function deny(id){
  const reason=prompt('Denial reason (optional):')||'';
  try{
    const r=await fetch('/api/escalations/'+id+'/deny',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approver:'operator',reason})});
    if(!r.ok){const e=await r.json();toast(e.error||'Failed','err');}else{toast('Denied','ok');loadEscalations();}
  }catch(err){toast(err.message,'err');}}

function toast(msg,kind){
  const el=document.getElementById('toast');el.className='toast toast-'+kind;el.textContent=msg;
  setTimeout(()=>el.textContent='',3000);}

loadEscalations();setInterval(loadEscalations,15000);
</script>
</body>
</html>
"""


def register_dashboard_route(mcp: Any, core: Any) -> None:
    """Register the /dashboard page on the FastMCP server.

    Args:
        mcp: A FastMCP server instance.
        core: A :class:`ServerCore` instance.
    """

    @mcp.custom_route("/dashboard", methods=["GET"])  # type: ignore[untyped-decorator]
    async def dashboard(request: Request) -> HTMLResponse:
        return HTMLResponse(DASHBOARD_HTML)
