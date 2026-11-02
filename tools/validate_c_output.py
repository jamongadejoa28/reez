"""Render actual C UI and translated Rust UI against the same LVGL library."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from PIL import Image,ImageChops
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--wokwi',type=Path,default=ROOT.parent/'wokwipj');a=p.parse_args()
    source=(a.wokwi/'pc/generated').resolve();lvgl=(a.wokwi/'.tools/lvgl').resolve()
    libraries=list((ROOT/'target/debug/build').glob('reez-lvgl-*/out/native/lib/liblvgl.a'))
    if not libraries:raise SystemExit('Build the desktop LVGL library first: uv run --locked cargo build --locked -p reez-monitor')
    library=max(libraries,key=lambda f:f.stat().st_mtime)
    evidence=ROOT/'artifacts/c-output-validation';evidence.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('backend',ROOT/'integration/backend/convert.py');backend=importlib.util.module_from_spec(spec);spec.loader.exec_module(backend)
    with tempfile.TemporaryDirectory(prefix='reez-parity-') as temp:
        work=Path(temp);base=work/'backend';base.mkdir()
        for file in (ROOT/'artifacts/c-backend-runtime').iterdir():(base/file.name).symlink_to(file,target_is_directory=file.is_dir())
        shutil.copy2(ROOT/'integration/backend/generated-Cargo.lock',base/'generated-Cargo.lock');backend.BASE=base
        flags=['-O2','-I'+str(lvgl),'-I'+str(source),'-DLV_CONF_PATH="'+str(ROOT/'crates/reez-lvgl/lv_conf.h')+'"']
        database=work/'compile_commands.json';database.write_text(json.dumps([{'directory':str(source),'file':str(f),'arguments':['clang',*flags,'-c',str(f)]} for f in sorted(source.glob('*.c'))]))
        output=work/'rust';report=backend.convert({'sourceDirectory':str(source),'outputDirectory':str(output),'projectDirectory':str(a.wokwi.resolve()),'settings':{'compilationDatabase':str(database)}})
        rustlib=Path(report['staticLibrary'])
        for name,ui in [('c',[str(f) for f in sorted(source.glob('*.c'))]),('rust',[str(rustlib)])]:
            # Rust variant links no original C UI unit, only the C test driver/LVGL.
            subprocess.run(['cc',*flags,str(ROOT/'tests/reference.c'),*ui,str(library),'-lSDL2','-lm','-ldl','-lpthread','-o',str(work/(name+'-reference'))],check=True)
        env={**os.environ,'SDL_VIDEODRIVER':'dummy'};screens=[]
        for screen in range(1,6):
            paths=[]
            for name in ['c','rust']:
                file=work/f'{name}-{screen}.bmp';subprocess.run([str(work/(name+'-reference')),str(screen),str(file)],env=env,check=True);paths.append(file)
            left,right=[Image.open(file).convert('RGB') for file in paths]
            pixels=sum(1 for pixel in ImageChops.difference(left,right).get_flattened_data() if pixel!=(0,0,0))
            assert pixels==0,f'Screen {screen}: {pixels} different pixels'
            right.save(evidence/f'rust-screen-{screen}.png');screens.append({'screen':screen,'different_pixels':pixels})
        result={'backend':'installed-extension-C-output-code','inputKind':'generated-c','translationUnits':report['translationUnits'],'rustCompileChecked':report['rustCompileChecked'],'original_c_ui_linked_into_rust_variant':False,'lvgl_library':str(library),'screens':screens}
        (evidence/'render-parity.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
if __name__=='__main__':main()
