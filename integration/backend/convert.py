"""Reez 0.3: translate completed C build outputs, not EEZ object-model JSON."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import uuid

VERSION='0.3.3'
BASE=Path(__file__).resolve().parent

def digest(file):return hashlib.sha256(Path(file).read_bytes()).hexdigest()
def local(path):
    if not path:return None
    value=str(path)
    if re.match(r'^[A-Za-z]:[\\/]',value) or value.startswith('\\\\'):
        return Path(subprocess.check_output(['wslpath','-u',value],text=True).strip())
    return Path(value)
def command_environment(settings):
    env=dict(os.environ)
    cargo=Path.home()/'.cargo/bin'
    if cargo.is_dir():env['PATH']=str(cargo)+os.pathsep+env.get('PATH','')
    env.pop('RUSTC_BOOTSTRAP',None)
    if settings.get('rustToolchain'):env['RUSTUP_TOOLCHAIN']=settings['rustToolchain']
    return env

def converter_command():
    tool=BASE/'runtime/bin/c2rust-transpile'
    loader=BASE/'runtime/lib/ld-linux-x86-64.so.2'
    if not tool.is_file():raise ValueError('C conversion runtime is missing. Install the complete Reez extension ZIP.')
    # ZIP installers do not consistently retain Unix executable permissions.
    for file in (tool,loader):
        if file.exists() and not os.access(file,os.X_OK):file.chmod(file.stat().st_mode|0o100)
    return [str(loader),'--library-path',str(BASE/'runtime/lib'),str(tool)] if loader.exists() else [str(tool)]

def windows_split(text):
    result=[];part=[];quoted=False;i=0
    while i<len(text):
        ch=text[i]
        if ch in ' \t' and not quoted:
            if part:result.append(''.join(part));part=[]
            i+=1;continue
        if ch=='\\':
            start=i
            while i<len(text) and text[i]=='\\':i+=1
            count=i-start
            if i<len(text) and text[i]=='"':
                part.extend('\\'*(count//2))
                if count%2:part.append('"')
                else:quoted=not quoted
                i+=1
            else:part.extend('\\'*count)
            continue
        if ch=='"':quoted=not quoted
        else:part.append(ch)
        i+=1
    if quoted:raise ValueError('Unbalanced quotes in Windows C compile command')
    if part:result.append(''.join(part))
    return result

def normalize_arguments(entry,directory,file):
    import shlex
    args=entry.get('arguments')
    if args is None:
        text=entry['command']
        args=windows_split(text) if re.match(r'^[A-Za-z]:',entry['directory']) or '\\' in text else shlex.split(text)
    if not args:raise ValueError(f'Empty C compile command: {file}')
    normalized=['clang'];i=1
    path_options={'-I','-isystem','-iquote','-idirafter','-include','-imacros','--sysroot','-isysroot','-resource-dir'}
    def convert_path(value):
        p=local(value)
        return str(p if p.is_absolute() else directory/p)
    while i<len(args):
        arg=args[i]
        if arg in ('-o','-MF','-MT','-MQ'):
            i+=2;continue
        if arg in ('-MMD','-MD','-MP','-c'):i+=1;continue
        if arg in path_options:
            if i+1>=len(args):raise ValueError(f'Missing path after {arg}')
            normalized.extend([arg,convert_path(args[i+1])]);i+=2;continue
        if arg.startswith('-I') and len(arg)>2:normalized.append('-I'+convert_path(arg[2:]));i+=1;continue
        if arg.startswith('--sysroot='):normalized.append('--sysroot='+convert_path(arg.split('=',1)[1]));i+=1;continue
        if re.match(r'^[A-Za-z]:[\\/]',arg) or arg.startswith('\\\\'):arg=str(local(arg))
        candidate=Path(arg)
        if arg==entry['file'] or (not arg.startswith('-') and (directory/candidate).resolve()==file):i+=1;continue
        normalized.append(arg);i+=1
    normalized.extend(['-resource-dir',str(BASE/'sdk/clang-resource'),'-c',str(file)])
    return normalized

def inputs_for(request):
    settings=request.get('settings',{});source=local(request['sourceDirectory']).resolve()
    if not source.is_dir():raise ValueError(f'C output directory not found: {source}')
    cpp=[f for f in source.rglob('*') if f.suffix.lower() in ('.cpp','.cc','.cxx')]
    if cpp:raise ValueError(f'C++ translation requires another frontend: {cpp[0].name}')
    database=local(settings.get('compilationDatabase'))
    entries=[]
    if database:
        if not database.is_absolute():database=local(request['projectDirectory'])/database
        for original in json.loads(database.read_text()):
            directory=local(original['directory'])
            if not directory.is_absolute():directory=database.parent/directory
            file=local(original['file']);file=(file if file.is_absolute() else directory/file).resolve()
            if not file.is_relative_to(source):continue
            if file.suffix.lower() in ('.cpp','.cc','.cxx'):raise ValueError(f'C++ translation is not supported by C2Rust: {file.name}')
            if file.suffix.lower()!='.c':continue
            entries.append({'directory':str(directory),'file':str(file),'arguments':normalize_arguments(original,directory,file)})
    else:
        profile=settings.get('compilerProfile','bundled-lvgl-9.5')
        if profile!='bundled-lvgl-9.5':raise ValueError('Configure compilationDatabase for the custom compiler profile')
        includes=[BASE/'sdk/lvgl',BASE/'sdk',source]
        includes.extend(local(p) for p in settings.get('includeDirectories',[]))
        for file in sorted(source.rglob('*.c')):
            args=['clang','-std=c11','-resource-dir',str(BASE/'sdk/clang-resource'),'-DLV_CONF_PATH="'+str(BASE/'sdk/lv_conf.h')+'"']
            args.extend('-I'+str(p.resolve()) for p in includes)
            args.extend('-D'+d for d in settings.get('defines',[]))
            args.extend(['-c',str(file)])
            entries.append({'directory':str(source),'file':str(file),'arguments':args})
    if not entries:raise ValueError('No generated C compilation units were selected')
    expected={str(f.resolve()) for f in source.rglob('*.c')}
    selected={e['file'] for e in entries}
    if selected!=expected:raise ValueError('Compilation database must cover every C output. Missing: '+', '.join(sorted(expected-selected)))
    if len(selected)!=len(entries):raise ValueError('Multiple compile configurations for the same C file; select one configuration')
    return source,entries

def stabilize(directory):
    for file in directory.rglob('*.rs'):
        text=file.read_text();pattern=r'(?m)^\s*pub type ([A-Za-z_][A-Za-z_0-9]*);\s*$'
        opaque=re.findall(pattern,text);text=re.sub(pattern,'',text)
        for name in opaque:text+=f'\n#[repr(C)]\npub struct {name} {{ _opaque: [u8;0] }}\n'
        text=text.replace('#![feature(extern_types)]\n','').replace('#![feature(raw_ref_op)]\n','')
        if re.search(r'\bcompile_error!\s*\(',text):raise ValueError(f'Incomplete C translation in {file.name}')
        file.write_text(text)

def publish(source,output,report):
    output.parent.mkdir(parents=True,exist_ok=True)
    lock=output.parent/f'.{output.name}.reez-lock'
    with lock.open('x'):
        try:
            old={}
            if (output/'.reez-c-output.json').exists():old=json.loads((output/'.reez-c-output.json').read_text())
            old_files=set(old.get('files',{}))
            legacy=output/'.reez-manifest.json'
            if legacy.exists():old_files.update(json.loads(legacy.read_text()).get('files',[]));old_files.add('.reez-manifest.json')
            fresh={str(p.relative_to(source)):digest(p) for p in source.rglob('*') if p.is_file()}
            for name in old_files|set(fresh):
                path=Path(name)
                if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe generated-file manifest')
                if any(p.is_symlink() for p in [(output/path),*(output/path).parents] if p!=output.parent):raise ValueError(f'Output contains symlink: {name}')
            for name in fresh:
                if (output/name).exists() and name not in old_files and name!='.reez-c-output.json':raise ValueError(f'Refusing to overwrite user-owned file: {name}')
            if output.is_symlink():raise ValueError('Rust output directory must not be a symlink')
            with tempfile.TemporaryDirectory(prefix='.reez-publish-',dir=output.parent) as temp:
                stage=Path(temp)/'stage';backup=Path(temp)/'previous'
                if output.exists():shutil.copytree(output,stage,symlinks=True)
                else:stage.mkdir()
                for name in old_files:
                    p=stage/name
                    if p.is_file() or p.is_symlink():p.unlink()
                shutil.copytree(source,stage,dirs_exist_ok=True)
                report={**report,'files':fresh}
                (stage/'.reez-c-output.json').write_text(json.dumps(report,indent=2)+'\n')
                had=output.exists()
                if had:output.rename(backup)
                try:stage.rename(output)
                except Exception:
                    if had:backup.rename(output)
                    raise
        finally:lock.unlink(missing_ok=True)
    return report

def check(settings):
    env=command_environment(settings);tool=subprocess.run([*converter_command(),'--version'],env=env,capture_output=True,text=True,check=True)
    cargo=shutil.which('cargo',path=env.get('PATH'))
    return {'version':VERSION,'backend':tool.stdout.strip(),'input':'generated C files','rustCompilerAvailable':bool(cargo),'compilerProfile':settings.get('compilerProfile','bundled-lvgl-9.5')}

def convert(request):
    settings=request.get('settings',{});env=command_environment(settings);source,entries=inputs_for(request)
    requested=local(request['outputDirectory']).absolute()
    if any(p.is_symlink() for p in [requested,*requested.parents]):raise ValueError('Rust output path contains symlink')
    output=requested.resolve()
    if source==output or source.is_relative_to(output) or output.is_relative_to(source):raise ValueError('C and Rust output directories must be separate')
    inputs={str(p.relative_to(source)):digest(p) for p in sorted(source.rglob('*')) if p.is_file() and p.suffix in ('.c','.h','.cpp','.hpp')}
    profile=hashlib.sha256(json.dumps(entries,sort_keys=True).encode()).hexdigest()
    # Reparse on every build: headers outside the C output may have changed.
    # Cargo retains incremental compiler results in the shared backend cache.
    cache=Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'reez/c-output';cache.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='conversion-',dir=cache) as temp:
        work=Path(temp);database=work/'compile_commands.json';database.write_text(json.dumps(entries));rust=work/'rust'
        command=[*converter_command(),'--emit-build-files','--emit-c-decl-map','--fail-on-error','--disable-refactoring','--disable-rustfmt','--output-dir',str(rust),str(database)]
        result=subprocess.run(command,env=env,capture_output=True,text=True)
        # Clang's frontend can report syntax errors while C2Rust still exits 0.
        diagnostics=result.stdout+'\n'+result.stderr
        if result.returncode or re.search(r'(?im)(?:^|\s)(?:fatal )?error:|^Error while processing ',diagnostics):raise RuntimeError('C translation failed:\n'+diagnostics[-12000:])
        if not (rust/'Cargo.toml').exists() or len(list((rust/'src').rglob('*.rs')))<len(entries):raise RuntimeError('C2Rust omitted one or more C translation units:\n'+result.stderr[-12000:])
        stabilize(rust)
        (rust/'build.rs').unlink(missing_ok=True)  # C2Rust's empty Unix-only example.
        lib=rust/'lib.rs'
        lib.write_text('#![cfg_attr(not(feature="std"), no_std)]\n'+lib.read_text())
        # Export stable Rust without pinning an obsolete C2Rust nightly toolchain.
        (rust/'rust-toolchain.toml').unlink(missing_ok=True)
        # Keep one compiler-cache identity per project, rather than a new crate
        # and incremental directory for every UI edit.
        crate_name='reez_ui_'+hashlib.sha256(str(source).encode()).hexdigest()[:12]
        manifest=rust/'Cargo.toml';text=re.sub(r'(?m)^name = "[^"]+"$',f'name = "{crate_name}"',manifest.read_text())
        text=text.replace('crate-type = ["staticlib", "rlib"]','crate-type = ["rlib"]')
        text+='\n[features]\ndefault=["std"]\nstd=[]\n\n[profile.dev]\ndebug=0\nincremental=true\n';manifest.write_text(text)
        dependencies=tomllib.loads(text).get('dependencies',{})
        if not dependencies:
            lock=f'version = 4\n\n[[package]]\nname = "{crate_name}"\nversion = "0.0.0"\n'
        elif set(dependencies)=={'c2rust-bitfields'}:
            text=text.replace('c2rust-bitfields = "0.22.1"','c2rust-bitfields = { version = "=0.22.1", features = ["no_std"] }')
            manifest.write_text(text)
            lock=(BASE/'generated-Cargo.lock').read_text();lock=re.sub(r'(?m)^name = "c2rust_probe_absolute"$',f'name = "{crate_name}"',lock)
        else:raise ValueError('Conversion requires additional Rust dependencies: '+', '.join(dependencies))
        (rust/'Cargo.lock').write_text(lock)
        verified=False
        static_library=None
        if settings.get('verifyRust',True):
            if not shutil.which('cargo',path=env.get('PATH')):raise ValueError('Rust compile-check requires Cargo in the WSL backend. Install Rust there or explicitly disable verifyRust.')
            env['CARGO_TARGET_DIR']=str(cache/'target')
            if settings.get('rustTarget'):env['CARGO_BUILD_TARGET']=settings['rustTarget']
            # A stable manifest path lets Cargo reuse the same project cache.
            # A new temporary package path on each build would accumulate caches.
            compiled=cache/'projects'/crate_name;compiled.parent.mkdir(exist_ok=True)
            with (cache/(crate_name+'.compile-lock')).open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                compiled.mkdir(exist_ok=True)
                current={p.relative_to(rust) for p in rust.rglob('*') if p.is_file()}
                for p in compiled.rglob('*'):
                    if p.is_file() and p.relative_to(compiled) not in current:p.unlink()
                for name in current:
                    target=compiled/name;target.parent.mkdir(parents=True,exist_ok=True)
                    if not target.exists() or digest(target)!=digest(rust/name):shutil.copy2(rust/name,target)
                built=subprocess.run(['cargo','rustc','--lib','--crate-type=staticlib','--offline','--locked','--config','source.crates-io.replace-with="reez-vendored"','--config','source.reez-vendored.directory='+json.dumps(str(BASE/'rust-vendor')),'--manifest-path',str(compiled/'Cargo.toml')],env=env,capture_output=True,text=True)
                if built.returncode:raise RuntimeError('Converted Rust compile-check failed:\n'+built.stderr[-12000:])
                root=cache/'target'
                if settings.get('rustTarget'):root/=settings['rustTarget']
                libraries=list((root/'debug/deps').glob('lib'+crate_name+'-*.a'))
                if libraries:static_library=str(max(libraries,key=lambda p:p.stat().st_mtime))
            verified=True
        now={str(p.relative_to(source)):digest(p) for p in sorted(source.rglob('*')) if p.is_file() and p.suffix in ('.c','.h','.cpp','.hpp')}
        if now!=inputs:raise RuntimeError('C build outputs changed during translation; rebuild')
        for p in rust.rglob('*.c_decls.json'):p.unlink()
        report={'version':VERSION,'backend':'c2rust-0.22.1','inputKind':'generated-c','inputDirectory':str(source),'inputs_sha256':inputs,'compiler_configuration_sha256':profile,'translationUnits':len(entries),'rustCompileChecked':verified,'crateName':crate_name}
        report=publish(rust,output,report)
        return {**report,'outputDirectory':str(output),'staticLibrary':static_library,'unchanged':False}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--request',type=Path,required=True);args=parser.parse_args()
    request=json.loads(args.request.read_text())
    result=check(request.get('settings',{})) if request.get('operation')=='check' else convert(request)
    print(json.dumps(result))
if __name__=='__main__':
    try:main()
    except Exception as error:print(json.dumps({'path':'c-output','message':str(error)}),file=sys.stderr);sys.exit(1)
