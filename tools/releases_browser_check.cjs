/* Optional release preparation check using independently invented bytes only. */
const {openTab,openMoreFilters}=require('./studio_navigation_browser_check.cjs');
const {spawn,spawnSync}=require('node:child_process');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),python=process.env.PYTHON||'python';
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'patchquest-releases-'));
const projectRoot=path.join(temp,'project'),manifest=path.join(projectRoot,'project.json');
function command(args,input='') {
  const r=spawnSync(python,['-X','utf8','-B',...args],{input,encoding:'utf8',windowsHide:true});
  assert.equal(r.status,0,r.stderr);return r.stdout;
}
function cli(action,params={}) {return JSON.parse(command([path.join(root,'tools/patchquest.py'),'state',manifest,action,'--input','-'],JSON.stringify(params)));}
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
let server,browser;
(async()=>{
  command([path.join(root,'examples/studio-demo.py'),'--workspace',projectRoot]);
  const original=cli('get',{key:'greeting'}),fields=Object.fromEntries(Object.entries(original).filter(([k])=>!['revision','human_corrected','provenance'].includes(k)));
  cli('put',{data:{...fields,target:'An invented protected greeting.'},expected:original.revision,role:'human'});
  const before=cli('get',{key:'greeting'}),snapshot=cli('snapshot').sha256;
  const source=path.join(projectRoot,'unprovided-fictional-source'),sourceBytes=Buffer.from('invented fixture, no ROM'),targetBytes=Buffer.from('invented translated fixture, no ROM');
  fs.writeFileSync(source,sourceBytes,{flag:'wx'});
  const out=path.join(projectRoot,'output'),target=path.join(out,'invented-target.fixture'),patchFile=path.join(out,'invented-patch.fixture');fs.mkdirSync(out,{recursive:true});fs.writeFileSync(target,targetBytes,{flag:'wx'});
  command([path.join(root,'tools/patchquest.py'),'bps-create',source,target,patchFile,'--output-root',out]);
  const patchBytes=fs.readFileSync(patchFile);
  for(const id of ['invented-build','invented-repeat'])cli('build-report',{data:{id,status:'validated',snapshot,artifacts:{rom:target,patch:patchFile}},expected:0});
  server=spawn(python,['-X','utf8','-B',path.join(root,'tools/patchquest.py'),'--platform',temp,'studio',manifest,'--port','0'],{windowsHide:true,stdio:['ignore','pipe','pipe']});
  const url=await new Promise((resolve,reject)=>{
    let output='';const timer=setTimeout(()=>reject(Error('Synthetic startup timed out')),15000);
    server.stdout.on('data',data=>{output+=data;const m=output.match(/http:\/\/127\.0\.0\.1:\d+\/#\S+/);if(m){clearTimeout(timer);resolve(m[0]);}});
    server.on('exit',code=>{clearTimeout(timer);reject(Error('Synthetic server exited: '+code));});
  });
  browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
  const page=await browser.newPage({viewport:{width:1400,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await openTab(page,'releases');
  await page.getByRole('button',{name:'New release candidate',exact:true}).click();
  for(const [label,value] of Object.entries({'Release ID':'invented-browser','Release title':'Invented <img src=x onerror=alert(1)>','Release version':'test-1','Required source edition / revision':'Invented fixture 1','Patch download filename (.bps)':'invented-test.bps','Patched image filename':'invented-test.bin','Compatibility and input requirements':'Exact synthetic fixture only.','Scope and remaining limitations':'No game or runtime testing.','Private notes (excluded from export)':'PRIVATE_NOT_FOR_EXPORT'}))await page.getByLabel(label,{exact:true}).fill(value);
  await page.getByLabel('Build to prepare',{exact:true}).selectOption('invented-build');
  await page.getByLabel('Patch artifact',{exact:true}).selectOption('patch');
  await page.getByLabel('Output image artifact',{exact:true}).selectOption('rom');
  await page.getByLabel('Repeat build (optional comparison)',{exact:true}).selectOption('invented-repeat');
  await page.getByRole('button',{name:'Save candidate draft',exact:true}).click();
  await page.getByRole('button',{name:'Validate saved candidate',exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Export private release manifest',exact:true}).count(),0);
  await page.getByRole('button',{name:'Validate saved candidate',exact:true}).click();
  await page.getByRole('button',{name:'Mark metadata reviewed',exact:true}).waitFor();
  await page.getByText(/Repeat build: matched_registered_artifacts/).waitFor();
  await page.getByRole('button',{name:'Mark metadata reviewed',exact:true}).click();
  const exportButton=page.getByRole('button',{name:'Export private release manifest',exact:true});await exportButton.waitFor();
  await page.locator('#releases-list').getByText(/Metadata reviewed previously/).waitFor();
  assert.equal(await page.locator('#releases-list').getByText('No release candidates yet.',{exact:true}).count(),0);
  await page.locator('#release-detail summary').filter({hasText:'Manifest content'}).click();
  assert.equal(await page.locator('#release-detail img').count(),0);
  await page.screenshot({path:path.join(temp,'releases-desktop.png'),fullPage:true});
  await page.locator('#release-detail').evaluate(node=>node.scrollTop=node.scrollHeight);
  await page.screenshot({path:path.join(temp,'releases-manifest.png'),fullPage:true});
  await exportButton.click();await page.locator('#notice').getByText(/Manifest saved privately/).waitFor();
  const folder=path.join(out,'release-manifests');let files=fs.readdirSync(folder);assert.equal(files.length,1);
  const exported=JSON.parse(fs.readFileSync(path.join(folder,files[0]))),frozen=fs.readFileSync(path.join(folder,files[0]));
  assert.equal(exported.source.sha256,hash(sourceBytes));assert.equal(exported.output.sha256,hash(targetBytes));assert.equal(exported.patch.sha256,hash(patchBytes));
  assert.equal(exported.release_approved,false);assert.equal(exported.publication_approved,false);
  for(const value of [projectRoot,'PRIVATE_NOT_FOR_EXPORT',snapshot,'invented-build'])assert.ok(!JSON.stringify(exported).includes(value));
  // Changing the inspected artifact must not write another export.
  fs.writeFileSync(target,Buffer.from('tampered invented output'));
  await exportButton.click();await page.locator('#notice.error').waitFor();assert.equal(fs.readdirSync(folder).length,1);fs.writeFileSync(target,targetBytes);
  // A conflicting edit keeps the local draft and does not reset the other editor.
  await page.getByLabel('Private notes (excluded from export)',{exact:true}).fill('Retain this draft.');
  assert.equal(await exportButton.isDisabled(),true);
  let candidate=cli('release-candidates').items[0];
  cli('release-put',{data:candidate.content,...candidate.selection,key:candidate.id,expected:candidate.revision,private_notes:'Another editor saved.'});
  await page.waitForTimeout(2300);assert.equal(await page.getByLabel('Private notes (excluded from export)',{exact:true}).inputValue(),'Retain this draft.');
  await page.getByRole('button',{name:'Save candidate draft',exact:true}).click();await page.locator('#notice').getByText(/Your draft is retained/).waitFor();
  page.once('dialog',d=>d.dismiss());await openTab(page,'translation');assert.equal(await page.locator('#releases-view').isVisible(),true);
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(temp,'releases-mobile.png'),fullPage:true});
  assert.deepEqual(fs.readFileSync(path.join(folder,files[0])),frozen);assert.deepEqual(fs.readFileSync(source),sourceBytes);assert.deepEqual(fs.readFileSync(patchFile),patchBytes);
  assert.deepEqual(cli('get',{key:'greeting'}),before);assert.equal(cli('snapshot').sha256,snapshot);assert.equal(cli('proposals',{key:'greeting'}).length,0);assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,evidence:temp,checks:['draft validation review export','exact checksums and patch reconstruction','repeat artifact comparison','private metadata exclusion','no binaries copied','no inferred approval','changed artifact blocks export','conflicting draft retention','polling and discard guard','desktop/mobile layout','source snapshots and corrections unchanged']}));
})().catch(error=>{console.error(error);console.error('Synthetic evidence:',temp);process.exitCode=1;})
  .finally(async()=>{if(browser)await browser.close();if(server)server.kill();});
