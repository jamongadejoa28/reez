"""Create a self-contained EEZ Studio extension ZIP and SHA-256 manifest."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def rust_notices(destination, triple):
    metadata = json.loads(subprocess.check_output(['cargo', 'metadata', '--locked', '--format-version=1', '--filter-platform', triple], cwd=ROOT))
    packages = {p['id']: p for p in metadata['packages']}
    root = next(p['id'] for p in packages.values() if p['name'] == 'reez')
    graph = {p['id']: p for p in metadata['resolve']['nodes']}
    pending = [root]; seen = set(); notices = []
    while pending:
        ident = pending.pop()
        if ident in seen: continue
        seen.add(ident)
        package = packages[ident]
        pending.extend(graph[ident]['dependencies'])
        if ident == root: continue
        notices.append(f"{package['name']} {package['version']}: {package.get('license') or package.get('license_file') or 'see source licence'}")
        folder = Path(package['manifest_path']).parent
        target = destination / 'crates' / f"{package['name']}-{package['version']}"
        for license_file in folder.iterdir():
            if license_file.is_file() and license_file.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE', 'UNLICENSE')):
                target.mkdir(parents=True, exist_ok=True); shutil.copy2(license_file, target/license_file.name)
    sysroot = Path(subprocess.check_output(['rustc', '--print', 'sysroot'], text=True).strip())
    rust_docs = sysroot/'share/doc/rust'
    for name in ['COPYRIGHT.html', 'COPYRIGHT-library.html']:
        if (rust_docs/name).is_file():
            destination.mkdir(parents=True, exist_ok=True); shutil.copy2(rust_docs/name, destination/name)
    if not (destination/'COPYRIGHT-library.html').is_file():
        raise RuntimeError('Install the rust-docs toolchain component to include Rust standard-library copyright notices')
    (destination/'CRATES.txt').write_text('\n'.join(sorted(notices))+'\n', encoding='utf8')

def package(binary, output):
    triple = "wasm32-wasip1"
    binary = Path(binary).resolve(); output = Path(output).resolve()
    if not binary.is_file(): raise ValueError(f'Build the native generator first: {binary}')
    magic = binary.read_bytes()[:4]
    if magic != b'\0asm': raise ValueError('Extension package requires the Rust WASI module (.wasm)')
    manifest = json.loads((ROOT/'integration/package.json').read_text())
    version = manifest['version']; archive = output/f"reez-rust-output-{version}.zip"
    output.mkdir(parents=True, exist_ok=True)
    if archive.exists(): raise FileExistsError(f'Refusing to replace an existing release: {archive}')
    with tempfile.TemporaryDirectory(prefix='reez-package-') as temp:
        stage = Path(temp)/'extension'; stage.mkdir()
        for name in ['index.js','panel.js','wasi-runner.js','package.json','LICENSE','install.ps1','INSTALL.txt','SUPPORT.md']:
            shutil.copy2(ROOT/'integration'/name,stage/name)
        dest = stage/'bin';dest.mkdir(parents=True);shutil.copy2(binary,dest/'reez.wasm')
        # Copy the exact runtime dependencies recorded in the native npm lockfile.
        shutil.copytree(ROOT/'node_modules', stage/'node_modules', ignore=shutil.ignore_patterns('.cache','.bin','.package-lock.json'))
        for name in ['package.json','package-lock.json']:
            shutil.copy2(ROOT/name,stage/f'build-{name}')
        for relative in ['Cargo.toml','Cargo.lock','rust-toolchain.toml','pyproject.toml','uv.lock','.python-version','LICENSE','README.md','package.json','package-lock.json']:
            target=stage/'source'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/relative,target)
        for name in ['crates','integration','tools','tests','.github']:
            shutil.copytree(ROOT/name,stage/'source'/name,ignore=shutil.ignore_patterns('__pycache__'))
        rust_notices(stage/'licenses',triple)
        with zipfile.ZipFile(archive.with_suffix('.zip.tmp'),'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for file in sorted(stage.rglob('*')):
                if file.is_file():
                    info=zipfile.ZipInfo(file.relative_to(stage).as_posix(),(2026,1,1,0,0,0))
                    info.create_system=3;info.compress_type=zipfile.ZIP_DEFLATED
                    mode=0o755 if file.suffix=='.py' else 0o644
                    info.external_attr=(stat.S_IFREG|mode)<<16
                    z.writestr(info,file.read_bytes())
        archive.with_suffix('.zip.tmp').replace(archive)
    checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{checksum}  {archive.name}\n')
    return archive

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary',type=Path,nargs='?',default=ROOT/'target/wasm32-wasip1/release/reez.wasm')
    parser.add_argument('--out',type=Path,default=ROOT/'artifacts/releases')
    args=parser.parse_args()
    print(package(args.binary,args.out))
if __name__=='__main__':main()
