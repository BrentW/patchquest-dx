/* Optional project-switching regression. Invented data, installed browser only. */
const {openTab,openMoreFilters}=require('./studio_navigation_browser_check.cjs');
const {spawn, spawnSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..'), python = process.env.PYTHON || 'python';
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'patchquest-project-picker-'));
const manifests = ['harbor', 'garden'].map(name => path.join(temp, name, 'project.json'));
function cli(index, action, params = {}) {
  const r = spawnSync(python, ['-X','utf8','-B',path.join(root,'tools/patchquest.py'),'state',manifests[index],action,'--input','-'],
    {input:JSON.stringify(params),encoding:'utf8',windowsHide:true});
  assert.equal(r.status, 0, r.stderr); return JSON.parse(r.stdout);
}
let server, browser;
(async () => {
  for (const [i, manifest] of manifests.entries()) {
    const demo = spawnSync(python, ['-X','utf8','-B',path.join(root,'examples/studio-demo.py'),'--workspace',path.dirname(manifest)], {encoding:'utf8',windowsHide:true});
    assert.equal(demo.status, 0, demo.stderr);
    const data = JSON.parse(fs.readFileSync(manifest));
    data.data = {...data.data, title:i ? 'Garden Translation' : 'Harbor Translation'};
    fs.writeFileSync(manifest, JSON.stringify(data));
  }
  const current = cli(1, 'get', {key:'greeting'});
  cli(1,'put',{data:{...Object.fromEntries(Object.entries(current).filter(([k])=>!['revision','human_corrected','provenance'].includes(k))),target:'Welcome to the invented garden.'},expected:current.revision});
  fs.mkdirSync(path.join(temp,'.local/config'), {recursive:true});
  fs.writeFileSync(path.join(temp,'.local/config/local.json'), JSON.stringify({schema_version:2,projects:{harbor:manifests[0],garden:manifests[1],missing:'missing/project.json'}}));
  const launcher = path.join(temp,'server.py');
  fs.writeFileSync(launcher, `import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'src'))
from patchquest.state import Store
from patchquest.studio import serve
from patchquest.jobs import BuildWorker
store=Store(sys.argv[2])
def build(job,progress):
    progress('Checking invented project snapshot')
    time.sleep(3)
    return {'status':'validated','approval':{'approved':False},'snapshot':job['snapshot']}
worker=BuildWorker(store,build,'Invented harbor worker').start()
try:serve(sys.argv[2],0,platform_root=sys.argv[3])
finally:worker.close()
`);
  server = spawn(python, ['-X','utf8','-B',launcher,root,manifests[0],temp], {windowsHide:true,stdio:['ignore','pipe','pipe']});
  const url = await new Promise((resolve,reject)=>{
    let output='';const timer=setTimeout(()=>reject(Error('Synthetic server startup timeout')),15000);
    server.stdout.on('data',data=>{output+=data;const m=output.match(/http:\/\/127\.0\.0\.1:\d+\/#\S+/);if(m){clearTimeout(timer);resolve(m[0]);}});
    server.on('exit',code=>{clearTimeout(timer);reject(Error('Synthetic server exited: '+code));});
  });
  browser = await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE ? {executablePath:process.env.BROWSER_EXECUTABLE} : {})});
  const page = await browser.newPage({viewport:{width:1400,height:1000}}), errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await openTab(page,'translation');await page.getByRole('button',{name:'greeting',exact:true}).click();
  const picker = page.getByLabel('Translation project',{exact:true});
  const choices = await picker.locator('option').evaluateAll(nodes=>nodes.map(n=>({id:n.value,title:n.textContent,disabled:n.disabled})));
  const a=choices.find(p=>p.title==='Harbor Translation').id, b=choices.find(p=>p.title==='Garden Translation').id;
  assert.equal(choices.length,3);assert.equal(choices.filter(p=>p.disabled).length,1);
  assert.equal(await picker.inputValue(),a);
  const header=await picker.boundingBox();assert.ok(header.x>900 && header.y<150,'Picker belongs in the top right');
  await page.locator('#english').fill('Unsaved harbor draft');
  page.once('dialog',d=>d.dismiss());await picker.selectOption(b);
  assert.equal(await picker.inputValue(),a);assert.equal(await page.locator('#english').inputValue(),'Unsaved harbor draft');
  page.once('dialog',d=>d.accept());await picker.selectOption(b);
  await page.getByRole('heading',{name:'Garden Translation',exact:true}).waitFor();
  await openTab(page,'translation');await page.getByRole('button',{name:'greeting',exact:true}).click();
  assert.equal(await page.locator('#english').inputValue(),'Welcome to the invented garden.');
  await page.reload();await page.getByRole('heading',{name:'Garden Translation',exact:true}).waitFor();
  assert.equal(await picker.inputValue(),b);
  const other=await browser.newPage();await other.goto(url);
  await other.getByRole('heading',{name:'Harbor Translation',exact:true}).waitFor();
  await openTab(page,'translation');await page.getByRole('button',{name:'greeting',exact:true}).click();
  await page.locator('#english').fill('A protected garden correction.');
  let release, entered;
  const hold=new Promise(resolve=>{release=resolve;}), saving=new Promise(resolve=>{entered=resolve;});
  await page.route('**/api/edit',async route=>{entered();await hold;await route.continue();});
  await page.getByRole('button',{name:'Save correction',exact:true}).click();await saving;
  assert.equal(await picker.isDisabled(),true,'Cannot switch during an in-flight save');
  release();await page.getByText('Correction saved. Future agents cannot silently replace it.').waitFor();
  assert.equal(await picker.isEnabled(),true);await page.unroute('**/api/edit');
  assert.equal(cli(1,'get',{key:'greeting'}).target,'A protected garden correction.');
  assert.equal(cli(1,'get',{key:'greeting'}).human_corrected,true);
  assert.notEqual(cli(0,'get',{key:'greeting'}).target,'A protected garden correction.');
  await openTab(page,'builds');
  assert.equal(await page.getByRole('button',{name:'Build test ROM',exact:true}).isDisabled(),true);
  await page.getByText('Upload a screenshot',{exact:true}).click();
  await page.getByLabel('Screenshot description',{exact:true}).fill('Unsaved screenshot details');
  page.once('dialog',d=>d.dismiss());await picker.selectOption(a);assert.equal(await picker.inputValue(),b);
  page.once('dialog',d=>d.accept());await picker.selectOption(a);
  await page.getByRole('heading',{name:'Harbor Translation',exact:true}).waitFor();
  // A delayed response for a shared record ID cannot populate the other project.
  let releaseRead, startedRead;
  const readHold=new Promise(resolve=>{releaseRead=resolve;}), reading=new Promise(resolve=>{startedRead=resolve;});
  await page.route('**/api/get?key=greeting',async route=>{startedRead();await readHold;await route.continue().catch(()=>{});});
  await openTab(page,'translation');await page.getByRole('button',{name:'greeting',exact:true}).click();await reading;
  await picker.selectOption(b);releaseRead();await page.unroute('**/api/get?key=greeting');
  await page.getByRole('heading',{name:'Garden Translation',exact:true}).waitFor();
  await openTab(page,'translation');await page.getByRole('button',{name:'greeting',exact:true}).click();
  assert.equal(await page.locator('#english').inputValue(),'A protected garden correction.');
  await openTab(other,'builds');
  await other.getByRole('button',{name:'Build test ROM',exact:true}).click();
  await other.getByLabel('Translation project',{exact:true}).selectOption(b);
  await other.getByRole('heading',{name:'Garden Translation',exact:true}).waitFor();
  await openTab(other,'builds');
  assert.equal(await other.getByRole('button',{name:'Build test ROM',exact:true}).isDisabled(),true);
  for(let attempt=0;attempt<30 && !cli(0,'jobs').some(j=>j.status==='validated');attempt++)await new Promise(r=>setTimeout(r,250));
  assert.equal(cli(0,'jobs')[0].status,'validated');assert.deepEqual(cli(1,'jobs'),[]);
  await page.goto(new URL('/?project=unknown',url).href);
  await page.getByText('Project unavailable. Choose an available project above.',{exact:true}).waitFor();
  await picker.selectOption(a);await page.getByRole('heading',{name:'Harbor Translation',exact:true}).waitFor();
  await page.screenshot({path:path.join(temp,'desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(temp,'mobile.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,evidence:temp,checks:['top-right selector','configured projects only','draft cancel/discard','save in flight','independent tabs','refresh persistence','stale read isolation','protected correction isolation','screenshot draft guard','project build capabilities','build continues after switch','unknown project recovery','mobile layout']}));
})().catch(error=>{console.error(error);console.error('Synthetic evidence:',temp);process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();if(server)server.kill();
});
