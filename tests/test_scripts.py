r"""Runs every script in ``tests/scripts`` in its own process (each one builds its own
QApplication and viewer) with a temporary output folder; a script passes when it exits
cleanly and its last line is ``OK``.

Scripts that need the sample data in ``C:\Temp`` are skipped when those files are not
there. Run: ``.venv\Scripts\python -m pytest tests``.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted((ROOT / 'tests' / 'scripts').glob('*.py'))
_DATA = re.compile(r"""['"](C:[\\/]+Temp[\\/][^'"]+)['"]""")   # r'C:\Temp\..' or 'C:/Temp/..'


def _missing_data(script: Path) -> list[str]:
    missing = []
    for path in _DATA.findall(script.read_text(encoding='utf-8')):
        p = Path(path)
        if not (p.exists() or any(p.parent.glob(p.name + '*'))):
            missing.append(path)
    return missing


@pytest.mark.parametrize('script', SCRIPTS, ids=[s.stem for s in SCRIPTS])
def test_script(script: Path, tmp_path: Path):
    missing = _missing_data(script)
    if missing:
        pytest.skip('sample data not found: ' + ', '.join(missing))
    env = dict(os.environ, PYTHONPATH=str(ROOT), MPLBACKEND='Agg',
               QT_QPA_PLATFORM=os.environ.get('QT_QPA_PLATFORM', 'offscreen'))
    r = subprocess.run([sys.executable, str(script), str(tmp_path)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=900)
    lines = r.stdout.strip().splitlines()
    assert r.returncode == 0 and lines and lines[-1] == 'OK', (
        f'exit {r.returncode}\n--- stdout (tail)\n' + '\n'.join(lines[-30:]) +
        '\n--- stderr (tail)\n' + '\n'.join(r.stderr.strip().splitlines()[-30:]))
