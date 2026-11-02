"""Install a release ZIP for the current EEZ Studio user; no app binary changes."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXTENSION_ID = 'reez-rust-output'
VERSION = json.loads((ROOT/'integration/package.json').read_text())['version']

def default_extensions():
    if sys.platform == 'win32':return Path(os.environ['APPDATA'])/'eezstudio/extensions'
    if sys.platform == 'darwin':return Path.home()/'Library/Application Support/eezstudio/extensions'
    release=Path('/proc/sys/kernel/osrelease')
    if release.exists() and 'microsoft' in release.read_text().lower():
        shell='/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'
        command='[Console]::OutputEncoding = [Text.UTF8Encoding]::new(); [Environment]::GetFolderPath("ApplicationData")'
        windows=subprocess.check_output([shell,'-NoProfile','-Command',command],text=True).strip()
        return Path(subprocess.check_output(['wslpath','-u',windows],text=True).strip())/'eezstudio/extensions'
    return Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'eezstudio/extensions'

def assert_reez_folder(folder):
    if folder.exists():
        manifest=folder/'package.json'
        data=json.loads(manifest.read_text()) if manifest.is_file() else {}
        if data.get('id')!=EXTENSION_ID and not (not data.get('id') and data.get('name')==EXTENSION_ID):
            raise ValueError(f'Refusing to replace a different extension: {folder}')

def reez_folders(extensions):
    """Find top-level ZIP and Yarn installs without searching package contents."""
    extensions=Path(extensions)
    candidates=[]
    if extensions.is_dir():
        candidates.extend(p for p in extensions.iterdir() if p.is_dir() and p.name not in ('cache','node_modules'))
    modules=extensions/'node_modules'
    if modules.is_dir():
        for p in modules.iterdir():
            if p.is_dir() and p.name.startswith('@'):
                candidates.extend(child for child in p.iterdir() if child.is_dir())
            elif p.is_dir():candidates.append(p)
    result=[]
    for folder in candidates:
        manifest=folder/'package.json'
        if not manifest.is_file():continue
        data=json.loads(manifest.read_text())
        if data.get('id')==EXTENSION_ID or (not data.get('id') and data.get('name')==EXTENSION_ID):
            if folder.is_symlink():raise ValueError(f'Refusing to remove a linked extension folder: {folder}')
            result.append((folder,data.get('name',EXTENSION_ID)))
    return result

def remove_legacy_registration(extensions,keep=None):
    """Remove duplicate Reez folders and Yarn entries, preserving other apps."""
    extensions=Path(extensions)
    folders=reez_folders(extensions)
    names={EXTENSION_ID}
    names.update(name for folder,name in folders if folder.is_relative_to(extensions/'node_modules'))
    root=extensions/'package.json'
    if root.is_file():
        data=json.loads(root.read_text())
        dependencies=data.get('dependencies') or {}
        if any(name in dependencies for name in names):
            for name in names:dependencies.pop(name,None)
            data['dependencies']=dependencies
            backup=root.with_name(root.name+'.before-reez')
            if not backup.exists():shutil.copy2(root,backup)
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf8',dir=root.parent,prefix='.reez-package-',delete=False) as file:
                json.dump(data,file,indent=2);file.write('\n');staged=Path(file.name)
            staged.replace(root)
    removed=[]
    for folder,_ in folders:
        if keep is not None and folder.resolve()==Path(keep).resolve():continue
        shutil.rmtree(folder);removed.append(folder)
    return removed

def remove(extensions):
    extensions=Path(extensions)
    remove_legacy_registration(extensions)

def install(archive,extensions):
    extensions=Path(extensions);cache=extensions/'cache';cache.mkdir(parents=True,exist_ok=True)
    destination=extensions/EXTENSION_ID
    with tempfile.TemporaryDirectory(prefix='reez-install-',dir=cache) as temp:
        stage=Path(temp)/'extension';stage.mkdir();backup=Path(temp)/'previous'
        with zipfile.ZipFile(archive) as z:
            manifest=json.loads(z.read('package.json'))
            if manifest.get('id') != EXTENSION_ID:raise ValueError('Not a Reez extension ZIP')
            for entry in z.infolist():
                parts=PurePosixPath(entry.filename).parts
                if not parts or entry.filename.startswith('/') or '..' in parts or '\\' in entry.filename or ':' in parts[0]:raise ValueError('Unsafe ZIP path')
            z.extractall(stage)
        for required in ['index.js','panel.js','c-output-runner.js','backend/convert.py','backend/runtime/bin/c2rust-transpile','backend/sdk/lvgl/lvgl.h']:
            if not (stage/required).is_file():raise ValueError(f'Incomplete extension ZIP: {required}')
        assert_reez_folder(destination)
        remove_legacy_registration(extensions,keep=destination)
        if destination.exists():destination.rename(backup)
        try:stage.rename(destination)
        except Exception:
            if backup.exists():backup.rename(destination)
            raise
    return destination

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',type=Path,default=ROOT/f'artifacts/releases/reez-rust-output-{VERSION}.zip')
    p.add_argument('--extensions',type=Path)
    p.add_argument('--project',type=Path)
    p.add_argument('--use-bundled',action='store_true',help='Migrate legacy JSON-generator settings to the C backend')
    p.add_argument('--remove',action='store_true')
    a=p.parse_args();extensions=a.extensions or default_extensions()
    if a.remove:
        remove(extensions)
        print('Removed Reez; restart Studio. Project files were preserved.');return
    print('Installed:',install(a.package,extensions))
    if a.project:
        config=a.project.parent/'reez.json'
        previous=json.loads(config.read_text()) if config.exists() else {}
        if not config.exists() or a.use_bundled:
            if config.exists() and any(k in previous for k in ['executable','args','wslDistro','environment']):
                backup=config.with_suffix('.json.before-portable');shutil.copy2(config,backup)
            c={k:v for k,v in previous.items() if k not in ('executable','args','environment')}
            c.update(enabled=previous.get('enabled',True),output=previous.get('output','rust-src'))
            config.write_text(json.dumps(c,indent=2)+'\n')
        print('Project config:',config)
    print('Restart Studio, then enable each project in the Rust output panel.')
if __name__=='__main__':main()
