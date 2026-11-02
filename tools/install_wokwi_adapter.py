"""Connect the existing Wokwi C reference tests to the Reez Rust implementation."""
import argparse
import json
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
def install(project):
    project=Path(project)
    expected=json.loads((ROOT/'crates/controller/data/registers.json').read_text())
    actual=json.loads((project/'common/registers.json').read_text())
    if actual!=expected:raise ValueError('Register map differs from the reviewed Rust map; reconcile it before testing')
    for name in ['reez.py','rust_native.py']:shutil.copy2(ROOT/'integration/wokwipj'/name,project/'tools'/name)
    demo=project/'tools/demo.py';text=demo.read_text()
    if "MONITOR_CORE" not in text:
        marker='\ndef main():\n'
        if marker not in text:raise ValueError('Unexpected tools/demo.py layout')
        text=text.replace(marker,"\nimport os\nif os.environ.get('MONITOR_CORE') == 'rust':\n    from tools.rust_native import RustNative as Native\n"+marker)
        demo.write_text(text)
    test=project/'tests/test_ui.py';text=test.read_text();old="str(ROOT/'build-pc/monitor-pc')"
    if "MONITOR_PC" not in text:
        if old not in text:raise ValueError('Unexpected tests/test_ui.py binary selection')
        test.write_text(text.replace(old,"os.environ.get('MONITOR_PC',str(ROOT/'build-pc/monitor-pc'))"))
    print('Wokwi Rust adapters installed:',project)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path,default=ROOT.parent/'wokwipj');a=p.parse_args();install(a.project)
