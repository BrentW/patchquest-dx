/* Optional browser regression; use already-installed Playwright + browser only.
   No package download, real project, ROM, credential or provider is required. */
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
  const args=withWorker?['-X','utf8','-B',launcher,root,manifest]:['-X','utf8','-B',path.join(root,'tools/patchquest.py'),'studio',manifest,'--port','0'];
  server=spawn(python,args,{windowsHide:true,stdio:['ignore','pipe','pipe']});
  server.stderr.on('data',data=>process.stderr.write(data));
  return new Promise((resolve,reject)=>{let output='';const timeout=setTimeout(()=>reject(new Error('Studio startup timed out')),15000);server.stdout.on('data',data=>{output+=data;const match=output.match(/http:\/\/127\.0\.0\.1:\d+\/#\S+/);if(match){clearTimeout(timeout);resolve(match[0]);}});server.on('exit',code=>{clearTimeout(timeout);reject(new Error('Studio exited: '+code));});});
}
(async()=>{
  const demo=spawnSync(python,['-B',path.join(root,'examples/studio-demo.py'),'--workspace',workspace],{encoding:'utf8',windowsHide:true});assert.equal(demo.status,0,demo.stderr);
  const url=await start();
  browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
  const page=await browser.newPage({viewport:{width:1400,height:1000}});
  activePage=page;
  page.on('requestfailed',request=>console.error('Browser request failed:',new URL(request.url()).pathname,request.failure()));
  page.on('console',message=>{if(message.type()==='error')console.error('Browser console:',message.text());});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.getByRole('button',{name:'greeting',exact:true}).click();
  await page.locator('#english').fill('Welcome to the harbor.');await page.getByRole('button',{name:'Save correction',exact:true}).click();
  await page.getByText('Correction saved. Future agents cannot silently replace it.').waitFor();
  let current=cli('get',{key:'greeting'});assert.equal(current.target,'Welcome to the harbor.');assert.equal(current.human_corrected,true);
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
  await page.getByText('Revision history',{exact:true}).click();await page.getByRole('button',{name:'Restore this revision',exact:true}).last().click();
  await page.getByText('Restored as a new protected revision; history retained.').waitFor();assert.equal(cli('get',{key:'greeting'}).target,'Hello.');
  await page.locator('#query').fill('あかり');await page.waitForFunction(()=>document.getElementById('result-count').textContent==='1–1 of 1');
  await page.getByRole('button',{name:'Glossary',exact:true}).click();await page.getByRole('button',{name:'term-lantern',exact:true}).click();
  await page.locator('#english').fill('signal lantern');await page.getByRole('button',{name:'Save correction',exact:true}).click();await page.getByText('Correction saved. Future agents cannot silently replace it.').waitFor();
  await page.getByRole('button',{name:'Issues',exact:true}).click();await page.getByRole('button',{name:'Report an issue',exact:true}).click();
  await page.getByLabel('Title',{exact:true}).fill('Invented wording concern');await page.getByLabel('What happened / how to reproduce').fill('Synthetic test only.');await page.getByLabel('Related record IDs').fill('greeting');await page.getByRole('button',{name:'Save issue',exact:true}).click();await page.getByText('Issue saved with history.').waitFor();
  assert.equal(cli('issues').length,1);
  cli('activity',{message:'Browser can see this agent event',actor:'Synthetic agent',status:'working'});
  await page.getByText(/Browser can see this agent event/).waitFor();
  await page.getByRole('button',{name:'Builds & activity',exact:true}).click();await page.getByRole('button',{name:'Freeze current build inputs',exact:true}).click();await page.getByText(/Frozen 5 records/).waitFor();
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
  await page.getByRole('button',{name:'Issues',exact:true}).click();await page.getByRole('button',{name:'Edit / history',exact:true}).click();
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
  await page.getByRole('button',{name:'Translations',exact:true}).click();await page.getByRole('button',{name:'greeting',exact:true}).click();
  const xss=cli('get',{key:'greeting'});const payload={...xss,target:'<img src=x onerror=alert(1)>'};delete payload.revision;delete payload.human_corrected;delete payload.provenance;cli('put',{data:payload,expected:xss.revision,role:'human'});
  await page.getByRole('button',{name:'Reload record',exact:true}).click();await page.waitForFunction(()=>document.getElementById('english').value.startsWith('<img'));
  assert.equal(await page.locator('#detail img[src="x"]').count(),0);
  cli('work-create',{key:'browser-work',title:'Review invented harbor wording',record_ids:['greeting']});
  const agent=cli('agent-start',{provider:'synthetic-agent',label:'Browser coordination check'});
  const lease=cli('work-claim',{session:agent.session,key:'browser-work'});
  await page.getByRole('button',{name:'Agents & work',exact:true}).click();
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
  if(process.env.STUDIO_SCREENSHOT){await page.screenshot({path:process.env.STUDIO_SCREENSHOT,fullPage:true});}
  await page.setViewportSize({width:500,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);await page.close();await browser.close();browser=null;server.kill();server=null;
  const restarted=await start(false);assert.match(restarted,/^http:/);assert.equal(cli('get',{key:'greeting'}).target,payload.target);
  console.log(JSON.stringify({status:'passed',checks:['edit','human precedence','cross-process conflict','draft retained','typing during save','restore','Japanese search','glossary correction','issue','live activity','snapshot','private image','browser build','immutable job input','failure and fresh retry','issue screenshot upload','association correction and history','invalid image rejection','XSS text','mobile width','agent queue and progress','handoff history','session closure','restart'],browser:'installed browser via Playwright'}));
})().catch(async e=>{console.error(e);if(activePage&&!activePage.isClosed()){console.error(await activePage.locator('#notice').textContent());console.error(await activePage.locator('#issue-detail').innerText());console.error(await activePage.locator('#english').inputValue().catch(()=>''));}process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)server.kill();/* Keep temporary synthetic artifacts for diagnosis; OS temp cleanup may remove them. */});
