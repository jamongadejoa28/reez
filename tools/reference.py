"""Build the independent C rendering oracle from Studio output; never link it into Rust."""
import os
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
WOKWI=Path(os.environ.get('WOKWI_PROJECT',ROOT.parent/'wokwipj'))
builds=list((ROOT/'target/debug/build').glob('reez-lvgl-*/out/native/lib/liblvgl.a'))
if not builds: raise SystemExit('build Rust monitor first')
library=max(builds,key=lambda p:p.stat().st_mtime)
args=['cc','-O2','-I'+str(WOKWI/'.tools/lvgl'),'-I'+str(WOKWI/'pc/generated'),'-DLV_CONF_PATH="'+str(ROOT/'crates/reez-lvgl/lv_conf.h')+'"',str(ROOT/'tests/reference.c'),*[str(p) for p in sorted((WOKWI/'pc/generated').glob('*.c'))],str(library),'-lSDL2','-lm','-o',str(ROOT/'artifacts/c-reference')]
subprocess.run(args,check=True)
