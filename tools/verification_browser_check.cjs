/* Optional browser check; only invented projects and installed browser software. */
const {openTab,openMoreFilters}=require('./studio_navigation_browser_check.cjs');
const {spawn, spawnSync} = require('node:child_process');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..'), python = process.env.PYTHON || 'python';
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'patchquest-verification-'));
const projectRoot = path.join(temp, 'project'), manifest = path.join(projectRoot, 'project.json');
function cli(action, params = {}) {
  const r = spawnSync(python, ['-X','utf8','-B',path.join(root,'tools/patchquest.py'),
    'state',manifest,action,'--input','-'], {input:JSON.stringify(params),encoding:'utf8',windowsHide:true});
  assert.equal(r.status, 0, r.stderr); return JSON.parse(r.stdout);
}
let server, browser;
(async () => {
  const demo = spawnSync(python, ['-X','utf8','-B',path.join(root,'examples/studio-demo.py'),
    '--workspace',projectRoot], {encoding:'utf8',windowsHide:true});
  assert.equal(demo.status, 0, demo.stderr);
  const record = cli('get', {key:'greeting'});
  const fields = Object.fromEntries(Object.entries(record).filter(([k])=>!['revision','human_corrected','provenance'].includes(k)));
  cli('put', {data:{...fields,target:'An invented protected greeting.'},expected:record.revision,role:'human'});
  const frozen = cli('snapshot');
  const artifact = path.join(projectRoot, 'output', 'invented.fixture');
  fs.mkdirSync(path.dirname(artifact), {recursive:true}); fs.writeFileSync(artifact, 'invented build bytes');
  cli('build-report', {data:{id:'invented-review',status:'validated',snapshot:frozen.sha256,
    artifacts:{rom:artifact}},expected:0});
  const area = {id:'greeting-review',label:'Greeting review',expectation:'Preserve the invented welcoming tone.',
    stage:'language_review',method:'manual_review',record_ids:['greeting']};
  cli('verification-plan-put', {data:{build_id:'invented-review',next_milestone:'Check the invented save menu.',
    areas:[area,{...area,id:'save-check',label:'Cold save reload',stage:'gameplay',method:'reported_human',record_ids:[]},
      {...area,id:'layout-check',label:'Menu padding',stage:'graphics_layout',method:'static'}]},expected:0});
  cli('verification-observe', {area_id:area.id,build_id:'invented-review',status:'passed',reference:'Invented editorial comparison.',expected:0,plan_revision:1});
  cli('verification-observe', {area_id:'layout-check',build_id:'invented-review',status:'failed',reference:'Invented padding finding.',expected:0,plan_revision:1});
  const before = cli('get',{key:'greeting'});
  server = spawn(python, ['-X','utf8','-B',path.join(root,'tools/patchquest.py'),'--platform',temp,
    'studio',manifest,'--port','0'], {windowsHide:true,stdio:['ignore','pipe','pipe']});
  const url = await new Promise((resolve,reject)=>{
    let output = ''; const timer = setTimeout(()=>reject(Error('Synthetic startup timed out')),15000);
    server.stdout.on('data',data=>{output+=data;const m=output.match(/http:\/\/127\.0\.0\.1:\d+\/#\S+/);
      if(m){clearTimeout(timer);resolve(m[0]);}});
    server.on('exit',code=>{clearTimeout(timer);reject(Error('Synthetic server exited: '+code));});
  });
  browser = await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
  const page = await browser.newPage({viewport:{width:1400,height:1100}}), errors = [], writes = [];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.method()==='POST')writes.push(r.url());});
  await page.goto(url);
  await openTab(page,'builds');
  const card = page.locator('#builds > .card').filter({has:page.getByRole('heading',{name:'invented-review',exact:true})});
  await card.getByRole('button',{name:'Verification coverage',exact:true}).click();
  await card.getByRole('heading',{name:'Planned verification coverage',exact:true}).waitFor();
  let content = await card.locator('.verification-coverage').innerText();
  assert.match(content,/Passed for scope/); assert.match(content,/Needs attention/); assert.match(content,/Untested/);
  assert.match(content,/manual review/); assert.match(content,/static/); assert.match(content,/reported human/);
  await page.screenshot({path:path.join(temp,'coverage-desktop.png'),fullPage:true});
  assert.deepEqual(cli('get',{key:'greeting'}),before);
  cli('put',{data:{...fields,target:'A later protected greeting.'},expected:before.revision,role:'human'});
  await page.waitForTimeout(2400);
  await card.getByRole('button',{name:'Verification coverage',exact:true}).click();
  await card.getByText(/Needs recheck/).first().waitFor();
  assert.match(await card.locator('.verification-coverage').innerText(),/differs from current saved revisions/);
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(temp,'coverage-mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]); assert.deepEqual(writes,[]);
  assert.equal(cli('get',{key:'greeting'}).target,'A later protected greeting.');
  assert.equal(cli('readiness').release_approved,false);
  console.log(JSON.stringify({passed:true,evidence:temp,checks:['scoped pass/failure/untested display',
    'method labels','changed correction invalidates evidence','no browser writes',
    'protected wording retained','mobile layout','no release approval']}));
})().catch(error=>{console.error(error);console.error('Synthetic evidence:',temp);process.exitCode=1;})
  .finally(async()=>{if(browser)await browser.close();if(server)server.kill();});
