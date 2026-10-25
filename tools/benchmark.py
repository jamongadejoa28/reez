"""Compare default debug info with the compact profile using disposable build caches."""
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'crates/monitor/src/main.rs'
original=source.read_bytes()
results={}
with tempfile.TemporaryDirectory(prefix='reez-benchmark-') as temp:
    try:
        for name,debug in [('default-debug', '2'),('compact','0')]:
            target=Path(temp)/name
            env={**os.environ,'CARGO_TARGET_DIR':str(target),'CARGO_PROFILE_DEV_DEBUG':debug,'CARGO_PROFILE_DEV_INCREMENTAL':'true','CARGO_PROFILE_DEV_LTO':'false'}
            def build():
                start=time.monotonic()
                p=subprocess.run(['cargo','build','--locked','--workspace'],cwd=ROOT,env=env,capture_output=True,text=True)
                if p.returncode:raise RuntimeError(p.stderr[-4000:])
                return time.monotonic()-start
            cold=build();warm=[build() for _ in range(3)];edits=[]
            for i in range(3):
                source.write_bytes(original+f'\n// benchmark edit {name} {i}\n'.encode());edits.append(build())
            size=sum(p.stat().st_size for p in target.rglob('*') if p.is_file())
            results[name]={'cold_seconds':round(cold,3),'warm_seconds_median':round(statistics.median(warm),3),'edit_seconds_median':round(statistics.median(edits),3),'target_bytes':size}
            print(name,results[name],flush=True)
            source.write_bytes(original)
            shutil.rmtree(target)
    finally:source.write_bytes(original)
(ROOT/'artifacts/build-benchmark.json').write_text(json.dumps(results,indent=2)+'\n')
