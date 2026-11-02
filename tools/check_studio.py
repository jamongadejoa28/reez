"""Real Windows Studio dual build, native actions/variables and failure recovery."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import uuid
ROOT=Path(__file__).resolve().parents[1]
source=Path('/mnt/c/Users/hajun/eez-projects/esp32-s3-monitor-sim/esp32-s3-monitor-sim.eez-project')
exe='/mnt/c/Users/hajun/AppData/Local/Programs/eezstudio/EEZ Studio.exe'
evidence=ROOT/'artifacts/c-output-validation';evidence.mkdir(parents=True,exist_ok=True)
def run(project):
    win=subprocess.check_output(['wslpath','-w',str(project)],text=True).strip()
    p=subprocess.run([exe,'--build-project',win],capture_output=True,timeout=660)
    return p.stdout.decode('utf8','replace')+'\n'+p.stderr.decode('utf8','replace')
def hashes(folder):
    return {str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
with tempfile.TemporaryDirectory(prefix='reez C integration ',dir='/mnt/c/Users/hajun/AppData/Local/Temp') as temp:
    base=Path(temp);project=base/'한글 프로젝트.eez-project';data=json.loads(source.read_text())
    data['actions']=[{'objID':str(uuid.uuid4()),'name':'on_test_click','implementationType':'native','components':[],'connectionLines':[],'userProperties':[],'localVariables':[]}]
    data['variables']['globalVariables']=[{'objID':str(uuid.uuid4()),'name':'test_status','type':'string','defaultValue':'"ready"','native':True,'persistent':False}]
    screen=data['userPages'][0]['components'][0]
    button=next(c for c in screen['children'] if c['type']=='LVGLButtonWidget')
    button['eventHandlers']=[{'objID':str(uuid.uuid4()),'eventName':'CLICKED','handlerType':'action','action':'on_test_click','userData':0}]
    label=next(c for c in screen['children'] if c['type']=='LVGLLabelWidget')
    label.update(text='test_status',textType='expression')
    project.write_text(json.dumps(data,ensure_ascii=False))
    conf={'enabled':False,'output':'rust-src'};config=base/'reez.json';config.write_text(json.dumps(conf))
    log=run(project);(evidence/'studio-c-only.log').write_text(log);assert 'Build successfully finished' in log,log
    before=hashes(base/'src/ui')
    conf['enabled']=True;config.write_text(json.dumps(conf));log=run(project);(evidence/'studio-native-actions.log').write_text(log)
    assert 'Rust output:' in log and 'Build successfully finished' in log,log
    assert before==hashes(base/'src/ui'),'C output changed when Rust was enabled'
    manifest=json.loads((base/'rust-src/.reez-c-output.json').read_text())
    assert manifest['inputKind']=='generated-c' and manifest['rustCompileChecked']
    rustsource='\n'.join(p.read_text() for p in (base/'rust-src').rglob('*.rs'))
    assert 'action_on_test_click' in rustsource and 'get_var_test_status' in rustsource
    rust=hashes(base/'rust-src')
    conf['compilationDatabase']='missing-compile_commands.json';config.write_text(json.dumps(conf));failed=run(project)
    (evidence/'studio-failure.log').write_text(failed)
    assert 'Build successfully finished' not in failed and 'Reez:' in failed,failed
    assert rust==hashes(base/'rust-src'),'Rust failure changed previous output'
    (evidence/'studio.json').write_text(json.dumps({'c_output_identical':True,'dual_build':True,'native_action_event_and_variable_translated':True,'rust_compiled':True,'failure_preserves_rust':True,'failure_suppresses_success':True,'unicode_and_space_paths':True,'c_translation_units':manifest['translationUnits']},indent=2)+'\n')
    print('Studio: native action event + variable, C-output parity, Rust compilation and failure recovery passed')
