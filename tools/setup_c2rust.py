"""Build project-local C2Rust 0.22.1 using a system LLVM/Clang development SDK."""
import os
from pathlib import Path
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    env=dict(os.environ)
    llvm=env.get('LLVM_CONFIG_PATH') or shutil.which('llvm-config')
    if not llvm:raise SystemExit('Install LLVM/Clang development packages; e.g. Ubuntu: llvm-18-dev libclang-18-dev clang-18, then set LLVM_CONFIG_PATH=/usr/bin/llvm-config-18')
    prefix=Path(subprocess.check_output([llvm,'--prefix'],text=True).strip())
    env['LLVM_CONFIG_PATH']=str(llvm)
    env.setdefault('CMAKE_LLVM_DIR',str(prefix/'lib/cmake/llvm'))
    env.setdefault('CMAKE_CLANG_DIR',str(prefix/'lib/cmake/clang'))
    env.setdefault('LLVM_LIB_DIR',str(prefix/'lib'))
    subprocess.run(['cargo','install','--locked','--version','0.22.1','--root',str(ROOT/'.tools/c2rust'),'--target-dir',str(ROOT/'target/c2rust'),'--jobs','4','c2rust'],env=env,cwd=ROOT,check=True)
