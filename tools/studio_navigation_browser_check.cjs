/* Navigation helpers and an optional synthetic-only browser smoke test. */
const assert = require('node:assert/strict');
const sectionForTab = {dashboard:'dashboard',agents:'dashboard',translation:'translate',glossary:'translate',
  builds:'testing',runtime:'testing',issues:'testing',testers:'testing',updates:'prepare',captures:'prepare',releases:'prepare'};

async function openTab(page, tab) {
  assert(Object.hasOwn(sectionForTab, tab), 'Known Studio child page required');
  const parent = page.locator(`nav [data-section="${sectionForTab[tab]}"]`);
  const child = page.locator(`nav [data-tab="${tab}"]`);
  if (await parent.getAttribute('aria-pressed') !== 'true') {
    await parent.click();
    // A refused transition must not try to click a hidden child afterwards.
    if (await parent.getAttribute('aria-pressed') !== 'true') return false;
  }
  if (await child.getAttribute('aria-pressed') !== 'true') await child.click();
  return await child.getAttribute('aria-pressed') === 'true';
}

async function openMoreFilters(page, selectId) {
  const select = page.locator('#' + selectId);
  const panel = select.locator('xpath=ancestor::details[1]');
  assert.equal(await panel.count(), 1, 'Advanced filter belongs in an expandable panel');
  if (!await panel.evaluate(node => node.open)) await panel.locator(':scope > summary').click();
  await select.waitFor({state:'visible'});
}

module.exports = {openTab, openMoreFilters, sectionForTab};

async function main() {
  const {spawn,spawnSync} = require('node:child_process');
  const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
  const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
  const root = path.resolve(__dirname,'..'), python = process.env.PYTHON || 'python';
  const evidence = process.env.STUDIO_NAVIGATION_EVIDENCE || fs.mkdtempSync(path.join(os.tmpdir(),'patchquest-navigation-'));
  fs.mkdirSync(evidence,{recursive:true});
  const project = path.join(evidence,'invented-project'), manifest = path.join(project,'project.json');
  function cli(action,params={}) {
    const r=spawnSync(python,['-X','utf8','-B',path.join(root,'tools/patchquest.py'),'state',manifest,action,'--input','-'],
      {input:JSON.stringify(params),encoding:'utf8',windowsHide:true});
    assert.equal(r.status,0,r.stderr);return JSON.parse(r.stdout);
  }
  let server,browser,page;
  try {
    const demo=spawnSync(python,['-X','utf8','-B',path.join(root,'examples/studio-demo.py'),'--workspace',project],{encoding:'utf8',windowsHide:true});
    assert.equal(demo.status,0,demo.stderr);
    const record=cli('get',{key:'greeting'}), fields={...record};
    for(const key of ['revision','human_corrected','provenance'])delete fields[key];
    cli('put',{data:fields,expected:record.revision,role:'human'});
    const png=path.join(project,'invented.png');
    const image=spawnSync(python,['-X','utf8','-B','-c',
      "import sys;from pathlib import Path;sys.path.insert(0,str(Path(sys.argv[1])/'src'));from patchquest.runtime import Frame;Path(sys.argv[2]).write_bytes(Frame(1,1,b'\\x01\\x02\\x03').png())",root,png],{encoding:'utf8',windowsHide:true});
    assert.equal(image.status,0,image.stderr);cli('attach',{path:png,description:'Independently authored one-pixel fixture.'});
    const before=cli('get',{key:'greeting'});
    server=spawn(python,['-X','utf8','-B','-u',path.join(root,'tools/patchquest.py'),'--platform',evidence,'studio',manifest,'--port','0'],{windowsHide:true,stdio:['ignore','pipe','pipe']});
    let stderr='';server.stderr.on('data',d=>stderr+=d);
    const url=await new Promise((resolve,reject)=>{let output='';const timer=setTimeout(()=>reject(Error('Invented server startup timed out')),15000);
      server.stdout.on('data',d=>{output+=d;const match=output.match(/http:\/\/127\.0\.0\.1:\d+\/#\S+/);if(match){clearTimeout(timer);resolve(match[0]);}});
      server.on('exit',code=>{clearTimeout(timer);reject(Error('Invented server exited: '+code));});});
    browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
    page=await browser.newPage({viewport:{width:1380,height:1000}});
    const errors=[],writes=[];page.on('pageerror',error=>errors.push(error.message));page.on('request',r=>{if(r.method()==='POST')writes.push(r.url());});
    await page.goto(url);await page.locator('#dashboard-view').waitFor();
    await page.waitForFunction(()=>document.querySelector('#counts')?.children.length===8);
    assert.equal(await page.locator('nav [data-section]').count(),4);
    assert.equal(await page.locator('nav [data-section="dashboard"]').getAttribute('aria-pressed'),'true');
    assert.equal(await page.locator('#editor-view').isVisible(),false);
    assert.equal(await page.locator('#counts').isVisible(),true);
    for(const [section,tabs] of Object.entries({dashboard:['dashboard','agents'],translate:['translation','glossary'],testing:['builds','runtime','issues','testers'],prepare:['updates','captures','releases']})) {
      await page.locator(`nav [data-section="${section}"]`).click();
      assert.deepEqual(await page.locator('nav [data-tab]:visible').evaluateAll(nodes=>nodes.map(n=>n.dataset.tab).sort()),[...tabs].sort());
      for(const tab of tabs){assert.equal(await openTab(page,tab),true);assert.equal(await page.locator('#counts').isVisible(),tab==='dashboard');}
    }
    await openTab(page,'translation');
    const chip=value=>page.locator(`button[data-filter-target="status"][data-filter-value="${value}"]`);
    assert.equal(await page.locator('#status').isVisible(),false);
    await chip('untranslated').click();
    await page.waitForFunction(()=>document.getElementById('result-count').textContent==='1–1 of 1' &&
      document.querySelectorAll('#records .record-link').length===1 &&
      document.querySelector('#records .record-link').textContent==='unknown');
    assert.equal(await page.locator('#status').inputValue(),'untranslated');
    assert.equal(await chip('untranslated').getAttribute('aria-pressed'),'true');
    assert.equal(await page.locator('#records .record-link').innerText(),'unknown');
    await openMoreFilters(page,'status');await page.locator('#status').selectOption('corrected');
    await page.waitForFunction(()=>document.querySelector('[data-filter-target="status"][data-filter-value="corrected"]').getAttribute('aria-pressed')==='true');
    await page.waitForFunction(()=>document.querySelector('#records .record-link')?.textContent==='greeting');
    await page.getByRole('button',{name:'Remove status filter: Human corrected',exact:true}).click();
    await page.waitForFunction(()=>document.getElementById('result-count').textContent==='1–4 of 4');
    await page.getByRole('button',{name:'greeting',exact:true}).click();
    await page.locator('#english').fill('Unsaved synthetic navigation draft');
    page.once('dialog',d=>d.dismiss());assert.equal(await openTab(page,'builds'),false);
    assert.equal(await page.locator('#english').inputValue(),'Unsaved synthetic navigation draft');
    page.once('dialog',d=>d.dismiss());await page.getByRole('button',{name:'Report issue',exact:true}).click();
    assert.equal(await page.locator('#english').inputValue(),'Unsaved synthetic navigation draft');
    let issuePrompts=0;page.once('dialog',async d=>{issuePrompts++;await d.accept();});
    await page.getByRole('button',{name:'Report issue',exact:true}).click();
    await page.locator('#issue-detail').getByRole('heading',{name:'Report an issue',exact:true}).waitFor();
    assert.equal(issuePrompts,1);
    assert.equal(await page.locator('nav [data-tab="issues"]').getAttribute('aria-pressed'),'true');
    assert.equal(await page.getByLabel('Related record IDs (comma separated)',{exact:true}).inputValue(),'greeting');
    await openTab(page,'translation');await page.getByRole('button',{name:'greeting',exact:true}).click();
    await page.locator('#english').fill('Unsaved synthetic navigation draft');
    assert.equal(await page.locator('nav [data-section="translate"]').getAttribute('aria-pressed'),'true');
    page.once('dialog',d=>d.dismiss());assert.equal(await openTab(page,'glossary'),false);
    assert.equal(await page.locator('nav [data-tab="translation"]').getAttribute('aria-pressed'),'true');
    assert.equal(await page.locator('#english').inputValue(),'Unsaved synthetic navigation draft');
    let prompts=0;page.once('dialog',async d=>{prompts++;await d.accept();});assert.equal(await openTab(page,'glossary'),true);assert.equal(prompts,1);
    await openTab(page,'dashboard');await page.locator('nav [data-section="translate"]').click();
    assert.equal(await page.locator('nav [data-tab="glossary"]').getAttribute('aria-pressed'),'true');
    await openTab(page,'captures');await page.getByRole('button',{name:'Prepare screenshot',exact:true}).click();
    await page.getByLabel('Capture caption',{exact:true}).fill('Unsaved synthetic caption');
    page.once('dialog',d=>d.dismiss());assert.equal(await openTab(page,'translation'),false);
    assert.equal(await page.getByLabel('Capture caption',{exact:true}).inputValue(),'Unsaved synthetic caption');
    page.once('dialog',d=>d.dismiss());assert.equal(await openTab(page,'releases'),false);
    assert.equal(await page.locator('nav [data-tab="captures"]').getAttribute('aria-pressed'),'true');
    assert.equal(await page.getByLabel('Capture caption',{exact:true}).inputValue(),'Unsaved synthetic caption');
    page.once('dialog',d=>d.accept());await openTab(page,'dashboard');
    await openTab(page,'builds');await page.getByText('Upload a screenshot',{exact:true}).click();
    await page.getByLabel('Screenshot description',{exact:true}).fill('Unsaved synthetic upload description');
    assert.equal(await page.locator('.screenshot-form[data-dirty="true"]').count(),1);
    page.once('dialog',d=>d.dismiss());assert.equal(await openTab(page,'dashboard'),false);
    assert.equal(await page.getByLabel('Screenshot description',{exact:true}).inputValue(),'Unsaved synthetic upload description');
    page.once('dialog',d=>d.dismiss());assert.equal(await openTab(page,'runtime'),false);
    assert.equal(await page.getByLabel('Screenshot description',{exact:true}).inputValue(),'Unsaved synthetic upload description');
    page.once('dialog',d=>d.accept());await openTab(page,'dashboard');
    assert.equal(await page.locator('.screenshot-form[data-dirty="true"]').count(),0);
    await page.locator('[data-open-tab="runtime"]').click();await page.locator('#runtime-view').waitFor();
    assert.equal(await page.locator('nav [data-section="testing"]').getAttribute('aria-pressed'),'true');
    assert.equal(await page.locator('nav [data-tab="runtime"]').getAttribute('aria-pressed'),'true');
    assert.equal(await page.locator('#counts').isVisible(),false);
    await page.screenshot({path:path.join(evidence,'navigation-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    for(const tab of ['dashboard','translation','runtime','captures']){await openTab(page,tab);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);}
    await page.screenshot({path:path.join(evidence,'navigation-mobile.png'),fullPage:true});
    assert.deepEqual(cli('get',{key:'greeting'}),before);assert.deepEqual(cli('screenshot-selection').items,[]);
    assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
    fs.writeFileSync(path.join(evidence,'server.log'),stderr);
    fs.writeFileSync(path.join(evidence,'result.json'),JSON.stringify({passed:true,checks:['Dashboard default and stats isolation','four primary areas and all child entries','remembered child','chip to select and select to chip','filter removal','editor parent and child refusal','capture caption parent and child refusal','separate upload-form dirty flag refusal and accepted discard','single accepted prompt','record issue respects refused and accepted navigation','programmatic cross-section quick link','mobile overflow','no browser writes/protected correction changes'],errors,writes},null,2));
    console.log(JSON.stringify({passed:true,evidence}));
  }catch(error){fs.writeFileSync(path.join(evidence,'failure.txt'),String(error.stack||error));if(page)await page.screenshot({path:path.join(evidence,'failure.png')}).catch(()=>{});throw error;}
  finally{if(browser)await browser.close();if(server)server.kill();}
}
if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1;});
