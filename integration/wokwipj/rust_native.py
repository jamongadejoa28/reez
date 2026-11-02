"""Load the Rust test adapter from the Reez workspace."""
import importlib.util
import os
from pathlib import Path
root=Path(os.environ.get('REEZ_ROOT',Path(__file__).resolve().parents[2]/'reez'))
spec=importlib.util.spec_from_file_location('reez_protocol_adapter',root/'tools/wokwipj_rust_native.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
RustNative=module.RustNative
