'use strict';
const $ = id => document.getElementById(id);
const launchToken = location.hash.slice(1);
if (launchToken) { sessionStorage.setItem('studio-token', launchToken); history.replaceState(null, '', '/'); }
const token = sessionStorage.getItem('studio-token') || '';
let tab = 'translation', offset = 0, selected = null, dirty = false, cursor = -1, total = 0, listSequence = 0, detailSequence = 0, draftEpoch = 0;
const pageSize = 40;
function el(tag, content, cls) { const node = document.createElement(tag); if (content !== undefined) node.textContent = content; if (cls) node.className = cls; return node; }
function notice(message, error = false) { $('notice').textContent = message; $('notice').className = error ? 'error' : ''; }
async function api(action, params = {}, write = false) {
  const options = {headers: {'X-Studio-Token': token}, cache: 'no-store'};
  let url = '/api/' + action;
  if (write) { options.method = 'POST'; options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(params); }
  else { const query = new URLSearchParams(params).toString(); if (query) url += '?' + query; }
  const response = await fetch(url, options); const data = await response.json();
  if (!response.ok) { const error = new Error(data.error || 'Request failed.'); error.status = response.status; throw error; }
  return data;
}
function action(label, fn, primary = false) { const b = el('button', label, primary ? 'primary' : ''); b.type = 'button'; b.addEventListener('click', () => Promise.resolve().then(fn).catch(e => notice(e.message, true))); return b; }
function field(label, value, multiline = false) { const wrap = el('label', label), input = el(multiline ? 'textarea' : 'input'); input.value = value || ''; wrap.append(input); return [wrap, input]; }
function detail(title, value) { const box = el('details'); box.append(el('summary', title), el('pre', typeof value === 'string' ? value : JSON.stringify(value, null, 2))); return box; }
function recordStatus(r) { return !r.target ? 'untranslated' : r.human_corrected ? 'corrected' : r.uncertainty ? 'uncertain' : 'translated'; }
function canLeave() { return !dirty || confirm('You have an unsaved draft. Discard it and continue?'); }
window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
async function overview() {
  const data = await api('overview'); $('project').textContent = data.title; $('counts').replaceChildren();
  for (const [key, title] of Object.entries({discovered:'Discovered', decoded:'Decoded', translated:'Translated', uncertain:'Uncertain', inserted:'Inserted', automated:'Automated tests', emulator:'Emulator checked', hardware:'Hardware checked'})) {
    const card = el('div', undefined, 'count'); card.append(el('span', title), el('strong', String(data.counts[key])), el('small', data.percentages[key] === null ? 'No catalog yet' : `${data.percentages[key]}% of catalog`)); $('counts').append(card);
  }
  $('denominator').textContent = `Counts use ${data.denominator}. Open issues: ${data.open_issues}.`;
  const a = data.activity; $('activity').textContent = a ? `${a.payload.actor || 'Agent'} · ${a.payload.status}: ${a.payload.message} (${new Date(a.created).toLocaleTimeString()})` : 'No agent activity recorded.';
  return data.cursor;
}
function facets(data) { for (const key of ['scene','speaker','category']) { const input = $(key), value = input.value; input.replaceChildren(new Option('All ' + (key === 'category' ? 'categories' : key + 's'), '')); for (const item of data[key]) input.append(new Option(item, item)); input.value = value; } }
async function listing() {
  if (!['translation','glossary'].includes(tab)) return;
  const request = ++listSequence;
  const data = await api('list', {kind:tab, query:$('query').value, scene:$('scene').value, speaker:$('speaker').value, category:$('category').value, status:$('status').value, offset, limit:pageSize});
  if (request !== listSequence) return;
  total = data.total; facets(data.facets); $('records').replaceChildren();
  for (const r of data.items) {
    const row = el('tr'); row.className = selected && selected.id === r.id ? 'selected' : '';
    const source = el('td'), button = action(r.id, () => selectRecord(r.id)); button.className = 'record-link'; source.append(button, el('div', r.source), el('div', [r.scene,r.speaker].filter(Boolean).join(' · '), 'meta'));
    const target = el('td', r.target || '—'), status = el('td'); status.append(el('span', recordStatus(r), 'badge ' + recordStatus(r))); row.append(source,target,status); $('records').append(row);
  }
  $('result-count').textContent = total ? `${offset+1}–${Math.min(offset+pageSize,total)} of ${total}` : 'No matching records'; $('previous').disabled = offset === 0; $('next').disabled = offset+pageSize >= total;
}
async function selectRecord(key, force = false) {
  if (!force && !canLeave()) return;
  const request = ++detailSequence, epoch = draftEpoch;
  const r = await api('get',{key});
  if (request !== detailSequence || epoch !== draftEpoch) return;
  selected=r; dirty=false;
  const panel=$('detail'); panel.replaceChildren(); panel.append(el('h2',r.id),el('p',`${r.kind} · revision ${r.revision} · ${r.provenance.role} ${r.provenance.actor}`, 'meta'));
  if (r.human_corrected) panel.append(el('p','Human correction protected. Agent alternatives are kept as proposals.','muted'));
  panel.append(el('h3','Japanese / source'),el('div',r.source,'source'));
  const [englishLabel,english]=field('English',r.target,true); english.id='english';
  const [uncertaintyLabel,uncertainty]=field('Uncertainty or question',r.uncertainty,true); uncertainty.id='uncertainty'; uncertainty.rows=2;
  for (const input of [english,uncertainty]) input.addEventListener('input',()=>{dirty=true;draftEpoch++;});
  panel.append(englishLabel,uncertaintyLabel);
  const controls=el('div',undefined,'actions');
  controls.append(action('Save correction',async()=>{
    const savingEpoch=draftEpoch;
    const result=await api('edit',{key:r.id,expected:r.revision,target:english.value,uncertainty:uncertainty.value},true);
    if (request !== detailSequence) return;
    if (savingEpoch !== draftEpoch) { r.revision=result.record.revision; notice('Earlier draft saved. Your newer unsaved changes are retained.'); await listing(); return; }
    dirty=false; await selectRecord(result.record.id,true); notice('Correction saved. Future agents cannot silently replace it.'); await listing();
  },true),action('Reload record',()=>selectRecord(r.id)),action('Report issue',()=>{if(canLeave()){dirty=false;showTab('issues');editIssue(null,[r.id]);}}));
  panel.append(controls,detail('Context, source and build binding',{speaker:r.speaker,scene:r.scene,category:r.category,context:r.context,source_ref:r.source_ref,build_binding:r.build_binding}),detail('Control codes / substitutions',r.controls));
  const memory=el('details');memory.open=true;memory.append(el('summary','Translation memory & related terminology'));panel.append(memory);
  const alternatives=el('details');alternatives.append(el('summary','Agent proposals'));panel.append(alternatives);
  const revisions=el('details');revisions.append(el('summary','Revision history'));panel.append(revisions);
  const [suggestions,proposals,historyRows,evidence,layouts]=await Promise.all([api('memory',{key}),api('proposals',{key}),api('history',{key}),api('evidence-list',{key}),api('layout-reports',{key})]);
  if(request!==detailSequence)return;
  if(!suggestions.length)memory.append(el('p','No related translations yet.','muted'));
  for(const s of suggestions){const card=el('div',undefined,'card');card.append(el('div',`${s.id} · r${s.revision} · ${s.current?'current':'historical'}${s.human_corrected?' · human corrected':''}`,'meta'),el('p',s.source),el('p',s.target),el('div',[s.scene,s.speaker,s.uncertainty].filter(Boolean).join(' · '),'meta'),action('Use as draft',()=>{english.value=s.target;dirty=true;draftEpoch++;notice('Draft copied. Review this context and controls before saving.');}));memory.append(card);}
  if(!proposals.length)alternatives.append(el('p','No proposals.','muted'));
  for(const s of proposals){const card=el('div',undefined,'card');card.append(el('p',s.payload.target),el('div',`${s.actor} · based on revision ${s.base}`,'meta'),action('Use as draft',()=>{english.value=s.payload.target;dirty=true;draftEpoch++;}));alternatives.append(card);}
  for(const h of historyRows){const card=el('div',undefined,'card');card.append(el('div',`Revision ${h.revision} · ${h.role} · ${new Date(h.created).toLocaleString()}`,'meta'),el('p',h.payload.target),el('p',h.reason,'meta'));if(h.revision!==r.revision)card.append(action('Restore this revision',async()=>{if(!canLeave())return;await api('restore',{key,revision:h.revision,expected:r.revision},true);dirty=false;await selectRecord(key,true);await listing();notice('Restored as a new protected revision; history retained.');}));revisions.append(card);}
  panel.append(detail('Technical and runtime evidence (per revision)',evidence));
  const layoutBox=el('details');layoutBox.open=true;layoutBox.append(el('summary','Dialogue layout'));
  if(!layouts.length)layoutBox.append(el('p','No revision-bound layout report yet. Build with a layout-aware private adapter to validate saved text.','muted'));
  for(const report of layouts){const card=el('div',undefined,'card');card.append(el('div',`${report.build_id} · r${report.revision} · ${report.current?'matches saved revision':'stale — rebuild after correction'}`,'meta'),el('p',report.verification));for(const [context,v] of Object.entries(report.variants)){card.append(el('p',`${context}: ${v.decision} · ${v.pages} page(s) · ${v.lines} logical line(s) · ${v.width_px}/${v.limit_px}px`));}layoutBox.append(card);}
  layoutBox.append(el('p','Reports describe saved build inputs, not an unsaved draft. Each window context is validated separately.','muted'));panel.append(layoutBox);
  const screenshots=el('details');screenshots.append(el('summary','Associated screenshots'));const images=el('div',undefined,'gallery');screenshots.append(images);panel.append(screenshots);await gallery(images,key);
}
async function showIssues(){const rows=await api('issues');$('issues').replaceChildren();for(const r of rows){const card=el('div',undefined,'card');card.append(el('h3',r.title),el('div',`${r.status} · ${r.category} · revision ${r.revision}`,'meta'),el('p',r.description),el('div',r.record_ids.join(', '),'meta'),action('Edit / history',()=>editIssue(r)));$('issues').append(card);}}
async function editIssue(existing=null,recordIds=[]){
  if(!canLeave())return;dirty=false;
  const r=existing||{id:'issue-'+crypto.randomUUID(),title:'',description:'',category:'wording',status:'open',record_ids:recordIds,scene:'',build_id:'',references:[]};
  const panel=$('issue-detail');panel.replaceChildren(el('h3',existing?'Update issue':'Report an issue'));
  const fields={};for(const [key,label] of Object.entries({title:'Title',description:'What happened / how to reproduce',category:'Category',scene:'Scene',build_id:'Build version'})){const [wrap,input]=field(label,r[key],key==='description');panel.append(wrap);fields[key]=input;input.addEventListener('input',()=>{dirty=true;draftEpoch++;});}
  const [linksWrap,links]=field('Related record IDs (comma separated)',r.record_ids.join(', '));panel.append(linksWrap);
  const [refsWrap,refs]=field('Private screenshot / evidence references (one per line)',r.references.join('\n'),true);panel.append(refsWrap);
  const label=el('label','Status'),status=el('select');for(const v of ['open','investigating','resolved','closed'])status.append(new Option(v,v));status.value=r.status;label.append(status);panel.append(label);for(const input of [links,refs,status])input.addEventListener('change',()=>{dirty=true;draftEpoch++;});
  panel.append(action('Save issue',async()=>{const data={...r,...Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.value])),status:status.value,record_ids:links.value.split(',').map(s=>s.trim()).filter(Boolean),references:refs.value.split('\n').map(s=>s.trim()).filter(Boolean)};delete data.revision;const saved=await api('issue-put',{data,expected:existing?.revision||0},true);dirty=false;await showIssues();await editIssue(saved);notice('Issue saved with history.');},true));
  if(existing){panel.append(detail('Issue history',await api('issue-history',{key:r.id})));const images=el('div',undefined,'gallery');screenshotForm(panel,null,{issue_ids:[r.id],record_ids:r.record_ids,scene:r.scene,build_id:r.build_id},()=>gallery(images,null,r.id));panel.append(images);await gallery(images,null,r.id);}else panel.append(el('p','Save the issue first, then attach screenshots.','muted'));
}
async function buildStatus(){const c=await api('capabilities');$('build-test').disabled=!c.available||!!c.active_job;$('build-capability').textContent=c.available?`${c.worker} · ${c.active_job?'Build in progress':'Ready'} · Full integrated builds`:"Build worker offline. Start the private project's Studio launcher to enable builds.";}
async function showBuilds(){
  await buildStatus();const jobs=await api('jobs');$('jobs').replaceChildren();
  for(const j of jobs){const card=el('div',undefined,'card');card.append(el('h3',j.status==='validated'?'Test ROM ready':j.status),el('p',j.payload.stage),el('div',`${j.id} · ${new Date(j.created).toLocaleString()}`,'meta'),detail('Frozen inputs',{snapshot:j.snapshot}));
    if(j.payload.error)card.append(el('p',j.payload.error.message,'error'),detail('Private diagnostics',j.payload.error));
    if(j.payload.result)card.append(detail('ROM, patch and validation locations',j.payload.result));
    $('jobs').append(card);
  }
  const rows=await api('builds');$('builds').replaceChildren();
  for(const r of rows){const card=el('div',undefined,'card');card.append(el('h3',r.id),el('div',`${r.status} · ${r.approval?.approved?'user-approved checkpoint':'not an approved checkpoint'}`,'meta'),el('p',r.summary||''));if(r.validation?.layout)card.append(detail('Static layout decisions — emulator review separate',r.validation.layout.counts));card.append(detail('Validation, snapshot and file locations',r));$('builds').append(card);}
  if(!rows.length)$('builds').append(el('p','No build reports yet.','muted'));
  if(!$('upload-screenshot').childElementCount)screenshotForm($('upload-screenshot'),null,{},()=>gallery($('screenshots')));
  await gallery($('screenshots'));const events=await api('events',{after:Math.max(0,cursor-60),limit:100});$('events').replaceChildren();for(const e of events.reverse())$('events').append(el('pre',`${new Date(e.created).toLocaleString()} · ${e.kind}\n${JSON.stringify(e.payload)}`));
}
let agentViewSignature='';
async function showAgents(){
 const [sessions,work]=await Promise.all([api('agent-sessions'),api('work-list')]);
 const signature=JSON.stringify([sessions,work]);if(signature===agentViewSignature)return;agentViewSignature=signature;
 $('agent-sessions').replaceChildren();$('work-items').replaceChildren();
 for(const a of sessions){const card=el('div',undefined,'card');card.append(el('h3',a.payload.label||a.payload.provider),el('div',`${a.status} · ${a.payload.provider} · ${a.payload.model||'model unspecified'}`,'meta'),el('p',`Session ${a.id} · expires ${new Date(a.expires*1000).toLocaleString()}`,'meta'));$('agent-sessions').append(card);}
 if(!sessions.length)$('agent-sessions').append(el('p','No agent sessions registered.','muted'));
 for(const w of work){const card=el('div',undefined,'card');card.append(el('h3',w.payload.title),el('div',`${w.status} · ${w.id} · revision ${w.revision}`,'meta'),el('p',w.payload.progress),el('p',w.payload.handoff),detail('Scope and dependencies',{records:w.payload.record_ids,resources:w.payload.resources,dependencies:w.payload.dependencies,owner:w.owner,expires:w.expires?new Date(w.expires*1000).toLocaleString():null}),action('Work history',async()=>{$('work-detail').replaceChildren(el('h3',w.payload.title),detail('Task history',await api('work-history',{key:w.id})));}));$('work-items').append(card);}
 if(!work.length)$('work-items').append(el('p','No work queued. Agents use the shared CLI to claim tasks and publish results.','muted'));
}
let buildRequest=null;
$('build-test').addEventListener('click',async()=>{
  $('build-test').disabled=true;buildRequest=buildRequest||crypto.randomUUID();
  try{const job=await api('build-submit',{request_id:buildRequest,mode:'full'},true);buildRequest=null;notice('Build queued from saved revisions. You can keep browsing.');await showBuilds();}
  catch(e){notice(e.message,true);if(e.status)buildRequest=null;await buildStatus();}
});
async function showTab(next){if(!canLeave())return;dirty=false;tab=next;detailSequence++;selected=null;offset=0;listSequence++;for(const b of document.querySelectorAll('nav button'))b.setAttribute('aria-pressed',String(b.dataset.tab===tab));$('editor-view').hidden=!['translation','glossary'].includes(tab);$('issues-view').hidden=tab!=='issues';$('builds-view').hidden=tab!=='builds';$('agents-view').hidden=tab!=='agents';if(['translation','glossary'].includes(tab)){for(const id of ['query','scene','speaker','category','status'])$(id).value='';$('detail').replaceChildren(el('p','Select a record.','empty'));await listing();}else if(tab==='issues'){await showIssues();}else if(tab==='agents')await showAgents();else await showBuilds();}
for(const b of document.querySelectorAll('nav button'))b.addEventListener('click',()=>showTab(b.dataset.tab).catch(e=>notice(e.message,true)));
let searchTimer;for(const id of ['query','scene','speaker','category','status'])$(id).addEventListener(id==='query'?'input':'change',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{offset=0;listing().catch(e=>notice(e.message,true));},180);});
$('previous').addEventListener('click',()=>{offset=Math.max(0,offset-pageSize);listing().catch(e=>notice(e.message,true));});$('next').addEventListener('click',()=>{offset+=pageSize;listing().catch(e=>notice(e.message,true));});
$('new-issue').addEventListener('click',()=>editIssue().catch(e=>notice(e.message,true)));
$('snapshot').addEventListener('click',async()=>{try{const result=await api('snapshot',{},true);notice(`Frozen ${result.records} records. Snapshot: ${result.path}`);}catch(e){notice(e.message,true);}});
function screenshotForm(container,existing=null,defaults={},onSave=async()=>{}){
 const form=el('details');form.append(el('summary',existing?'Edit screenshot associations':'Upload a screenshot'));if(existing)form.open=true;
 const r=existing||{description:'',record_ids:[],issue_ids:[],scene:'',resource:'',build_id:'',association:'provisional',...defaults};
 let file;if(!existing){const label=el('label','Screenshot file (PNG/JPEG, up to 10 MiB)');file=el('input');file.type='file';file.accept='image/png,image/jpeg';label.append(file);form.append(label);}
 const fields={};for(const [key,label] of Object.entries({description:'Screenshot description',record_ids:'Screenshot record IDs (comma separated)',issue_ids:'Screenshot issue IDs (comma separated)',scene:'Screenshot scene',resource:'Interface resource',build_id:'Screenshot build version'})){
  const [wrap,input]=field(label,Array.isArray(r[key])?r[key].join(', '):r[key]);fields[key]=input;form.append(wrap);
 }
 const label=el('label','Association confidence'),confidence=el('select');confidence.append(new Option('Provisional — needs checking','provisional'),new Option('Confirmed by user','confirmed'));confidence.value=r.association;label.append(confidence);form.append(label);
 form.append(action(existing?'Save associations':'Upload screenshot',async()=>{
  const metadata=Object.fromEntries(Object.entries(fields).map(([key,input])=>[key,['record_ids','issue_ids'].includes(key)?input.value.split(',').map(x=>x.trim()).filter(Boolean):input.value]));metadata.association=confidence.value;
  let result;
  if(existing)result=await api('attachment-update',{digest:r.digest,data:metadata,expected:r.revision},true);
  else{
   const selected=file.files[0];if(!selected)throw Error('Choose a screenshot first.');if(selected.size>10*1024*1024)throw Error('Screenshot exceeds 10 MiB.');
   const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Cannot read screenshot'));reader.readAsDataURL(selected);});
   result=await api('upload',{base64:encoded,metadata},true);
  }
  notice(result.already_registered?'This screenshot already exists. Its saved associations were retained; use Edit associations to change them.':'Screenshot saved privately with association history.');
  await onSave(result);if(!existing)file.value='';
 },true));
 if(existing)form.append(action('Cancel association edit',()=>{container.dataset.editing='';form.remove();}),detail('Current associations',r));
 container.append(form);
}
async function gallery(container,key=null,issue_id=null){
 if(container.dataset.editing)return;
 const sequence=Number(container.dataset.sequence||0)+1;container.dataset.sequence=sequence;
 const rows=await api('attachments',{...(key?{key}:{}),...(issue_id?{issue_id}:{})});
 if(container.dataset.editing||Number(container.dataset.sequence)!==sequence)return;container.replaceChildren();
 for(const r of rows){
  const card=el('div',undefined,'card');card.append(el('div',`${r.build_id||'Build unspecified'} · ${r.association}`,'meta'),el('p',r.description),el('div',[r.scene,r.resource,...r.record_ids,...r.issue_ids].filter(Boolean).join(' · '),'meta'));
  const response=await fetch('/media/'+r.digest,{headers:{'X-Studio-Token':token},cache:'no-store'});
  if(container.dataset.editing||Number(container.dataset.sequence)!==sequence)return;
  if(response.ok){const url=URL.createObjectURL(await response.blob());const image=el('img');image.src=url;image.alt=r.description||'Project screenshot';image.onload=image.onerror=()=>URL.revokeObjectURL(url);card.append(image);}else card.append(el('p','Image unavailable.','muted'));
  card.append(action('Edit associations',()=>{if(container.dataset.editing)return;container.dataset.editing='true';screenshotForm(container,r,{},async()=>{container.dataset.editing='';await gallery(container,key,issue_id);});}),action('Association history',async()=>{card.append(detail('Screenshot association history',await api('attachment-history',{digest:r.digest})));}));
  container.append(card);
 }
 if(!rows.length)container.append(el('p','No screenshots registered for this view.','muted'));
}
let polling=false;async function poll(){if(polling)return;polling=true;try{const next=await overview();if(tab==='builds')await buildStatus();if(tab==='agents')await showAgents();$('connection').textContent='Local connection · updates every 2 seconds';if(next!==cursor){const initial=cursor===-1;cursor=next;if(['translation','glossary'].includes(tab)){await listing();if(selected){const checking=selected;const current=await api('get',{key:checking.id});if(selected===checking&&current.revision!==checking.revision)notice('This record changed elsewhere. Your current draft is untouched; reload to compare.',true);}}else if(tab==='issues')await showIssues();else if(tab==='builds')await showBuilds();if(initial)notice('Ready. Browse freely; saved corrections are protected.');}}catch(e){$('connection').textContent='Disconnected';notice(e.message,true);}finally{polling=false;}}
poll();setInterval(poll,2000);
