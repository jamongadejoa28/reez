import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
import pytest
ROOT=Path(__file__).resolve().parents[1]
WOKWI=Path(os.environ.get('WOKWI_PROJECT',ROOT.parent/'wokwipj'))
PROJECT=Path(os.environ.get('EEZ_PROJECT','/mnt/c/Users/hajun/eez-projects/esp32-s3-monitor-sim/esp32-s3-monitor-sim.eez-project'))
@pytest.fixture
def demo(tmp_path):
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    control=tmp_path/'control.json';control.write_text(json.dumps({'temperature':-12.5,'humidity':62.3,'alarm_word1':1025}))
    env=dict(os.environ);env.pop('VIRTUAL_ENV',None)
    if os.environ.get('REEZ_REFERENCE_C') == '1':
        command=['uv','run','--locked','python','-m','tools.demo','--port',str(port),'--control-file',str(control)]
        cwd=WOKWI
    else:
        command=[str(ROOT/'target/debug/reez-firmware-host'),'--port',str(port),'--control-file',str(control),'--trace',str(tmp_path/'rtu.jsonl')]
        cwd=ROOT
    process=subprocess.Popen(command,cwd=cwd,env=env,stdout=subprocess.DEVNULL)
    url=f'http://127.0.0.1:{port}'
    try:
        for _ in range(60):
            try:
                if json.load(urllib.request.urlopen(url+'/api/state',timeout=.3))['connected']:break
            except OSError:pass
            time.sleep(.1)
        else:raise AssertionError('mock server not ready')
        yield url,control
    finally:process.terminate();process.wait(timeout=10)
