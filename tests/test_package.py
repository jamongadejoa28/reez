import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
import pytest
from conftest import ROOT
spec=importlib.util.spec_from_file_location('reez_installer',ROOT/'tools/install_studio.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
VERSION=json.loads((ROOT/'integration/package.json').read_text())['version']
ARCHIVE=Path(os.environ.get('REEZ_PACKAGE',ROOT/f'artifacts/releases/reez-rust-output-{VERSION}.zip'))
@pytest.fixture
def archive():
    if not ARCHIVE.exists():pytest.skip('build the extension ZIP first')
    return ARCHIVE

def test_release_contents(archive):
    with zipfile.ZipFile(archive) as z:
        names=set(z.namelist())
        assert {'package.json','index.js','panel.js','c-output-runner.js','backend/convert.py','backend/runtime/bin/c2rust-transpile','backend/sdk/lvgl/lvgl.h','backend/sources/SOURCES.json','source/integration/backend/convert.py'}<=names
        assert z.read('backend/runtime/bin/c2rust-transpile').startswith(b'\x7fELF')
        assert 'bin/reez.wasm' not in names and 'reez.json' not in names
        package=json.loads(z.read('package.json'))
        assert package['version']==VERSION
        assert package['eez-studio'].get('node-module') is True
        assert not package['eez-studio'].get('main')
        manifest=json.loads(z.read('backend/runtime-manifest.json'))
        import hashlib
        for name,value in manifest['runtime_files'].items():assert hashlib.sha256(z.read('backend/'+name)).hexdigest()==value,name

def test_install_upgrade_and_configuration_preservation(archive,tmp_path):
    extensions=tmp_path/'unrelated user'/'extensions'
    other=extensions/'other-extension';other.mkdir(parents=True);(other/'user.txt').write_text('keep')
    dest=installer.install(archive,extensions);assert (dest/'backend/convert.py').is_file()
    (dest/'old-release-marker').write_text('old')
    installer.install(archive,extensions);assert not (dest/'old-release-marker').exists();assert (other/'user.txt').read_text()=='keep'

def test_legacy_yarn_install_cannot_reappear_after_migration(tmp_path):
    extensions=tmp_path/'extensions';extensions.mkdir()
    root=extensions/'package.json'
    root.write_text(json.dumps({'name':'extensions','dependencies':{'reez-rust-output':'0.2.0','other-extension':'1.0.0'}}))
    legacy=extensions/'node_modules/reez-rust-output';legacy.mkdir(parents=True)
    (legacy/'package.json').write_text(json.dumps({'id':'reez-rust-output','version':'0.2.0'}))
    other=extensions/'node_modules/other-extension';other.mkdir()
    (other/'keep.txt').write_text('keep')
    installer.remove_legacy_registration(extensions)
    assert json.loads(root.read_text())['dependencies']=={'other-extension':'1.0.0'}
    assert (extensions/'package.json.before-reez').is_file()
    assert not legacy.exists()
    assert (other/'keep.txt').read_text()=='keep'

def test_duplicate_releases_are_removed_without_touching_other_extensions(tmp_path):
    extensions=tmp_path/'extensions';extensions.mkdir()
    root=extensions/'package.json'
    root.write_text(json.dumps({'dependencies':{'reez-rust-output':'0.3.1','reez-old-name':'0.2.0','other-extension':'1.0.0'}}))
    current=extensions/'reez-rust-output';current.mkdir()
    (current/'package.json').write_text(json.dumps({'id':'reez-rust-output','name':'reez-rust-output','version':VERSION}))
    direct=extensions/'reez-copy-old';direct.mkdir()
    (direct/'package.json').write_text(json.dumps({'id':'reez-rust-output','name':'reez-rust-output','version':'0.3.1'}))
    yarn=extensions/'node_modules/reez-old-name';yarn.mkdir(parents=True)
    (yarn/'package.json').write_text(json.dumps({'id':'reez-rust-output','name':'reez-old-name','version':'0.2.0'}))
    unrelated=extensions/'other-extension';unrelated.mkdir()
    (unrelated/'package.json').write_text(json.dumps({'id':'other-extension','name':'other-extension'}))
    installer.remove_legacy_registration(extensions,keep=current)
    assert current.exists()
    assert not direct.exists() and not yarn.exists()
    assert unrelated.exists()
    assert json.loads(root.read_text())['dependencies']=={'other-extension':'1.0.0'}

@pytest.mark.skipif(sys.platform!='linux' or not shutil.which('powershell.exe') or not shutil.which('wslpath'),reason='Windows PowerShell via WSL required')
def test_windows_installer_replaces_duplicate_release_and_uninstalls(request):
    windows_temp=subprocess.check_output(['powershell.exe','-NoProfile','-Command','$env:TEMP'],text=True).strip()
    linux_temp=subprocess.check_output(['wslpath','-u',windows_temp],text=True).strip()
    tmp_path=Path(tempfile.mkdtemp(prefix='reez-install-test-',dir=linux_temp))
    request.addfinalizer(lambda: shutil.rmtree(tmp_path,ignore_errors=True))
    source=tmp_path/'downloaded';source.mkdir()
    shutil.copy2(ROOT/'integration/install.ps1',source/'install.ps1')
    (source/'package.json').write_text(json.dumps({'id':'reez-rust-output','name':'reez-rust-output','version':VERSION}))
    runtime=source/'backend/runtime/bin';runtime.mkdir(parents=True)
    (runtime/'c2rust-transpile').write_text('fixture')
    extensions=tmp_path/'profile/extensions';extensions.mkdir(parents=True)
    root=extensions/'package.json'
    root.write_text(json.dumps({'dependencies':{'reez-rust-output':'0.3.1','reez-old-name':'0.2.0','other-extension':'1.0.0'}}))
    for folder,name,version in [
        (extensions/'reez-rust-output','reez-rust-output','0.3.1'),
        (extensions/'reez-copy-old','reez-rust-output','0.3.1'),
        (extensions/'node_modules/reez-old-name','reez-old-name','0.2.0')]:
        folder.mkdir(parents=True)
        (folder/'package.json').write_text(json.dumps({'id':'reez-rust-output','name':name,'version':version}))
    other=extensions/'other-extension';other.mkdir()
    (other/'keep.txt').write_text('keep')
    def winpath(path):
        return subprocess.check_output(['wslpath','-w',str(path)],text=True).strip()
    command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',winpath(source/'install.ps1'),'-ExtensionsPath',winpath(extensions)]
    installed=subprocess.run(command,capture_output=True,encoding='utf-8',errors='replace')
    assert installed.returncode==0,installed.stderr+installed.stdout
    current=extensions/'reez-rust-output'
    assert json.loads((current/'package.json').read_text())['version']==VERSION
    assert not (extensions/'reez-copy-old').exists()
    assert not (extensions/'node_modules/reez-old-name').exists()
    assert json.loads(root.read_text())['dependencies']=={'other-extension':'1.0.0'}
    assert (other/'keep.txt').read_text()=='keep'
    removed=subprocess.run(command+['-Uninstall'],capture_output=True,encoding='utf-8',errors='replace')
    assert removed.returncode==0,removed.stderr+removed.stdout
    assert not current.exists()
    assert (other/'keep.txt').read_text()=='keep'

def test_remove_cleans_folder_and_yarn_registration(tmp_path):
    extensions=tmp_path/'extensions';extensions.mkdir()
    (extensions/'package.json').write_text(json.dumps({'dependencies':{'reez-rust-output':'0.2.0'}}))
    current=extensions/'reez-rust-output';current.mkdir()
    (current/'package.json').write_text(json.dumps({'id':'reez-rust-output','version':VERSION}))
    installer.remove(extensions)
    assert not current.exists()
    assert 'reez-rust-output' not in json.loads((extensions/'package.json').read_text())['dependencies']

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

def test_relocated_package_converts_c_and_compiles_rust(archive,tmp_path):
    folder=tmp_path/'한글 extension with spaces';folder.mkdir()
    with zipfile.ZipFile(archive) as z:z.extractall(folder)
    source=folder/'C outputs';source.mkdir();shutil.copy2(ROOT/'tests/fixtures/c-output/actions_and_state.c',source)
    out=folder/'Rust outputs';request=folder/'request.json'
    request.write_text(json.dumps({'sourceDirectory':str(source),'outputDirectory':str(out),'projectDirectory':str(folder),'settings':{}}))
    result=subprocess.run(['node',str(folder/'c-output-runner.js'),'--request',str(request)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout)
    assert report['rustCompileChecked'] and report['translationUnits']==1
    assert 'action' in (out/'src/actions_and_state.rs').read_text()
