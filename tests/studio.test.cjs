const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'../integration/index.js'),'utf8');
function fixture(t,{rustFails=false,cFails=false,changed=false,backendVersion='0.3.3',staleAdapter=false}={}) {
    const dir=fs.mkdtempSync(path.join(os.tmpdir(),'reez-studio-test-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
    fs.writeFileSync(path.join(dir,'reez.json'),JSON.stringify({enabled:true,output:'rust-src'}));
    const messages=[];let calls=0;let snapshot='snapshot';let loaded=false;
    const output={clear(){messages.length=0;},write(...args){messages.push(args);},setLoading(_,v){loaded=v;},getSection(){return {numErrors:messages.filter(m=>m[1]==='error').length}}};
    const store={filePath:path.join(dir,'example.eez-project'),project:{settings:{build:{destinationFolder:'src/ui'}}},outputSectionsStore:output};
    const build={async build(){output.write('output','info','C generated');if(changed)snapshot='changed';if(cFails)output.write('output','error','C failed');output.write('output','info','Build successfully finished at now');return 123;}};
    const storeModule={getJSON(){return snapshot;},Section:{OUTPUT:'output'}};
    const child={execFile(file,args,options,callback){calls++;const request=JSON.parse(fs.readFileSync(args[args.indexOf('--request')+1],'utf8'));if(request.operation==='check'){queueMicrotask(()=>callback(null,JSON.stringify({version:backendVersion}),''));return;}assert.equal(request.operation,'convert');assert.equal(request.sourceDirectory,path.join(dir,'src/ui'));assert.equal(request.outputDirectory,path.join(dir,'rust-src'));assert(!('project' in request));queueMicrotask(()=>callback(rustFails?new Error('failure'):null,'{"ok":true}',rustFails?'unsupported widget':''));}};
    const extensionDir=fs.mkdtempSync(path.join(os.tmpdir(),'reez-extension-test-'));t.after(()=>fs.rmSync(extensionDir,{recursive:true,force:true}));
    fs.writeFileSync(path.join(extensionDir,'package.json'),JSON.stringify({id:'reez-rust-output',name:'reez-rust-output',version:'0.3.3'}));fs.writeFileSync(path.join(extensionDir,'c-output-runner.js'),'');fs.mkdirSync(path.join(extensionDir,'backend/runtime/bin'),{recursive:true});fs.writeFileSync(path.join(extensionDir,'backend/runtime/bin/c2rust-transpile'),'');
    const fallback=[];const yarn={async yarnUninstall(name){fallback.push(name);}};
    const registry={extensions:new Map([['reez-rust-output',{installationFolderPath:extensionDir}]])};
    let previousDestroyed=false;
    if(staleAdapter){const unwrapped=build.build;const previous=async()=>{};previous.__reez=true;build.build=previous;registry.extensions.set('reez-rust-output',{version:'0.3.1',installationFolderPath:path.join(extensionDir,'old'),destroy(){previousDestroyed=true;build.build=unwrapped;}});}
    function requireMock(name){if(name==='project-editor/build/build')return build;if(name==='project-editor/store')return storeModule;if(name==='project-editor/core/object')return {MessageType:{ERROR:'error',INFO:'info'}};if(name==='child_process')return child;if(name==='eez-studio-shared/extensions/yarn')return yarn;if(name==='eez-studio-shared/extensions/extensions')return registry;if(name==='eez-studio-shared/extensions/extension-folder')return {getExtensionFolderPath:()=>extensionDir};return require(name)}
    requireMock.cache={};
    const context={__dirname:extensionDir,exports:{},process:{type:'renderer',pid:123,env:{},execPath:'/installed/EEZ Studio'},window:{},console,require:requireMock};
    vm.runInNewContext(source,context);context.exports.install();return {build,store,messages,calls:()=>calls,loaded:()=>loaded,dir,extensionDir,api:context.exports,window:context.window,yarn,registry,fallback,previousDestroyed:()=>previousDestroyed};
}
test('ZIP extension appears as a Project Editor extension with one manifest version', t => {
    const f=fixture(t);
    const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,'../integration/package.json'),'utf8'));
    assert.equal(manifest['eez-studio']['node-module'],true);
    assert.equal(f.api.default.extensionType,'pext');
    assert.equal(f.window.reezOutput.version,'0.3.3');
});
test('version check reports matching adapter/backend and rejects a stale backend', async t => {
    const current=fixture(t);
    const report=JSON.parse(await current.api.checkInstallation(current.store.filePath));
    assert.equal(report.version,'0.3.3');
    assert.equal(report.adapterPath,current.extensionDir);
    const stale=fixture(t,{backendVersion:'0.2.0'});
    await assert.rejects(stale.api.checkInstallation(stale.store.filePath),/adapter 0.3.3 and backend 0.2.0 differ/);
});
test('new adapter replaces an already active older Reez hook', async t => {
    const f=fixture(t,{staleAdapter:true});
    assert.equal(f.previousDestroyed(),true);
    assert.equal(f.window.reezOutput.version,'0.3.3');
    await f.build.build(f.store,'buildFiles');
    assert.equal(f.calls(),1);
});
test('Studio manager removes the ZIP folder and retains Yarn for other extensions', async t => {
    const f=fixture(t);
    await f.yarn.yarnUninstall('some-other-package');
    assert.deepEqual(f.fallback,['some-other-package']);
    assert(fs.existsSync(f.extensionDir));
    await f.yarn.yarnUninstall('reez-rust-output');
    assert(!fs.existsSync(f.extensionDir));
    assert.deepEqual(f.fallback,['some-other-package']);
});
test('a real Yarn Reez install still follows Studio Yarn removal', async t => {
    const f=fixture(t);
    f.registry.extensions.set('reez-rust-output',{installationFolderPath:'/installed/node_modules/reez-rust-output'});
    await f.yarn.yarnUninstall('reez-rust-output');
    assert.deepEqual(f.fallback,['reez-rust-output']);
    assert(fs.existsSync(f.extensionDir));
});
test('both outputs complete before success; snapshot cleaned',async t=>{const f=fixture(t);assert.equal(await f.build.build(f.store,'buildFiles'),123);assert.equal(f.calls(),1);assert.match(f.messages.at(-1)[2],/^Build successfully/);assert.equal(f.loaded(),false);assert.deepEqual(fs.readdirSync(f.dir),['reez.json']);});
test('Rust failure suppresses C success and restores logging',async t=>{const f=fixture(t,{rustFails:true});const write=f.store.outputSectionsStore.write;await f.build.build(f.store,'buildFiles');assert.equal(f.calls(),1);assert(!f.messages.some(m=>m[2].startsWith('Build successfully')));assert(f.messages.some(m=>m[1]==='error'));assert.equal(f.store.outputSectionsStore.write,write);assert.equal(f.loaded(),false);});
test('C failure does not run Rust',async t=>{const f=fixture(t,{cFails:true});await f.build.build(f.store,'buildFiles');assert.equal(f.calls(),0);assert(!f.messages.some(m=>m[2].startsWith('Build successfully')));});
test('changed in-memory project cannot publish mismatched Rust',async t=>{const f=fixture(t,{changed:true});await f.build.build(f.store,'buildFiles');assert.equal(f.calls(),0);assert(f.messages.some(m=>m[2].includes('Project changed')));});
test('check and simulator build bypass output adapter',async t=>{const f=fixture(t);await f.build.build(f.store,'check');await f.build.build(f.store,'buildAssets');assert.equal(f.calls(),0);});
test('overlapping destination is rejected',async t=>{const f=fixture(t);fs.writeFileSync(path.join(f.dir,'reez.json'),JSON.stringify({enabled:true,executable:'reez',output:'src'}));await f.build.build(f.store,'buildFiles');assert.equal(f.calls(),0);assert(f.messages.some(m=>m[2].includes('separate')));});

test('new projects stay opt-in after installing the extension', async t => {
    const f=fixture(t);fs.unlinkSync(path.join(f.dir,'reez.json'));await f.build.build(f.store,'buildFiles');assert.equal(f.calls(),0);
});
test('C backend settings select the Studio bridge without personal paths', t => {
    const f=fixture(t);
    fs.writeFileSync(path.join(f.dir,'reez.json'),JSON.stringify({enabled:true,output:'rust-src'}));
    const c=f.api.config(f.store.filePath);assert.equal(c.executable,'/installed/EEZ Studio');assert.equal(c.environment.ELECTRON_RUN_AS_NODE,'1');assert(c.args[0].endsWith('c-output-runner.js'));
});
test('missing runtime gives a useful installation error', t => {
    const f=fixture(t);fs.rmSync(path.join(f.extensionDir,'backend'),{recursive:true});fs.writeFileSync(path.join(f.dir,'reez.json'),JSON.stringify({enabled:true,output:'rust-src'}));assert.throws(()=>f.api.config(f.store.filePath),/complete Reez extension ZIP/);
});
test('settings save preserves compiler context', t => {
    const f=fixture(t);f.api.writeSettings(f.store.filePath,{enabled:false,output:'custom output',compilationDatabase:'build/compile_commands.json'});
    const c=JSON.parse(fs.readFileSync(path.join(f.dir,'reez.json'),'utf8'));assert.equal(c.compilationDatabase,'build/compile_commands.json');assert.equal(c.enabled,false);assert.equal(c.output,'custom output');
});
test('extension removal restores the original build handler',async t=>{
    const f=fixture(t);f.api.destroy();await f.build.build(f.store,'buildFiles');assert.equal(f.calls(),0);
});

test('settings panel enables a project and saves a portable output folder',t=>{
    const nodes=[];
    function element(tag){const e={tag,children:[],style:{},textContent:'',append(...x){this.children.push(...x);},setAttribute(){},remove(){this.removed=true;}};nodes.push(e);return e;}
    const body=element('body');const document={body,createElement:element,createTextNode:text=>({textContent:text}),getElementById:()=>null};
    const store={filePath:'/projects/example.eez-project'};let settings={enabled:false,output:'rust-src'};let cleared=false;
    const context={exports:{},document,require(){return {tabs:{activeTab:{projectStore:store}}}},setInterval(){return {unref(){}}},clearInterval(){cleared=true;}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../integration/panel.js'),'utf8'),context);
    const api={version:'0.3.3',readSettings(){return settings},writeSettings(_,next){settings=next},async checkInstallation(){return 'reez 0.3.3'}};
    const panel=context.exports.mount(api);const toggle=nodes.find(e=>e.tag==='button');assert.match(toggle.textContent,/OFF/);toggle.onclick();
    nodes.find(e=>e.type==='checkbox').checked=true;nodes.find(e=>e.type==='text').value='custom rust';nodes.find(e=>e.textContent==='Save').onclick();
    assert.equal(settings.enabled,true);assert.equal(settings.output,'custom rust');assert.match(toggle.textContent,/ON/);panel.destroy();assert(cleared);
});
