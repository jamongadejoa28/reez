"""Opt-in tests for the real C translation path, independent of EEZ JSON."""
import importlib.util
import json
from pathlib import Path
import subprocess
import pytest
from conftest import ROOT
spec=importlib.util.spec_from_file_location('c_output',ROOT/'tools/transpile_c_output.py')
backend=importlib.util.module_from_spec(spec);spec.loader.exec_module(backend)
CONVERTER=ROOT/'.tools/c2rust/bin/c2rust'
pytestmark=pytest.mark.skipif(not CONVERTER.exists(),reason='local C2Rust 0.22.1 backend not installed')

def test_c_actions_state_callbacks_and_resources(tmp_path):
    source=ROOT/'tests/fixtures/c-output/actions_and_state.c';driver=source.parent/'driver.c';database=tmp_path/'compile_commands.json'
    database.write_text(json.dumps([{'directory':str(source.parent),'file':str(source),'arguments':['clang','-std=c11','-c',str(source)]}]))
    output=tmp_path/'rust-output';result=backend.transpile(database,output,CONVERTER)
    assert result['input_kind']=='C compilation units' and result['cargo_build_passed']
    subprocess.run(['cc',str(driver),str(source),'-o',str(tmp_path/'c')],check=True)
    subprocess.run(['cc',str(driver),result['static_library'],'-lm','-ldl','-lpthread','-o',str(tmp_path/'rust')],check=True)
    assert subprocess.check_output([str(tmp_path/'c')])==subprocess.check_output([str(tmp_path/'rust')])
    before={str(f.relative_to(output)):f.read_bytes() for f in output.rglob('*') if f.is_file()}
    with pytest.raises(ValueError,match='never overwritten'):backend.transpile(database,output,CONVERTER)
    assert before=={str(f.relative_to(output)):f.read_bytes() for f in output.rglob('*') if f.is_file()}

def test_cpp_is_not_silently_skipped(tmp_path):
    source=tmp_path/'flow.cpp';source.write_text('int action(){return 3;}')
    database=tmp_path/'compile_commands.json';database.write_text(json.dumps([{'directory':str(tmp_path),'file':str(source),'arguments':['clang++','-c',str(source)]}]))
    with pytest.raises(ValueError,match='C\\+\\+'):backend.transpile(database,tmp_path/'rust',CONVERTER)
    assert not (tmp_path/'rust').exists()
