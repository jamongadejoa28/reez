import copy
import json
import os
from pathlib import Path
import subprocess
import pytest
from conftest import ROOT,PROJECT
BIN=ROOT/'target/debug/reez'
@pytest.fixture
def project(tmp_path):
    data=json.loads((ROOT/'tests/fixtures/minimal.eez-project').read_text());data['fonts']=[]
    for page in data['userPages']:
        def walk(w):
            for states in w['localStyles']['definition'].values():
                for props in states.values():props.pop('text_font',None)
            for child in w['children']:walk(child)
        walk(page['components'][0])
    path=tmp_path/'input.eez-project';path.write_text(json.dumps(data))
    return path,data,tmp_path/'rust-src'
def run(path,out,check=False):
    return subprocess.run([str(BIN),'--project',str(path),'--out',str(out),*(['--check'] if check else [])],capture_output=True,text=True)
def test_deterministic_and_user_files(project):
    path,data,out=project
    assert run(path,out).returncode==0
    (out/'application.rs').write_text('// user code')
    before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in out.iterdir()}
    assert run(path,out).returncode==0
    assert before=={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in out.iterdir()}
def test_stale_managed_file_removed(project):
    path,_,out=project;assert run(path,out).returncode==0
    manifest=out/'.reez-manifest.json';d=json.loads(manifest.read_text());d['files'].append('obsolete.rs');manifest.write_text(json.dumps(d));(out/'obsolete.rs').write_text('old');(out/'user.rs').write_text('keep')
    assert run(path,out).returncode==0
    assert not (out/'obsolete.rs').exists() and (out/'user.rs').read_text()=='keep'
@pytest.mark.parametrize('change', ['flow','widget','style','expression','collision','flags','unknown_property','nul','font','action'])
def test_rejects_unsupported_without_changing_output(project,change):
    path,d,out=project;assert run(path,out).returncode==0
    before={p.name:p.read_bytes() for p in out.iterdir()};screen=d['userPages'][0]['components'][0];label=screen['children'][0]
    if change=='flow':d['settings']['general']['flowSupport']=True
    elif change=='widget':label['type']='LVGLChartWidget'
    elif change=='style':label['localStyles']['definition']['MAIN']['DEFAULT']['bg_gradient']='foo'
    elif change=='expression':label['textType']='expression'
    elif change=='collision':label['identifier']=screen['identifier'].upper()
    elif change=='flags':label['widgetFlags']='TYPO_FLAG'
    elif change=='unknown_property':label['layout']='GRID'
    elif change=='nul':label['text']='a\0b'
    elif change=='font':label['localStyles']['definition']['MAIN']['DEFAULT']['text_font']='missing'
    elif change=='action':d['actions']=[{'name':'test'}]
    path.write_text(json.dumps(d));p=run(path,out);assert p.returncode!=0;assert json.loads(p.stderr)['path'];assert before=={p.name:p.read_bytes() for p in out.iterdir()}
def test_unowned_file_not_overwritten(project):
    path,_,out=project;out.mkdir();(out/'mod.rs').write_text('user');assert run(path,out).returncode!=0;assert (out/'mod.rs').read_text()=='user'
def test_check_does_not_write(project):
    path,_,out=project;assert run(path,out,True).returncode==0;assert not out.exists()
def test_rust_escaping_and_keywords(project):
    path,d,out=project;label=d['userPages'][0]['components'][0]['children'][0];label['identifier']='type';label['text']='한글 " quote \\ tab\t\n';path.write_text(json.dumps(d));assert run(path,out).returncode==0
    s=(out/'screens.rs').read_text();assert 'o_type' in s and '\\" quote \\\\ tab\\t\\n' in s
@pytest.mark.parametrize('destination',['.','src/ui','src','../'])
def test_refuses_output_overlap(project,destination):
    path,_,_=project;assert run(path,path.parent/destination).returncode!=0;assert path.exists()
def test_manifest_traversal_rejected(project):
    path,_,out=project;out.mkdir();(out/'.reez-manifest.json').write_text(json.dumps({'schema':1,'files':['../input.eez-project']}));assert run(path,out).returncode!=0;assert path.exists()

def test_generated_ui_compiles_without_std(project,tmp_path):
    path,_,out=project;assert run(path,out).returncode==0
    wrapper=tmp_path/'nostd.rs';wrapper.write_text('#![no_std]\n#[path='+json.dumps(str(out/'mod.rs'))+'] pub mod ui;\n')
    result=subprocess.run(['rustc','--edition=2024','--crate-type=rlib','--emit=metadata','--extern',f'reez_lvgl={ROOT}/target/debug/libreez_lvgl.rlib','-L',f'dependency={ROOT}/target/debug/deps',str(wrapper),'-o',str(tmp_path/'nostd.rmeta')],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
