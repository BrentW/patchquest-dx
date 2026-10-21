/* Optional browser check. Invented frames only; never emulator verification. */
const {openTab,openMoreFilters}=require('./studio_navigation_browser_check.cjs');
const {spawn, spawnSync} = require('node:child_process');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root=path.resolve(__dirname,'..'),python=process.env.PYTHON||'python';
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'patchquest-captures-'));
const projectRoot=path.join(temp,'project'),manifest=path.join(projectRoot,'project.json');
function cli(action,params={}) {
  const r=spawnSync(python,['-X','utf8','-B',path.join(root,'tools/patchquest.py'),'state',manifest,action,'--input','-'],
    {input:JSON.stringify(params),encoding:'utf8',windowsHide:true});
  assert.equal(r.status,0,r.stderr);return JSON.parse(r.stdout);
}
let server,browser;
(async()=>{
  const demo=spawnSync(python,['-X','utf8','-B',path.join(root,'examples/studio-demo.py'),'--workspace',projectRoot],{encoding:'utf8',windowsHide:true});
  assert.equal(demo.status,0,demo.stderr);
  const original=cli('get',{key:'greeting'});
  const fields=Object.fromEntries(Object.entries(original).filter(([k])=>!['revision','human_corrected','provenance'].includes(k)));
  cli('put',{data:{...fields,target:'An invented protected greeting.'},expected:original.revision,role:'human'});
  const before=cli('get',{key:'greeting'}),snapshot=cli('snapshot').sha256;
  const seed=spawnSync(python,['-X','utf8','-B','-c',`
import sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'src'))
from patchquest.state import Store
from patchquest.runtime import Frame,run,register,sha
store=Store(sys.argv[2]);snapshot=store.snapshot()['sha256']
rom=store.context.output.write_new('invented.fixture',b'invented data, not a ROM')
store.build(dict(id='PRIVATE BUILD',snapshot=snapshot,status='validated',artifacts={'rom':str(rom)}),0)
class Synthetic:
 def describe(self):return dict(kind='synthetic',name='Invented color grid',sha256='1'*64,options={})
 def load(self,rom,work):pass
 def step(self,buttons):return Frame(256,144,bytes(v for y in range(144) for x in range(256) for v in ((40,96,144) if (x//32+y//24)%2 else (92,176,160))))
 def close(self):pass
scenario=dict(schema=1,id='grid',snapshot=snapshot,rom_sha256=sha(rom.read_bytes()),records={'greeting':store.get('greeting')['revision']},timeout_seconds=5,
 steps=[dict(frames=1,capture='grid',assertions=[dict(kind='color_count',label='Invented corner',rect=[0,0,1,1],color=[92,176,160],minimum=1)])])
run(store,'PRIVATE BUILD',scenario,Synthetic(),'synthetic-run');register(store,'synthetic-run')
`,root,manifest],{encoding:'utf8',windowsHide:true});
  assert.equal(seed.status,0,seed.stderr);
  server=spawn(python,['-X','utf8','-B',path.join(root,'tools/patchquest.py'),'--platform',temp,'studio',manifest,'--port','0'],{windowsHide:true,stdio:['ignore','pipe','pipe']});
  const url=await new Promise((resolve,reject)=>{
    let output='';const timer=setTimeout(()=>reject(Error('Synthetic startup timed out')),15000);
    server.stdout.on('data',data=>{output+=data;const m=output.match(/http:\/\/127\.0\.0\.1:\d+\/#\S+/);if(m){clearTimeout(timer);resolve(m[0]);}});
    server.on('exit',code=>{clearTimeout(timer);reject(Error('Synthetic server exited: '+code));});
  });
  browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
  const page=await browser.newPage({viewport:{width:1400,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));await page.goto(url);
  await openTab(page,'captures');
  await page.getByRole('button',{name:'Prepare screenshot',exact:true}).click();
  const image=page.locator('#capture-detail img');
  await image.waitFor();assert.equal(await image.evaluate(i=>i.complete&&i.naturalWidth===256),true);
  await page.getByLabel('Capture caption',{exact:true}).fill('Invented grid <img src=x onerror=alert(1)>');
  await page.getByLabel('Accessible image description',{exact:true}).fill('Alternating blue and green rectangles.');
  await page.getByLabel('Reviewed build label',{exact:true}).fill('Invented test build');
  await page.getByLabel('Capture date (leave blank if unknown)',{exact:true}).fill('2026-01-01');
  await page.getByLabel('Private capture notes (excluded)',{exact:true}).fill('PRIVATE NOTES SENTINEL');
  await page.getByLabel('Spoiler flag',{exact:true}).selectOption('none');
  await page.getByLabel('Registered capture reference',{exact:true}).selectOption({index:1});
  await page.getByText(/registered run · Run passed/).waitFor();
  assert.equal(await page.getByLabel('Capture provenance',{exact:true}).inputValue(),'synthetic');
  await page.getByRole('button',{name:'Save capture draft',exact:true}).click();
  await page.getByText('Draft · Spoilers: none',{exact:true}).waitFor();
  assert.equal(cli('screenshot-preview').items.length,0);
  const edit=()=>page.locator('#captures-list').getByRole('button',{name:'Edit / review capture',exact:true}).click();
  await edit();await page.getByRole('button',{name:'Mark capture reviewed',exact:true}).click();
  await page.getByText('Reviewed · not selected · Spoilers: none',{exact:true}).waitFor();
  await edit();await page.getByRole('button',{name:'Select capture for export',exact:true}).click();
  await page.getByText('Selected for export · Spoilers: none',{exact:true}).waitFor();
  assert.equal(await page.locator('#captures-list img').count(),0);
  const preview=cli('screenshot-preview');
  assert.equal(preview.items[0].capture.kind,'synthetic');assert.equal(preview.items[0].capture.frame,1);
  await page.getByRole('button',{name:'Export selected metadata',exact:true}).click();
  await page.locator('#notice').getByText(/Saved 1 screenshot metadata entries privately/).waitFor();
  const exported=cli('screenshot-history').filter(r=>r.kind==='screenshot-selection.exported').at(-1).payload;
  const bytes=fs.readFileSync(exported.path,'utf8');assert.deepEqual(JSON.parse(bytes),preview);
  assert.equal(bytes.includes('PRIVATE'),false);assert.equal(JSON.parse(bytes).images_included,false);
  await edit();await image.waitFor();await page.screenshot({path:path.join(temp,'captures-desktop.png'),fullPage:true});
  // Changed attachment associations invalidate review and block the complete export.
  const attachment=cli('attachments')[0];
  const metadata=Object.fromEntries(['description','record_ids','build_id','issue_ids','scene','resource','association'].map(k=>[k,attachment[k]]));
  cli('attachment-update',{digest:attachment.digest,expected:attachment.revision,data:{...metadata,association:'confirmed'}});
  await page.getByRole('button',{name:'Refresh screenshots',exact:true}).click();
  await page.getByRole('heading',{name:'Metadata export blocked',exact:true}).waitFor();
  await edit();assert.equal(await page.getByRole('button',{name:'Mark capture reviewed',exact:true}).isDisabled(),true);
  await page.getByRole('button',{name:'Remove from export',exact:true}).click();
  await page.getByRole('heading',{name:'Metadata export · 0 selected',exact:true}).waitFor();
  await edit();await page.getByRole('button',{name:'Save capture draft',exact:true}).click();
  await page.getByText('Draft · Spoilers: none',{exact:true}).waitFor();
  // A concurrent saved edit must not overwrite or discard the browser draft.
  await edit();await page.getByLabel('Capture caption',{exact:true}).fill('My retained caption.');
  const old=cli('screenshot-selection').items[0];
  cli('screenshot-put',{key:old.id,expected:old.revision,digest:old.source.digest,context_token:old.source.token,
    runtime_report:old.source.runtime_report,runtime_capture:old.source.runtime_capture,
    data:{...old.content,caption:'Another editor saved this.'},private_notes:old.private_notes});
  await page.waitForTimeout(2300);
  assert.equal(await page.getByLabel('Capture caption',{exact:true}).inputValue(),'My retained caption.');
  await page.getByRole('button',{name:'Save capture draft',exact:true}).click();
  await page.locator('#notice').getByText(/Your draft is retained/).waitFor();
  assert.equal(await page.getByLabel('Capture caption',{exact:true}).inputValue(),'My retained caption.');
  assert.equal(await page.getByRole('button',{name:'Mark capture reviewed',exact:true}).isDisabled(),true);
  page.once('dialog',d=>d.dismiss());await openTab(page,'translation');
  assert.equal(await page.locator('#captures-view').isVisible(),true);
  page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'Cancel capture edit',exact:true}).click();
  await page.getByRole('heading',{name:'Another editor saved this.',exact:true}).waitFor();
  await edit();await image.waitFor();await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(temp,'captures-mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(cli('get',{key:'greeting'}),before);
  assert.equal(cli('snapshot').sha256,snapshot);assert.equal(fs.readFileSync(exported.path,'utf8'),bytes);
  console.log(JSON.stringify({passed:true,evidence:temp,checks:['loaded image before review','draft-review-select-export',
    'registered synthetic provenance','spoiler flag','markup rendered as text','metadata-only allowlist',
    'stale evidence blocks export','stale selection can be removed','concurrent editor draft retained',
    'polling and discard protection','mobile layout','protected translation and snapshot unchanged']}));
})().catch(error=>{console.error(error);console.error('Synthetic evidence:',temp);process.exitCode=1;})
  .finally(async()=>{if(browser)await browser.close();if(server)server.kill();});
