/* Invented projects only. Uses installed Playwright/browser; never installs. */
const {openTab,openMoreFilters}=require('./studio_navigation_browser_check.cjs');
const {spawn} = require('node:child_process');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),python=process.env.PYTHON||'python';
const evidence=process.env.RUNTIME_REVIEW_EVIDENCE||fs.mkdtempSync(path.join(os.tmpdir(),'patchquest-runtime-review-'));
fs.mkdirSync(evidence,{recursive:true});
const helper=String.raw`
import copy,hashlib,json,sys,threading
from pathlib import Path
root=Path(sys.argv[1]);sys.path[:0]=[str(root/'src'),str(root/'tests')]
import test_runtime_coverage as fixtures
from patchquest.runtime_contracts import contract_digest
from patchquest.runtime_review import ReviewProvider
from patchquest.studio import StudioServer
f=fixtures.CoverageTests();f.setUp()
other=fixtures.CoverageTests();other.setUp()
groups=[]
for label,actual,failed in [('positive',True,False),('negative',True,True),('unknown',True,False),('synthetic',False,False)]:
 g=f.fixture(actual=actual,suffix='-'+label,config={'invented_fixture':label},failed=failed)
 if label=='unknown':g['runs'][0]['findings']=[]
 if label=='positive':
  for i in range(45):
   c=copy.deepcopy(g['cases'][0]);c.update(case_id='invented-unexecuted-'+str(i),page=i+1,record_ids=[])
   if i==0:c.update(message_id=None,page=None)
   g['cases'].append(c)
 groups.append(g)
provider=ReviewProvider(f.store,groups,admit_run=f.proofs.get,artifacts=f,historical_contexts=[dict(candidate_context_id='invented-legacy',retained_legacy_execution_status='failed',not_a_new_executable_CaseSpec=True)])
server=StudioServer(f.store,0,progress_interval=86400,runtime_review_providers=[(f.store.manifest_path,provider)])
server.projects._add(other.store.manifest_path,'Other invented project',other.store)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
before=f.store.get('greeting')
print(json.dumps({'ready':True,'url':server.url,'project':server.projects._key(f.store.manifest_path),'other':server.projects._key(other.store.manifest_path),'before':before}),flush=True)
try:
 for line in sys.stdin:
  if line.strip()=='change':
   r=f.store.get('greeting');fields={k:v for k,v in r.items() if k not in ('revision','human_corrected','provenance')};fields['target']='A later invented protected correction.'
   f.store.put(fields,r['revision'],role='human');print(json.dumps({'changed':True}),flush=True)
  elif line.strip()=='check':print(json.dumps({'record':f.store.get('greeting'),'issues':f.store.issues(),'release':False}),flush=True)
  elif line.strip()=='stop':break
finally:
 server.shutdown();server.server_close();thread.join();f.doCleanups();other.doCleanups()
`;
const helperPath=path.join(evidence,'invented-server.py');fs.writeFileSync(helperPath,helper);
let server,browser,errorsLog='';const pending=[],lines=[];
function response(predicate){const found=lines.findIndex(predicate);if(found>=0)return Promise.resolve(lines.splice(found,1)[0]);return new Promise((resolve,reject)=>{const item={predicate,resolve,reject};item.timer=setTimeout(()=>reject(Error('Invented server response timed out')),30000);pending.push(item);});}
function accept(value){const index=pending.findIndex(x=>x.predicate(value));if(index>=0){const item=pending.splice(index,1)[0];clearTimeout(item.timer);item.resolve(value);}else lines.push(value);}
(async()=>{
  server=spawn(python,['-X','utf8','-B',helperPath,root],{windowsHide:true,stdio:['pipe','pipe','pipe']});
  let buffer='';server.stderr.on('data',d=>errorsLog+=d);
  server.stdout.on('data',d=>{buffer+=d;let newline;while((newline=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,newline).trim();buffer=buffer.slice(newline+1);if(line)try{accept(JSON.parse(line));}catch{errorsLog+=line+'\n';}}});
  const ready=await response(x=>x.ready);
  browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
  const page=await browser.newPage({viewport:{width:1380,height:1000}}),errors=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')writes.push(r.url());});
  await page.goto(ready.url);await openTab(page,'runtime');
  await page.locator('.runtime-case').first().waitFor();
  assert.equal(await page.locator('.runtime-case').count(),20);
  await page.getByRole('button',{name:'Next runtime page',exact:true}).click();await page.getByText(/21–40 of/).waitFor();
  assert.equal(await page.locator('.runtime-case').count(),20);
  await openMoreFilters(page,'runtime-status');await page.getByLabel('Disposition',{exact:true}).selectOption('failed');
  await page.locator('.runtime-case').filter({hasText:'failed · renderer'}).waitFor();assert.equal(await page.locator('.runtime-case').count(),1);
  await page.locator('.runtime-case img').waitFor();await page.waitForFunction(()=>document.querySelector('.runtime-case img')?.naturalWidth===1);
  assert.equal(await page.locator('.runtime-case img').evaluate(x=>x.naturalHeight),1);
  await page.locator('.runtime-case input[type=checkbox]').focus();await page.keyboard.press('Space');
  assert.match(await page.locator('#runtime-comparison').innerText(),/Select two/);
  await openMoreFilters(page,'runtime-status');await page.getByLabel('Disposition',{exact:true}).selectOption('unknown');await page.locator('.runtime-case').filter({hasText:'unknown · renderer'}).waitFor();
  await page.locator('.runtime-case input[type=checkbox]').check();await page.getByRole('heading',{name:'Selected comparison',exact:true}).waitFor();
  assert.match(await page.locator('#runtime-comparison').innerText(),/Recorded differences|unknown starting state/);
  assert.match(await page.locator('#runtime-comparison').innerText(),/animation timing/);
  await page.getByText('Separate coverage views and unresolved scope',{exact:true}).click();
  for(const name of ['Catalog translations','Editorial review'])await page.getByRole('heading',{name,exact:true}).waitFor();
  assert.match(await page.locator('#runtime-summary').innerText(),/Actual-renderer evidence/);
  assert.match(await page.locator('#runtime-summary').innerText(),/Ordinary gameplay/);
  assert.match(await page.locator('#runtime-summary').innerText(),/No whole-game/);
  await page.screenshot({path:path.join(evidence,'runtime-desktop.png'),fullPage:true});
  await page.getByRole('button',{name:/Prepare issue for/}).click();
  await page.getByText('Issue draft prepared with tested build, revisions and evidence. Nothing has been saved.',{exact:true}).waitFor();
  assert.equal(await page.getByLabel('Build version',{exact:true}).inputValue(),'invented-build');
  const references=page.getByLabel('Private screenshot / evidence references (one per line)',{exact:true});
  assert.match(await references.inputValue(),/Tested translation revisions/);assert.match(await references.inputValue(),/Capture: /);
  assert.deepEqual(writes,[]);
  page.once('dialog',dialog=>dialog.dismiss());await openTab(page,'runtime');
  assert.equal(await page.locator('#issues-view').isVisible(),true);
  page.once('dialog',dialog=>dialog.accept());await openTab(page,'runtime');
  await openMoreFilters(page,'runtime-status');await page.getByLabel('Disposition',{exact:true}).selectOption('stale');
  server.stdin.write('change\n');await response(x=>x.changed);
  await page.getByRole('button',{name:'Refresh runtime review',exact:true}).click();
  await page.getByText('Needs recheck: contributing saved revisions differ from this historical evidence.').first().waitFor();
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(evidence,'runtime-mobile.png'),fullPage:true});
  const links=await page.locator('#runtime-view a').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('href')));
  assert(links.every(x=>x.startsWith('blob:')));
  await page.route('**/api/runtime-review?**',route=>route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'Invented stale catalog refusal'})}));
  await page.getByRole('button',{name:'Refresh runtime review',exact:true}).click();
  await page.getByText(/Runtime review unavailable/).waitFor();
  assert.equal(await page.locator('#runtime-summary').innerText(),'');assert.equal(await page.locator('#runtime-comparison').innerText(),'');
  await page.unroute('**/api/runtime-review?**');
  await page.getByLabel('Translation project',{exact:true}).selectOption(ready.other);
  await openTab(page,'runtime');
  await page.getByText('Runtime review is not configured for this project.',{exact:true}).waitFor();
  assert.equal(await page.locator('.runtime-case').count(),0);assert.equal(await page.locator('#runtime-view img').count(),0);
  server.stdin.write('check\n');const state=await response(x=>x.record);
  assert.equal(state.record.target,'A later invented protected correction.');assert.equal(state.issues.length,0);
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  fs.writeFileSync(path.join(evidence,'result.json'),JSON.stringify({passed:true,checks:['bounded pagination','failure and uncertainty','separate denominators/methods/purposes','keyboard comparison','original PNG dimensions','issue draft retains tested revisions','unsaved draft navigation guard','current stale labels','failed refresh clears prior presentation','mobile layout','project isolation','no browser writes or verification awards'],errors,writes},null,2));
  console.log(JSON.stringify({passed:true,evidence}));
  fs.writeFileSync(path.join(evidence,'server.log'),errorsLog);
})().catch(async error=>{fs.writeFileSync(path.join(evidence,'failure.txt'),String(error.stack||error));fs.writeFileSync(path.join(evidence,'server.log'),errorsLog);const page=browser?.contexts()[0]?.pages()[0];if(page)await page.screenshot({path:path.join(evidence,'failure.png')}).catch(()=>{});console.error(error);process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();if(server){server.stdin.write('stop\n');server.stdin.end();}
});
