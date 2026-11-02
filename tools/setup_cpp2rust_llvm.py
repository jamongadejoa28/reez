"""Stage the matching LLVM/Clang 23 SDK locally without changing system packages."""
import gzip,hashlib
from pathlib import Path
import subprocess
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
BASE='https://apt.llvm.org/resolute/'
PACKAGES=['llvm-23-dev','llvm-23','llvm-23-runtime','llvm-23-linker-tools','libllvm23','clang-23','libclang-23-dev','libclang-common-23-dev','libclang-cpp23-dev','libclang-cpp23','libclang1-23','libclang-rt-23-dev']
folder=ROOT/'.tools/llvm23';folder.mkdir(parents=True,exist_ok=True)
index=folder/'Packages.gz'
if not index.exists():urllib.request.urlretrieve(BASE+'dists/llvm-toolchain-resolute-23/main/binary-amd64/Packages.gz',index)
entries={}
for block in gzip.decompress(index.read_bytes()).decode().split('\n\n'):
 entry={}
 for line in block.splitlines():
  if ': ' in line:
   key,value=line.split(': ',1)
   if key in ('Package','Filename','SHA256','Size'):entry[key]=value
 if entry.get('Package') in PACKAGES:entries[entry['Package']]=entry
for name in PACKAGES:
 entry=entries[name];file=folder/Path(entry['Filename']).name
 if not file.exists():
  print('Download:',name,flush=True)
  urllib.request.urlretrieve(BASE+entry['Filename'],file)
 if file.stat().st_size!=int(entry['Size']) or hashlib.sha256(file.read_bytes()).hexdigest()!=entry['SHA256']:raise RuntimeError('Package checksum mismatch: '+name)
 print('Extract:',name,flush=True)
 subprocess.run(['dpkg-deb','-x',str(file),str(folder/'root')],check=True)
z3=folder/'root/usr/lib/x86_64-linux-gnu/libz3.so'
if not z3.exists():
    packages=list(folder.glob('libz3-4_*_amd64.deb'))
    if not packages:
        subprocess.run(['apt-get','download','libz3-4'],cwd=folder,check=True)
        packages=list(folder.glob('libz3-4_*_amd64.deb'))
    if len(packages)!=1:raise RuntimeError('Expected one libz3-4 package')
    subprocess.run(['dpkg-deb','-x',str(packages[0]),str(folder/'root')],check=True)
    z3.symlink_to('libz3.so.4')
exports=folder/'root/usr/lib/llvm-23/lib/cmake/llvm/LLVMExports.cmake'
source=exports.read_text().replace('/usr/lib/x86_64-linux-gnu/libz3.so',str(z3))
exports.write_text(source)
print('LLVM 23 SDK:',folder/'root')
