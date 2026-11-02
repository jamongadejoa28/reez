"""Package the C-output backend, SDK and EEZ adapter as an installable ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def package(runtime,output):
    runtime=Path(runtime).resolve();output=Path(output).resolve()
    for name in ['runtime/bin/c2rust-transpile','runtime/lib/ld-linux-x86-64.so.2','sdk/lvgl/lvgl.h','rust-vendor','sources/SOURCES.json','runtime-manifest.json']:
        if not (runtime/name).exists():raise ValueError('Build the complete backend first: missing '+name)
    version=json.loads((ROOT/'integration/package.json').read_text())['version']
    output.mkdir(parents=True,exist_ok=True);archive=output/f'reez-rust-output-{version}.zip'
    if archive.exists():raise FileExistsError('Refusing to replace an existing release: '+str(archive))
    with tempfile.TemporaryDirectory(prefix='reez-package-') as temp:
        stage=Path(temp)/'extension';stage.mkdir()
        for name in ['index.js','panel.js','c-output-runner.js','package.json','LICENSE','install.ps1','INSTALL.txt','SUPPORT.md']:
            shutil.copy2(ROOT/'integration'/name,stage/name)
        shutil.copytree(runtime,stage/'backend')
        runtime_manifest=json.loads((stage/'backend/runtime-manifest.json').read_text())
        for name,expected in runtime_manifest['runtime_files'].items():
            if hashlib.sha256((stage/'backend'/name).read_bytes()).hexdigest()!=expected:raise ValueError('Runtime changed during packaging: '+name)
        for name in ['convert.py','generated-Cargo.lock']:shutil.copy2(ROOT/'integration/backend'/name,stage/'backend'/name)
        source=stage/'source';source.mkdir()
        for name in ['Cargo.toml','Cargo.lock','rust-toolchain.toml','pyproject.toml','uv.lock','.python-version','LICENSE','README.md','package.json','package-lock.json']:
            shutil.copy2(ROOT/name,source/name)
        for name in ['crates','integration','tools','tests','docs','.github']:
            shutil.copytree(ROOT/name,source/name,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
        with zipfile.ZipFile(archive.with_suffix('.zip.tmp'),'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for file in sorted(stage.rglob('*')):
                if not file.is_file():continue
                info=zipfile.ZipInfo(file.relative_to(stage).as_posix(),(2026,1,1,0,0,0))
                info.create_system=3;info.compress_type=zipfile.ZIP_DEFLATED
                info.external_attr=(stat.S_IFREG|(file.stat().st_mode&0o777))<<16
                z.writestr(info,file.read_bytes())
        archive.with_suffix('.zip.tmp').replace(archive)
    checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{checksum}  {archive.name}\n')
    return archive

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('runtime',type=Path,nargs='?',default=ROOT/'artifacts/c-backend-runtime')
    p.add_argument('--out',type=Path,default=ROOT/'artifacts/releases');a=p.parse_args();print(package(a.runtime,a.out))
