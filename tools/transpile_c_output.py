"""Experimental C-output backend. Converts compilation units, never EEZ project JSON.

Requires project-local C2Rust 0.22.1 and the actual C compiler headers/flags.
It is not yet the portable Windows extension backend.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def stable_opaque_types(folder):
    """Incomplete C types are only used through pointers; keep that ABI on stable Rust."""
    for file in folder.rglob('*.rs'):
        text=file.read_text()
        pattern=r'(?m)^\s*pub type ([A-Za-z_][A-Za-z_0-9]*);\s*$'
        names=re.findall(pattern,text)
        text=re.sub(pattern,'',text)
        for name in names:text+=f'\n#[repr(C)]\npub struct {name} {{ _opaque: [u8; 0] }}\n'
        text=text.replace('#![feature(extern_types)]\n','').replace('#![feature(raw_ref_op)]\n','')
        file.write_text(text)

def transpile(database,output,converter,source_root=None):
    database=Path(database).resolve();output=Path(output).resolve();converter=Path(converter).resolve()
    if output.exists():raise ValueError('Choose a fresh output directory; existing Rust output is never overwritten by this experimental backend')
    if not converter.is_file():raise ValueError('C2Rust 0.22.1 is not installed at the configured path')
    original=json.loads(database.read_text());entries=[];inputs={}
    for entry in original:
        directory=Path(entry['directory'])
        if not directory.is_absolute():directory=database.parent/directory
        file=Path(entry['file']);file=file if file.is_absolute() else directory/file;file=file.resolve()
        if source_root and not file.is_relative_to(source_root):continue
        if file.suffix.lower() not in ('.c','.cpp','.cc','.cxx'):continue
        if file.suffix.lower()!='.c':raise ValueError(f'C++ translation needs a separate backend: {file}')
        normalized={**entry,'directory':str(directory.resolve()),'file':str(file)}
        entries.append(normalized);inputs[str(file)]=hashlib.sha256(file.read_bytes()).hexdigest()
    if not entries:raise ValueError('No C translation units selected from compilation database')
    output.parent.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'RUSTUP_TOOLCHAIN':'1.99.1'}
    with tempfile.TemporaryDirectory(prefix='reez-c-transpile-',dir=output.parent) as temp:
        work=Path(temp);db=work/'compile_commands.json';db.write_text(json.dumps(entries,indent=2));rust=work/'rust'
        command=[str(converter),'transpile','--emit-build-files','--emit-c-decl-map','--fail-on-error','--disable-refactoring','--output-dir',str(rust),str(db)]
        result=subprocess.run(command,env=env,capture_output=True,text=True)
        (work/'transpile.log').write_text(result.stdout+'\n'+result.stderr)
        if result.returncode:raise RuntimeError('C2Rust failed:\n'+result.stderr[-12000:])
        modules=list((rust/'src').rglob('*.rs'))
        if len(modules)<len(entries):raise RuntimeError('C2Rust did not emit every selected translation unit')
        stable_opaque_types(rust)
        (rust/'rust-toolchain.toml').write_text('[toolchain]\nchannel = "1.99.1"\n')
        crate_name='reez_c_'+hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:12]
        manifest=rust/'Cargo.toml';text=manifest.read_text()
        text=re.sub(r'(?m)^name = \"[^\"]+\"$',f'name = \"{crate_name}\"',text)
        text+='\n[profile.dev]\ndebug=0\nincremental=true\n';manifest.write_text(text)
        # Use a shared build cache outside the published source tree.
        env['CARGO_TARGET_DIR']=str(ROOT/'target/c-output')
        subprocess.run(['cargo','generate-lockfile','--manifest-path',str(manifest)],env=env,check=True)
        check=subprocess.run(['cargo','build','--locked','--manifest-path',str(manifest)],env=env,capture_output=True,text=True)
        if check.returncode:raise RuntimeError('Converted Rust did not compile on Rust 1.99.1:\n'+check.stderr[-12000:])
        if any(hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest for name,digest in inputs.items()):raise RuntimeError('C inputs changed during conversion; retry from a completed EEZ build')
        shutil.copy2(work/'transpile.log',rust/'transpile.log')
        report={'backend':'c2rust-0.22.1','input_kind':'C compilation units','experimental':True,'rust_version':'1.99.1','inputs_sha256':inputs,'translation_units':len(entries),'rust_modules':len(modules),'cargo_build_passed':True,'crate_name':crate_name,'static_library':str(ROOT/'target/c-output/debug'/f'lib{crate_name}.a')}
        (rust/'.reez-c-output.json').write_text(json.dumps(report,indent=2)+'\n')
        rust.rename(output)
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compilation-database',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--source-root',type=Path)
    parser.add_argument('--converter',type=Path,default=ROOT/'.tools/c2rust/bin/c2rust')
    args=parser.parse_args()
    root=args.source_root.resolve() if args.source_root else None
    print(json.dumps(transpile(args.compilation_database,args.out,args.converter,root)))
if __name__=='__main__':main()
