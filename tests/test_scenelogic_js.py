"""Logika planovace cinnosti (web/scenelogic.js) ma vlastni testy v Node:

    node --test "tests/js/*.test.js"

Tady se jen spusti, at je `python -m pytest` hlida taky. Bez Node se preskoci."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js neni nainstalovany")
def test_scenelogic_node_suite():
    files = sorted(str(p) for p in (ROOT / "tests/js").glob("*.test.js"))
    assert files
    r = subprocess.run(["node", "--test", *files], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
