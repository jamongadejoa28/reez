"""Build the portable Rust generator included in the EEZ extension ZIP."""
from pathlib import Path
import subprocess
ROOT = Path(__file__).resolve().parents[1]
if __name__ == '__main__':
    subprocess.run(['cargo','build','--locked','--release','-p','reez','--target','wasm32-wasip1'],cwd=ROOT,check=True)
    print(ROOT/'target/wasm32-wasip1/release/reez.wasm')
