"""Build with Windows Studio and require both outputs to report success."""
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
project=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/mnt/c/Users/hajun/eez-projects/esp32-s3-monitor-sim/esp32-s3-monitor-sim.eez-project')
win=subprocess.check_output(['wslpath','-w',str(project)],text=True).strip()
p=subprocess.run(['/mnt/c/Users/hajun/AppData/Local/Programs/eezstudio/EEZ Studio.exe','--build-project',win],capture_output=True,timeout=660)
stdout=p.stdout.decode('utf8','replace');stderr=p.stderr.decode('utf8','replace')
(root/'artifacts').mkdir(exist_ok=True)
(root/'artifacts/studio-build.log').write_text(stdout+'\n'+stderr)
print(stdout[-7000:]);print(stderr[-1500:],file=sys.stderr)
if p.returncode or 'Rust output:' not in stdout or 'Build successfully finished' not in stdout:raise SystemExit('Dual build did not report success')
