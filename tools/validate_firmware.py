"""Rebuild Studio UI, run Rust firmware/UI regression checks and capture a live GUI."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,default=Path(os.environ.get('EEZ_PROJECT','/mnt/c/Users/hajun/eez-projects/esp32-s3-monitor-sim/esp32-s3-monitor-sim.eez-project')))
    p.add_argument('--wokwi',type=Path,default=ROOT.parent/'wokwipj')
    p.add_argument('--skip-studio-build',action='store_true')
    a=p.parse_args();env={**os.environ,'EEZ_PROJECT':str(a.project),'EEZ_RUST_SRC':str(a.project.parent/'rust-src'),'WOKWI_PROJECT':str(a.wokwi),'REEZ_ROOT':str(ROOT)}
    def run(*args,**kwargs):subprocess.run([str(x) for x in args],cwd=ROOT,env=env,check=True,**kwargs)
    run(sys.executable,'tools/install_wokwi_adapter.py','--project',a.wokwi)
    if not a.skip_studio_build:
        run(sys.executable,'tools/studio_build.py',a.project)
        reference_env=dict(env);reference_env.pop('VIRTUAL_ENV',None)
        subprocess.run(['uv','run','--locked','python','tools/sync_ui.py'],cwd=a.wokwi,env=reference_env,check=True)
    run('cargo','build','--locked','--workspace')
    run('cargo','test','--locked','-p','reez-controller')
    run('cargo','check','--locked','-p','reez-controller','--target','thumbv7em-none-eabihf')
    child=dict(env);child.pop('VIRTUAL_ENV',None)
    subprocess.run(['uv','run','--locked','python','tools/reez.py','test','-q'],cwd=a.wokwi,env=child,check=True)
    run(sys.executable,'tools/reference.py')
    run(sys.executable,'-m','pytest','-q','tests/test_gui.py')
    artifacts=ROOT/'artifacts/rust-firmware';artifacts.mkdir(parents=True,exist_ok=True)
    control=artifacts/'control.json';control.write_text(json.dumps({'temperature':-12.5,'humidity':62.3,'alarm_word1':1025}))
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    url=f'http://127.0.0.1:{port}';trace=artifacts/'rtu.jsonl'
    server=subprocess.Popen([str(ROOT/'target/debug/reez-firmware-host'),'--port',str(port),'--control-file',str(control),'--trace',str(trace)],env=env,stdout=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                state=json.load(urllib.request.urlopen(url+'/api/state',timeout=.5))
                if state['connected']:break
            except OSError:pass
            time.sleep(.05)
        else:raise RuntimeError('Rust firmware server did not start')
        run(ROOT/'target/debug/reez-monitor','--url',url,'--frames','1500','--exercise-mock','--report',artifacts/'report.json','--screenshot',artifacts/'screen.bmp')
        report=json.loads((artifacts/'report.json').read_text())
        assert report['ui_origin']=='studio-output' and report['firmware_engine']=='rust'
        assert report['values']['set_temp']==23.1 and report['values']['power_on']==0 and report['screen']=='alarms'
        from PIL import Image
        Image.open(artifacts/'screen.bmp').save(artifacts/'screen.png')
        print('Verified: Studio Rust sources → Rust GUI → Rust HTTP firmware → Rust Modbus core → mock controller')
        print('Report:',artifacts/'report.json')
        print('Screenshot:',artifacts/'screen.png')
    finally:server.terminate();server.wait(timeout=5)
if __name__=='__main__':main()
