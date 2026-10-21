/* Optional local intake/triage check using independently invented reports only. */
const {openTab,openMoreFilters}=require('./studio_navigation_browser_check.cjs');
const {spawn,spawnSync}=require('node:child_process');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),python=process.env.PYTHON||'python';
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'patchquest-testers-'));
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
  const artifact=path.join(projectRoot,'output','invented.fixture'),bytes=Buffer.from('invented test artifact');
  fs.mkdirSync(path.dirname(artifact),{recursive:true});fs.writeFileSync(artifact,bytes,{flag:'wx'});
  cli('build-report',{data:{id:'invented-build',status:'validated',snapshot,artifacts:{rom:artifact}},expected:0});
  const document={schema_version:1,report_type:'tester-reports',project_id:'invented-lantern-demo',source:'invented-browser-test',reports:[{
    external_id:'one',title:'Invented menu <img src=x onerror=alert(1)>',observed:'The invented label touches the frame.',
    steps:'Open the invented menu.',expected:'Comfortable spacing.',environment:'Invented environment only.',
    build_label:'Invented build',artifact_sha256:crypto.createHash('sha256').update(bytes).digest('hex'),suggested_translation:'This must stay inactive.'}]};
  const reportFile=path.join(temp,'reports.json');fs.writeFileSync(reportFile,JSON.stringify(document));
  server=spawn(python,['-X','utf8','-B',path.join(root,'tools/patchquest.py'),'--platform',temp,'studio',manifest,'--port','0'],{windowsHide:true,stdio:['ignore','pipe','pipe']});
  const url=await new Promise((resolve,reject)=>{
    let output='';const timer=setTimeout(()=>reject(Error('Synthetic startup timed out')),15000);
    server.stdout.on('data',data=>{output+=data;const m=output.match(/http:\/\/127\.0\.0\.1:\d+\/#\S+/);if(m){clearTimeout(timer);resolve(m[0]);}});
    server.on('exit',code=>{clearTimeout(timer);reject(Error('Synthetic server exited: '+code));});
  });
  browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
  const page=await browser.newPage({viewport:{width:1400,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));await page.goto(url);
  await openTab(page,'testers');
  await page.getByRole('button',{name:'Import tester reports',exact:true}).click();
  await page.getByLabel('Tester report JSON file',{exact:true}).setInputFiles(reportFile);
  await page.waitForFunction(()=>document.querySelector('#tester-detail textarea')?.value.includes('invented-browser-test'));
  assert.equal(await page.getByRole('button',{name:'Import previewed reports',exact:true}).isDisabled(),true);
  await page.getByRole('button',{name:'Preview report import',exact:true}).click();
  await page.getByText('1 new · 0 already imported',{exact:true}).waitFor();
  assert.equal(cli('tester-reports').total,0);
  await page.getByRole('button',{name:'Import previewed reports',exact:true}).click();
  await page.locator('#notice').getByText(/Imported 1 reports/).waitFor();
  assert.equal(await page.locator('#testers-list img').count(),0);
  const edit=()=>page.getByRole('button',{name:'Inspect / triage',exact:true}).click();
  await edit();await page.getByText('This must stay inactive.',{exact:true}).waitFor();
  await page.getByLabel('Build tested',{exact:true}).selectOption('invented-build');
  await page.getByLabel('Affected translation IDs (one per line)',{exact:true}).fill('greeting');
  await page.getByLabel('Private triage notes',{exact:true}).fill('Investigate the invented frame spacing.');
  await page.getByLabel('Intake decision',{exact:true}).selectOption('accepted');
  await page.getByLabel('Create a new linked issue',{exact:true}).selectOption('yes');
  assert.equal(await page.getByRole('button',{name:'Save report triage',exact:true}).isDisabled(),true);
  await page.getByRole('button',{name:'Inspect build and record links',exact:true}).click();
  await page.getByText(/Reported artifact: matched/).waitFor();
  await page.getByRole('button',{name:'Save report triage',exact:true}).click();
  await page.locator('#testers-list').getByText(/Accepted for investigation/).waitFor();
  let report=cli('tester-reports').items[0];const issueId=report.triage.issue_id;
  assert.ok(issueId);assert.equal(cli('issues').length,1);
  assert.equal(report.triage.binding.records.greeting,before.revision);
  assert.deepEqual(cli('get',{key:'greeting'}),before);
  // An identical re-import preserves the report's decision and existing issue.
  await page.getByRole('button',{name:'Import tester reports',exact:true}).click();
  await page.getByLabel('Tester report JSON',{exact:true}).fill(JSON.stringify(document));
  await page.getByRole('button',{name:'Preview report import',exact:true}).click();
  await page.getByText('0 new · 1 already imported',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Import previewed reports',exact:true}).click();
  await page.locator('#notice').getByText(/Imported 0 reports; 1 already present/).waitFor();
  assert.equal(cli('tester-reports').items[0].revision,report.revision);
  await edit();await page.getByText(/Linked issue:/).waitFor();
  await page.screenshot({path:path.join(temp,'testers-desktop.png'),fullPage:true});
  // Polling and a conflicting triage write must preserve the user's unsaved notes.
  await page.getByLabel('Private triage notes',{exact:true}).fill('My retained investigation notes.');
  await page.getByRole('button',{name:'Inspect build and record links',exact:true}).click();
  await page.getByText(/Reported artifact: matched/).waitFor();
  const ctx=cli('tester-context',{key:report.id,build_id:'invented-build',record_ids:['greeting']});
  cli('tester-triage',{key:report.id,expected:report.revision,context_token:ctx.token,build_id:'invented-build',record_ids:['greeting'],status:'needs_info',notes:'Another editor requested details.',issue_id:issueId});
  await page.waitForTimeout(2300);
  assert.equal(await page.getByLabel('Private triage notes',{exact:true}).inputValue(),'My retained investigation notes.');
  await page.getByRole('button',{name:'Save report triage',exact:true}).click();
  await page.locator('#notice').getByText(/Your draft is retained/).waitFor();
  page.once('dialog',d=>d.dismiss());await openTab(page,'translation');
  assert.equal(await page.locator('#testers-view').isVisible(),true);
  page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'Cancel report triage',exact:true}).click();
  await page.locator('#testers-list').getByText(/Needs information/).waitFor();
  await edit();await page.getByLabel('Private triage notes',{exact:true}).fill('Inspect changed artifact before saving.');
  await page.getByRole('button',{name:'Inspect build and record links',exact:true}).click();
  await page.getByText(/Reported artifact: matched/).waitFor();
  report=cli('tester-reports').items[0];fs.writeFileSync(artifact,'changed invented artifact');
  await page.getByRole('button',{name:'Save report triage',exact:true}).click();
  await page.locator('#notice').getByText(/Your draft is retained/).waitFor();
  assert.equal(cli('tester-reports').items[0].revision,report.revision);fs.writeFileSync(artifact,bytes);
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(temp,'testers-mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(cli('get',{key:'greeting'}),before);
  assert.equal(cli('snapshot').sha256,snapshot);assert.equal(cli('proposals',{key:'greeting'}).length,0);
  console.log(JSON.stringify({passed:true,evidence:temp,checks:['file preview and import','markup rendered as text',
    'build and historical revision binding','issue creation','inactive wording preserves corrections',
    'idempotent reimport preserves triage','conflicting editor retains draft','changed artifact rejects save',
    'polling and discard protection','desktop/mobile layout','snapshot unchanged']}));
})().catch(error=>{console.error(error);console.error('Synthetic evidence:',temp);process.exitCode=1;})
  .finally(async()=>{if(browser)await browser.close();if(server)server.kill();});
