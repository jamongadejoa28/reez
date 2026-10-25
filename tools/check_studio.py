"""Exercise the installed Windows Studio adapter against disposable project copies."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
source=Path('/mnt/c/Users/hajun/eez-projects/esp32-s3-monitor-sim/esp32-s3-monitor-sim.eez-project')
exe='/mnt/c/Users/hajun/AppData/Local/Programs/eezstudio/EEZ Studio.exe'
def run(project):
    win=subprocess.check_output(['wslpath','-w',str(project)],text=True).strip()
    p=subprocess.run([exe,'--build-project',win],capture_output=True,timeout=120)
    return p.stdout.decode('utf8','replace')+'\n'+p.stderr.decode('utf8','replace')
def hashes(folder):
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.suffix in ('.c','.h','.rs')}
with tempfile.TemporaryDirectory(prefix='reez integration ',dir='/mnt/c/Users/hajun/AppData/Local/Temp') as temp:
    base=Path(temp);project=base/'한글 프로젝트.eez-project';project.write_bytes(source.read_bytes());conf=json.loads((source.parent/'reez.json').read_text());conf['enabled']=False
    config=base/'reez.json';config.write_text(json.dumps(conf));log=run(project);assert 'Build successfully finished' in log,log
    before=hashes(base/'src/ui')
    conf['enabled']=True;config.write_text(json.dumps(conf));log=run(project);assert 'Rust output:' in log and 'Build successfully finished' in log,log
    assert before==hashes(base/'src/ui'),'C output changed when Rust was enabled'
    rust=hashes(base/'rust-src');d=json.loads(project.read_text());d['userPages'][0]['components'][0]['children'][0]['recolor']=True;project.write_text(json.dumps(d));failed=run(project)
    assert 'label recolor is not supported' in failed,failed
    assert 'Build successfully finished' not in failed,failed
    assert rust==hashes(base/'rust-src'),'Rust failure changed previous output'
    (ROOT/'artifacts/studio-negative.log').write_text(failed)
    (ROOT/'artifacts/studio-validation.json').write_text(json.dumps({'c_output_identical':True,'dual_build':True,'failure_preserves_rust':True,'failure_suppresses_success':True,'unicode_and_space_paths':True},indent=2)+'\n')
    print('Studio: C output unchanged, dual build passed, Rust failure preserved outputs, Unicode/space paths passed')
