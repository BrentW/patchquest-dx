/* Optional browser regression; use already-installed Playwright + browser only.
   No package download, real project, ROM, credential or provider is required. */
const {openTab,openMoreFilters}=require('./studio_navigation_browser_check.cjs');
const {spawn, spawnSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname,'..');
const python = process.env.PYTHON || 'python';
const temp = fs.mkdtempSync(path.join(os.tmpdir(),'patchquest-studio-'));
const workspace = path.join(temp,'invented-project');
const manifest = path.join(workspace,'project.json');
// Explicit synthetic composition root: no ROM, private plugin or game adapter.
const launcher=path.join(temp,'synthetic-worker.py');
fs.writeFileSync(launcher,`import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1])/'src'))
from patchquest.state import Store
from patchquest.jobs import BuildWorker
from patchquest.studio import serve
store=Store(sys.argv[2])
def pipeline(job, progress):
    snapshot=json.loads(Path(store.export_snapshot(job['snapshot'])).read_text(encoding='utf8'))
    progress('Checking invented snapshot')
    time.sleep(3)
    greeting=next(r['target'] for r in snapshot['records'] if r['id']=='greeting')
    if greeting=='Synthetic build failure': raise ValueError('Invented capacity failure')
    return {'status':'validated','approval':{'approved':False},'snapshot':job['snapshot'],'synthetic_greeting':greeting}
worker=BuildWorker(store,pipeline,'Synthetic test worker').start()
try: serve(sys.argv[2],0)
finally: worker.close()
`);
let server, browser, activePage;
function cli(action,params={}) {
  const r=spawnSync(python,['-X','utf8','-B',path.join(root,'tools/patchquest.py'),'state',manifest,action,'--input','-'],{input:JSON.stringify(params),encoding:'utf8',windowsHide:true});
  assert.equal(r.status,0,r.stderr);return JSON.parse(r.stdout);
}
async function start(withWorker=true){
  const args=withWorker?['-X','utf8','-B',launcher,root,manifest]:['-X','utf8','-B',path.join(root,'tools/patchquest.py'),'--platform',temp,'studio',manifest,'--port','0'];
  server=spawn(python,args,{windowsHide:true,stdio:['ignore','pipe','pipe']});
  server.stderr.on('data',data=>process.stderr.write(data));
  return new Promise((resolve,reject)=>{let output='';const timeout=setTimeout(()=>reject(new Error('Studio startup timed out')),15000);server.stdout.on('data',data=>{output+=data;const match=output.match(/http:\/\/127\.0\.0\.1:\d+\/#\S+/);if(match){clearTimeout(timeout);resolve(match[0]);}});server.on('exit',code=>{clearTimeout(timeout);reject(new Error('Studio exited: '+code));});});
}
(async()=>{
  const demo=spawnSync(python,['-B',path.join(root,'examples/studio-demo.py'),'--workspace',workspace],{encoding:'utf8',windowsHide:true});assert.equal(demo.status,0,demo.stderr);
  const url=await start();
  browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
  const page=await browser.newPage({viewport:{width:1400,height:1000}, timezoneId:'America/Los_Angeles', locale:'en-GB'});
  activePage=page;
  page.on('requestfailed',request=>console.error('Browser request failed:',new URL(request.url()).pathname,request.failure()));
  page.on('console',message=>{if(message.type()==='error')console.error('Browser console:',message.text());});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await openTab(page,'translation');await page.getByRole('button',{name:'greeting',exact:true}).click();
  await page.locator('#query').fill('greeting');
  await page.waitForFunction(()=>document.getElementById('result-count').textContent==='1–1 of 1');
  const downloadEvent=page.waitForEvent('download');
  await page.getByRole('button',{name:'Export filtered CSV',exact:true}).click();
  const download=await downloadEvent, csvPath=path.join(temp,'filtered.csv');await download.saveAs(csvPath);
  const exported=fs.readFileSync(csvPath,'utf8');assert.match(exported,/project_id,id,revision,source,target/);assert.match(exported,/greeting/);assert.ok(!exported.includes('term-lantern'));
  const edited=exported.replace(',Hello.,',',Bulk CSV correction,');assert.notEqual(edited,exported);
  await page.locator('#csv-file').setInputFiles({name:'edited.csv',mimeType:'text/csv',buffer:Buffer.from(edited)});
  await page.getByText('Imported 1 corrections; 0 unchanged.',{exact:false}).waitFor();
  assert.equal(cli('get',{key:'greeting'}).target,'Bulk CSV correction');
  await page.locator('#csv-file').setInputFiles({name:'stale.csv',mimeType:'text/csv',buffer:Buffer.from(edited)});
  await page.getByText('CSV record changed: greeting',{exact:true}).waitFor();
  await page.locator('#query').fill('');
  await openTab(page,'translation');await page.getByRole('button',{name:'greeting',exact:true}).click();
  // Editing English must not normalize an untouched source's stored CRLF bytes.
  const beforeLineEndings=cli('get',{key:'greeting'});
  const crlfData={...beforeLineEndings,source:beforeLineEndings.source+'\r\n'};delete crlfData.revision;delete crlfData.human_corrected;delete crlfData.provenance;
  cli('put',{data:crlfData,expected:beforeLineEndings.revision,role:'human'});
  await page.getByRole('button',{name:'Reload record',exact:true}).click();
  await page.waitForFunction(text=>document.getElementById('japanese-source')?.value===text,beforeLineEndings.source+'\n');
  await page.locator('#english').fill('English-only edit with untouched source');
  await page.getByRole('button',{name:'Save correction',exact:true}).click();
  await page.getByText('Correction saved. Future agents cannot silently replace it.').waitFor();
  assert.equal(cli('get',{key:'greeting'}).source,crlfData.source);
  cli('restore',{key:'greeting',revision:beforeLineEndings.revision,expected:cli('get',{key:'greeting'}).revision});
  await page.getByRole('button',{name:'Reload record',exact:true}).click();
  await page.waitForFunction(text=>document.getElementById('japanese-source')?.value===text,beforeLineEndings.source);
  // Source transcription corrections use the same versioned, protected store.
  const beforeSource=cli('get',{key:'greeting'}), correctedSource='こんにちは。\nあかりを確認しました。 <unmapped:01>';
  await page.getByLabel('Japanese / source',{exact:true}).fill(correctedSource);
  page.once('dialog',d=>d.dismiss());await page.getByRole('button',{name:'Reload record',exact:true}).click();
  assert.equal(await page.locator('#japanese-source').inputValue(),correctedSource);
  await page.getByRole('button',{name:'Save correction',exact:true}).click();
  await page.getByText('Correction saved. Future agents cannot silently replace it.').waitFor();
  let sourceRecord=cli('get',{key:'greeting'});assert.equal(sourceRecord.source,correctedSource);assert.equal(sourceRecord.target,beforeSource.target);
  for(const field of ['controls','source_ref','build_binding','context','decoded'])assert.deepEqual(sourceRecord[field],beforeSource[field]);
  await page.getByText('Revision history',{exact:true}).click();
  const sourceHistory=page.locator('#detail details').filter({has:page.locator('summary').filter({hasText:/^Revision history$/})});
  await sourceHistory.getByText(correctedSource,{exact:true}).waitFor();
  await sourceHistory.getByText(beforeSource.source,{exact:true}).first().waitFor();
  if(process.env.SOURCE_SCREENSHOT)await page.screenshot({path:process.env.SOURCE_SCREENSHOT,fullPage:true});
  // A new draft can even revert to the old source while the earlier save finishes.
  await page.route('**/api/edit',async route=>{const response=await route.fetch();await page.locator('#japanese-source').fill(correctedSource);await route.fulfill({response});});
  await page.locator('#japanese-source').fill('こんにちは。保存中の文です。');
  await page.getByRole('button',{name:'Save correction',exact:true}).click();
  await page.getByText('Earlier draft saved. Your newer unsaved changes are retained.').waitFor();
  assert.equal(await page.locator('#japanese-source').inputValue(),correctedSource);
  await page.unroute('**/api/edit');
  await page.getByRole('button',{name:'Save correction',exact:true}).click();
  await page.getByText('Correction saved. Future agents cannot silently replace it.').waitFor();
  assert.equal(cli('get',{key:'greeting'}).source,correctedSource);
  sourceRecord=cli('get',{key:'greeting'});
  const sourceData={...sourceRecord,source:'こんにちは。別の訂正です。'};delete sourceData.revision;delete sourceData.human_corrected;delete sourceData.provenance;
  await page.locator('#japanese-source').fill('手元の下書きです。');
  cli('put',{data:sourceData,expected:sourceRecord.revision,role:'human'});
  const staleSource=page.waitForResponse(r=>r.url().endsWith('/api/edit')&&r.status()===409);
  await page.getByRole('button',{name:'Save correction',exact:true}).click();await staleSource;
  assert.equal(await page.locator('#japanese-source').inputValue(),'手元の下書きです。');
  assert.equal(cli('get',{key:'greeting'}).source,sourceData.source);
  page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'Reload record',exact:true}).click();
  await page.waitForFunction(text=>document.getElementById('japanese-source')?.value===text,sourceData.source);
  await page.locator('#japanese-source').fill(beforeSource.source);await page.getByRole('button',{name:'Save correction',exact:true}).click();
  await page.getByText('Correction saved. Future agents cannot silently replace it.').waitFor();
  // Memory links always open the current item, including from historical matches.
  await page.getByRole('button',{name:'lantern',exact:true}).click();
  const memoryCards=page.locator('#detail details').filter({has:page.locator('summary').filter({hasText:/^Translation memory & related terminology$/})}).locator('.card');
  await memoryCards.filter({hasText:'term-lantern'}).first().getByRole('button',{name:'Edit current item',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('japanese-source')?.value==='あかり');
  await page.locator('#japanese-source').fill('あかりの灯');await page.getByRole('button',{name:'Save correction',exact:true}).click();
  await page.getByText('Correction saved. Future agents cannot silently replace it.').waitFor();
  await page.getByRole('button',{name:'lantern',exact:true}).click();
  await memoryCards.filter({hasText:'term-lantern'}).filter({hasText:'historical'}).getByRole('button',{name:'Edit current item',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('japanese-source')?.value==='あかりの灯');
  await page.locator('#japanese-source').fill('あかり');await page.getByRole('button',{name:'Save correction',exact:true}).click();
  await page.getByText('Correction saved. Future agents cannot silently replace it.').waitFor();
  await openTab(page,'translation');await page.getByRole('button',{name:'greeting',exact:true}).click();
  const times=await page.evaluate(()=>{
    const original={created:'2026-01-02T05:27:00Z',payload:{handoff:'Leave 21:27 in quoted text.',updated:'2026-01-02T05:27:00Z'},expires:1767331620};
    const before=JSON.stringify(original),shown=timestampDetails(original);
    return {night:formatTimestamp(original.created),midnight:formatTimestamp('2026-01-02T08:00:00Z'),noon:formatTimestamp('2026-01-02T20:00:00Z'),
      offset:formatTimestamp('2026-01-02T00:27:00-05:00'),summer:formatTimestamp('2026-07-02T04:27:00Z'),invalid:formatTimestamp('invalid'),empty:formatTimestamp(null),shown,unchanged:before===JSON.stringify(original)};
  });
  assert.match(times.night,/Jan 1, 2026.*9:27 PM.*PST/);assert.equal(times.offset,times.night);
  assert.match(times.midnight,/12:00 AM/);assert.match(times.noon,/12:00 PM/);assert.match(times.summer,/9:27 PM.*PDT/);
  assert.equal(times.invalid,'Unknown time');assert.equal(times.empty,'—');assert.equal(times.unchanged,true);
  assert.equal(times.shown.payload.handoff,'Leave 21:27 in quoted text.');assert.equal(times.shown.payload.updated,times.night);
  const tokyo=await browser.newPage({timezoneId:'Asia/Tokyo'});
  await tokyo.goto(url);await openTab(tokyo,'translation');await tokyo.getByRole('button',{name:'greeting',exact:true}).waitFor();
  assert.match(await tokyo.evaluate(()=>formatTimestamp('2026-01-02T05:27:00Z')),/Jan 2, 2026.*2:27 PM/);await tokyo.close();
  await page.locator('#english').fill('Welcome to the harbor.');await page.getByRole('button',{name:'Save correction',exact:true}).click();
  await page.getByText('Correction saved. Future agents cannot silently replace it.').waitFor();
  let current=cli('get',{key:'greeting'});assert.equal(current.target,'Welcome to the harbor.');assert.equal(current.human_corrected,true);
  const layoutSnapshot=cli('snapshot').sha256;
  cli('build-report',{expected:0,data:{id:'browser-layout',status:'validated',snapshot:layoutSnapshot,
    validation:{layout:{schema:1,counts:{paginated:1},records:{greeting:{revision:current.revision,
      variants:{'invented-panel':{decision:'paginated',pages:2,lines:2,width_px:72,limit_px:80}}}}}}}});
  await page.getByRole('button',{name:'Reload record',exact:true}).click();
  await page.getByText('invented-panel: paginated · 2 page(s) · 2 logical line(s) · 72/80px',{exact:true}).waitFor();
  await page.getByText(/browser-layout.*matches saved revision/).waitFor();
  await page.route('**/api/edit',async route=>{
    const response=await route.fetch();
    await page.locator('#english').fill('Newer draft typed during save');
    await route.fulfill({response});
  });
  await page.locator('#english').fill('Earlier draft');await page.getByRole('button',{name:'Save correction',exact:true}).click();
  await page.getByText('Earlier draft saved. Your newer unsaved changes are retained.').waitFor();
  assert.equal(await page.locator('#english').inputValue(),'Newer draft typed during save');
  assert.equal(cli('get',{key:'greeting'}).target,'Earlier draft');
  await page.unroute('**/api/edit');
  await page.getByRole('button',{name:'Save correction',exact:true}).click();
  await page.getByText('Correction saved. Future agents cannot silently replace it.').waitFor();
  current=cli('get',{key:'greeting'});assert.equal(current.target,'Newer draft typed during save');
  const data={...current,target:'Another agent alternative'};delete data.revision;delete data.human_corrected;delete data.provenance;
  assert.equal(cli('put',{data,expected:current.revision,role:'agent'})['outcome'],'proposed');
  await page.locator('#english').fill('Local draft stays here');
  cli('put',{data:{...data,target:'Other human correction'},expected:current.revision,role:'human'});
  const conflictResponse=page.waitForResponse(r=>r.url().endsWith('/api/edit')&&r.status()===409);
  await page.getByRole('button',{name:'Save correction',exact:true}).click();
  await conflictResponse;assert.equal(await page.locator('#english').inputValue(),'Local draft stays here');
  page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'Reload record',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('english')?.value==='Other human correction');
  await page.getByText(/browser-layout.*stale — rebuild after correction/).waitFor();
  await page.getByText('Revision history',{exact:true}).click();await page.getByRole('button',{name:'Restore this revision',exact:true}).last().click();
  await page.getByText('Restored as a new protected revision; history retained.').waitFor();assert.equal(cli('get',{key:'greeting'}).target,'Hello.');
  await page.locator('#query').fill('あかり');await page.waitForFunction(()=>document.getElementById('result-count').textContent==='1–1 of 1');
  await openTab(page,'glossary');await page.getByRole('button',{name:'term-lantern',exact:true}).click();
  await page.locator('#english').fill('signal lantern');await page.getByRole('button',{name:'Save correction',exact:true}).click();await page.getByText('Correction saved. Future agents cannot silently replace it.').waitFor();
  await openTab(page,'issues');await page.getByRole('button',{name:'Report an issue',exact:true}).click();
  await page.getByLabel('Title',{exact:true}).fill('Invented wording concern');await page.getByLabel('What happened / how to reproduce').fill('Synthetic test only.');await page.getByLabel('Related record IDs').fill('greeting');await page.getByRole('button',{name:'Save issue',exact:true}).click();await page.getByText('Issue saved with history.').waitFor();
  assert.equal(cli('issues').length,1);
  cli('activity',{message:'Browser can see this agent event',actor:'Synthetic agent',status:'working'});
  await openTab(page,'dashboard');await page.getByText(/Browser can see this agent event/).waitFor();
  await openTab(page,'builds');await page.getByRole('button',{name:'Freeze current build inputs',exact:true}).click();await page.getByText(/Frozen 5 records/).waitFor();
  const png=path.join(workspace,'invented-screen.png');await page.screenshot({path:png});cli('attach',{path:png,description:'Synthetic browser screenshot',record_ids:['greeting']});
  await page.locator('#screenshots img').waitFor();
  await page.getByRole('button',{name:'Build test ROM',exact:true}).click();
  await page.getByText('Checking invented snapshot',{exact:true}).waitFor();
  const queued=cli('jobs')[0], captured=cli('get',{key:'greeting'});
  const later={...captured,target:'Saved while build was running'};delete later.revision;delete later.human_corrected;delete later.provenance;
  cli('put',{data:later,expected:captured.revision,role:'human'});
  await page.getByText('Test ROM ready',{exact:true}).waitFor();
  let job=cli('jobs')[0];assert.equal(job.id,queued.id);assert.equal(job.payload.result.synthetic_greeting,captured.target);assert.equal(job.payload.result.approval.approved,false);
  const failed={...later,target:'Synthetic build failure'};cli('put',{data:failed,expected:captured.revision+1,role:'human'});
  await page.getByRole('button',{name:'Build test ROM',exact:true}).click();await page.getByText('Invented capacity failure',{exact:true}).waitFor();
  assert.equal(cli('jobs')[0].status,'failed');assert.equal(cli('get',{key:'greeting'}).target,failed.target);
  cli('put',{data:later,expected:captured.revision+2,role:'human'});
  await page.getByRole('button',{name:'Build test ROM',exact:true}).click();await page.waitForFunction(()=>document.querySelectorAll('#jobs h3')[0]?.textContent==='Test ROM ready');
  assert.equal(cli('jobs')[0].payload.result.synthetic_greeting,later.target);
  await openTab(page,'issues');await page.getByRole('button',{name:'Edit / history',exact:true}).click();
  await page.locator('#issue-detail').getByText('Upload a screenshot',{exact:true}).click();
  const screen=await page.screenshot();await page.locator('#issue-detail input[type=file]').setInputFiles({name:'invented.png',mimeType:'image/png',buffer:screen});
  await page.locator('#issue-detail').getByLabel('Screenshot description',{exact:true}).fill('Synthetic issue evidence');
  await page.locator('#issue-detail').getByLabel('Interface resource',{exact:true}).fill('invented-menu');
  await page.getByRole('button',{name:'Upload screenshot',exact:true}).click();await page.getByText('Screenshot saved privately with association history.').waitFor();
  await page.locator('#issue-detail .gallery img').waitFor();
  const attached=cli('attachments').find(x=>x.description==='Synthetic issue evidence');assert.equal(attached.association,'provisional');assert.deepEqual(attached.issue_ids,[cli('issues')[0].id]);
  await page.getByRole('button',{name:'Edit associations',exact:true}).click();
  const associations=page.locator('#issue-detail .gallery details[open]');
  await associations.locator('select').selectOption('confirmed');
  await associations.getByLabel('Screenshot scene',{exact:true}).fill('Verified invented scene');
  await page.getByRole('button',{name:'Save associations',exact:true}).click();
  await page.getByText(/Build unspecified · confirmed/).waitFor();
  assert.equal(cli('attachment-history',{digest:attached.digest}).length,2);
  await page.getByRole('button',{name:'Association history',exact:true}).click();await page.getByText('Screenshot association history',{exact:true}).waitFor();
  await page.locator('#issue-detail input[type=file]').setInputFiles({name:'bad.png',mimeType:'image/png',buffer:Buffer.from('<svg/>')});
  await page.getByRole('button',{name:'Upload screenshot',exact:true}).click();await page.waitForFunction(()=>document.getElementById('notice').classList.contains('error'));
  assert.equal(cli('attachments').length,2);
  // Failed upload input remains an unsaved screenshot draft.
  page.once('dialog',d=>d.dismiss());assert.equal(await openTab(page,'translation'),false);
  assert.equal(await page.locator('#issues-view').isVisible(),true);
  page.once('dialog',d=>d.accept());assert.equal(await openTab(page,'translation'),true);
  await page.getByRole('button',{name:'greeting',exact:true}).click();
  const xss=cli('get',{key:'greeting'});const payload={...xss,target:'<img src=x onerror=alert(1)>'};delete payload.revision;delete payload.human_corrected;delete payload.provenance;cli('put',{data:payload,expected:xss.revision,role:'human'});
  await page.getByRole('button',{name:'Reload record',exact:true}).click();await page.waitForFunction(()=>document.getElementById('english').value.startsWith('<img'));
  assert.equal(await page.locator('#detail img[src="x"]').count(),0);
  cli('work-create',{key:'browser-work',title:'Review invented harbor wording',record_ids:['greeting']});
  const agent=cli('agent-start',{provider:'synthetic-agent',label:'Browser coordination check'});
  const lease=cli('work-claim',{session:agent.session,key:'browser-work'});
  await openTab(page,'agents');
  await page.getByText('Browser coordination check',{exact:true}).waitFor();
  await page.getByText(/leased · browser-work/).waitFor();
  cli('work-renew',{session:agent.session,key:lease.id,fence:lease.fence,progress:'Reviewing protected human wording'});
  await page.getByText('Reviewing protected human wording',{exact:true}).waitFor();
  cli('work-finish',{session:agent.session,key:lease.id,fence:lease.fence,handoff:'Human correction retained; ready for follow-up'});
  await page.getByText('Human correction retained; ready for follow-up',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Work history',exact:true}).click();
  await page.getByText('Task history',{exact:true}).waitFor();
  cli('agent-close',{session:agent.session});
  await page.getByText(/closed · synthetic-agent/).waitFor();
  const runtimeRow=cli('get',{key:'greeting'}),runtimeSnapshot=cli('snapshot').sha256;
  cli('build-report',{expected:0,data:{id:'browser-runtime',status:'validated',snapshot:runtimeSnapshot,validation:{runtime:[{
    id:'invented-highlight',level:'synthetic',status:'passed',records:{greeting:runtimeRow.revision},snapshot:runtimeSnapshot,
    rom_sha256:'0'.repeat(64),scenario_sha256:'1'.repeat(64),configuration_sha256:'2'.repeat(64),human_accepted:false,
    captures:[{id:'selection',frame:12,digest:attached.digest}],assertions:[{label:'Invented highlight moved',passed:true}],emulator:{name:'Synthetic grid'}
  }]}}});
  await openTab(page,'builds');
  await page.getByText('invented-highlight · Synthetic orchestration test · passed',{exact:true}).waitFor();
  await page.getByText('Matches associated saved revisions · Human acceptance is separate.',{exact:true}).waitFor();
  await page.getByAltText('invented-highlight: selection, frame 12',{exact:true}).waitFor();
  const revised={...runtimeRow,context:{...runtimeRow.context,synthetic_runtime_note:'Revision changed after capture'}};
  delete revised.revision;delete revised.human_corrected;delete revised.provenance;
  cli('put',{data:revised,expected:runtimeRow.revision,role:'human'});
  await page.getByText('Stale — associated translations changed · Human acceptance is separate.',{exact:true}).waitFor();
  // New assets may be served by a process started before the read API existed.
  // Evidence must not break the established build/issue workflows in that case.
  await page.route('**/api/runtime-reports',route=>route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'Unknown action'})}));
  await openTab(page,'agents');
  await openTab(page,'builds');
  await page.getByText('Runtime evidence is unavailable in this server session. Existing build reports remain available.',{exact:true}).waitFor();
  await page.getByRole('heading',{name:'browser-runtime',exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Build test ROM',exact:true}).isEnabled(),true);
  await page.unroute('**/api/runtime-reports');
  await openTab(page,'agents');
  await openTab(page,'builds');
  await page.getByText('invented-highlight · Synthetic orchestration test · passed',{exact:true}).waitFor();
  if(process.env.STUDIO_SCREENSHOT){await page.screenshot({path:process.env.STUDIO_SCREENSHOT,fullPage:true});}
  // Non-graphic synthetic editorial evidence exercises the real browser/API.
  const assessmentBefore=cli('snapshot').sha256;
  await openTab(page,'issues');
  await page.getByRole('button',{name:'Report an issue',exact:true}).click();
  await page.getByLabel('Title',{exact:true}).fill('Synthetic content observation');
  await page.getByLabel('Related record IDs (comma separated)',{exact:true}).fill('greeting');
  await page.getByText('Structured assessment',{exact:true}).click();
  await page.getByLabel('Assessment type',{exact:true}).selectOption('content');
  await page.getByLabel('Assessment category',{exact:true}).selectOption('explicit_sexual');
  await page.getByLabel('What needs attention and why',{exact:true}).fill('Invented non-graphic classification fixture.');
  await page.getByLabel('Evidence references (one per line)',{exact:true}).fill('synthetic-observation:content');
  await page.getByRole('button',{name:'Review current inputs',exact:true}).click();
  await page.getByRole('button',{name:'Use these reviewed revisions',exact:true}).click();
  await page.getByRole('button',{name:'Save issue',exact:true}).click();
  await page.getByText('Issue saved with history.',{exact:true}).waitFor();
  assert.equal(cli('snapshot').sha256,assessmentBefore);
  let assessmentRecord=cli('get',{key:'greeting'}),packet=cli('assessment-context',{key:'greeting'});
  cli('issue-put',{expected:0,data:{id:'synthetic-context',title:'Synthetic missing context',status:'investigating',record_ids:['greeting'],assessment:{
    kind:'exception',code:'missing_context',severity:'medium',rationale:'Invented context evidence is incomplete.',references:['synthetic:context'],
    bindings:packet.records,narrative_sha256:packet.narrative_sha256,next_action:'Inspect the invented scene note.'}}});
  await openTab(page,'translation');
  await openMoreFilters(page,'content-filter');await page.locator('#content-filter').selectOption('explicit_sexual');
  await page.locator('#exception-filter').selectOption('missing_context');
  await page.locator('#severity-filter').selectOption('medium');
  await page.locator('#investigation-filter').selectOption('investigating');
  await page.getByText('1–1 of 1',{exact:true}).waitFor();
  await openTab(page,'translation');await page.getByRole('button',{name:'greeting',exact:true}).click();
  await page.locator('#detail').getByRole('heading',{name:'Explicit sexual content',exact:true}).waitFor();
  await page.locator('#detail').getByRole('heading',{name:'Missing scene context',exact:true}).waitFor();
  assert.equal(await page.locator('#records').getByText('corrected',{exact:true}).count(),1);
  const staleRecord={...assessmentRecord,context:{...assessmentRecord.context,assessment_fixture:'changed context'}};
  delete staleRecord.revision;delete staleRecord.human_corrected;delete staleRecord.provenance;
  cli('put',{data:staleRecord,expected:assessmentRecord.revision,role:'human'});
  await page.locator('#stale-filter').selectOption('stale');
  await page.locator('#records').getByText(/Missing scene context.*stale/).waitFor();
  await page.locator('#clear-assessment-filters').click();
  assert.equal(cli('get',{key:'greeting'}).target,assessmentRecord.target);
  assert.equal(cli('get',{key:'greeting'}).human_corrected,true);
  if(process.env.ASSESSMENT_SCREENSHOT){await page.screenshot({path:process.env.ASSESSMENT_SCREENSHOT,fullPage:true});}
  await page.setViewportSize({width:500,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);await page.close();await browser.close();browser=null;server.kill();server=null;
  const restarted=await start(false);assert.match(restarted,/^http:/);assert.equal(cli('get',{key:'greeting'}).target,payload.target);
  console.log(JSON.stringify({status:'passed',checks:['Japanese source correction and history','source draft retention, save races and stale conflicts','historical memory opens current item for correction','filtered CSV download, bulk correction upload and stale import rejection','local 12-hour timestamps, DST and cross-timezone display','timestamp metadata copy preserves stored values and handoff prose','edit','human precedence','cross-process conflict','draft retained','typing during save','restore','Japanese search','glossary correction','issue','live activity','snapshot','private image','browser build','immutable job input','failure and fresh retry','issue screenshot upload','association correction and history','invalid image rejection','XSS text','mobile width','agent queue and progress','handoff history','session closure','restart','layout decisions','stale layout revision','runtime provenance and synthetic label','runtime capture display','runtime revision staleness','older server preserves build view','structured content editor and revision capture','combined assessment filters','stale assessment indication','labels preserve protected corrections'],browser:'installed browser via Playwright'}));
})().catch(async e=>{console.error(e);if(activePage&&!activePage.isClosed()){console.error(await activePage.locator('#notice').textContent());console.error(await activePage.locator('#issue-detail').innerText());console.error(await activePage.locator('#english').inputValue().catch(()=>''));}process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)server.kill();/* Keep temporary synthetic artifacts for diagnosis; OS temp cleanup may remove them. */});
