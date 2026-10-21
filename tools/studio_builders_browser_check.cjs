/* Browser regression using only invented projects and explicitly supplied callbacks. */
const {openTab,openMoreFilters}=require('./studio_navigation_browser_check.cjs');
const {spawn,spawnSync}=require('node:child_process');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),python=process.env.PYTHON||'python';
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'patchquest-builder-switch-'));
const names=['Harbor','Garden','Museum'],manifests=names.map(n=>path.join(temp,n,'project.json'));
function cli(i,action,params={}){
  const r=spawnSync(python,['-X','utf8','-B',path.join(root,'tools/patchquest.py'),'state',manifests[i],action,'--input','-'],{input:JSON.stringify(params),encoding:'utf8',windowsHide:true});
  assert.equal(r.status,0,r.stderr);return JSON.parse(r.stdout);
}
let server,browser;
(async()=>{
  for(const [i,manifest] of manifests.entries()){
    const r=spawnSync(python,['-X','utf8','-B',path.join(root,'examples/studio-demo.py'),'--workspace',path.dirname(manifest)],{encoding:'utf8',windowsHide:true});
    assert.equal(r.status,0,r.stderr);
    const data=JSON.parse(fs.readFileSync(manifest));data.data={...data.data,title:names[i]+' Translation'};fs.writeFileSync(manifest,JSON.stringify(data));
  }
  const protectedRecord=cli(1,'get',{key:'greeting'});
  cli(1,'put',{data:{...Object.fromEntries(Object.entries(protectedRecord).filter(([k])=>!['revision','human_corrected','provenance'].includes(k))),target:'An invented protected garden greeting.'},expected:protectedRecord.revision,role:'human'});
  const before=manifests.map((_,i)=>cli(i,'get',{key:'greeting'}));
  fs.mkdirSync(path.join(temp,'.local/config'),{recursive:true});
  fs.writeFileSync(path.join(temp,'.local/config/local.json'),JSON.stringify({schema_version:2,projects:Object.fromEntries(names.map((n,i)=>[n,manifests[i]]))}));
  const launcher=path.join(temp,'server.py');
  fs.writeFileSync(launcher,`import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'src'))
from patchquest.studio import serve
from patchquest.studio_builders import BuilderBinding
from patchquest.state import Store
manifests=[Path(sys.argv[2])/name/'project.json' for name in ['Harbor','Garden']]
def pipeline(manifest):
    def run(job,progress):
        store=Store(manifest)
        frozen=json.loads(Path(store.export_snapshot(job['snapshot'])).read_text(encoding='utf-8'))
        progress('Validating invented saved input')
        time.sleep(3)
        return {'status':'validated','approval':{'approved':False},'snapshot':job['snapshot'],'greeting':next(r['target'] for r in frozen['records'] if r['id']=='greeting')}
    return run
serve(manifests[0],0,platform_root=Path(sys.argv[2]),builders=[BuilderBinding(m,pipeline(m),m.parent.name+' pipeline') for m in manifests],initial_builder=manifests[0])
`);
  server=spawn(python,['-X','utf8','-B',launcher,root,temp],{windowsHide:true,stdio:['ignore','pipe','pipe']});
  const url=await new Promise((resolve,reject)=>{
    let output='';const timer=setTimeout(()=>reject(Error('Synthetic startup timed out')),15000);
    server.stdout.on('data',data=>{output+=data;const m=output.match(/http:\/\/127\.0\.0\.1:\d+\/#\S+/);if(m){clearTimeout(timer);resolve(m[0]);}});
    server.on('exit',code=>{clearTimeout(timer);reject(Error('Synthetic server exited '+code));});
  });
  browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
  const page=await browser.newPage({viewport:{width:1400,height:1000}}),other=await browser.newPage(),errors=[];
  for(const p of [page,other])p.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.getByRole('heading',{name:'Harbor Translation',exact:true}).waitFor();
  const picker=page.getByLabel('Translation project',{exact:true});
  const keys=await picker.locator('option').evaluateAll(options=>options.map(o=>({id:o.value,title:o.textContent})));
  const key=n=>keys.find(k=>k.title===n+' Translation').id;
  async function choose(n){await picker.selectOption(key(n));await page.getByRole('heading',{name:n+' Translation',exact:true}).waitFor();await openTab(page,'builds');}
  await choose('Garden');
  await page.waitForFunction(()=>!document.getElementById('builder-switch').disabled);
  assert.match(await page.locator('#builder-workers').innerText(),/Loaded builder: Harbor Translation/);
  assert.match(await page.locator('#builder-workers').innerText(),/Idle/);
  assert.equal(await page.locator('#build-test').isDisabled(),true);
  await other.goto(url);await openTab(other,'builds');
  await other.locator('#build-test').click();
  await page.waitForFunction(()=>document.getElementById('builder-workers').textContent.includes('Validating invented saved input'));
  assert.equal(await page.locator('#builder-switch').isDisabled(),true);
  await page.waitForFunction(()=>!document.getElementById('builder-switch').disabled);
  await page.locator('#builder-switch').click();
  await page.waitForFunction(()=>!document.getElementById('build-test').disabled);
  assert.match(await page.locator('#builder-workers').innerText(),/Loaded builder: Garden Translation/);
  assert.deepEqual(cli(1,'jobs'),[],'Loading must not start a build');
  await other.waitForFunction(()=>document.getElementById('builder-workers').textContent.includes('Garden Translation'));
  assert.equal(await other.locator('#builder-switch').isEnabled(),true);
  await page.locator('#build-test').click();
  await page.getByRole('heading',{name:'Test ROM ready',exact:true}).waitFor();
  const built=cli(1,'jobs')[0];assert.equal(built.status,'validated');assert.equal(built.payload.result.greeting,before[1].target);
  assert.equal(built.payload.result.approval.approved,false);
  await choose('Harbor');await page.waitForFunction(()=>!document.getElementById('builder-switch').disabled);
  await page.locator('#builder-panel').screenshot({path:path.join(temp,'switch-panel.png')});
  await page.locator('#builder-switch').click();await page.waitForFunction(()=>!document.getElementById('build-test').disabled);
  await choose('Museum');
  await page.getByText(/No build adapter is configured for this project/).waitFor();
  assert.equal(await page.locator('#builder-switch').isDisabled(),true);
  assert.match(await page.locator('#builder-workers').innerText(),/Loaded builder: Harbor Translation/);
  await page.locator('#builder-panel').screenshot({path:path.join(temp,'unconfigured-panel.png')});
  await page.setViewportSize({width:390,height:844});
  await page.locator('#builder-panel').screenshot({path:path.join(temp,'mobile-panel.png')});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(before,manifests.map((_,i)=>cli(i,'get',{key:'greeting'})));
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,evidence:temp,checks:['loaded project identity','cross-project job progress','running-build switch blocked','idle switch both directions','no implicit build','snapshot-bound target callback','independent tabs','unconfigured adapter','protected correction preserved','mobile layout']}));
})().catch(error=>{console.error(error);console.error('Synthetic evidence:',temp);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)server.kill();});
