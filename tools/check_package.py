"""Smoke-test a release ZIP in Windows using only EEZ Studio's bundled runtime."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--zip',type=Path,default=ROOT/'artifacts/releases/reez-rust-output-0.2.0.zip')
p.add_argument('--studio',default='/mnt/c/Users/hajun/AppData/Local/Programs/eezstudio/EEZ Studio.exe')
p.add_argument('--project',type=Path,default=Path('/mnt/c/Users/hajun/eez-projects/esp32-s3-monitor-sim/esp32-s3-monitor-sim.eez-project'))
a=p.parse_args()
def windows(path):return subprocess.check_output(['wslpath','-w',str(path)],text=True).strip()
with tempfile.TemporaryDirectory(prefix='reez 배포 test ',dir='/mnt/c/Users/hajun/AppData/Local/Temp') as temp:
    folder=Path(temp)
    with zipfile.ZipFile(a.zip) as z:z.extractall(folder)
    env={**os.environ,'ELECTRON_RUN_AS_NODE':'1','NODE_NO_WARNINGS':'1'}
    env['WSLENV']=env.get('WSLENV','')+':ELECTRON_RUN_AS_NODE:NODE_NO_WARNINGS'
    for arguments in [['--version'],['--project',windows(a.project),'--out',windows(folder/'rust output')]]:
        r=subprocess.run([a.studio,windows(folder/'wasi-runner.js'),*arguments],capture_output=True,env=env,timeout=60)
        stdout=r.stdout.decode('utf8','replace');stderr=r.stderr.decode('utf8','replace')
        print(stdout,stderr)
        if r.returncode:raise SystemExit('Windows packaged generator failed')
    native=ROOT/'artifacts/package-native-reference'
    subprocess.run([str(ROOT/'target/debug/reez'),'--project',str(a.project),'--out',str(native)],check=True,capture_output=True)
    for name in ['mod.rs','screens.rs','styles.rs','resources.rs']:
        if (native/name).read_bytes()!=(folder/'rust output'/name).read_bytes():raise SystemExit(f'WASM/native output mismatch: {name}')
    print('Windows EEZ runtime: version, font conversion, 114-object generation, space/Unicode paths and native/WASM parity passed')
