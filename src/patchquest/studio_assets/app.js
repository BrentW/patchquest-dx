'use strict';
const $ = id => document.getElementById(id);
const launchToken = location.hash.slice(1);
if (launchToken) { sessionStorage.setItem('studio-token', launchToken); history.replaceState(null, '', location.pathname + location.search); }
const token = sessionStorage.getItem('studio-token') || '';
let projectKey = new URLSearchParams(location.search).get('project');
let pendingWrites = 0, leavingProject = false;
function projectHeaders() { return {'X-Studio-Token': token, ...(projectKey !== null ? {'X-Studio-Project': projectKey} : {})}; }
let tab = 'dashboard', offset = 0, selected = null, dirty = false, cursor = -1, total = 0, listSequence = 0, detailSequence = 0, draftEpoch = 0;
const pageSize = 40;
function el(tag, content, cls) { const node = document.createElement(tag); if (content !== undefined) node.textContent = content; if (cls) node.className = cls; return node; }
function notice(message, error = false) { $('notice').textContent = message; $('notice').className = error ? 'error' : ''; }
async function api(action, params = {}, write = false) {
  const options = {headers: projectHeaders(), cache: 'no-store'};
  let url = '/api/' + action;
  if (write) { options.method = 'POST'; options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(params); }
  else { const query = new URLSearchParams(params).toString(); if (query) url += '?' + query; }
  if (write) { pendingWrites++; $('project-picker').disabled = true; }
  try {
    const response = await fetch(url, options); const data = await response.json();
    if (!response.ok) { const error = new Error(data.error || 'Request failed.'); error.status = response.status; throw error; }
    return data;
  } finally { if (write) { pendingWrites--; $('project-picker').disabled = pendingWrites > 0; } }
}
async function initProjects() {
  const catalogue = await api('projects'), picker = $('project-picker');
  if (projectKey === null) projectKey = catalogue.default;
  picker.replaceChildren();
  for (const project of catalogue.projects) {
    const option = new Option(project.title + (project.available ? '' : ' — unavailable'), project.id);
    option.disabled = !project.available; option.title = project.note; picker.append(option);
  }
  const current = catalogue.projects.find(p => p.id === projectKey && p.available);
  if (!current) { const missing = new Option('Choose an available project', '', true, true); missing.disabled = true; picker.prepend(missing); }
  else picker.value = projectKey;
  picker.disabled = false;
  $('project-hint').textContent = catalogue.projects.length > 1 ? 'Switch projects in this tab.' : 'Other registered projects will appear here.';
  picker.addEventListener('change', () => {
    const next = picker.value;
    if (next === projectKey) return;
    if (pendingWrites || (hasDraft() && !confirm('You have an unsaved draft. Discard it and continue?'))) { picker.value = current ? projectKey : ''; return; }
    // A new document discards old view state and in-flight read responses.
    // Every request in the old document remains bound to its original project.
    leavingProject = true; picker.disabled = true;
    location.assign('/?project=' + encodeURIComponent(next));
  });
  if (!current) throw Error('Project unavailable. Choose an available project above.');
}
function action(label, fn, primary = false) { const b = el('button', label, primary ? 'primary' : ''); b.type = 'button'; b.addEventListener('click', () => Promise.resolve().then(fn).catch(e => notice(e.message, true))); return b; }
function field(label, value, multiline = false) { const wrap = el('label', label), input = el(multiline ? 'textarea' : 'input'); input.value = value || ''; wrap.append(input); return [wrap, input]; }
// Presentation only: the browser supplies the local zone; state/API values stay intact.
function formatTimestamp(value, withDate = true) {
  if (value === null || value === undefined || value === '') return '—';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return 'Unknown time';
  return new Intl.DateTimeFormat('en-US', {
    ...(withDate ? {year:'numeric', month:'short', day:'numeric'} : {}),
    hour:'numeric', minute:'2-digit', hour12:true, timeZoneName:'short'
  }).format(date);
}
function timestampDetails(value) {
  if (Array.isArray(value)) return value.map(timestampDetails);
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key,
    ['created','updated'].includes(key) && typeof item === 'string' && /^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(item)
      ? formatTimestamp(item)
      : key === 'expires' && typeof item === 'number' && item > 0 ? formatTimestamp(item * 1000) : timestampDetails(item)
  ]));
}
function detail(title, value) { const box = el('details'); box.append(el('summary', title), el('pre', typeof value === 'string' ? value : JSON.stringify(value, null, 2))); return box; }
function recordStatus(r) { return !r.target ? 'untranslated' : r.human_corrected ? 'corrected' : 'translated'; }
function hasDraft() { return dirty || Boolean(document.querySelector('.screenshot-form[data-dirty="true"]')); }
function canLeave() {
  if (pendingWrites) { notice('Please wait for the current save to finish.', true); return false; }
  return !hasDraft() || confirm('You have an unsaved draft. Discard it and continue?');
}
window.addEventListener('beforeunload', e => { if (!leavingProject && (hasDraft() || pendingWrites)) { e.preventDefault(); e.returnValue = ''; } });
async function overview() {
  const data = await api('overview'); $('project').textContent = data.title; $('counts').replaceChildren();
  for (const [key, title] of Object.entries({discovered:'Discovered', decoded:'Decoded', translated:'Translated', human_corrected:'Human corrected', inserted:'Inserted', automated:'Automated tests', emulator:'Emulator checked', hardware:'Hardware checked'})) {
    const card = el('div', undefined, 'count'); card.append(el('span', title), el('strong', String(data.counts[key])), el('small', data.percentages[key] === null ? 'No catalog yet' : `${data.percentages[key]}% of catalog`)); $('counts').append(card);
  }
  $('denominator').textContent = `Counts use ${data.denominator}. Open issues: ${data.open_issues}.`;
  const a = data.activity; $('activity').textContent = a ? `${a.payload.actor || 'Agent'} · ${a.payload.status}: ${a.payload.message} (${formatTimestamp(a.created, false)})` : 'No agent activity recorded.';
  return data.cursor;
}
function facets(data) { for (const key of ['scene','speaker','category']) { const input = $(key), value = input.value; input.replaceChildren(new Option('All ' + (key === 'category' ? 'categories' : key + 's'), '')); for (const item of data[key]) input.append(new Option(item, item)); input.value = value; } syncFilterUI(); }
function recordFilters() {
  return {kind:tab, query:$('query').value, scene:$('scene').value, speaker:$('speaker').value, category:$('category').value, status:$('status').value, ...assessmentFilters()};
}
async function listing() {
  if (!['translation','glossary'].includes(tab)) return;
  const request = ++listSequence;
  const data = await api('list', {...recordFilters(), offset, limit:pageSize});
  if (request !== listSequence) return;
  total = data.total; facets(data.facets); $('records').replaceChildren();
  for (const r of data.items) {
    const row = el('tr'); row.className = selected && selected.id === r.id ? 'selected' : '';
    const source = el('td'), button = action(r.id, () => selectRecord(r.id)); button.className = 'record-link'; source.append(button, el('div', r.source), el('div', [r.scene,r.speaker].filter(Boolean).join(' · '), 'meta'));
    const target = el('td', r.target || '—'), status = el('td'), notes=el('td'); status.append(el('span', recordStatus(r), 'badge ' + recordStatus(r)));
    for(const a of r.assessments||[])notes.append(el('div',`${a.assessment_label} · ${a.status}${a.stale?' · stale':''}`,a.stale?'changed':'meta'));
    if(!r.assessments?.length)notes.append(el('span',r.uncertainty?'Legacy uncertainty note':'No assessments','meta'));
    notes.append(action('Details',()=>selectRecord(r.id)));row.append(source,target,status,notes); $('records').append(row);
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
  const [sourceLabel,source]=field('Japanese / source',r.source,true); source.id='japanese-source'; source.spellcheck=false;
  // Textareas normalize line endings; compare against the displayed baseline.
  let savedSource=source.value;
  panel.append(sourceLabel,el('p','Correct the source transcription here. Original extracted bytes and control codes are kept separately.','muted'));
  const [englishLabel,english]=field('English',r.target,true); english.id='english';
  const [uncertaintyLabel,uncertainty]=field('Legacy uncertainty note (use issues for new concerns)',r.uncertainty,true); uncertainty.id='uncertainty'; uncertainty.rows=2;
  for (const input of [source,english,uncertainty]) input.addEventListener('input',()=>{dirty=true;draftEpoch++;});
  panel.append(englishLabel,uncertaintyLabel);
  const controls=el('div',undefined,'actions');
  controls.append(action('Save correction',async()=>{
    const savingEpoch=draftEpoch;
    const changes={key:r.id,expected:r.revision,target:english.value,uncertainty:uncertainty.value};
    if(source.value!==savedSource)changes.source=source.value;
    const result=await api('edit',changes,true);
    if (request !== detailSequence) return;
    if (savingEpoch !== draftEpoch) { r.revision=result.record.revision; r.source=result.record.source; if('source' in changes)savedSource=changes.source; notice('Earlier draft saved. Your newer unsaved changes are retained.'); await listing(); return; }
    dirty=false; await selectRecord(result.record.id,true); notice('Correction saved. Future agents cannot silently replace it.'); await listing();
  },true),action('Reload record',()=>selectRecord(r.id)),action('Report issue',async()=>{if(await showTab('issues'))await editIssue(null,[r.id]);}));
  panel.append(controls,detail('Context, source and build binding',{speaker:r.speaker,scene:r.scene,category:r.category,context:r.context,source_ref:r.source_ref,build_binding:r.build_binding}),detail('Control codes / substitutions',r.controls));
  const assessments=el('section');assessments.id='record-assessments';assessments.append(el('h3','Exceptions & content'));panel.append(assessments);
  await refreshSelectedAssessments();if(request!==detailSequence)return;
  const memory=el('details');memory.open=true;memory.append(el('summary','Translation memory & related terminology'));panel.append(memory);
  const alternatives=el('details');alternatives.append(el('summary','Agent proposals'));panel.append(alternatives);
  const revisions=el('details');revisions.append(el('summary','Revision history'));panel.append(revisions);
  const [suggestions,proposals,historyRows,evidence,layouts]=await Promise.all([api('memory',{key}),api('proposals',{key}),api('history',{key}),api('evidence-list',{key}),api('layout-reports',{key})]);
  if(request!==detailSequence)return;
  if(!suggestions.length)memory.append(el('p','No related translations yet.','muted'));
  for(const s of suggestions){const card=el('div',undefined,'card');card.append(el('div',`${s.id} · r${s.revision} · ${s.current?'current':'historical'}${s.human_corrected?' · human corrected':''}`,'meta'),el('div',s.source,'source'),el('p',s.target),el('div',[s.scene,s.speaker,s.uncertainty].filter(Boolean).join(' · '),'meta'),action('Edit current item',()=>selectRecord(s.id)),action('Use as draft',()=>{english.value=s.target;dirty=true;draftEpoch++;notice('Draft copied. Review this context and controls before saving.');}));memory.append(card);}
  if(!proposals.length)alternatives.append(el('p','No proposals.','muted'));
  for(const s of proposals){const card=el('div',undefined,'card');card.append(el('p',s.payload.target),el('div',`${s.actor} · based on revision ${s.base}`,'meta'),action('Use as draft',()=>{english.value=s.payload.target;dirty=true;draftEpoch++;}));alternatives.append(card);}
  revisions.append(el('p','Restoring a revision restores its source text, English and notes together. Earlier revisions remain in history.','muted'));
  for(const h of historyRows){const card=el('div',undefined,'card');card.append(el('div',`Revision ${h.revision} · ${h.role} · ${formatTimestamp(h.created)}`,'meta'),el('h4','Japanese / source'),el('div',h.payload.source,'source'),el('h4','English'),el('p',h.payload.target),el('p',h.reason,'meta'));if(h.revision!==r.revision)card.append(action('Restore this revision',async()=>{if(!canLeave())return;await api('restore',{key,revision:h.revision,expected:r.revision},true);dirty=false;await selectRecord(key,true);await listing();notice('Restored as a new protected revision; history retained.');}));revisions.append(card);}
  panel.append(detail('Technical and runtime evidence (per revision)',timestampDetails(evidence)));
  const layoutBox=el('details');layoutBox.open=true;layoutBox.append(el('summary','Dialogue layout'));
  if(!layouts.length)layoutBox.append(el('p','No revision-bound layout report yet. Build with a layout-aware private adapter to validate saved text.','muted'));
  for(const report of layouts){const card=el('div',undefined,'card');card.append(el('div',`${report.build_id} · r${report.revision} · ${report.current?'matches saved revision':'stale — rebuild after correction'}`,'meta'),el('p',report.verification));for(const [context,v] of Object.entries(report.variants)){card.append(el('p',`${context}: ${v.decision} · ${v.pages} page(s) · ${v.lines} logical line(s) · ${v.width_px}/${v.limit_px}px`));}layoutBox.append(card);}
  layoutBox.append(el('p','Reports describe saved build inputs, not an unsaved draft. Each window context is validated separately.','muted'));panel.append(layoutBox);
  const screenshots=el('details');screenshots.append(el('summary','Associated screenshots'));const images=el('div',undefined,'gallery');screenshots.append(images);panel.append(screenshots);await gallery(images,key);
}
let assessmentCatalog=null;
const assessmentFilterNames=['exception','content','severity','investigation','stale'];
function assessmentFilters(){return Object.fromEntries(assessmentFilterNames.map(k=>[k,$(k+'-filter').value]));}
async function initAssessments(){
  assessmentCatalog=await api('assessment-catalog');
  for(const [id,items] of Object.entries({exception:assessmentCatalog.exceptions,content:assessmentCatalog.content,severity:assessmentCatalog.severities,investigation:assessmentCatalog.statuses})){
    for(const [value,label] of Array.isArray(items)?items.map(x=>[x,x.replaceAll('_',' ')]):Object.entries(items))$(id+'-filter').append(new Option(label,value));
  }
}
function assessmentCard(r){
  const card=el('div',undefined,'card assessment');const a=r.assessment;
  card.append(el('h3',a?r.assessment_label||assessmentCatalog?.[a.kind==='content'?'content':'exceptions']?.[a.code]||r.title:r.title),
    el('div',`${a?.kind||'legacy issue'} · ${r.status.replaceAll('_',' ')} · ${a?.severity||'unrated'} · ${a?.build_impact?.replaceAll('_',' ')||'build impact unspecified'}`,'meta'),
    el('p',r.stale===true?'Stale — recheck changed wording or context.':r.stale===false?'Current revision bindings':'Unbound legacy evidence',r.stale?'changed':'meta'));
  const expanded=el('details');expanded.append(el('summary','Details'));
  if(a){
    expanded.append(el('p',a.rationale),el('p',`Next action: ${a.next_action||'Not specified'}`),
      detail('Evidence, alternatives and investigation',{references:a.references,alternatives:a.alternatives,attempted:a.attempted,resolution:a.resolution,private_note:r.description}),
      detail('Revision and provider provenance',{bindings:a.bindings,narrative_sha256:a.narrative_sha256,provenance:a.provenance,provider_outcome:a.provider_outcome,age:a.age,consent:a.consent}));
  }else expanded.append(el('p',r.description));
  expanded.append(el('div',r.record_ids.join(', '),'meta'));card.append(expanded);return card;
}
let assessmentRefreshSequence=0;
async function refreshSelectedAssessments(){
  const record=selected,panel=$('record-assessments'),sequence=++assessmentRefreshSequence;
  if(!record||!panel)return;
  const rows=await api('assessments',{key:record.id});
  if(selected!==record||panel!==$('record-assessments')||sequence!==assessmentRefreshSequence)return;
  const signature=JSON.stringify(rows);if(panel.dataset.signature===signature)return;
  panel.dataset.signature=signature;panel.replaceChildren(el('h3','Exceptions & content'));
  for(const row of rows)panel.append(assessmentCard(row));
  if(!rows.length)panel.append(el('p','No assessments recorded. Content labels do not change wording or approval.','muted'));
}
function selectField(panel,label,options,value){
  const wrap=el('label',label),input=el('select');input.setAttribute('aria-label',label);for(const [v,t] of options)input.append(new Option(t,v));input.value=value;wrap.append(input);panel.append(wrap);return input;
}
function assessmentEditor(panel,r,links){
  const section=el('details');section.open=!!r.assessment;section.append(el('summary','Structured assessment'));panel.append(section);
  const a=r.assessment||{};let bindings=a.bindings||null,guide=a.narrative_sha256??null;
  const kind=selectField(section,'Assessment type',[['','General issue (unbound)'],['exception','Exception'],['content','Content classification'],['processing','Provider permission observation']],a.kind||'');
  if(a.kind)kind.disabled=true;
  const code=selectField(section,'Assessment category',[],a.code||'');
  const severity=selectField(section,'Assessment severity',assessmentCatalog.severities.map(x=>[x,x]),a.severity||'info');
  const impact=selectField(section,'Build impact',assessmentCatalog.build_impacts.map(x=>[x,x.replaceAll('_',' ')]),a.build_impact||'none');
  const populate=()=>{const current=code.value;code.replaceChildren();const options=kind.value==='content'?assessmentCatalog.content:kind.value==='processing'?{permitted:'Provider permission observed'}:assessmentCatalog.exceptions;for(const [v,t]of Object.entries(options))code.append(new Option(t,v));code.value=Object.hasOwn(options,current)?current:Object.keys(options)[0];severity.disabled=impact.disabled=kind.value!=='exception';if(kind.value!=='exception'){severity.value='info';impact.value='none';}};
  populate();if(a.code)code.value=a.code;kind.addEventListener('change',populate);
  const outcome=selectField(section,'Observed provider outcome (separate from content)',[['','No provider outcome'],...assessmentCatalog.outcomes.map(x=>[x,x.replaceAll('_',' ')])],a.provider_outcome||'');
  const facts={};for(const [key,choices]of Object.entries({age:['unknown','adult','minor','not_applicable'],consent:['unknown','consensual','non_consensual','not_applicable']})){
    const value=selectField(section,`${key} evidence`,choices.map(x=>[x,x.replaceAll('_',' ')]),a[key]?.value||'unknown');
    const [wrap,refs]=field(`${key} evidence references (one per line)`,a[key]?.references?.join('\n'),true);section.append(wrap);facts[key]={value,refs};
  }
  const fields={};for(const [key,label]of Object.entries({rationale:'What needs attention and why',references:'Evidence references (one per line)',alternatives:'Plausible alternatives (one per line)',attempted:'Investigation attempted (one per line)',next_action:'Recommended next action / resolution criteria',resolution:'Resolution note'})){
    const [wrap,input]=field(label,Array.isArray(a[key])?a[key].join('\n'):a[key],true);section.append(wrap);fields[key]=input;
  }
  // Existing age/consent/provider facts remain intact. New facts are added through
  // the shared API with explicit evidence; this form never guesses them.
  if(a.age||a.provider_outcome)section.append(detail('Retained factual context',{age:a.age,consent:a.consent,provider_outcome:a.provider_outcome,provenance:a.provenance}));
  const bindingLabel=el('p',bindings?'Bound to reviewed revisions; status edits retain these bindings.':'Capture reviewed inputs before saving a structured assessment.','meta');section.append(bindingLabel);
  section.append(action('Review current inputs',async()=>{
    const keys=links.value.split(',').map(s=>s.trim()).filter(Boolean);if(!keys.length)throw new Error('Add related record IDs first.');
    const packets=await Promise.all(keys.map(key=>api('assessment-context',{key})));const records=await Promise.all(keys.map(key=>api('get',{key})));
    if(packets.some(p=>p.narrative_sha256!==packets[0].narrative_sha256))throw new Error('Context changed while reading; retry.');
    const preview=el('details');preview.open=true;preview.append(el('summary','Source and translation to review'));
    for(const record of records)preview.append(el('h4',`${record.id} · revision ${record.revision}`),el('p',record.source),el('p',record.target),detail('Context',record.context));
    preview.append(action('Use these reviewed revisions',()=>{bindings=Object.assign({},...packets.map(p=>p.records));guide=packets[0].narrative_sha256;bindingLabel.textContent='Inputs captured. Saving will reject changed revisions.';dirty=true;draftEpoch++;preview.remove();}));section.append(preview);
  }));
  for(const input of section.querySelectorAll('input,textarea,select'))input.addEventListener('input',()=>{dirty=true;draftEpoch++;});
  return ()=>{
    if(!kind.value)return null;
    if(!bindings)throw new Error('Review and capture source/context revisions first.');
    const values=Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,['references','alternatives','attempted'].includes(k)?v.value.split('\n').map(x=>x.trim()).filter(Boolean):v.value]));
    const result={...a,...values,kind:kind.value,code:code.value,severity:severity.value,build_impact:impact.value,bindings,narrative_sha256:guide,
      provenance:a.provenance||{agent:'Studio user',method:'evidence-backed assessment'}};
    for(const [key,fact]of Object.entries(facts))result[key]={value:fact.value.value,references:fact.refs.value.split('\n').map(x=>x.trim()).filter(Boolean)};
    if(outcome.value)result.provider_outcome=outcome.value;else delete result.provider_outcome;
    return result;
  };
}
async function showIssues(){const rows=await api('assessments',assessmentFilters());$('issues').replaceChildren();for(const r of rows){const card=assessmentCard(r);card.append(action('Edit / history',()=>editIssue(r)));$('issues').append(card);}}
async function editIssue(existing=null,recordIds=[],draft={}){
  if(!canLeave())return;dirty=false;
  const r=existing||{id:'issue-'+crypto.randomUUID(),title:'',description:'',category:'wording',status:'open',record_ids:recordIds,scene:'',build_id:'',references:[],...draft};
  const panel=$('issue-detail');panel.replaceChildren(el('h3',existing?'Update issue':'Report an issue'));
  const fields={};for(const [key,label] of Object.entries({title:'Title',description:'What happened / how to reproduce',category:'Category',scene:'Scene',build_id:'Build version'})){const [wrap,input]=field(label,r[key],key==='description');panel.append(wrap);fields[key]=input;input.addEventListener('input',()=>{dirty=true;draftEpoch++;});}
  const [linksWrap,links]=field('Related record IDs (comma separated)',r.record_ids.join(', '));panel.append(linksWrap);
  const [refsWrap,refs]=field('Private screenshot / evidence references (one per line)',r.references.join('\n'),true);panel.append(refsWrap);
  const label=el('label','Status'),status=el('select');for(const v of ['open','investigating','needs_input','resolved','closed'])status.append(new Option(v,v));status.value=r.status;label.append(status);panel.append(label);for(const input of [links,refs,status])input.addEventListener('change',()=>{dirty=true;draftEpoch++;});
  const collectAssessment=assessmentEditor(panel,r,links);
  panel.append(action('Save issue',async()=>{const data={...r,...Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.value])),status:status.value,record_ids:links.value.split(',').map(s=>s.trim()).filter(Boolean),references:refs.value.split('\n').map(s=>s.trim()).filter(Boolean)};for(const k of ['revision','stale','stale_reasons','assessment_label'])delete data[k];const a=collectAssessment();if(a)data.assessment=a;const saved=await api('issue-put',{data,expected:existing?.revision||0},true);dirty=false;await showIssues();await editIssue(saved);notice('Issue saved with history.');},true));
  if(existing){panel.append(detail('Issue history',timestampDetails(await api('issue-history',{key:r.id}))));const images=el('div',undefined,'gallery');screenshotForm(panel,null,{issue_ids:[r.id],record_ids:r.record_ids,scene:r.scene,build_id:r.build_id},()=>gallery(images,null,r.id));panel.append(images);await gallery(images,null,r.id);}else panel.append(el('p','Save the issue first, then attach screenshots.','muted'));
}
let builderState=null, switchingBuilder=false, builderSequence=0;
async function buildStatus(){
  const sequence=++builderSequence;
  let state;
  try { state=await api('builder-status'); }
  catch(error) {
    if(error.status!==404)throw error;
    // Updated static assets can be served by an older resident Python process.
    const c=await api('capabilities');
    if(sequence!==builderSequence)return;
    builderState=null;$('builder-workers').textContent=c.available?`Loaded builder: ${c.worker}`:'No builder connected to this project.';
    $('build-capability').textContent='Restart Studio through its private launcher to load builder switching.';
    $('builder-switch').disabled=true;$('build-test').disabled=!c.available||!!c.active_job;return;
  }
  if(sequence!==builderSequence)return;
  builderState=state;
  const panel=$('builder-workers');panel.replaceChildren();
  if(!state.workers.length)panel.append(el('p','No build worker is loaded.'));
  for(const worker of state.workers){
    const row=el('div',undefined,'builder-row');
    row.append(el('strong',`${worker.available?'Loaded builder':'Unfinished build'}: ${worker.title}`));
    if(worker.worker)row.append(el('span',worker.worker,'meta'));
    row.append(el('span',worker.job?`${worker.job.status==='queued'?'Queued':'Running'} · ${worker.job.id} · ${worker.job.stage}`:'Idle · No build running','meta'));
    if(worker.available&&!worker.managed)row.append(el('span','Managed by a separate launcher','meta'));
    panel.append(row);
  }
  $('build-capability').textContent=`Selected project: ${state.selected.title}. ${state.reason}`;
  const button=$('builder-switch');
  button.textContent=switchingBuilder?'Switching builder…':state.selected.available?'Builder loaded for selected project':state.workers.some(w=>w.managed)?'Switch builder to selected project':'Load selected project’s builder';
  button.disabled=switchingBuilder||!state.can_switch;
  $('build-test').disabled=switchingBuilder||!state.selected.available||!!state.selected.job;
}
$('builder-switch').addEventListener('click',async()=>{
  if(switchingBuilder||!builderState?.can_switch)return;
  const expected=builderState.version;
  switchingBuilder=true;$('builder-switch').disabled=true;$('builder-switch').textContent='Switching builder…';$('build-test').disabled=true;
  try { await api('builder-switch',{expected},true);notice('Builder loaded for the selected project. Click Build test ROM when you are ready.'); }
  catch(error){notice(error.message,true);}
  finally{switchingBuilder=false;await buildStatus().catch(error=>notice(error.message,true));}
});
async function showBuilds(){
  await buildStatus();const jobs=await api('jobs');$('jobs').replaceChildren();
  for(const j of jobs){const card=el('div',undefined,'card');card.append(el('h3',j.status==='validated'?'Test ROM ready':j.status),el('p',j.payload.stage),el('div',`${j.id} · ${formatTimestamp(j.created)}`,'meta'),detail('Frozen inputs',{snapshot:j.snapshot}));
    if(j.payload.error)card.append(el('p',j.payload.error.message,'error'),detail('Private diagnostics',j.payload.error));
    if(j.payload.result)card.append(detail('ROM, patch and validation locations',j.payload.result));
    $('jobs').append(card);
  }
  const rows=await api('builds');$('builds').replaceChildren();
  let runtime=[];
  try{runtime=await api('runtime-reports');}
  catch(error){
    if(![400,404].includes(error.status))throw error;
    $('builds').append(el('p','Runtime evidence is unavailable in this server session. Existing build reports remain available.','muted'));
  }
  for(const r of rows){
    const card=el('div',undefined,'card');
    card.append(el('h3',r.id),el('div',`${r.status} · ${r.approval?.approved?'user-approved checkpoint':'not an approved checkpoint'}`,'meta'),el('p',r.summary||''));
    if(r.validation?.layout)card.append(detail('Static layout decisions — emulator review separate',r.validation.layout.counts));
    const coverage=el('div',undefined,'verification-coverage');
    card.append(action('Verification coverage',async()=>{
      coverage.replaceChildren(el('p','Checking this build’s evidence…','muted'));
      try{
        const report=await api('verification-report',{build_id:r.id});
        coverage.replaceChildren(el('h4','Planned verification coverage'),
          el('p',report.build_current?'This build matches saved revisions.':'This build is unavailable or differs from current saved revisions.','meta'),
          el('p','Results apply only to the planned scope and stated methods. Release approval is separate.','muted'));
        if(report.next_milestone)coverage.append(el('p','Next milestone: '+report.next_milestone));
        if(!report.areas.length)coverage.append(el('p','Not yet assessed — no verification areas have been planned.'));
        const labels={passed:'Passed for scope',failed:'Needs attention',stale:'Needs recheck',in_progress:'In progress',untested:'Untested'};
        for(const a of report.areas){
          const item=el('div',undefined,'card');item.append(el('h4',a.label),
            el('p',`${labels[a.status]||a.status} · ${a.method.replaceAll('_',' ')}`),el('p',a.expectation),
            detail('Private evidence and scope',timestampDetails(a)));coverage.append(item);
        }
      }catch(error){coverage.replaceChildren(el('p',[400,404].includes(error.status)?'Coverage is unavailable in this server session.':error.message,'error'));}
    }),coverage);
    for(const run of runtime.filter(x=>x.build_id===r.id))card.append(await runtimeCard(run));
    card.append(detail('Validation, snapshot and file locations',timestampDetails(r)));$('builds').append(card);
  }
  if(!rows.length)$('builds').append(el('p','No build reports yet.','muted'));
  if(!$('upload-screenshot').childElementCount)screenshotForm($('upload-screenshot'),null,{},()=>gallery($('screenshots')));
  await gallery($('screenshots'));const events=await api('events',{after:Math.max(0,cursor-60),limit:100});$('events').replaceChildren();for(const e of events.reverse())$('events').append(el('pre',`${formatTimestamp(e.created)} · ${e.kind}\n${JSON.stringify(timestampDetails(e.payload))}`));
}
let agentViewSignature='';
async function runtimeCard(run){
  const section=el('div',undefined,'card runtime-evidence');
  section.append(el('h4',`${run.id} · ${run.level==='automated_runtime'?'Automated emulator evidence':'Synthetic orchestration test'} · ${run.status}`),
    el('p',`${run.current?'Matches associated saved revisions':'Stale — associated translations changed'} · Human acceptance is separate.`,'meta'),
    detail('Runtime assertions and provenance',run));
  for(const capture of run.captures){
    const response=await fetch('/media/'+capture.digest,{headers:{'X-Studio-Token':token},cache:'no-store'});
    if(response.ok){
      const url=URL.createObjectURL(await response.blob()),image=el('img');
      image.src=url;image.alt=`${run.id}: ${capture.id}, frame ${capture.frame}`;
      image.onload=image.onerror=()=>URL.revokeObjectURL(url);section.append(image);
    }else section.append(el('p','Runtime capture unavailable.','muted'));
  }
  return section;
}
async function showAgents(){
 const [sessions,work]=await Promise.all([api('agent-sessions'),api('work-list')]);
 const signature=JSON.stringify([sessions,work]);if(signature===agentViewSignature)return;agentViewSignature=signature;
 $('agent-sessions').replaceChildren();$('work-items').replaceChildren();
 for(const a of sessions){const card=el('div',undefined,'card');card.append(el('h3',a.payload.label||a.payload.provider),el('div',`${a.status} · ${a.payload.provider} · ${a.payload.model||'model unspecified'}`,'meta'),el('p',`Session ${a.id} · expires ${formatTimestamp(a.expires*1000)}`,'meta'));$('agent-sessions').append(card);}
 if(!sessions.length)$('agent-sessions').append(el('p','No agent sessions registered.','muted'));
 for(const w of work){const card=el('div',undefined,'card');card.append(el('h3',w.payload.title),el('div',`${w.status} · ${w.id} · revision ${w.revision}`,'meta'),el('p',w.payload.progress),el('p',w.payload.handoff),detail('Scope and dependencies',{records:w.payload.record_ids,resources:w.payload.resources,dependencies:w.payload.dependencies,owner:w.owner,expires:w.expires?formatTimestamp(w.expires*1000):null}),action('Work history',async()=>{$('work-detail').replaceChildren(el('h3',w.payload.title),detail('Task history',timestampDetails(await api('work-history',{key:w.id}))));}));$('work-items').append(card);}
 if(!work.length)$('work-items').append(el('p','No work queued. Agents use the shared CLI to claim tasks and publish results.','muted'));
}
let buildRequest=null;
$('build-test').addEventListener('click',async()=>{
  $('build-test').disabled=true;buildRequest=buildRequest||crypto.randomUUID();
  try{const job=await api('build-submit',{request_id:buildRequest,mode:'full'},true);buildRequest=null;notice('Build queued from saved revisions. You can keep browsing.');await showBuilds();}
  catch(e){notice(e.message,true);if(e.status)buildRequest=null;await buildStatus();}
});
const pageSections={dashboard:'dashboard',agents:'dashboard',translation:'translate',glossary:'translate',
  builds:'testing',runtime:'testing',issues:'testing',testers:'testing',
  updates:'prepare',captures:'prepare',releases:'prepare'};
const lastSectionPage={dashboard:'dashboard',translate:'translation',testing:'builds',prepare:'updates'};
function syncNavigation(){
  const section=pageSections[tab];
  for(const button of document.querySelectorAll('nav [data-section]'))
    button.setAttribute('aria-pressed',String(button.dataset.section===section));
  for(const button of document.querySelectorAll('nav [data-tab]')){
    button.hidden=button.dataset.parent!==section;
    button.setAttribute('aria-pressed',String(button.dataset.tab===tab));
  }
}
async function showTab(next){
  if(!Object.hasOwn(pageSections,next))return false;
  if(next===tab)return true;
  if(!canLeave())return false;
  dirty=false;
  for(const form of document.querySelectorAll('.screenshot-form[data-dirty="true"]'))form.dataset.dirty='false';
  tab=next;lastSectionPage[pageSections[tab]]=tab;
  detailSequence++;selected=null;offset=0;listSequence++;syncNavigation();
  $('assessment-filters').hidden=!['translation','glossary','issues'].includes(tab);
  $('editor-view').hidden=!['translation','glossary'].includes(tab);
  for(const name of ['dashboard','issues','builds','agents','updates','captures','testers','releases','runtime'])
    $(name+'-view').hidden=tab!==name;
  if(tab!=='runtime'){runtimeSequence++;clearRuntimeImages();}
  if(['translation','glossary'].includes(tab)){
    for(const id of ['query','scene','speaker','category','status'])$(id).value='';
    $('editor-heading').textContent=tab==='glossary'?'Glossary':'Translations';
    $('detail').replaceChildren(el('p','Select a record.','empty'));
    syncFilterUI();await listing();
  }else if(tab==='dashboard')await overview();
  else if(tab==='issues')await showIssues();
  else if(tab==='agents')await showAgents();
  else if(tab==='updates')await showUpdates();
  else if(tab==='captures')await showCaptures();
  else if(tab==='testers')await showTesters();
  else if(tab==='releases')await showReleases();
  else if(tab==='runtime')await showRuntime();
  else await showBuilds();
  return true;
}
for(const button of document.querySelectorAll('nav [data-tab], [data-open-tab]'))
  button.addEventListener('click',()=>showTab(button.dataset.tab||button.dataset.openTab).catch(e=>notice(e.message,true)));
for(const button of document.querySelectorAll('nav [data-section]'))
  button.addEventListener('click',()=>showTab(lastSectionPage[button.dataset.section]).catch(e=>notice(e.message,true)));

function filterChoices(hostId,selectId,values){
  const select=$(selectId);
  for(const option of select.options){
    if(values&&!values.includes(option.value))continue;
    const button=action(option.textContent,()=>{
      select.value=option.value;select.dispatchEvent(new Event('change'));
    });
    button.dataset.filterTarget=selectId;button.dataset.filterValue=option.value;
    $(hostId).append(button);
  }
}
function activeFilters(hostId,ids){
  const host=$(hostId);host.replaceChildren();
  const labels={query:'Search',scene:'Scene',speaker:'Speaker',category:'Category',status:'Status',
    'runtime-group':'Build group','runtime-status':'Result','runtime-method':'Method','runtime-purpose':'Purpose',
    'exception-filter':'Exception','content-filter':'Content','severity-filter':'Severity',
    'investigation-filter':'Investigation','stale-filter':'Freshness'};
  for(const id of ids){
    const input=$(id);if(!input.value)continue;
    const text=(input.selectedOptions?.[0]?.textContent||input.value);
    const button=action(`${labels[id]}: ${text} ×`,()=>{
      input.value='';input.dispatchEvent(new Event(id==='query'?'input':'change'));
    });
    button.setAttribute('aria-label',`Remove ${labels[id].toLowerCase()} filter: ${text}`);
    host.append(button);
  }
  if(host.childElementCount)host.append(action('Clear filters',()=>{
    for(const id of ids)$(id).value='';
    $(ids[0]).dispatchEvent(new Event(ids[0]==='query'?'input':'change'));
  }));
}
function syncFilterUI(){
  for(const button of document.querySelectorAll('[data-filter-target]'))
    button.setAttribute('aria-pressed',String($(button.dataset.filterTarget).value===button.dataset.filterValue));
  activeFilters('record-active',['query','scene','speaker','category','status']);
  activeFilters('assessment-active',assessmentFilterNames.map(name=>name+'-filter'));
  activeFilters('runtime-active',['runtime-group','runtime-status','runtime-method','runtime-purpose']);
}
let searchTimer;for(const id of ['query','scene','speaker','category','status'])$(id).addEventListener(id==='query'?'input':'change',()=>{syncFilterUI();clearTimeout(searchTimer);searchTimer=setTimeout(()=>{offset=0;listing().catch(e=>notice(e.message,true));},180);});
$('previous').addEventListener('click',()=>{offset=Math.max(0,offset-pageSize);listing().catch(e=>notice(e.message,true));});$('next').addEventListener('click',()=>{offset+=pageSize;listing().catch(e=>notice(e.message,true));});
$('new-issue').addEventListener('click',()=>editIssue().catch(e=>notice(e.message,true)));
$('csv-export').addEventListener('click',async()=>{
  const button=$('csv-export');button.disabled=true;
  try {
    const response=await fetch('/api/csv-export?'+new URLSearchParams(recordFilters()),{headers:projectHeaders(),cache:'no-store'});
    if(!response.ok)throw Error('CSV export failed.');
    const url=URL.createObjectURL(await response.blob()),link=el('a');link.href=url;link.download='translations.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    notice('Exported all saved records matching the selected filters.');
  }catch(e){notice(e.message,true);}finally{button.disabled=false;}
});
$('csv-import').addEventListener('click',()=>{if(hasDraft()){notice('Save or discard your draft before importing CSV.',true);return;}$('csv-file').click();});
$('csv-file').addEventListener('change',async()=>{
  const input=$('csv-file'),file=input.files[0];if(!file)return;
  const button=$('csv-import');button.disabled=true;
  try{
    if(hasDraft())throw Error('Save or discard your draft before importing CSV.');
    if(file.size>10*1024*1024)throw Error('CSV must be 10 MB or smaller.');
    const csv=await file.text();
    if(hasDraft())throw Error('Save or discard your draft before importing CSV.');
    const result=await api('csv-import',{csv},true);
    offset=0;await listing();if(selected&&!dirty)await selectRecord(selected.id,true);await overview();
    notice(`Imported ${result.saved} corrections; ${result.unchanged} unchanged. Import uses the rows in the file, regardless of current filters.`);
  }catch(e){notice(e.message,true);}finally{input.value='';button.disabled=false;}
});
$('snapshot').addEventListener('click',async()=>{try{const result=await api('snapshot',{},true);notice(`Frozen ${result.records} records. Snapshot: ${result.path}`);}catch(e){notice(e.message,true);}});
function screenshotForm(container,existing=null,defaults={},onSave=async()=>{}){
 const form=el('details',undefined,'screenshot-form');form.append(el('summary',existing?'Edit screenshot associations':'Upload a screenshot'));if(existing)form.open=true;
 for(const event of ['input','change'])form.addEventListener(event,()=>{form.dataset.dirty='true';});
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
  form.dataset.dirty='';await onSave(result);if(!existing)file.value='';
 },true));
 if(existing)form.append(action('Cancel association edit',()=>{container.dataset.editing='';form.remove();}),detail('Current associations',timestampDetails(r)));
 container.append(form);
}
async function gallery(container,key=null,issue_id=null){
 if(container.dataset.editing)return;
 const sequence=Number(container.dataset.sequence||0)+1;container.dataset.sequence=sequence;
 const rows=await api('attachments',{...(key?{key}:{}),...(issue_id?{issue_id}:{})});
 if(container.dataset.editing||Number(container.dataset.sequence)!==sequence)return;container.replaceChildren();
 for(const r of rows){
  const card=el('div',undefined,'card');card.append(el('div',`${r.build_id||'Build unspecified'} · ${r.association}`,'meta'),el('p',r.description),el('div',[r.scene,r.resource,...r.record_ids,...r.issue_ids].filter(Boolean).join(' · '),'meta'));
  const response=await fetch('/media/'+r.digest,{headers:projectHeaders(),cache:'no-store'});
  if(container.dataset.editing||Number(container.dataset.sequence)!==sequence)return;
  if(response.ok){const url=URL.createObjectURL(await response.blob());const image=el('img');image.src=url;image.alt=r.description||'Project screenshot';image.onload=image.onerror=()=>URL.revokeObjectURL(url);card.append(image);}else card.append(el('p','Image unavailable.','muted'));
  card.append(action('Edit associations',()=>{if(container.dataset.editing)return;container.dataset.editing='true';screenshotForm(container,r,{},async()=>{container.dataset.editing='';await gallery(container,key,issue_id);});}),action('Association history',async()=>{card.append(detail('Screenshot association history',timestampDetails(await api('attachment-history',{digest:r.digest}))));}));
  container.append(card);
 }
 if(!rows.length)container.append(el('p','No screenshots registered for this view.','muted'));
}
let polling=false;async function poll(){if(polling)return;polling=true;try{const next=await overview();if(['translation','glossary'].includes(tab))await refreshSelectedAssessments();if(tab==='builds')await buildStatus();if(tab==='agents')await showAgents();$('connection').textContent='Local connection · updates every 2 seconds';if(next!==cursor){const initial=cursor===-1;cursor=next;if(['translation','glossary'].includes(tab)){await listing();if(selected){const checking=selected;const current=await api('get',{key:checking.id});if(selected===checking&&current.revision!==checking.revision)notice('This record changed elsewhere. Your current draft is untouched; reload to compare.',true);}}else if(tab==='issues')await showIssues();else if(tab==='builds')await showBuilds();else if(tab==='runtime')await showRuntime();if(initial)notice('Ready. Browse freely; saved corrections are protected.');}}catch(e){$('connection').textContent='Disconnected';notice(e.message,true);}finally{polling=false;}}
async function refreshAssessments(){syncFilterUI();offset=0;if(tab==='issues')await showIssues();else await listing();}
for(const name of assessmentFilterNames)$(name+'-filter').addEventListener('change',()=>refreshAssessments().catch(e=>notice(e.message,true)));
$('clear-assessment-filters').addEventListener('click',()=>{for(const name of assessmentFilterNames)$(name+'-filter').value='';refreshAssessments().catch(e=>notice(e.message,true));});
let updatesSequence = 0;
const updateCategories = ['progress','translation','review','testing','tooling'];
const updateBases = {not_verified:'Not verified',static:'Static checks',automated_runtime:'Automated runtime',reported_human:'Human-reported testing',hardware:'Hardware testing'};
async function showUpdates() {
  const sequence = ++updatesSequence;
  const board = await api('milestones'), preview = await api('milestone-preview');
  if (tab !== 'updates' || sequence !== updatesSequence) return;
  if (board.revision !== preview.selection_revision) throw Error('Updates changed while loading. Reopen Milestone updates to refresh.');
  $('update-detail').replaceChildren(el('p','Select a summary or start a draft.','empty'));
  $('updates-toolbar').replaceChildren(action('New summary',()=>editUpdate()),action('Refresh summaries',async()=>{if(canLeave()){dirty=false;await showUpdates();}}));
  $('updates-list').replaceChildren();
  for (const item of board.items.slice().reverse()) {
    const card = el('div',undefined,'card');
    card.append(el('h3',item.content.title),el('p',item.content.summary),el('div',`${item.content.date} · ${item.selected?'Selected for export':item.review?'Reviewed · not selected':'Draft · review required'}`,'meta'),action('Edit / review',()=>editUpdate(item)));
    $('updates-list').append(card);
  }
  if (!board.items.length) $('updates-list').append(el('p','No milestone summaries yet.','muted'));
  const exportButton = action('Export selected summaries',async()=>{
    if (dirty) throw Error('Save or discard your draft before exporting.');
    exportButton.disabled=true;
    try {
      const result=await api('milestone-export',{expected:preview.selection_revision},true);
      notice(`Saved ${result.count} selected summaries privately: ${result.path}. Nothing was published.`);
    } finally {exportButton.disabled=false;}
  });
  $('updates-preview').replaceChildren(el('h3',`Export preview · ${preview.items.length} selected`),el('p','Only the fields below are exported. Empty selections produce an empty list. Earlier exports remain unchanged.','muted'),detail('Exact export content',preview),exportButton);
}
function editUpdate(item=null) {
  if (!canLeave()) return;
  ++updatesSequence; dirty=false;
  const today=new Date(),calendarDate=[today.getFullYear(),String(today.getMonth()+1).padStart(2,'0'),String(today.getDate()).padStart(2,'0')].join('-');
  const form=el('div'), content=item?.content||{date:calendarDate,title:'',summary:'',category:'progress',verification_basis:'not_verified',limitations:''}, inputs={};
  form.append(el('h3',item?'Edit milestone summary':'New milestone summary'));
  for (const [key,label] of Object.entries({date:'Milestone date',title:'Summary title',summary:'Summary text',limitations:'Scope and remaining limitations',private_notes:'Private notes / evidence references (excluded from export)'})) {
    const [wrap,input]=field(label,key==='private_notes'?item?.private_notes:content[key],['summary','limitations','private_notes'].includes(key));
    if(key==='date')input.type='date';
    input.maxLength={date:10,title:160,summary:2000,limitations:1000,private_notes:8000}[key];
    inputs[key]=input;form.append(wrap);
  }
  for (const [key,label,choices] of [['category','Category',Object.fromEntries(updateCategories.map(x=>[x,x]))],['verification_basis','Verification basis (reported, not certified)',updateBases]]) {
    const wrap=el('label',label),input=el('select');
    input.setAttribute('aria-label',label);
    for(const [value,name] of Object.entries(choices))input.append(new Option(name,value));
    input.value=content[key];inputs[key]=input;wrap.append(input);form.append(wrap);
  }
  const reviewedActions=el('div',undefined,'actions');
  const lock=state=>{for(const input of form.querySelectorAll('input,textarea,select,button'))input.disabled=state;};
  form.addEventListener('input',()=>{dirty=true;for(const button of reviewedActions.querySelectorAll('button'))button.disabled=true;});
  const run=async(actionName,params)=>{
    lock(true);
    try {await api(actionName,params,true);dirty=false;if(tab==='updates')await showUpdates();notice('Milestone saved privately. Nothing was published.');}
    finally {lock(false);if(dirty)for(const b of reviewedActions.querySelectorAll('button'))b.disabled=true;}
  };
  form.append(action('Save draft',()=>run('milestone-put',{
    data:Object.fromEntries(['date','title','summary','category','verification_basis','limitations'].map(key=>[key,inputs[key].value])),
    private_notes:inputs.private_notes.value,expected:item?.revision||0,...(item?{key:item.id}:{})
  }),true));
  if(item) {
    form.append(el('p','Review the saved text, its scope, evidence and privacy before marking it reviewed. Verification basis is an editorial label; it does not certify a test result.','muted'),detail('Saved content for review',item.content));
    reviewedActions.append(action('Mark reviewed',()=>{if(dirty)throw Error('Save this draft before reviewing.');return run('milestone-review',{key:item.id,expected:item.revision,content_sha256:item.content_sha256});}));
    if(item.review)reviewedActions.append(action(item.selected?'Remove from export':'Select for export',()=>{if(dirty)throw Error('Save this draft first.');return run('milestone-select',{key:item.id,expected:item.revision,selected:!item.selected});}));
    form.append(reviewedActions);
  }
  form.append(action('Cancel edit',async()=>{if(canLeave()){dirty=false;await showUpdates();}}));
  $('update-detail').replaceChildren(form);
}
let capturesSequence=0;
const captureKinds={unknown:'Unknown / uploaded image',reported_emulator:'Emulator capture (reported)',reported_hardware:'Hardware capture (reported)',static_preview:'Static preview (reported)',synthetic:'Synthetic image',registered_runtime:'Registered emulator capture'};
async function captureImage(container,digest,alt) {
  const response=await fetch('/media/'+digest,{headers:projectHeaders(),cache:'no-store'});
  if(!response.ok)throw Error('Registered image is unavailable or changed.');
  const url=URL.createObjectURL(await response.blob()),image=el('img');
  image.alt=alt;image.className='selected-capture';
  // Bind review to an image that has actually loaded, not just its metadata.
  await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('Image could not be displayed.'));image.src=url;})
    .finally(()=>URL.revokeObjectURL(url));
  container.append(image);
}
async function showCaptures() {
  const sequence=++capturesSequence;
  const board=await api('screenshot-selection'),attachments=await api('attachments');
  let preview=null,blocked='';
  try {preview=await api('screenshot-preview');}catch(error){blocked='A selected screenshot has changed or its evidence is unavailable. Refresh its draft and review again, or remove it from export.';}
  if(tab!=='captures'||sequence!==capturesSequence)return;
  if(preview&&preview.selection_revision!==board.revision)throw Error('Screenshot selection changed while loading. Refresh this section.');
  $('capture-detail').replaceChildren(el('p','Choose an uploaded screenshot or a saved selection.','empty'));
  $('captures-toolbar').replaceChildren(action('Refresh screenshots',async()=>{if(canLeave()){dirty=false;await showCaptures();}}));
  $('captures-list').replaceChildren(el('h3','Saved selections'));
  for(const item of board.items.slice().reverse()) {
    const card=el('div',undefined,'card');
    card.append(el('h4',item.content.caption),el('p',`${item.stale?'Needs fresh review · ':''}${item.selected?'Selected for export':item.review?'Reviewed · not selected':'Draft'} · Spoilers: ${item.content.spoiler}`,'meta'),action('Edit / review capture',()=>editCapture(item.source.digest,item)));
    if(item.selected)card.append(action('Remove from export',async()=>{await api('screenshot-select',{key:item.id,expected:item.revision,selected:false},true);if(!dirty)await showCaptures();}));
    $('captures-list').append(card);
  }
  if(!board.items.length)$('captures-list').append(el('p','No screenshots selected.','muted'));
  $('captures-list').append(el('h3','Registered screenshots'));
  for(const attachment of attachments) {
    const card=el('div',undefined,'card');
    card.append(el('p',attachment.description||'Screenshot without a description'),el('p',`${attachment.build_id||'Build unlinked'} · ${attachment.association}`,'meta'),action('Prepare screenshot',()=>editCapture(attachment.digest)));
    $('captures-list').append(card);
  }
  if(!attachments.length)$('captures-list').append(el('p','Upload a screenshot in Builds & activity first.','muted'));
  $('captures-preview').replaceChildren(el('h3',preview?`Metadata export · ${preview.items.length} selected`:'Metadata export blocked'));
  if(!preview){$('captures-preview').append(el('p',blocked,'changed'));return;}
  const button=action('Export selected metadata',async()=>{
    if(dirty)throw Error('Save or discard your draft before exporting.');
    button.disabled=true;
    try {const result=await api('screenshot-export',{expected:preview.selection_revision},true);notice(`Saved ${result.count} screenshot metadata entries privately: ${result.path}. Images were not copied or published.`);}
    finally {button.disabled=false;}
  });
  $('captures-preview').append(el('p','Metadata only: images, internal paths, notes and raw runtime reports are excluded. Earlier exports remain unchanged.','muted'),detail('Exact screenshot metadata export',preview),button);
}
async function editCapture(digest,item=null) {
  if(!canLeave())return;
  dirty=false;const sequence=++capturesSequence;
  let runtimeReport=item?.source.runtime_report||'',runtimeCapture=item?.source.runtime_capture||'';
  const initial=await api('screenshot-context',{digest});
  let current=initial;
  if(runtimeReport) {
    try {current=await api('screenshot-context',{digest,runtime_report:runtimeReport,runtime_capture:runtimeCapture});}
    catch(error){runtimeReport='';runtimeCapture='';notice('The saved runtime reference is unavailable. Choose valid provenance and save a fresh draft.',true);}
  }
  if(tab!=='captures'||sequence!==capturesSequence)return;
  const content=item?.content||{caption:'',alt_text:'',spoiler:'unknown',build_label:'',capture_kind:'unknown',capture_date:''};
  const form=el('div'),inputs={},reviewActions=el('div',undefined,'actions');
  form.append(el('h3',item?'Edit screenshot metadata':'Prepare screenshot metadata'));
  await captureImage(form,digest,content.alt_text||'Selected private screenshot');
  if(tab!=='captures'||sequence!==capturesSequence)return;
  const sourceInfo=el('p',undefined,'meta');
  const describe=()=>{sourceInfo.textContent=`${current.image.width} × ${current.image.height} · ${current.build_association} build association · ${current.capture.basis.replaceAll('_',' ')}${current.capture.runtime_status?' · Run '+current.capture.runtime_status:''}`;};describe();form.append(sourceInfo);
  for(const [key,label] of Object.entries({caption:'Capture caption',alt_text:'Accessible image description',build_label:'Reviewed build label',capture_date:'Capture date (leave blank if unknown)',private_notes:'Private capture notes (excluded)'})) {
    const [wrap,input]=field(label,key==='private_notes'?item?.private_notes:content[key],['caption','alt_text','private_notes'].includes(key));
    input.maxLength={caption:1000,alt_text:500,build_label:160,capture_date:10,private_notes:8000}[key];
    if(key==='capture_date')input.type='date';
    inputs[key]=input;form.append(wrap);
  }
  for(const [key,label,options] of [['spoiler','Spoiler flag',{unknown:'Not assessed',none:'No spoilers',spoilers:'Contains spoilers'}],['capture_kind','Capture provenance',captureKinds]]) {
    const wrap=el('label',label),input=el('select');input.setAttribute('aria-label',label);
    for(const [value,name] of Object.entries(options))input.append(new Option(name,value));
    input.value=content[key];inputs[key]=input;wrap.append(input);form.append(wrap);
  }
  const wrap=el('label','Registered capture reference'),reference=el('select');reference.setAttribute('aria-label','Registered capture reference');
  reference.append(new Option('None — reported provenance only',''));
  for(const c of initial.runtime_choices)reference.append(new Option(c.capture+' · '+c.report.slice(0,12),JSON.stringify(c)));
  reference.value=runtimeReport?JSON.stringify({report:runtimeReport,capture:runtimeCapture}):'';
  wrap.append(reference);form.append(wrap);
  let loading=false;
  const stale=()=>item&&(!current||current.token!==item.source.token);
  const updateReviewButtons=()=>{for(const b of reviewActions.querySelectorAll('button'))b.disabled=dirty||loading||stale();};
  form.addEventListener('input',()=>{dirty=true;updateReviewButtons();});
  reference.addEventListener('change',async()=>{
    loading=true;dirty=true;reference.disabled=true;updateReviewButtons();
    try {
      const choice=reference.value?JSON.parse(reference.value):{report:'',capture:''};
      current=await api('screenshot-context',{digest,runtime_report:choice.report,runtime_capture:choice.capture});
      runtimeReport=choice.report;runtimeCapture=choice.capture;
      if(runtimeReport)inputs.capture_kind.value=current.capture.kind;
      else if(inputs.capture_kind.value==='registered_runtime')inputs.capture_kind.value='unknown';
      describe();
    }catch(error){notice('Capture provenance is unavailable. Select another reference before saving.',true);current=null;}
    finally {loading=false;reference.disabled=false;updateReviewButtons();}
  });
  const lock=value=>{for(const input of form.querySelectorAll('input,textarea,select,button'))input.disabled=value;};
  const run=async(actionName,params)=>{
    lock(true);
    try {await api(actionName,params,true);dirty=false;if(tab==='captures')await showCaptures();notice('Screenshot metadata saved privately. Nothing was published.');}
    finally {lock(false);if(current)updateReviewButtons();}
  };
  form.append(action('Save capture draft',()=>{
    if(loading||!current)throw Error('Wait for valid capture provenance before saving.');
    return run('screenshot-put',{digest,runtime_report:runtimeReport,runtime_capture:runtimeCapture,context_token:current.token,
      data:Object.fromEntries(['caption','alt_text','spoiler','build_label','capture_kind','capture_date'].map(k=>[k,inputs[k].value])),
      private_notes:inputs.private_notes.value,expected:item?.revision||0,...(item?{key:item.id}:{})});
  },true));
  if(item) {
    form.append(el('p','Review the image, caption, build, provenance and spoiler flag. Reported provenance does not establish runtime verification or publication rights.','muted'),detail('Saved screenshot metadata',item.content));
    if(stale())form.append(el('p','Source associations changed. Save a refreshed draft before review.','changed'));
    reviewActions.append(action('Mark capture reviewed',()=>{if(dirty||loading||stale())throw Error('Save and inspect a current draft first.');return run('screenshot-review',{key:item.id,expected:item.revision,review_token:item.review_token});}));
    if(item.review)reviewActions.append(action(item.selected?'Deselect capture':'Select capture for export',()=>{if(dirty||loading||stale())throw Error('Save and inspect a current draft first.');return run('screenshot-select',{key:item.id,expected:item.revision,selected:!item.selected});}));
    form.append(reviewActions);updateReviewButtons();
  }
  form.append(action('Cancel capture edit',async()=>{if(canLeave()){dirty=false;await showCaptures();}}));
  $('capture-detail').replaceChildren(form);
}
let testersSequence=0,testersOffset=0,testersStatus='';
const testerStates={new:'New',needs_info:'Needs information',accepted:'Accepted for investigation',duplicate:'Duplicate',rejected:'Rejected',closed:'Closed intake'};
async function showTesters() {
  const sequence=++testersSequence;
  const list=await api('tester-reports',{status:testersStatus,offset:testersOffset,limit:50});
  if(tab!=='testers'||sequence!==testersSequence)return;
  const filter=el('select');filter.setAttribute('aria-label','Report intake status');
  filter.append(new Option('All intake statuses',''));
  for(const [key,label] of Object.entries(testerStates))filter.append(new Option(label,key));filter.value=testersStatus;
  filter.addEventListener('change',()=>{if(canLeave()){dirty=false;testersStatus=filter.value;testersOffset=0;showTesters().catch(e=>notice(e.message,true));}else filter.value=testersStatus;});
  $('testers-toolbar').replaceChildren(action('Import tester reports',()=>editTesterImport()),action('Refresh reports',async()=>{if(canLeave()){dirty=false;await showTesters();}}),filter);
  $('testers-list').replaceChildren(el('p',`${list.total} reports · page ${Math.floor(testersOffset/50)+1}`,'meta'));
  for(const r of list.items) {
    const card=el('div',undefined,'card');card.append(el('h3',r.content.title),el('p',`${testerStates[r.triage.status]} · ${r.content.category}`,'meta'),el('p',r.content.build_label||'Tested build not reported'),action('Inspect / triage',()=>editTester(r.id)));
    $('testers-list').append(card);
  }
  const previous=action('Previous reports',async()=>{if(canLeave()){dirty=false;testersOffset=Math.max(0,testersOffset-50);await showTesters();}});
  const next=action('Next reports',async()=>{if(canLeave()){dirty=false;testersOffset+=50;await showTesters();}});
  previous.disabled=testersOffset===0;next.disabled=testersOffset+50>=list.total;
  $('testers-list').append(previous,next);
  $('tester-detail').replaceChildren(el('p','Select a report or import a JSON file. Original submissions are retained.','empty'));
}
async function editTesterImport() {
  if(!canLeave())return;dirty=false;const sequence=++testersSequence;
  const form=el('div');form.append(el('h3','Import private tester reports'),el('p','Preview before importing. Repeated identical IDs are skipped; changed submissions need a new ID. Nothing here applies suggested wording.','muted'));
  const [wrap,input]=field('Tester report JSON','',true),file=el('input');file.type='file';file.accept='.json,application/json';file.setAttribute('aria-label','Tester report JSON file');
  let epoch=0,prepared=null;const preview=el('div');
  const commit=action('Import previewed reports',async()=>{
    if(!prepared)throw Error('Preview the current file first.');
    input.disabled=file.disabled=commit.disabled=true;
    try {const r=await api('tester-import',{document:prepared.document,preview_token:prepared.token},true);if(sequence===testersSequence&&tab==='testers'){dirty=false;await showTesters();}notice(`Imported ${r.imported} reports; ${r.existing} already present. Translations are unchanged.`);}
    finally {input.disabled=file.disabled=false;commit.disabled=!prepared;}
  },true);commit.disabled=true;
  const changed=()=>{epoch++;dirty=true;prepared=null;commit.disabled=true;preview.replaceChildren();};
  input.addEventListener('input',changed);
  file.addEventListener('change',async()=>{
    changed();const current=epoch;
    try {const selected=file.files[0];if(!selected)return;if(selected.size>256*1024)throw Error('Report file exceeds 256 KiB.');const data=await selected.text();if(epoch===current&&sequence===testersSequence&&tab==='testers')input.value=data;}
    catch(error){notice(error.message,true);}
  });
  form.append(file,wrap,action('Preview report import',async()=>{
    const current=epoch;prepared=null;commit.disabled=true;preview.replaceChildren();
    const document=JSON.parse(input.value),result=await api('tester-import-preview',{document},true);
    if(current!==epoch||sequence!==testersSequence||tab!=='testers')return;
    prepared=result;preview.append(el('p',`${result.new} new · ${result.existing} already imported`),detail('Exact normalized reports to import',result.document));commit.disabled=false;
  }),preview,commit,action('Cancel report import',async()=>{if(canLeave()){dirty=false;await showTesters();}}));
  $('tester-detail').replaceChildren(form);
}
async function editTester(key) {
  if(!canLeave())return;dirty=false;const sequence=++testersSequence;
  const r=await api('tester-report',{key}),builds=await api('builds');
  if(sequence!==testersSequence||tab!=='testers')return;
  const form=el('div'),inputs={},binding=r.triage.binding;
  form.append(el('h3',r.content.title),el('p',`${r.source} · ${r.content.external_id} · ${testerStates[r.triage.status]}`,'meta'));
  for(const [key,label] of Object.entries({observed:'Reported observation',steps:'Steps to reproduce',expected:'Expected result',environment:'Reported environment',suggested_translation:'Suggested wording — inactive'})) {
    if(r.content[key])form.append(el('h4',label),el('p',r.content[key],'translation'));
  }
  form.append(detail('Original submitted report',r.content));
  if(r.changed_since_triage)form.append(el('p','Build, record revisions or evidence changed since triage. Inspect current links before saving.','changed'));
  if(r.binding_unavailable)form.append(el('p','Linked evidence is unavailable. Original bindings remain in history; choose valid links or record an unlinked follow-up.','changed'));
  if(r.context?.differs_from_build.length)form.append(el('p','These translations now differ from the tested build: '+r.context.differs_from_build.join(', '),'changed'));
  if(r.issue)form.append(el('p',`Linked issue: ${r.issue.title} · ${r.issue.status}`,'meta'),action('Open linked issue',async()=>{await showTab('issues');if(tab==='issues')editIssue(r.issue);}));
  const buildWrap=el('label','Build tested'),build=el('select');build.setAttribute('aria-label','Build tested');build.append(new Option('Unlinked / unknown',''));
  for(const b of builds)build.append(new Option(b.id+' · '+b.status,b.id));
  build.value=binding?.build_id||'';buildWrap.append(build);form.append(buildWrap);inputs.build=build;
  for(const [key,label,value,multi] of [
    ['records','Affected translation IDs (one per line)',Object.keys(binding?.records||{}).join('\n'),true],
    ['images','Registered screenshot hashes (one per line)',Object.keys(binding?.attachments||{}).join('\n'),true],
    ['issue','Existing issue ID',r.triage.issue_id,false],['duplicate','Original report ID (for duplicates)',r.triage.duplicate_of,false],
    ['notes','Private triage notes',r.triage.notes,true]]) {
    const [wrap,input]=field(label,value,multi);inputs[key]=input;form.append(wrap);
  }
  const stateWrap=el('label','Intake decision'),state=el('select');state.setAttribute('aria-label','Intake decision');
  for(const [key,label] of Object.entries(testerStates))state.append(new Option(label,key));state.value=r.triage.status;stateWrap.append(state);form.append(stateWrap);
  const createWrap=el('label','Create a new linked issue'),create=el('select');create.setAttribute('aria-label','Create a new linked issue');
  create.append(new Option('No','no'),new Option('Yes — accepted reports only','yes'));createWrap.append(create);form.append(createWrap);
  const contextView=el('div');let ctx=null,epoch=0;
  const lines=input=>input.value.split('\n').map(s=>s.trim()).filter(Boolean);
  const links=()=>({key,build_id:build.value,record_ids:lines(inputs.records),attachment_digests:lines(inputs.images)});
  const save=action('Save report triage',async()=>{
    if(!ctx)throw Error('Inspect the selected build and record links first.');
    for(const input of form.querySelectorAll('input,textarea,select,button'))input.disabled=true;
    try {await api('tester-triage',{...links(),expected:r.revision,context_token:ctx.token,status:state.value,notes:inputs.notes.value,issue_id:inputs.issue.value,duplicate_of:inputs.duplicate.value,create_issue:create.value==='yes'},true);if(sequence===testersSequence&&tab==='testers'){dirty=false;await showTesters();}notice('Triage saved privately. Original report and translations are unchanged.');}
    finally {for(const input of form.querySelectorAll('input,textarea,select,button'))input.disabled=false;save.disabled=!ctx;}
  },true);save.disabled=true;
  form.addEventListener('input',()=>{dirty=true;});
  for(const input of [build,inputs.records,inputs.images])input.addEventListener('input',()=>{epoch++;ctx=null;save.disabled=true;contextView.replaceChildren();});
  form.append(action('Inspect build and record links',async()=>{
    const current=epoch;ctx=null;save.disabled=true;contextView.replaceChildren();
    const result=await api('tester-context',links(),true);
    if(current!==epoch||sequence!==testersSequence||tab!=='testers')return;
    ctx=result;contextView.append(el('p',`Reported artifact: ${result.artifact_match}. ${result.differs_from_build.length} linked translations differ from this build.`,'meta'),detail('Exact build and revision links',result.binding));save.disabled=false;
  }),contextView,el('p','Acceptance opens investigation; closed intake is not proof of a fix. Use the linked issue for investigation and the verification workflow for retesting. Suggested wording is never applied here.','muted'),save,
  action('Cancel report triage',async()=>{if(canLeave()){dirty=false;await showTesters();}}),action('Show report history',async()=>{const rows=await api('tester-history',{key});if(tab==='testers'&&sequence===testersSequence)form.append(detail('Private report history',rows));}));
  $('tester-detail').replaceChildren(form);
}
let releasesSequence=0;
function releaseCards(board) {
  $('releases-list').replaceChildren();
  for(const item of board.items.slice().reverse()) {
    const card=el('div',undefined,'card');card.append(el('h3',item.content.title+' · '+item.content.version),el('p',item.review?'Metadata reviewed previously · inspect current files':item.validation?'Validated previously · inspect current files':'Draft','meta'),action('Inspect release candidate',()=>editRelease(item)));
    $('releases-list').append(card);
  }
  if(!board.items.length)$('releases-list').append(el('p','No release candidates yet.','empty'));
}
async function showReleases() {
  const sequence=++releasesSequence,board=await api('release-candidates');
  if(sequence!==releasesSequence||tab!=='releases')return;
  $('releases-toolbar').replaceChildren(action('New release candidate',()=>editRelease()),action('Refresh candidates',async()=>{if(canLeave()){dirty=false;await showReleases();}}),action('Release preparation history',async()=>{
    if(!canLeave())return;dirty=false;const current=++releasesSequence,rows=await api('release-history');
    if(current===releasesSequence&&tab==='releases')$('release-detail').replaceChildren(detail('Private preparation history',rows));
  }));
  releaseCards(board);
  $('release-detail').replaceChildren(el('p','Select a candidate or start a draft. All preparation remains private.','empty'));
}
async function editRelease(item=null) {
  if(!canLeave())return;dirty=false;const sequence=++releasesSequence,builds=await api('builds');
  const board=await api('release-candidates');
  if(item){item=board.items.find(x=>x.id===item.id);if(!item)throw Error('Candidate unavailable. Refresh the list.');}
  if(sequence!==releasesSequence||tab!=='releases')return;
  releaseCards(board);
  const form=el('div'),inputs={},content=item?.content||{},selection=item?.selection||{};
  form.append(el('h3',item?'Inspect release candidate':'New release candidate'),el('p','The exact original file pinned by this project is used. No header removal, normalization, source discovery or build execution occurs.','muted'));
  for(const [key,label] of Object.entries({release_id:'Release ID',title:'Release title',version:'Release version',source_label:'Required source edition / revision',patch_filename:'Patch download filename (.bps)',output_filename:'Patched image filename',compatibility:'Compatibility and input requirements',limitations:'Scope and remaining limitations',private_notes:'Private notes (excluded from export)'})) {
    const [wrap,input]=field(label,key==='private_notes'?item?.private_notes:content[key],['compatibility','limitations','private_notes'].includes(key));
    input.maxLength=key==='private_notes'?8000:['compatibility','limitations'].includes(key)?4000:160;inputs[key]=input;form.append(wrap);
  }
  const selectField=(label)=>{const wrap=el('label',label),input=el('select');input.setAttribute('aria-label',label);wrap.append(input);form.append(wrap);return input;};
  const build=selectField('Build to prepare'),patch=selectField('Patch artifact'),output=selectField('Output image artifact'),repeat=selectField('Repeat build (optional comparison)');
  build.append(new Option('Choose a build',''));repeat.append(new Option('Not provided — no repeat-build claim',''));
  for(const b of builds){build.append(new Option(b.id+' · '+b.status,b.id));repeat.append(new Option(b.id+' · '+b.status,b.id));}
  build.value=selection.build_id||'';repeat.value=selection.repeat_build_id||'';
  const artifacts=()=>{patch.replaceChildren(new Option('Choose the patch',''));output.replaceChildren(new Option('Choose the output image',''));const b=builds.find(b=>b.id===build.value);for(const name of Object.keys(b?.artifacts||{})){patch.append(new Option(name,name));output.append(new Option(name,name));}};
  artifacts();patch.value=selection.patch_artifact||'';output.value=selection.output_artifact||'';build.addEventListener('change',artifacts);
  const checkedActions=el('div',undefined,'actions'),preview=el('div');
  const lock=value=>{for(const input of form.querySelectorAll('input,textarea,select,button'))input.disabled=value;};
  const isCurrent=()=>sequence===releasesSequence&&tab==='releases';
  const clean=()=>{if(dirty)throw Error('Save or discard your draft first.');};
  const run=async(actionName,params)=>{
    lock(true);
    try {const saved=await api(actionName,params,true);if(isCurrent()){dirty=false;await editRelease(saved);}notice('Candidate saved privately. No release was approved or published.');}
    finally {lock(false);if(dirty)for(const b of checkedActions.querySelectorAll('button'))b.disabled=true;}
  };
  form.addEventListener('input',()=>{dirty=true;for(const b of checkedActions.querySelectorAll('button'))b.disabled=true;});
  form.append(action('Save candidate draft',()=>run('release-put',{
    data:Object.fromEntries(['release_id','title','version','source_label','patch_filename','output_filename','compatibility','limitations'].map(k=>[k,inputs[k].value])),
    build_id:build.value,patch_artifact:patch.value,output_artifact:output.value,repeat_build_id:repeat.value,
    private_notes:inputs.private_notes.value,expected:item?.revision||0,...(item?{key:item.id}:{})
  }),true));
  if(item)checkedActions.append(action('Validate saved candidate',()=>{clean();return run('release-validate',{key:item.id,expected:item.revision});}));
  form.append(checkedActions,preview,el('p','Checksums and successful patch reconstruction do not prove gameplay compatibility or distribution rights. Patch literals and metadata may contain protected material. Metadata review is not release or publication approval.','muted'),action('Cancel candidate edit',async()=>{if(canLeave()){dirty=false;await showReleases();}}));
  $('release-detail').replaceChildren(form);
  if(item?.validation) {
    try {
      const ctx=await api('release-preview',{key:item.id});if(!isCurrent())return;
      preview.append(el('h4','Exact manifest for review'),detail('Manifest content',ctx.manifest),el('p',`Patch reconstruction: passed. Repeat build: ${ctx.manifest.checks.repeat_build}. Runtime and rights are not assessed.`,'meta'));
      if(!ctx.reviewed)checkedActions.append(action('Mark metadata reviewed',()=>{clean();return run('release-review',{key:item.id,expected:item.revision,validation_token:ctx.token});}));
      else checkedActions.append(action('Export private release manifest',async()=>{
        clean();lock(true);
        try {const result=await api('release-export',{key:item.id,expected:item.revision,validation_token:ctx.token},true);notice(`Manifest saved privately: ${result.path}. SHA-256: ${result.sha256}. No patch or ROM was copied or published.`);}
        finally {lock(false);if(dirty)for(const b of checkedActions.querySelectorAll('button'))b.disabled=true;}
      },true));
      if(dirty)for(const b of checkedActions.querySelectorAll('button'))b.disabled=true;
    } catch(error) {if(isCurrent())preview.append(el('p','Current files could not be verified. Validate again after resolving the source or artifact problem. '+error.message,'changed'));}
  }
}
let runtimeSequence=0, runtimeOffset=0, runtimeRead=null;
const runtimeURLs=new Set(), runtimeSelected=new Map();
function clearRuntimeImages(){for(const url of runtimeURLs)URL.revokeObjectURL(url);runtimeURLs.clear();}
function runtimeImageURL(capture){return '/api/runtime-review-image?'+new URLSearchParams({evidence_id:capture.evidence_id,sha256:capture.sha256});}
async function runtimeImage(capture,host,sequence,label){
  const image=el('img');image.alt=label;image.loading='lazy';image.className='runtime-thumbnail';host.append(image);
  try{
    const response=await fetch(runtimeImageURL(capture),{headers:projectHeaders(),cache:'no-store'});
    if(!response.ok)throw Error('Capture unavailable');
    const bytes=await response.blob();if(sequence!==runtimeSequence||tab!=='runtime')return;
    const url=URL.createObjectURL(bytes);runtimeURLs.add(url);image.src=url;
    const original=el('a','Open original capture');original.href=url;original.target='_blank';original.rel='noopener';original.setAttribute('aria-label','Open original capture: '+label);host.append(original);
  }catch{if(sequence===runtimeSequence)host.append(el('p','Original capture unavailable or changed.','changed'));}
}
function runtimeLabel(value){return value.replaceAll('_',' ');}
function runtimeSummary(data,progress){
  const host=$('runtime-summary');host.replaceChildren();
  const catalog=el('article',undefined,'card');catalog.append(el('h3','Catalog translations'),
    el('p',`${progress.translated_records} of ${progress.total_records} known records translated`),
    el('p','Translation progress describes the known catalog. It does not establish renderer or gameplay coverage.','muted'));
  const editorial=el('article',undefined,'card');editorial.append(el('h3','Editorial review'),
    el('p','No aggregate editorial review rate is supplied by this runtime report.'),
    action('Open existing verification views',()=>showTab('builds')));
  host.append(catalog,editorial);
  for(const group of data.groups){
    const panel=el('article',undefined,'card');panel.append(el('h3',group.build_id),
      el('p',group.scope.description),el('p','Historical runtime evidence for this tested build. Current catalog contexts remain separate.','muted'),el('p','Extraction completeness: '+runtimeLabel(group.scope.extraction_completeness),'meta'));
    for(const section of group.sections){
      const title=section.scope_kind==='normal_gameplay'?'Ordinary gameplay':section.method==='synthetic'?'Synthetic renderer checks':'Actual-renderer evidence';
      panel.append(el('h4',title),el('p',`${section.counts.passed} passed of ${section.denominator} declared cases · ${runtimeLabel(section.method)}`),
        detail('All dispositions and declared denominator',section));
    }
    panel.append(detail('Exact build, configuration and scope',{binding:group.binding,scope:group.scope,runs:group.runs}),
      detail('Current and historical catalog contexts',{historical:group.historical_catalog,current:group.current_catalog}),
      detail('Unresolved scope (bounded preview)',group.gap_candidates));host.append(panel);
  }
  host.append(el('p','No whole-game verified percentage or record verification award is supplied.','muted'));
}
function runtimeComparison(){
  const host=$('runtime-comparison');host.replaceChildren();
  if(runtimeSelected.size!==2){host.append(el('p','Select two cases to compare their recorded setups and original captures.'));return;}
  const [left,right]=[...runtimeSelected.values()];
  const differences=Object.keys(left.comparison_axes).filter(key=>JSON.stringify(left.comparison_axes[key])!==JSON.stringify(right.comparison_axes[key]));
  const bindingNames={configuration_sha256:'configuration',scenario_sha256:'scenario',artifacts:'build artifacts',snapshot:'snapshot',records:'tested record revisions',expectation_sha256:'expectations'};
  const bindingDifferences=Object.keys(left.comparison_axes.binding).filter(key=>JSON.stringify(left.comparison_axes.binding[key])!==JSON.stringify(right.comparison_axes.binding[key])).map(key=>bindingNames[key]||runtimeLabel(key));
  if(!left.comparison_axes.starting_states.length||!right.comparison_axes.starting_states.length)differences.push('unknown starting state');
  host.append(el('h3','Selected comparison'),el('p',`${left.case_id} / ${right.case_id}`),
    el('p',differences.length?'Recorded differences: '+differences.map(runtimeLabel).join(', '):'The recorded setup fields match.'),
    el('p','Still captures do not establish animation timing or interchangeable starting states.','muted'));
  if(bindingDifferences.length)host.append(el('p','Binding differences: '+bindingDifferences.join(', ')));
  const pair=el('div',undefined,'runtime-pair');
  for(const item of [left,right]){const panel=el('div');panel.append(el('h4',item.case_id),el('p',`${runtimeLabel(item.status)} · ${runtimeLabel(item.method)} · ${runtimeLabel(item.purpose)}`));
    const capture=item.captures.at(-1);if(capture)runtimeImage(capture,panel,runtimeSequence,item.case_id);else panel.append(el('p','No capture for this declared case.'));pair.append(panel);}
  host.append(pair,detail('Exact comparison fields',{left:left.comparison_axes,right:right.comparison_axes}));
}
async function runtimeIssue(item){
  const references=[`Runtime group: ${item.group_id}`,`Case: ${item.case_id} / ${item.case_sha256}`,
    `Tested build: ${item.build_id}`,`Tested translation revisions: ${JSON.stringify(item.record_revisions)}`,
    ...item.observations.map(o=>`Observation: ${o.observation_id} / run ${o.run_id}`),
    ...item.captures.map(c=>`Capture: ${c.evidence_id} / SHA-256 ${c.sha256} / frame ${c.frame}`),
    ...item.findings.map(f=>`Finding: ${f.finding_id} / ${f.status}`)];
  if(!await showTab('issues'))return;
  await editIssue(null,Object.keys(item.record_revisions),{title:'Runtime review: '+item.case_id,
    description:`${runtimeLabel(item.status)} in the tested ${runtimeLabel(item.purpose)} scope. ${item.reason}\nCurrent saved revisions: ${JSON.stringify(item.current_revisions)}. Historical evidence is retained; inspect current wording before adding a structured assessment.`,
    category:'runtime',build_id:item.build_id,scene:item.scene_ids.join(', '),references});
  dirty=true;
  notice('Issue draft prepared with tested build, revisions and evidence. Nothing has been saved.');
}
async function showRuntime(reset=false){
  if(reset){runtimeOffset=0;runtimeGapOffset=0;}
  syncFilterUI();
  const sequence=++runtimeSequence;clearRuntimeImages();
  for(const id of ['runtime-summary','runtime-comparison','runtime-history','runtime-sheets'])$(id).replaceChildren();
  $('runtime-previous').disabled=true;$('runtime-next').disabled=true;
  const filters={offset:runtimeOffset,limit:Number($('runtime-limit').value)};
  for(const [key,id] of Object.entries({group_id:'runtime-group',status:'runtime-status',method:'runtime-method',purpose:'runtime-purpose'}))if($(id).value)filters[key]=$(id).value;
  $('runtime-results').replaceChildren(el('p','Loading declared cases…'));$('runtime-page').textContent='Loading…';
  try{
    const [data,progress]=await Promise.all([api('runtime-review',filters),api('progress')]);
    if(sequence!==runtimeSequence||tab!=='runtime'||data.project_key!==projectKey)return;
    if(data.available===false){runtimeSelected.clear();runtimeRead=null;$('runtime-results').replaceChildren(el('p',data.reason));$('runtime-page').textContent='No configured runtime review';return;}
    if(runtimeRead&&runtimeRead!==data.catalog_read_sha256){runtimeSelected.clear();notice('The catalog changed. Runtime selections were cleared; historical evidence stays intact.');}
    runtimeRead=data.catalog_read_sha256;
    const selector=$('runtime-group'),current=selector.value;selector.replaceChildren(new Option('All binding groups',''));
    for(const group of data.groups)selector.append(new Option(group.build_id+' · '+group.group_id.slice(0,10),group.group_id));selector.value=current;syncFilterUI();
    runtimeSummary(data,progress);
    $('runtime-page').textContent=data.total?`${data.offset+1}–${Math.min(data.offset+data.limit,data.total)} of ${data.total} declared case views`:'No cases match these filters.';
    $('runtime-previous').disabled=data.offset===0;$('runtime-next').disabled=data.offset+data.limit>=data.total;
    const host=$('runtime-results');host.replaceChildren();
    for(const item of data.items){
      const card=el('article',undefined,'card runtime-case');card.append(el('h3',item.case_id),
        el('p',`${item.build_id} · evidence group ${item.group_id.slice(0,10)} · ${item.scene_ids.join(', ')||'Scene not recorded'} · ${item.message_id===null?'Message not specified':'message '+item.message_id} · ${item.page===null?'Page not specified':'page '+item.page}`,'meta'),
        el('p',`${runtimeLabel(item.status)} · ${runtimeLabel(item.purpose)} · ${runtimeLabel(item.method)}`),el('p',item.reason));
      if(item.freshness==='stale')card.append(el('p','Needs recheck: contributing saved revisions differ from this historical evidence.','changed'));
      const choose=el('label','Select for comparison '),check=el('input');check.type='checkbox';check.checked=runtimeSelected.has(item.review_id);check.setAttribute('aria-label',`Compare ${item.case_id} · ${item.group_id.slice(0,10)} · ${item.purpose} · ${item.method}`);choose.append(check);
      check.addEventListener('change',()=>{if(check.checked){if(runtimeSelected.size===2){check.checked=false;notice('Select at most two cases for comparison.',true);return;}runtimeSelected.set(item.review_id,item);}else runtimeSelected.delete(item.review_id);runtimeComparison();});card.append(choose);
      const capture=item.captures.at(-1);if(capture)runtimeImage(capture,card,sequence,item.case_id);else card.append(el('p','No original capture is available for this declared case.','muted'));
      card.append(detail('Tested revisions and current catalog',{tested:item.record_revisions,current:item.current_revisions,contexts:item.current_contexts}),
        detail('Original observations and findings',{observations:item.observations,findings:item.findings,superseded:item.superseded_observations}),
        detail('Other attempts — not counted in this purpose and method',item.unselected_attempts),
        action('Prepare issue for '+item.case_id,()=>runtimeIssue(item)));
      for(const key of Object.keys(item.record_revisions))card.append(action('Review saved wording: '+key,async()=>{if(await showTab('translation'))await selectRecord(key);}));
      host.append(card);
    }
    const history=$('runtime-history');history.replaceChildren(el('h3',`${data.historical_contexts.total} historical investigation contexts`),el('p',data.historical_contexts.limitation));
    for(const item of data.historical_contexts.items)history.append(detail(item.candidate_context_id||'Historical context',item));
    const sheets=$('runtime-sheets');sheets.replaceChildren();
    for(const sheet of data.contact_sheets){const panel=el('article',undefined,'card');panel.append(el('h3','Prepared private contact sheet'),detail('Derived-sheet provenance',sheet.sources||{}));runtimeImage(sheet.reference,panel,sequence,'Private derived contact sheet');sheets.append(panel);}
    runtimeComparison();
    if($('runtime-gaps-panel').open)await showRuntimeGaps();
  }catch(error){if(sequence===runtimeSequence&&tab==='runtime'){runtimeSelected.clear();runtimeRead=null;$('runtime-results').replaceChildren(el('p','Runtime review unavailable. '+error.message,'error'));$('runtime-page').textContent='Refresh after checking the selected project.';}}
}
for(const id of ['runtime-group','runtime-status','runtime-method','runtime-purpose','runtime-limit'])$(id).addEventListener('change',()=>showRuntime(true));
$('runtime-refresh').addEventListener('click',()=>showRuntime(true));
$('runtime-previous').addEventListener('click',()=>{runtimeOffset=Math.max(0,runtimeOffset-Number($('runtime-limit').value));showRuntime();});
$('runtime-next').addEventListener('click',()=>{runtimeOffset+=Number($('runtime-limit').value);showRuntime();});
filterChoices('record-status-choices','status',['','untranslated','translated','corrected']);
filterChoices('runtime-status-choices','runtime-status',['','failed','unknown','stale','passed']);

let runtimeGapOffset=0,runtimeGapKind='uncatalogued',runtimeGapSequence=0;
const runtimeGapLabels={uncatalogued:'No catalog link',unexercised:'Not captured',unmapped:'Unclear mapping',
  preserved_source:'Preserved source',graphics_text:'Graphics text',discovery:'New discoveries'};
for(const [kind,label] of Object.entries(runtimeGapLabels)){
  const button=action(label,async()=>{runtimeGapKind=kind;runtimeGapOffset=0;await showRuntimeGaps();});
  button.dataset.gapKind=kind;button.setAttribute('aria-pressed',String(kind===runtimeGapKind));
  $('runtime-gap-kinds').append(button);
}
async function showRuntimeGaps(){
  if(tab!=='runtime'||!$('runtime-gaps-panel').open)return;
  const sequence=++runtimeGapSequence,viewSequence=runtimeSequence,host=$('runtime-gaps');
  for(const button of $('runtime-gap-kinds').children)button.setAttribute('aria-pressed',String(button.dataset.gapKind===runtimeGapKind));
  host.replaceChildren(el('p','Loading investigation leads…'));
  $('runtime-gap-previous').disabled=true;$('runtime-gap-next').disabled=true;
  try{
    const params={kind:runtimeGapKind,offset:runtimeGapOffset,limit:10};
    if($('runtime-group').value)params.group_id=$('runtime-group').value;
    const data=await api('runtime-gaps',params);
    if(sequence!==runtimeGapSequence||viewSequence!==runtimeSequence||tab!=='runtime'||data.project_key!==projectKey)return;
    host.replaceChildren();
    if(data.available===false){$('runtime-gap-page').textContent=data.reason;return;}
    $('runtime-gap-page').textContent=data.total?`${data.offset+1}–${Math.min(data.offset+data.limit,data.total)} of ${data.total} investigation leads`:'No candidates in this category.';
    $('runtime-gap-previous').disabled=data.offset===0;
    $('runtime-gap-next').disabled=data.offset+data.limit>=data.total;
    for(const item of data.items){
      const card=el('article',undefined,'card runtime-gap');
      card.append(el('h3',item.label),el('p',item.build_id+' · evidence group '+item.group_id.slice(0,10),'meta'),el('p',item.reason));
      if(item.case_ids.length)card.append(el('p','Contexts: '+item.case_ids.join(', ')));
      const records=Object.keys(item.record_revisions);
      if(records.length)card.append(el('p','Records: '+records.join(', ')));
      if(item.freshness==='stale')card.append(el('p','Historical evidence: saved revisions have changed.','changed'));
      if(item.discovery)card.append(el('p',runtimeLabel(item.discovery.mode)+' · '+(item.discovery.admitted?'Reviewed run':'Run not admitted')),
        el('p',item.discovery.limitation,'muted'));
      card.append(detail('Evidence and tested revisions',{tested:item.record_revisions,current:item.current_revisions,
        provenance:item.provenance,discovery:item.discovery,report:item.report_id}));
      if(item.issue){
        card.append(el('p','Linked issue: '+item.issue.status),
          action('Open linked issue',async()=>{if(!await showTab('issues'))return;const issues=await api('issues');
            const current=issues.find(i=>i.id===item.issue.id);if(current)await editIssue(current);}));
      }else{
        card.append(action('Create investigation issue',async()=>{
          const saved=await api('runtime-gap-issue',{candidate_id:item.candidate_id,catalog_read_sha256:data.catalog_read_sha256},true);
          if(await showTab('issues'))await editIssue(saved.issue);
          notice(saved.created?'Investigation issue saved. Translations are unchanged.':'Existing issue opened; its history and resolution are unchanged.');
        },true));
      }
      host.append(card);
    }
  }catch(error){if(sequence===runtimeGapSequence&&viewSequence===runtimeSequence&&tab==='runtime'){
    host.replaceChildren(el('p',error.message,'error'));$('runtime-gap-page').textContent='Refresh candidates to retry.';
  }}
}
$('runtime-gaps-panel').addEventListener('toggle',()=>{if($('runtime-gaps-panel').open){runtimeGapOffset=0;showRuntimeGaps();}else runtimeGapSequence++;});
$('runtime-gap-refresh').addEventListener('click',()=>{runtimeGapOffset=0;showRuntimeGaps();});
$('runtime-gap-previous').addEventListener('click',()=>{runtimeGapOffset=Math.max(0,runtimeGapOffset-10);showRuntimeGaps();});
$('runtime-gap-next').addEventListener('click',()=>{runtimeGapOffset+=10;showRuntimeGaps();});
syncNavigation();syncFilterUI();
initProjects().then(initAssessments).then(()=>{poll();setInterval(poll,2000);}).catch(e=>notice(e.message,true));
