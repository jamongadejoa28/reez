"""Locked development launcher: uv run --locked python tools/project.py ACTION."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
def run(*args,**kwargs):subprocess.run([str(a) for a in args],cwd=ROOT,check=True,**kwargs)
def setup():
    run('npm','ci')
    lvgl=Path(os.environ.get('REEZ_LVGL',ROOT.parent/'wokwipj/.tools/lvgl'))
    if not (lvgl/'lvgl.h').exists():raise SystemExit('Set REEZ_LVGL to the pinned LVGL checkout (see tools/dependencies.json).')
    actual=subprocess.check_output(['git','-C',str(lvgl),'rev-parse','HEAD'],text=True).strip()
    expected=json.loads((ROOT/'tools/dependencies.json').read_text())['lvgl']['commit']
    if actual!=expected:raise SystemExit(f'LVGL revision mismatch: {actual}')
    print('LVGL source verified:',actual)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['setup','build','generate','run','test','lint','install-studio','build-studio','benchmark']);a,extra=p.parse_known_args()
    if a.action=='setup':setup()
    elif a.action=='build':run('cargo','build','--locked','--workspace',*extra)
    elif a.action=='generate':run('cargo','run','--locked','-p','reez','--',*extra)
    elif a.action=='run':run(ROOT/'target/debug/reez-monitor',*extra)
    elif a.action=='lint':
        run('cargo','fmt','--all','--check');run('cargo','clippy','--locked','--workspace','--all-targets','--','-D','warnings')
    elif a.action=='test':
        run('cargo','test','--locked','--workspace');run(sys.executable,'tools/reference.py');run('node','--test','tests/studio.test.cjs');run(sys.executable,'-m','pytest','-q',*extra)
    else:run(sys.executable,{'install-studio':'tools/install_studio.py','build-studio':'tools/studio_build.py','benchmark':'tools/benchmark.py'}[a.action],*extra)
if __name__=='__main__':main()
