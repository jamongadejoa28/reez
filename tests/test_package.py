import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
import pytest
from conftest import ROOT

spec=importlib.util.spec_from_file_location('reez_installer',ROOT/'tools/install_studio.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
ARCHIVE=ROOT/'artifacts/releases/reez-rust-output-0.2.0.zip'

@pytest.fixture
def archive():
    if not ARCHIVE.exists():pytest.skip('build the extension ZIP first')
    return ARCHIVE

def test_release_contents(archive):
    with zipfile.ZipFile(archive) as z:
        names=set(z.namelist())
        assert {'package.json','index.js','panel.js','wasi-runner.js','bin/reez.wasm','install.ps1','licenses/CRATES.txt','source/crates/reez/src/lib.rs'}<=names
        assert z.read('bin/reez.wasm').startswith(b'\0asm')
        assert not any(n.endswith(('.exe','.dll')) or n=='reez.json' for n in names)
        assert json.loads(z.read('package.json'))['eez-studio']['node-module'] is True

def test_install_upgrade_and_configuration_preservation(archive,tmp_path):
    extensions=tmp_path/'unrelated user'/'extensions'
    other=extensions/'other-extension';other.mkdir(parents=True);(other/'user.txt').write_text('keep')
    dest=installer.install(archive,extensions);assert (dest/'bin/reez.wasm').is_file()
    (dest/'old-release-marker').write_text('old')
    installer.install(archive,extensions);assert not (dest/'old-release-marker').exists();assert (other/'user.txt').read_text()=='keep'

def test_install_rollback_on_locked_destination(archive,tmp_path,monkeypatch):
    dest=installer.install(archive,tmp_path);(dest/'old-release-marker').write_text('keep')
    rename=Path.rename
    def locked(self,target):
        if self.name=='extension':raise PermissionError('destination in use')
        return rename(self,target)
    monkeypatch.setattr(Path,'rename',locked)
    with pytest.raises(PermissionError):installer.install(archive,tmp_path)
    assert (dest/'old-release-marker').read_text()=='keep'

def test_rejects_zip_traversal(tmp_path):
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('package.json',json.dumps({'id':'reez-rust-output'}));z.writestr('../escaped.txt','no')
    with pytest.raises(ValueError,match='Unsafe'):installer.install(archive,tmp_path/'extensions')
    assert not (tmp_path/'escaped.txt').exists()

def test_package_runs_after_relocation_without_external_tools(archive,tmp_path):
    folder=tmp_path/'한글 extension with spaces';folder.mkdir()
    with zipfile.ZipFile(archive) as z:z.extractall(folder)
    project=folder/'sample.eez-project';shutil.copy2(ROOT/'tests/fixtures/minimal.eez-project',project)
    out=folder/'generated rust'
    env={**os.environ,'PATH':'','NODE_NO_WARNINGS':'1'}
    result=subprocess.run([shutil.which('node'),str(folder/'wasi-runner.js'),'--project',str(project),'--out',str(out)],env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['output']==str(out)
    assert (out/'screens.rs').exists()
    before={f.name:f.read_bytes() for f in out.iterdir()}
    data=json.loads(project.read_text());data['userPages'][0]['components'][0]['children'][0]['recolor']=True;project.write_text(json.dumps(data))
    result=subprocess.run([shutil.which('node'),str(folder/'wasi-runner.js'),'--project',str(project),'--out',str(out)],env=env,capture_output=True,text=True)
    assert result.returncode!=0 and 'recolor' in result.stderr
    assert before=={f.name:f.read_bytes() for f in out.iterdir()}
