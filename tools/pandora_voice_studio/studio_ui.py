from __future__ import annotations

import json


def render_studio_ui_html(token: str) -> str:
    token_json = json.dumps(token)
    return f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pandora Voice Studio</title>
<style>
:root{{color-scheme:dark;font-family:Segoe UI,system-ui,sans-serif}}
body{{max-width:1200px;margin:0 auto;padding:24px;background:#101018;color:#eee}}
.panel,.card{{background:#1a1a28;border:1px solid #34344a;border-radius:14px;padding:16px;margin:12px 0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:14px}}
button,input,textarea{{font:inherit}}button{{cursor:pointer;border:0;border-radius:8px;padding:9px 12px;margin:3px}}
.primary{{background:#7c3aed;color:white}}.select{{background:#059669;color:white}}
.danger{{background:#991b1b;color:white}}.muted{{color:#aaa}}audio{{width:100%;margin:8px 0}}
.categories{{display:flex;flex-wrap:wrap;gap:6px}}.category{{background:#323249;color:#eee;font-size:12px}}
.category.played{{background:#166534}}textarea,input{{width:100%;box-sizing:border-box;background:#11111a;color:#eee;border:1px solid #44445b;border-radius:8px;padding:9px}}
.status{{position:sticky;bottom:0;background:#09090f;padding:12px;border:1px solid #34344a;border-radius:10px}}
.bad{{color:#fca5a5}}.good{{color:#86efac}}
</style>
</head>
<body>
<h1>Pandora Voice Studio</h1>
<p class="muted">Yerel ses adaylarını dinle, sekiz kalite alanını doğrula ve tek Pandora sesini seç.</p>
<section class="panel">
  <label for="zipPath">Candidate ZIP yolu</label>
  <input id="zipPath" autocomplete="off">
  <button class="primary" id="importButton">ZIP'i içe aktar</button>
</section>
<div id="packs"></div>
<div id="candidates" class="grid"></div>
<div class="status" id="status">Hazır.</div>
<script>
"use strict";
const TOKEN = {token_json};
const REQUIRED = ["01_greeting","02_weather","03_news","04_technical_success","05_security_warning","06_numbers_dates","07_mixed_turkish_english","08_long_form"];
const played = new Map();
const blobUrls = new Set();

function headers(jsonBody=false) {{
  const value = {{"X-Pandora-Studio-Token": TOKEN}};
  if (jsonBody) value["Content-Type"] = "application/json";
  return value;
}}
function status(message, bad=false) {{
  const node=document.getElementById("status");
  node.textContent=message;
  node.className="status "+(bad?"bad":"");
}}
function text(tag, value, cls="") {{
  const node=document.createElement(tag);
  node.textContent=String(value ?? "");
  if(cls) node.className=cls;
  return node;
}}
async function api(url, options={{}}) {{
  const response=await fetch(url, options);
  let data=null;
  try{{data=await response.json();}}catch{{}}
  if(!response.ok) throw new Error(data?.detail || data?.error || `HTTP ${{response.status}}`);
  return data;
}}
async function audioBlobUrl(url) {{
  const response=await fetch(url, {{headers:headers()}});
  if(!response.ok) {{
    let detail=`HTTP ${{response.status}}`;
    try{{detail=(await response.json()).detail || detail;}}catch{{}}
    throw new Error(detail);
  }}
  const objectUrl=URL.createObjectURL(await response.blob());
  blobUrls.add(objectUrl);
  return objectUrl;
}}
function clearBlobUrls() {{
  for(const url of blobUrls) URL.revokeObjectURL(url);
  blobUrls.clear();
}}

async function loadPacks() {{
  const packs=await api("/api/packs", {{headers:headers()}});
  const root=document.getElementById("packs");
  root.replaceChildren();
  for(const pack of packs) {{
    const button=document.createElement("button");
    button.className="panel primary";
    button.textContent=`Pack ${{pack.pack_hash}} · ${{pack.candidate_count}} aday`;
    button.onclick=()=>loadCandidates(pack.pack_hash);
    root.append(button);
  }}
}}
async function importPack() {{
  const zip_path=document.getElementById("zipPath").value.trim();
  if(!zip_path) return status("ZIP yolu gerekli.", true);
  status("İçe aktarılıyor...");
  try {{
    const result=await api("/api/import", {{
      method:"POST", headers:headers(true), body:JSON.stringify({{zip_path}})
    }});
    status(`${{result.candidate_count}} aday içe aktarıldı.`);
    await loadPacks();
  }} catch(error) {{status(error.message,true);}}
}}
function metricsText(metrics) {{
  if(metrics.error) return metrics.error;
  return `${{metrics.duration_seconds}} sn · ${{metrics.sample_rate}} Hz · peak ${{metrics.peak_amplitude}} · clipping ${{metrics.clipping_ratio}}`;
}}
function playedSet(candidateId) {{
  if(!played.has(candidateId)) played.set(candidateId,new Set());
  return played.get(candidateId);
}}
async function play(pack,candidate,category,audio,button) {{
  const url=`/api/packs/${{encodeURIComponent(pack)}}/candidates/${{encodeURIComponent(candidate)}}/audio/${{encodeURIComponent(category)}}`;
  const objectUrl=await audioBlobUrl(url);
  audio.src=objectUrl;
  await audio.play();
  playedSet(candidate).add(category);
  button.classList.add("played");
}}
async function update(pack,candidate,payload) {{
  await api(`/api/packs/${{encodeURIComponent(pack)}}/candidates/${{encodeURIComponent(candidate)}}`, {{
    method:"PUT",headers:headers(true),body:JSON.stringify(payload)
  }});
}}
async function selectPandora(pack,candidate,selectable) {{
  if(!selectable) return status("Bu aday otomatik kalite kapısını geçmedi.",true);
  const accepted=[...playedSet(candidate)].filter(item=>REQUIRED.includes(item));
  if(accepted.length!==REQUIRED.length) return status("Önce sekiz kalite klibinin tamamını dinle.",true);
  const expected=`SELECT PANDORA ${{candidate}}`;
  const confirmation=prompt(`Seçimi onaylamak için yaz:\\n${{expected}}`);
  if(confirmation!==expected) return status("Seçim iptal edildi.",true);
  try {{
    const result=await api("/api/select-pandora", {{
      method:"POST",headers:headers(true),
      body:JSON.stringify({{pack_hash:pack,candidate_id:candidate,confirmation,accepted_categories:accepted}})
    }});
    status(`Pandora seçildi: ${{result.candidate_id}}`,false);
  }} catch(error) {{status(error.message,true);}}
}}
async function loadCandidates(pack) {{
  clearBlobUrls();
  const candidates=await api(`/api/packs/${{encodeURIComponent(pack)}}/candidates`,{{headers:headers()}});
  const root=document.getElementById("candidates");
  root.replaceChildren();
  for(const candidate of candidates) {{
    const card=document.createElement("article"); card.className="card";
    card.append(text("h2",candidate.candidate_id));
    card.append(text("p",`seed ${{candidate.seed}} · ${{metricsText(candidate.metrics)}}`,candidate.selectable?"good":"bad"));
    const audio=document.createElement("audio"); audio.controls=true; card.append(audio);
    const categoryRoot=document.createElement("div"); categoryRoot.className="categories";
    for(const category of candidate.categories) {{
      const button=text("button",category,"category");
      button.onclick=()=>play(pack,candidate.candidate_id,category,audio,button).catch(error=>status(error.message,true));
      categoryRoot.append(button);
    }}
    card.append(categoryRoot);
    const notes=document.createElement("textarea"); notes.value=candidate.notes||""; notes.placeholder="Notlar";
    notes.onchange=()=>update(pack,candidate.candidate_id,{{notes:notes.value}}).catch(error=>status(error.message,true));
    card.append(notes);
    const favorite=text("button",candidate.favorite?"Favoriden çıkar":"Favori","primary");
    favorite.onclick=()=>update(pack,candidate.candidate_id,{{favorite:!candidate.favorite}}).then(()=>loadCandidates(pack));
    const reject=text("button",candidate.rejected?"Reddetmeyi kaldır":"Reddet","danger");
    reject.onclick=()=>update(pack,candidate.candidate_id,{{rejected:!candidate.rejected}}).then(()=>loadCandidates(pack));
    const select=text("button","Pandora olarak seç","select");
    select.onclick=()=>selectPandora(pack,candidate.candidate_id,candidate.selectable);
    card.append(favorite,reject,select);
    root.append(card);
  }}
}}
document.getElementById("importButton").onclick=importPack;
window.addEventListener("beforeunload",clearBlobUrls);
loadPacks().catch(error=>status(error.message,true));
</script>
</body>
</html>"""
