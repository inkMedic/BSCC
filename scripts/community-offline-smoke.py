"""Boot real community Headless without account/API configuration; no game."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
runtime = root / 'artifacts/community/headless'
env = {k: v for k, v in os.environ.items() if not k.startswith('COMMUNITY_')}
env.update(BA_COMMUNITY='1', BA_UDP_PORT='0', PYTHONPATH=str(runtime / 'python-site-packages'))
with tempfile.TemporaryDirectory(prefix='bscn-offline-') as directory:
    (Path(directory) / 'cache').mkdir()
    command = "import babase, _baplus; assert babase.app.plus.user is None; assert babase.app.plus.state=='signed_out'; _baplus.set_identity('', ''); print('COMMUNITY_OFFLINE_BOOT_OK', flush=True); babase.apptimer(0.1, babase.quit)"
    result = subprocess.run([str(runtime / 'ballisticakit_headless'), '-d', str(runtime), '-C', directory, '-a', directory + '/cache', '-e', command],
        env=env, cwd=runtime, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=20)
    (root / 'artifacts/community/offline-engine-smoke.log').write_text(result.stdout)
    assert result.returncode == 0 and 'COMMUNITY_OFFLINE_BOOT_OK' in result.stdout, result.stdout
print('PASS: real engine boots signed out without API configuration; no game run')
