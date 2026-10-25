const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'../integration/index.js'),'utf8');
function fixture(t,{rustFails=false,cFails=false,changed=false}={}) {
    const dir=fs.mkdtempSync(path.join(os.tmpdir(),'reez-studio-test-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
    fs.writeFileSync(path.join(dir,'reez.json'),JSON.stringify({enabled:true,executable:'reez',output:'rust-src'}));
    const messages=[];let calls=0;let snapshot='snapshot';let loaded=false;
    const output={clear(){messages.length=0;},write(...args){messages.push(args);},setLoading(_,v){loaded=v;},getSection(){return {numErrors:messages.filter(m=>m[1]==='error').length}}};
    const store={filePath:path.join(dir,'example.eez-project'),project:{settings:{build:{destinationFolder:'src/ui'}}},outputSectionsStore:output};
    const build={async build(){output.write('output','info','C generated');if(changed)snapshot='changed';if(cFails)output.write('output','error','C failed');output.write('output','info','Build successfully finished at now');return 123;}};
    const storeModule={getJSON(){return snapshot;},Section:{OUTPUT:'output'}};
    const child={execFile(file,args,options,callback){calls++;if(args.includes('--project'))assert.equal(fs.readFileSync(args[args.indexOf('--project')+1],'utf8'),'snapshot');queueMicrotask(()=>callback(rustFails?new Error('failure'):null,'{"ok":true}',rustFails?'unsupported widget':''));}};
    const extensionDir=fs.mkdtempSync(path.join(os.tmpdir(),'reez-extension-test-'));t.after(()=>fs.rmSync(extensionDir,{recursive:true,force:true}));
    const context={__dirname:extensionDir,exports:{},process:{type:'renderer',pid:123,env:{},execPath:'/installed/EEZ Studio'},window:{},console,require(name){if(name==='project-editor/build/build')return build;if(name==='project-editor/store')return storeModule;if(name==='project-editor/core/object')return {MessageType:{ERROR:'error',INFO:'info'}};if(name==='child_process')return child;return require(name)}};
    vm.runInNewContext(source,context);context.exports.install();return {build,store,messages,calls:()=>calls,loaded:()=>loaded,dir,extensionDir,api:context.exports};
}
test('both outputs complete before success; snapshot cleaned',async t=>{const f=fixture(t);assert.equal(await f.build.build(f.store,'buildFiles'),123);assert.equal(f.calls(),1);assert.match(f.messages.at(-1)[2],/^Build successfully/);assert.equal(f.loaded(),false);assert.deepEqual(fs.readdirSync(f.dir),['reez.json']);});
test('Rust failure suppresses C success and restores logging',async t=>{const f=fixture(t,{rustFails:true});const write=f.store.outputSectionsStore.write;await f.build.build(f.store,'buildFiles');assert.equal(f.calls(),1);assert(!f.messages.some(m=>m[2].startsWith('Build successfully')));assert(f.messages.some(m=>m[1]==='error'));assert.equal(f.store.outputSectionsStore.write,write);assert.equal(f.loaded(),false);});
test('C failure does not run Rust',async t=>{const f=fixture(t,{cFails:true});await f.build.build(f.store,'buildFiles');assert.equal(f.calls(),0);assert(!f.messages.some(m=>m[2].startsWith('Build successfully')));});
test('changed in-memory project cannot publish mismatched Rust',async t=>{const f=fixture(t,{changed:true});await f.build.build(f.store,'buildFiles');assert.equal(f.calls(),0);assert(f.messages.some(m=>m[2].includes('Project changed')));});
test('check and simulator build bypass output adapter',async t=>{const f=fixture(t);await f.build.build(f.store,'check');await f.build.build(f.store,'buildAssets');assert.equal(f.calls(),0);});
test('overlapping destination is rejected',async t=>{const f=fixture(t);fs.writeFileSync(path.join(f.dir,'reez.json'),JSON.stringify({enabled:true,executable:'reez',output:'src'}));await f.build.build(f.store,'buildFiles');assert.equal(f.calls(),0);assert(f.messages.some(m=>m[2].includes('separate')));});

test('new projects stay opt-in after installing the extension', async t => {
    const f=fixture(t);fs.unlinkSync(path.join(f.dir,'reez.json'));await f.build.build(f.store,'buildFiles');assert.equal(f.calls(),0);
});
test('portable settings select EEZ runtime and do not require personal paths', t => {
    const f=fixture(t);fs.mkdirSync(path.join(f.extensionDir,'bin'));fs.writeFileSync(path.join(f.extensionDir,'bin/reez.wasm'),'wasm');
    const converter=path.join(f.extensionDir,'node_modules/lv_font_conv');fs.mkdirSync(converter,{recursive:true});fs.writeFileSync(path.join(converter,'lv_font_conv.js'),'');
    fs.writeFileSync(path.join(f.dir,'reez.json'),JSON.stringify({enabled:true,output:'rust-src'}));
    const c=f.api.config(f.store.filePath);assert.equal(c.executable,'/installed/EEZ Studio');assert.equal(c.environment.ELECTRON_RUN_AS_NODE,'1');assert(c.args[0].endsWith('wasi-runner.js'));
});
test('missing runtime gives a useful installation error', t => {
    const f=fixture(t);fs.writeFileSync(path.join(f.dir,'reez.json'),JSON.stringify({enabled:true,output:'rust-src'}));assert.throws(()=>f.api.config(f.store.filePath),/complete Reez extension ZIP/);
});
test('settings save preserves explicit legacy launchers', t => {
    const f=fixture(t);f.api.writeSettings(f.store.filePath,{enabled:false,output:'custom output'});
    const c=JSON.parse(fs.readFileSync(path.join(f.dir,'reez.json'),'utf8'));assert.equal(c.executable,'reez');assert.equal(c.enabled,false);assert.equal(c.output,'custom output');
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
    const api={version:'0.2.0',readSettings(){return settings},writeSettings(_,next){settings=next},async checkInstallation(){return 'reez 0.2.0'}};
    const panel=context.exports.mount(api);const toggle=nodes.find(e=>e.tag==='button');assert.match(toggle.textContent,/OFF/);toggle.onclick();
    nodes.find(e=>e.type==='checkbox').checked=true;nodes.find(e=>e.type==='text').value='custom rust';nodes.find(e=>e.textContent==='Save').onclick();
    assert.equal(settings.enabled,true);assert.equal(settings.output,'custom rust');assert.match(toggle.textContent,/ON/);panel.destroy();assert(cleared);
});
