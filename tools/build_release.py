"""Assemble the pinned C conversion runtime for the Studio extension."""
from build_c_backend import build,ROOT
if __name__=='__main__':build(ROOT/'artifacts/c-backend-runtime')
