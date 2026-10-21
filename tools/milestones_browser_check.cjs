/* Optional editorial flow check: invented data and installed browser tools only. */
const {openTab,openMoreFilters}=require('./studio_navigation_browser_check.cjs');
const {spawn, spawnSync} = require('node:child_process');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root=path.resolve(__dirname,'..'),python=process.env.PYTHON||'python';
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'patchquest-milestones-'));
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
  server=spawn(python,['-X','utf8','-B',path.join(root,'tools/patchquest.py'),'--platform',temp,'studio',manifest,'--port','0'],{windowsHide:true,stdio:['ignore','pipe','pipe']});
  const url=await new Promise((resolve,reject)=>{
    let output='';const timer=setTimeout(()=>reject(Error('Synthetic startup timed out')),15000);
    server.stdout.on('data',data=>{output+=data;const m=output.match(/http:\/\/127\.0\.0\.1:\d+\/#\S+/);if(m){clearTimeout(timer);resolve(m[0]);}});
    server.on('exit',code=>{clearTimeout(timer);reject(Error('Synthetic server exited: '+code));});
  });
  browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
  const page=await browser.newPage({viewport:{width:1400,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);
  await openTab(page,'updates');
  await page.getByRole('button',{name:'New summary',exact:true}).click();
  await page.getByLabel('Summary title',{exact:true}).fill('Invented menu review');
  await page.getByLabel('Summary text',{exact:true}).fill('Invented menus now have consistent spacing. <img src=x onerror=alert(1)>');
  await page.getByLabel('Scope and remaining limitations',{exact:true}).fill('Runtime navigation remains untested.');
  await page.getByLabel('Private notes / evidence references (excluded from export)',{exact:true}).fill('PRIVATE NOTES SENTINEL');
  await page.getByLabel('Verification basis (reported, not certified)',{exact:true}).selectOption('static');
  await page.getByRole('button',{name:'Save draft',exact:true}).click();
  await page.getByText('Draft · review required',{exact:false}).waitFor();
  assert.equal(cli('milestone-preview').items.length,0);
  const edit=()=>page.locator('#updates-list').getByRole('button',{name:'Edit / review',exact:true}).click();
  await edit();await page.getByRole('button',{name:'Mark reviewed',exact:true}).click();
  await page.getByText('Reviewed · not selected',{exact:false}).waitFor();
  assert.equal(cli('milestone-preview').items.length,0);
  await edit();await page.getByRole('button',{name:'Select for export',exact:true}).click();
  await page.getByText('Selected for export',{exact:false}).first().waitFor();
  assert.equal(cli('milestone-preview').items.length,1);
  assert.equal(await page.locator('#updates-list img').count(),0);
  await page.getByRole('button',{name:'Export selected summaries',exact:true}).click();
  await page.locator('#notice').getByText(/Saved 1 selected summaries privately/).waitFor();
  const exported=cli('milestone-history').filter(r=>r.kind==='milestone.exported').at(-1).payload;
  assert.equal(JSON.parse(fs.readFileSync(exported.path)).items.length,1);
  assert.equal(fs.readFileSync(exported.path,'utf8').includes('PRIVATE'),false);
  await page.screenshot({path:path.join(temp,'updates-desktop.png'),fullPage:true});
  // A separate writer changes the saved record while an editor retains its draft.
  await edit();await page.getByLabel('Summary text',{exact:true}).fill('My retained draft.');
  const old=cli('milestones').items[0];
  cli('milestone-put',{key:old.id,expected:old.revision,data:{...old.content,summary:'Another editor saved this.'},private_notes:old.private_notes});
  await page.waitForTimeout(2300);
  assert.equal(await page.getByLabel('Summary text',{exact:true}).inputValue(),'My retained draft.');
  assert.equal(await page.getByRole('button',{name:'Mark reviewed',exact:true}).isDisabled(),true);
  await page.getByRole('button',{name:'Save draft',exact:true}).click();
  await page.locator('#notice').getByText(/Your draft is retained/).waitFor();
  assert.equal(await page.getByLabel('Summary text',{exact:true}).inputValue(),'My retained draft.');
  assert.equal(cli('milestone-preview').items.length,0);
  page.once('dialog',dialog=>dialog.dismiss());
  await openTab(page,'translation');
  assert.equal(await page.locator('#updates-view').isVisible(),true);
  page.once('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:'Cancel edit',exact:true}).click();
  await page.getByText('Another editor saved this.',{exact:true}).waitFor();
  await edit();
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(temp,'updates-mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(cli('get',{key:'greeting'}),before);
  assert.equal(cli('snapshot').sha256,snapshot);
  console.log(JSON.stringify({passed:true,evidence:temp,checks:['draft-review-select-export',
    'private notes excluded','markup rendered as text','editing revokes selection',
    'concurrent editor conflict retains draft','polling preserves draft','discard prompt',
    'mobile layout','protected translation and snapshot unchanged']}));
})().catch(error=>{console.error(error);console.error('Synthetic evidence:',temp);process.exitCode=1;})
  .finally(async()=>{if(browser)await browser.close();if(server)server.kill();});
