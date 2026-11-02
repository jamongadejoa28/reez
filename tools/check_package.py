"""Execute the relocated ZIP through Windows EEZ Electron and the WSL bridge."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile
ROOT=Path(__file__).resolve().parents[1]
VERSION=json.loads((ROOT/'integration/package.json').read_text())['version']
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--zip',type=Path,default=ROOT/f'artifacts/releases/reez-rust-output-{VERSION}.zip')
p.add_argument('--studio',default='/mnt/c/Users/hajun/AppData/Local/Programs/eezstudio/EEZ Studio.exe')
p.add_argument('--source',type=Path,default=Path('/mnt/c/Users/hajun/eez-projects/esp32-s3-monitor-sim/src/ui'))
a=p.parse_args()
def windows(path):return subprocess.check_output(['wslpath','-w',str(path)],text=True).strip()
with tempfile.TemporaryDirectory(prefix='reez 배포 test ',dir='/mnt/c/Users/hajun/AppData/Local/Temp') as temp:
    folder=Path(temp)
    with zipfile.ZipFile(a.zip) as z:z.extractall(folder)
    env={**os.environ,'ELECTRON_RUN_AS_NODE':'1','NODE_NO_WARNINGS':'1'}
    env['WSLENV']=env.get('WSLENV','')+':ELECTRON_RUN_AS_NODE:NODE_NO_WARNINGS'
    reports=[]
    requests=[{'operation':'check','settings':{}},{'operation':'convert','sourceDirectory':windows(a.source),'outputDirectory':windows(folder/'Rust 출력'),'projectDirectory':windows(folder),'settings':{}}]
    for request in requests:
        file=folder/'request.json';file.write_text(json.dumps(request))
        r=subprocess.run([a.studio,windows(folder/'c-output-runner.js'),'--request',windows(file)],capture_output=True,env=env,timeout=660)
        stdout=r.stdout.decode('utf8','replace');stderr=r.stderr.decode('utf8','replace')
        if r.returncode:raise SystemExit('Windows packaged backend failed:\n'+stdout+'\n'+stderr)
        reports.append(json.loads(stdout))
    assert reports[1]['inputKind']=='generated-c' and reports[1]['rustCompileChecked']
    evidence=ROOT/'artifacts/c-output-validation';evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'windows-relocation.json').write_text(json.dumps({'windows_electron_wsl_bridge':True,'unicode_space_paths':True,'rustCompileChecked':True,'translationUnits':reports[1]['translationUnits'],'version':reports[0]['version']},indent=2)+'\n')
    print('Windows relocated ZIP: C translation, Rust compilation, Unicode/space paths and bridge passed')
