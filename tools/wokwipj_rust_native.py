"""Existing protocol fixtures can exercise the real Rust controller over RTU frames.

This adapter contains no protocol implementation and never loads libmonitor.so.
"""
import json
import math
import os
from pathlib import Path
import subprocess
import time

class RustNative:
    def __init__(self,fixture):
        root=Path(os.environ.get('REEZ_ROOT',Path(__file__).resolve().parents[2]/'reez'))
        binary=Path(os.environ.get('REEZ_FIRMWARE',root/'target/debug/reez-firmware-host'))
        self.fixture=fixture
        self.process=subprocess.Popen([str(binary),'--stdio-rtu'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
        self._request({'op':'init','slave':fixture.slave})
    def _request(self,value):
        self.process.stdin.write(json.dumps(value)+'\n');self.process.stdin.flush()
        while True:
            line=self.process.stdout.readline()
            if not line:raise RuntimeError('Rust firmware process stopped')
            reply=json.loads(line)
            if reply.get('op')!='exchange':return reply
            data=self.fixture.exchange(bytes(reply['request']))
            self.process.stdin.write(json.dumps({'response':list(data)})+'\n');self.process.stdin.flush()
    def tick(self):self._request({'op':'tick','now_ms':int(time.monotonic()*1000)})
    def state(self):return self._request({'op':'state','now_ms':int(time.monotonic()*1000)})
    def command(self,name,value):
        return self._request({'op':'command','name':name,'value':value if math.isfinite(value) else str(value)})['status']
    def close(self):
        p=getattr(self,'process',None)
        if p is not None and p.poll() is None:
            p.stdin.close()
            try:p.wait(timeout=2)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        if p is not None and p.stdout is not None:p.stdout.close()
    def __del__(self):self.close()
