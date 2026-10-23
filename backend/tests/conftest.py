import os, shutil, sys, tempfile
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
WORKBOOK = ROOT / "data" / "client_export.xlsx"

# env must be set at import time: test modules import app.config during collection
_tmp = Path(tempfile.mkdtemp(prefix="arc-test-"))
shutil.copytree(ROOT / "spec", _tmp / "spec")
os.environ.update({"LOCAL_DB": str(_tmp / "erp.sqlite"), "SPEC_DIR": str(_tmp / "spec"),
                   "WATCH_INTERVAL_S": "0", "AS_OF": "2026-09-22"})


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app import main
    from app.state import get_state
    from app.ingest.loader import load_workbook_into_erp
    s = get_state()
    load_workbook_into_erp(WORKBOOK, s.erp, s.schema)
    s.refresh(reason="test")
    return TestClient(main.app)
