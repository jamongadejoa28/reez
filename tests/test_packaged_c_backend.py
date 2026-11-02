"""Behavior and publication tests for the actual extension backend."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import pytest
from conftest import ROOT

spec=importlib.util.spec_from_file_location('extension_backend',ROOT/'integration/backend/convert.py')
backend=importlib.util.module_from_spec(spec);spec.loader.exec_module(backend)
RUNTIME=ROOT/'artifacts/c-backend-runtime'
pytestmark=pytest.mark.skipif(not (RUNTIME/'runtime/bin/c2rust-transpile').exists(),reason='build the pinned backend first')

@pytest.fixture
def conversion(tmp_path,monkeypatch):
    # Backend source remains live; resources are the exact release resources.
    stage=tmp_path/'backend';stage.mkdir()
    for p in RUNTIME.iterdir():(stage/p.name).symlink_to(p,target_is_directory=p.is_dir())
    shutil.copy2(ROOT/'integration/backend/generated-Cargo.lock',stage/'generated-Cargo.lock')
    monkeypatch.setattr(backend,'BASE',stage)
    source=tmp_path/'generated C';source.mkdir()
    shutil.copy2(ROOT/'tests/fixtures/c-output/actions_and_state.c',source)
    output=tmp_path/'Rust 출력'
    return {'sourceDirectory':str(source),'outputDirectory':str(output),'projectDirectory':str(tmp_path),'settings':{}},source,output

def test_actions_callbacks_state_resources_and_atomic_failure(conversion,tmp_path):
    request,source,output=conversion
    original={p.name:p.read_bytes() for p in source.iterdir()}
    report=backend.convert(request)
    assert report['translationUnits']==1 and report['rustCompileChecked'] and report['inputKind']=='generated-c'
    assert original=={p.name:p.read_bytes() for p in source.iterdir()}
    library=Path(report['staticLibrary'])
    driver=ROOT/'tests/fixtures/c-output/driver.c'
    subprocess.run(['cc',str(driver),str(source/'actions_and_state.c'),'-o',str(tmp_path/'C')],check=True)
    subprocess.run(['cc',str(driver),str(library),'-lm','-ldl','-lpthread','-o',str(tmp_path/'Rust')],check=True)
    assert subprocess.check_output([str(tmp_path/'C')])==subprocess.check_output([str(tmp_path/'Rust')])
    (output/'my_logic.rs').write_text('// keep user logic')
    # Native C body changes drive Rust output changes, with no EEZ JSON involved.
    file=source/'actions_and_state.c';file.write_text(file.read_text()+'\nint another_action(void){return 91;}\n')
    revised=backend.convert(request)
    assert revised['crateName']==report['crateName']
    assert 'another_action' in (output/'src/actions_and_state.rs').read_text()
    assert (output/'my_logic.rs').read_text()=='// keep user logic'
    before={str(p.relative_to(output)):p.read_bytes() for p in output.rglob('*') if p.is_file()}
    file.write_text('broken invalid C input !')
    with pytest.raises(RuntimeError,match='C translation failed'):backend.convert(request)
    assert before=={str(p.relative_to(output)):p.read_bytes() for p in output.rglob('*') if p.is_file()}

def test_database_must_cover_all_and_cpp_never_skipped(conversion,tmp_path):
    request,source,output=conversion
    db=tmp_path/'compile_commands.json';db.write_text('[]');request['settings']['compilationDatabase']=str(db)
    with pytest.raises(ValueError,match='No generated C'):backend.convert(request)
    (source/'flow.cpp').write_text('int flow(){return 1;}')
    with pytest.raises(ValueError,match=r'C\+\+'):backend.convert(request)
    assert not output.exists()

def test_user_owned_collision_and_symlink_rejected(conversion,tmp_path):
    request,source,output=conversion
    output.mkdir();(output/'Cargo.toml').write_text('user file')
    with pytest.raises(ValueError,match='user-owned'):backend.convert(request)
    assert (output/'Cargo.toml').read_text()=='user file'
    (output/'Cargo.toml').unlink()
    outside=tmp_path/'outside';outside.mkdir();(output/'src').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match='symlink'):backend.convert(request)
    assert list(outside.iterdir())==[]

def test_translated_logic_as_no_std_cortex_m_dependency(conversion,tmp_path):
    libdir=subprocess.check_output(['rustc','--print','target-libdir','--target','thumbv7em-none-eabihf'],text=True).strip()
    if not list(Path(libdir).glob('libcore-*')):pytest.skip('Cortex-M Rust target not installed')
    request,source,output=conversion
    (source/'actions_and_state.c').write_text('unsigned state; unsigned action(unsigned x){state+=x;return state;}')
    report=backend.convert(request)
    consumer=tmp_path/'consumer';consumer.mkdir()
    (consumer/'lib.rs').write_text('#![no_std]\npub unsafe fn run(x:u32)->u32 { unsafe { ui::src::actions_and_state::action(x) } }')
    (consumer/'Cargo.toml').write_text('[workspace]\n[package]\nname="reez_embedded_check"\nversion="0.0.0"\nedition="2024"\n[lib]\npath="lib.rs"\n[dependencies.ui]\npackage="'+report['crateName']+'"\npath='+json.dumps(str(output))+'\ndefault-features=false\n')
    import os
    env={**os.environ,'CARGO_TARGET_DIR':str(ROOT/'target/c-output-nostd')}
    subprocess.run(['cargo','generate-lockfile','--offline','--manifest-path',str(consumer/'Cargo.toml')],env=env,check=True,capture_output=True)
    subprocess.run(['cargo','check','--offline','--locked','--target','thumbv7em-none-eabihf','--manifest-path',str(consumer/'Cargo.toml')],env=env,check=True,capture_output=True)
