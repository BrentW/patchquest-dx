/* Invented projects only. No installs or access to the shared Studio. */
const {openTab}=require('./studio_navigation_browser_check.cjs');
const {spawn}=require('node:child_process'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),python=process.env.PYTHON||'python';
const evidence=process.env.RUNTIME_GAPS_EVIDENCE||fs.mkdtempSync(path.join(os.tmpdir(),'patchquest-gaps-'));
fs.mkdirSync(evidence,{recursive:true});
const helper=String.raw`
import copy,json,sys,threading
from pathlib import Path
root=Path(sys.argv[1]);sys.path[:0]=[str(root/'src'),str(root/'tests')]
import test_runtime_coverage as fixtures
from patchquest.runtime_review import ReviewProvider
from patchquest.studio import StudioServer
f=fixtures.CoverageTests();f.setUp()
other=fixtures.CoverageTests();other.setUp()
g=f.fixture()
for i in range(12):
 c=copy.deepcopy(g['cases'][0]);c.update(case_id='invented-uncatalogued-'+str(i),record_ids=[],page=i+1)
 g['cases'].append(c)
provider=ReviewProvider(f.store,[g],admit_run=f.proofs.get,artifacts=f)
server=StudioServer(f.store,0,progress_interval=86400,runtime_review_providers=[(f.store.manifest_path,provider)])
server.projects._add(other.store.manifest_path,'Other invented project',other.store)
t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
before=f.store.get('unseen');history=f.store.history('unseen')
print(json.dumps(dict(ready=True,url=server.url,other=server.projects._key(other.store.manifest_path))),flush=True)
try:
 for line in sys.stdin:
  if line.strip()=='check':
   print(json.dumps(dict(checked=True,records_unchanged=f.store.get('unseen')==before,
    history_unchanged=f.store.history('unseen')==history,issues=f.store.issues(),other_issues=other.store.issues())),flush=True)
  elif line.strip()=='stop':break
finally:
 server.shutdown();server.server_close();t.join();f.doCleanups();other.doCleanups()
`;
const helperPath=path.join(evidence,'invented-server.py');fs.writeFileSync(helperPath,helper);
let server,browser,errorsLog='';const pending=[],lines=[];
function response(predicate){
 const index=lines.findIndex(predicate);if(index>=0)return Promise.resolve(lines.splice(index,1)[0]);
 return new Promise((resolve,reject)=>{const item={predicate,resolve,reject};item.timer=setTimeout(()=>reject(Error('Fixture server timeout')),30000);pending.push(item);});
}
function accept(value){
 const index=pending.findIndex(x=>x.predicate(value));
 if(index>=0){const item=pending.splice(index,1)[0];clearTimeout(item.timer);item.resolve(value);}else lines.push(value);
}
(async()=>{
 server=spawn(python,['-X','utf8','-B',helperPath,root],{windowsHide:true,stdio:['pipe','pipe','pipe']});
 let buffer='';server.stderr.on('data',d=>errorsLog+=d);
 server.stdout.on('data',d=>{buffer+=d;let newline;while((newline=buffer.indexOf('\n'))>=0){
   const line=buffer.slice(0,newline).trim();buffer=buffer.slice(newline+1);
   if(line)try{accept(JSON.parse(line));}catch{errorsLog+=line+'\n';}
 }});
 const ready=await response(x=>x.ready);
 browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],writes=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')writes.push(r.url());});
 await page.goto(ready.url);await openTab(page,'runtime');
 await page.locator('.runtime-case').first().waitFor();
 await page.getByText('Text coverage & discovery',{exact:true}).click();
 await page.locator('.runtime-gap').first().waitFor();
 assert.equal(await page.locator('.runtime-gap').count(),10);
 assert.match(await page.locator('.runtime-gap').first().innerText(),/Displayed text is not established/);
 assert.match(await page.locator('#runtime-gap-page').innerText(),/of 12/);
 assert.deepEqual(writes,[]);
 await page.getByRole('button',{name:'Next candidates',exact:true}).click();
 await page.waitForFunction(()=>document.querySelectorAll('.runtime-gap').length===2);
 await page.getByRole('button',{name:'Previous candidates',exact:true}).click();
 await page.waitForFunction(()=>document.querySelectorAll('.runtime-gap').length===10);
 await page.getByRole('button',{name:'Not captured',exact:true}).focus();await page.keyboard.press('Enter');
 await page.waitForFunction(()=>document.querySelectorAll('.runtime-gap').length===1);
 assert.match(await page.locator('.runtime-gap').innerText(),/unseen/);
 await page.screenshot({path:path.join(evidence,'gaps-desktop.png')});
 await page.getByRole('button',{name:'Create investigation issue',exact:true}).click();
 await page.getByText('Investigation issue saved. Translations are unchanged.',{exact:true}).waitFor();
 assert.equal(await page.locator('#issues-view').isVisible(),true);
 assert.match(await page.locator('#issue-detail').innerText(),/Save issue/);
 await openTab(page,'runtime');
 await page.getByRole('button',{name:'Open linked issue',exact:true}).waitFor();
 await page.getByRole('button',{name:'Open linked issue',exact:true}).click();
 assert.equal(await page.locator('#issues-view').isVisible(),true);
 assert.equal(writes.length,1);assert.match(writes[0],/runtime-gap-issue$/);
 await openTab(page,'runtime');
 await page.getByRole('button',{name:'New discoveries',exact:true}).click();
 await page.getByText('No candidates in this category.',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Not captured',exact:true}).click();
 await page.getByRole('button',{name:'Open linked issue',exact:true}).waitFor();
 await page.setViewportSize({width:390,height:900});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
 await page.locator('#runtime-gaps-panel').scrollIntoViewIfNeeded();
 await page.screenshot({path:path.join(evidence,'gaps-mobile.png')});
 await page.selectOption('#project-picker',ready.other);
 await page.waitForFunction(()=>document.querySelector('#project-picker')?.disabled===false);
 await openTab(page,'runtime');
 await page.getByText('Text coverage & discovery',{exact:true}).click();
 await page.getByText('Text coverage and discovery is not configured for this project.',{exact:true}).waitFor();
 server.stdin.write('check\n');const state=await response(x=>x.checked);
 assert.equal(state.records_unchanged,true);assert.equal(state.history_unchanged,true);
 assert.equal(state.issues.length,1);assert.deepEqual(state.other_issues,[]);
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(evidence,'result.json'),JSON.stringify({passed:true,checks:12,writes:writes.length,
   protected_records_unchanged:true,protected_history_unchanged:true,other_project_unchanged:true,errors},null,2));
 console.log(JSON.stringify({passed:true,checks:12}));
})().catch(e=>{fs.writeFileSync(path.join(evidence,'failure.txt'),String(e.stack));console.error(e);process.exitCode=1;})
.finally(async()=>{
 if(browser)await browser.close();
 if(server){server.stdin.write('stop\n');await new Promise(resolve=>{if(server.exitCode!==null)return resolve();server.once('exit',resolve);});}
 fs.writeFileSync(path.join(evidence,'server.log'),errorsLog);
});
