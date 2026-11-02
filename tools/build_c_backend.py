"""Assemble the pinned C2Rust/Clang runtime and SDK for the C-output extension."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request
ROOT=Path(__file__).resolve().parents[1]

def glibc_sources(destination):
    """Bundle corresponding libc sources, including the distro's modifications."""
    sources=destination/'sources';sources.mkdir(exist_ok=True)
    version=subprocess.check_output(['dpkg-query','-W','-f=${Version}','libc6'],text=True).strip()
    base='https://archive.ubuntu.com/ubuntu/pool/main/g/glibc/'
    dsc_name=f'glibc_{version}.dsc';dsc=sources/dsc_name
    if not dsc.exists():urllib.request.urlretrieve(base+dsc_name,dsc)
    checks=re.search(r'Checksums-Sha256:\n((?: [^\n]+\n)+)',dsc.read_text())
    if not checks:raise RuntimeError('Missing source archive checksums in glibc .dsc')
    files={}
    for line in checks.group(1).splitlines():
        checksum,size,name=line.split();target=sources/name
        if not target.exists():urllib.request.urlretrieve(base+name,target)
        if target.stat().st_size!=int(size) or hashlib.sha256(target.read_bytes()).hexdigest()!=checksum:raise RuntimeError('Invalid source archive: '+name)
        files[name]=checksum
    (sources/'SOURCES.json').write_text(json.dumps({'package':'glibc','version':version,'url':base,'sha256':files},indent=2)+'\n')

def build(destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    converter=ROOT/'.tools/c2rust/bin/c2rust-transpile'
    if not converter.exists():raise SystemExit('Install project-local C2Rust 0.22.1 first (tools/setup_c2rust.py)')
    version=subprocess.check_output([str(converter),'--version'],text=True).strip()
    if '0.22.1' not in version:raise SystemExit('C2Rust must be pinned to 0.22.1')
    bin_dir=destination/'runtime/bin';lib_dir=destination/'runtime/lib';bin_dir.mkdir(parents=True,exist_ok=True);lib_dir.mkdir(parents=True,exist_ok=True)
    shutil.copy2(converter,bin_dir/'c2rust-transpile')
    output=subprocess.check_output(['ldd',str(converter)],text=True)
    libraries={Path(match) for match in re.findall(r'(/[^\s()]+)',output) if Path(match).is_file()}
    for library in libraries:shutil.copy2(library.resolve(),lib_dir/library.name)
    sdk=destination/'sdk';sdk.mkdir(exist_ok=True)
    import os
    lvgl=Path(os.environ.get('REEZ_LVGL',ROOT/'.tools/lvgl'))
    if not lvgl.exists():
        subprocess.run(['git','clone','--filter=blob:none','https://github.com/lvgl/lvgl.git',str(lvgl)],check=True)
        subprocess.run(['git','-C',str(lvgl),'checkout','85aa60d18b3d5e5588d7b247abf90198f07c8a63'],check=True)
    head=subprocess.check_output(['git','-C',str(lvgl),'rev-parse','HEAD'],text=True).strip()
    if head!='85aa60d18b3d5e5588d7b247abf90198f07c8a63':raise SystemExit('Bundled LVGL must be the pinned 9.5.0 commit')
    for file in lvgl.rglob('*.h'):
        relative=file.relative_to(lvgl)
        if relative.parts[0] not in ('src','lvgl.h','lvgl_private.h','lv_version.h','lv_conf_template.h'):continue
        target=sdk/'lvgl'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target)
    shutil.copy2(lvgl/'LICENCE.txt' if (lvgl/'LICENCE.txt').exists() else lvgl/'LICENSE',sdk/'LVGL-LICENSE.txt')
    llvm=os.environ.get('LLVM_CONFIG_PATH','/usr/bin/llvm-config-21')
    llvm_version=subprocess.check_output([llvm,'--version'],text=True).strip()
    llvm_prefix=Path(subprocess.check_output([llvm,'--prefix'],text=True).strip())
    resource=llvm_prefix/'lib/clang'/llvm_version.split('.')[0]/'include'
    shutil.copytree(resource,sdk/'clang-resource/include',dirs_exist_ok=True)
    config=['#ifndef LV_CONF_H','#define LV_CONF_H','#define LV_COLOR_DEPTH 32','#define LV_USE_OS LV_OS_NONE','#define LV_USE_STDLIB_MALLOC LV_STDLIB_CLIB','#define LV_USE_STDLIB_STRING LV_STDLIB_CLIB','#define LV_USE_STDLIB_SPRINTF LV_STDLIB_CLIB','#define LV_USE_SDL 0','#define LV_USE_FS_MEMFS 1',"#define LV_FS_MEMFS_LETTER 'M'"]
    config.extend(f'#define LV_FONT_MONTSERRAT_{size} 1' for size in range(8,50,2));config.append('#endif');(sdk/'lv_conf.h').write_text('\n'.join(config)+'\n')
    registry=Path.home()/'.cargo/registry/src';vendor=destination/'rust-vendor';vendor.mkdir(exist_ok=True)
    import tomllib
    dependencies=ROOT/'.tools/runtime-deps';dependencies.mkdir(parents=True,exist_ok=True)
    (dependencies/'Cargo.toml').write_text('[workspace]\n[package]\nname="c2rust_probe_absolute"\nversion="0.0.0"\nedition="2021"\n[lib]\npath="lib.rs"\n[dependencies]\nc2rust-bitfields="=0.22.1"\n')
    (dependencies/'lib.rs').write_text('')
    shutil.copy2(ROOT/'integration/backend/generated-Cargo.lock',dependencies/'Cargo.lock')
    subprocess.run(['cargo','fetch','--locked','--manifest-path',str(dependencies/'Cargo.toml')],cwd=ROOT,check=True)
    lock=tomllib.loads((ROOT/'integration/backend/generated-Cargo.lock').read_text())
    for package in lock['package']:
        if 'source' not in package:continue
        folder=next(registry.glob(f'*/{package["name"]}-{package["version"]}'))
        target=vendor/folder.name
        shutil.copytree(folder,target,dirs_exist_ok=True)
        files={str(p.relative_to(target)):hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file() and p.name!='.cargo-checksum.json'}
        (target/'.cargo-checksum.json').write_text(json.dumps({'files':files,'package':package['checksum']},sort_keys=True))
    licenses=destination/'licenses';licenses.mkdir(exist_ok=True)
    packages={'libc6','libstdc++6','libgcc-s1'}
    for library in libraries:
        owner=subprocess.run(['dpkg-query','-S',str(library)],capture_output=True,text=True)
        if owner.returncode==0:packages.add(owner.stdout.split(': ')[0].split(':')[0])
    for package in packages:
        file=Path('/usr/share/doc')/package/'copyright'
        if file.exists():shutil.copy2(file,licenses/(package+'.copyright'))
    c2rust_source=next(registry.glob('*/c2rust-0.22.1'));license_files=list(c2rust_source.glob('LICENSE*'))
    for file in license_files:shutil.copy2(file,licenses/('c2rust-'+file.name))
    # Native C2Rust statically links Rust dependencies and the Rust standard library.
    notices=[]
    for package in tomllib.loads((c2rust_source/'Cargo.lock').read_text())['package']:
        for folder in registry.glob(f'*/{package["name"]}-{package["version"]}'):
            metadata=tomllib.loads((folder/'Cargo.toml').read_text())['package']
            notices.append(f'{package["name"]} {package["version"]}: {metadata.get("license", "see crate source")}')
            for file in folder.iterdir():
                if file.is_file() and file.name.upper().startswith(('LICENSE','COPYING','NOTICE','UNLICENSE')):
                    target=licenses/'rust-crates'/folder.name;target.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target/file.name)
    (licenses/'RUST-CRATES.txt').write_text('\n'.join(sorted(set(notices)))+'\n')
    sysroot=Path(subprocess.check_output(['rustc','--print','sysroot'],text=True).strip())
    for name in ['COPYRIGHT.html','COPYRIGHT-library.html']:
        file=sysroot/'share/doc/rust'/name
        if not file.is_file():raise RuntimeError('Install rust-docs to package standard library notices: rustup component add rust-docs')
        shutil.copy2(file,licenses/name)
    glibc_sources(destination)
    manifest={'c2rust':'0.22.1','llvm':llvm_version,'lvgl_commit':head,'architecture':'x86_64-linux','runtime_files':{str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file() and p.name!='runtime-manifest.json'}}
    (destination/'runtime-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(destination)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=ROOT/'artifacts/c-backend-runtime');a=p.parse_args();build(a.out)
