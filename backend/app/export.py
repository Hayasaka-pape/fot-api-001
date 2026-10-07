"""Self-contained OBS snapshot, with text-only DOM rendering of upstream strings."""
import io
import json
import os
import zipfile
from pathlib import Path

STYLE = """
*{box-sizing:border-box}html,body{margin:0;padding:0;overflow:hidden;font-family:Arial,'Noto Sans JP',sans-serif}#canvas{position:relative;overflow:hidden}.widget{position:absolute;border:1px solid color-mix(in srgb,var(--accent) 25%,transparent);border-radius:20px;padding:20px;overflow:hidden;background:var(--panel);color:var(--text);box-shadow:0 12px 38px #0003}.widget h2{font-size:.65em;color:var(--accent);margin:0 0 18px;letter-spacing:.12em;text-transform:uppercase}.muted{opacity:.7;font-size:.65em}.row{display:flex;align-items:center;justify-content:space-between;gap:20px;margin:12px 0}.score{font-size:2.2em;font-weight:800;white-space:nowrap}.team-name{font-weight:700;max-width:34%;overflow-wrap:anywhere}.score-meta{text-align:center;font-size:.5em;color:var(--accent)}.stat-label{font-size:.65em;opacity:.8;text-align:center}.value{font-weight:700;min-width:15%;text-align:center}.columns{display:grid;grid-template-columns:1fr 1fr;gap:20px}.player{font-size:.55em;margin:10px 0}.number{display:inline-block;color:var(--accent);min-width:2em;font-weight:700}.fixture{padding:12px 0;border-bottom:1px solid #ffffff1a;font-size:.55em}.fixture .row{margin:6px 0}.table{width:100%;border-collapse:collapse;font-size:.5em;text-align:right}.table td,.table th{padding:8px 5px;border-bottom:1px solid #ffffff1a}.table td:nth-child(2),.table th:nth-child(2){text-align:left}.badge{position:absolute;bottom:12px;left:16px;border-radius:6px;background:#06101ee8;color:white;font-size:14px;padding:6px 10px;z-index:1000;max-width:90%}.badge.demo{color:#ffe498;border:1px solid #ffe498}.badge.error{color:#ffb7ad}.empty{opacity:.65;font-size:.7em;padding:18px 0}
"""

SCRIPT = r"""
(() => {
 'use strict';
 const config = JSON.parse(document.getElementById('config').textContent);
 let data = JSON.parse(document.getElementById('data').textContent);
 const canvas = document.getElementById('canvas');
 const titles={scoreboard:'スコア',stats:'試合スタッツ',lineup:'ラインナップ',fixtures:'試合日程',standings:'順位表',team:'チーム情報',league:'大会情報',squad:'登録選手'};
 const el=(tag,text,className)=>{const n=document.createElement(tag);if(text!==undefined&&text!==null)n.textContent=String(text);if(className)n.className=className;return n;};
 const add=(parent,...nodes)=>nodes.forEach(n=>parent.appendChild(n));
 const safe=v=>v===null||v===undefined?'—':v;
 const time=v=>{if(!v)return '日時未取得';try{return new Intl.DateTimeFormat('ja-JP',{timeZone:config.query.timezone,month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(v));}catch{return String(v);}};
 function renderSection(section,value,node){
  if(value===undefined){add(node,el('p','この項目は取得できません','empty'));return;}
  if(section==='scoreboard'){
   add(node,el('div',[safe(value.league),safe(value.clock||value.status),time(value.kickoff)].join(' • '),'score-meta'));
   const row=el('div',null,'row');add(row,el('span',value.home.name,'team-name'),el('span',`${safe(value.home.score)} : ${safe(value.away.score)}`,'score'),el('span',value.away.name,'team-name'));add(node,row);
  }else if(section==='stats'){
   value.forEach(s=>{const row=el('div',null,'row');if(s.away===null){add(row,el('span',s.label,'stat-label'),el('span',safe(s.home),'value'));}else{add(row,el('span',safe(s.home),'value'),el('span',s.label,'stat-label'),el('span',safe(s.away),'value'));}add(node,row);});
  }else if(section==='lineup'){
   const labels={live:'現在の出場選手',final:'試合終了時の出場選手',starting:'先発予定',unavailable:'ラインナップ未取得',uncertain:'一部の出場選手を確認できません'};add(node,el('div',labels[value.state]||'ラインナップ','muted'));
   const columns=el('div',null,'columns');['home','away'].forEach(side=>{const team=value[side];const col=el('div');add(col,el('div',team.name),el('div',`先発登録配置 ${safe(team.formation)}`,'muted'));if(team.tracking==='uncertain'){add(col,el('div','現在の出場選手を確認できません','empty'));}team.players.forEach(p=>{const row=el('div',null,'player');add(row,el('span',safe(p.shirtNumber),'number'),el('span',`${p.name}${p.enteredAt?' · IN '+p.enteredAt:''}`));add(col,row);});add(columns,col);});add(node,columns);
  }else if(section==='fixtures'){
   value.forEach(f=>{const item=el('div',null,'fixture');add(item,el('div',[safe(f.league),time(f.kickoff),safe(f.status)].join(' • '),'muted'));const row=el('div',null,'row');add(row,el('span',f.home),el('strong',`${safe(f.homeScore)} : ${safe(f.awayScore)}`),el('span',f.away));add(item,row);add(node,item);});
  }else if(section==='standings'){
   const table=el('table',null,'table');const head=el('tr');['#','チーム','試','勝','分','負','得失','点'].forEach(t=>add(head,el('th',t)));add(table,head);value.forEach(t=>{const row=el('tr');[t.position,t.team,t.played,t.won,t.drawn,t.lost,t.goalDifference,t.points].forEach(v=>add(row,el('td',safe(v))));add(table,row);});add(node,table);
  }else if(section==='squad'){
   value.forEach(p=>{const row=el('div',null,'player');add(row,el('span',safe(p.shirtNumber),'number'),el('span',`${p.name} · ${safe(p.position)}`));add(node,row);});
  }else{
   const labels={name:'名称',country:'国',coach:'監督',venue:'スタジアム',season:'シーズン'};Object.entries(value).forEach(([key,v])=>{const row=el('div',null,'row');add(row,el('span',labels[key]||key,'muted'),el('span',safe(v)));add(node,row);});
  }
 }
 function render(error){
  canvas.replaceChildren();canvas.style.width=config.canvas.width+'px';canvas.style.height=config.canvas.height+'px';canvas.style.background=config.canvas.background;
  canvas.style.setProperty('--accent',config.theme.accent);canvas.style.setProperty('--text',config.theme.text);
  // Theme values were validated server-side; use opacity on the background only.
  const bg=config.theme.background;canvas.style.setProperty('--panel',`color-mix(in srgb, ${bg} ${config.theme.opacity*100}%, transparent)`);
  config.widgets.filter(w=>config.sections.includes(w.section)).forEach(w=>{const box=el('section',null,'widget');Object.assign(box.style,{left:w.x+'px',top:w.y+'px',width:w.width+'px',height:w.height+'px',fontSize:w.fontSize+'px'});add(box,el('h2',titles[w.section]||w.section));renderSection(w.section,data.modules[w.section],box);add(canvas,box);});
  const label=data.source==='demo'?'DEMO · 架空の表示サンプル':(config.connectedApiUrl?'FotMob':'SNAPSHOT · 固定データ');
  const stamp=time(data.fetchedAt);add(canvas,el('div',`${label} · 取得 ${stamp}${error?' · 更新失敗：前回データを表示中':''}`,'badge '+(data.source==='demo'?'demo':'')+(error?' error':'')));
 }
 render(false);
 if(config.connectedApiUrl){
  let busy=false;const refresh=async()=>{if(busy)return;busy=true;try{const response=await fetch(config.connectedApiUrl,{cache:'no-store'});if(!response.ok)throw new Error('fetch');data=await response.json();render(false);}catch{render(true);}finally{busy=false;}};
  setInterval(refresh,Math.max(15,config.pollInterval)*1000);
 }
})();
"""


def safe_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def make_export(scene, data, connected_url=None, frontend_dist=None):
    config = {**scene, "connectedApiUrl": connected_url, "snapshot": connected_url is None}
    dist = Path(frontend_dist or os.getenv("FRONTEND_DIST", "../frontend/dist"))
    portable_script = dist / "export" / "overlay-export.js"
    portable_style = dist / "export" / "style.css"
    use_portable = portable_script.is_file() and portable_style.is_file()
    script = portable_script.read_text(encoding="utf-8") if use_portable else SCRIPT
    style = portable_style.read_text(encoding="utf-8") if use_portable else STYLE
    root_id = "root" if use_portable else "canvas"
    # Embed a copy so opening index.html as a local OBS file requires no fetch/file permission.
    html = '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fot API OBS overlay</title><link rel="stylesheet" href="style.css"></head><body><main id="' + root_id + '"></main><script type="application/json" id="config">' + safe_json(config) + '</script><script type="application/json" id="data">' + safe_json(data) + '</script><script src="overlay.js"></script></body></html>'
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("index.html", html)
        archive.writestr("style.css", style)
        archive.writestr("overlay.js", script)
        archive.writestr("data.json", json.dumps(data, ensure_ascii=False, indent=2))
        archive.writestr("config.json", json.dumps(config, ensure_ascii=False, indent=2))
        archive.writestr("README.txt", "OBS のブラウザソース → ローカルファイル → index.html を指定し、保存したキャンバスの幅と高さを設定してください。\nSNAPSHOT は書き出し時点の固定データです。リアルタイム更新にはアプリの /overlay/{id} URL を使用してください。\nデモは架空の表示サンプルです。\n")
    return memory.getvalue()
