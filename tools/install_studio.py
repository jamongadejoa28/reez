"""Install a release ZIP for the current EEZ Studio user; no app binary changes."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXTENSION_ID = 'reez-rust-output'

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

def install(archive,extensions):
    extensions=Path(extensions);cache=extensions/'cache';cache.mkdir(parents=True,exist_ok=True)
    destination=extensions/EXTENSION_ID
    with tempfile.TemporaryDirectory(prefix='reez-install-',dir=cache) as temp:
        stage=Path(temp)/'extension';stage.mkdir();backup=Path(temp)/'previous'
        with zipfile.ZipFile(archive) as z:
            manifest=json.loads(z.read('package.json'))
            if manifest.get('id') != EXTENSION_ID:raise ValueError('Not a Reez extension ZIP')
            for entry in z.infolist():
                target=(stage/entry.filename).resolve()
                if not target.is_relative_to(stage.resolve()) or '\\' in entry.filename:raise ValueError('Unsafe ZIP path')
            z.extractall(stage)
        for required in ['index.js','panel.js','wasi-runner.js','bin/reez.wasm','node_modules/lv_font_conv/lv_font_conv.js']:
            if not (stage/required).is_file():raise ValueError(f'Incomplete extension ZIP: {required}')
        if destination.exists():destination.rename(backup)
        try:stage.rename(destination)
        except Exception:
            if backup.exists():backup.rename(destination)
            raise
    return destination

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',type=Path,default=ROOT/'artifacts/releases/reez-rust-output-0.2.0.zip')
    p.add_argument('--extensions',type=Path)
    p.add_argument('--project',type=Path)
    p.add_argument('--use-bundled',action='store_true',help='Replace an explicit legacy launcher with the portable runtime')
    p.add_argument('--remove',action='store_true')
    a=p.parse_args();extensions=a.extensions or default_extensions()
    if a.remove:
        destination=extensions/EXTENSION_ID
        if destination.exists():shutil.rmtree(destination)
        print('Removed Reez; restart Studio. Project files were preserved.');return
    print('Installed:',install(a.package,extensions))
    if a.project:
        config=a.project.parent/'reez.json'
        previous=json.loads(config.read_text()) if config.exists() else {}
        if not config.exists() or a.use_bundled:
            if config.exists() and any(k in previous for k in ['executable','args','wslDistro','environment']):
                backup=config.with_suffix('.json.before-portable');shutil.copy2(config,backup)
            c={'enabled':previous.get('enabled',True),'output':previous.get('output','rust-src')}
            config.write_text(json.dumps(c,indent=2)+'\n')
        print('Project config:',config)
    print('Restart Studio, then enable each project in the Rust output panel.')
if __name__=='__main__':main()
