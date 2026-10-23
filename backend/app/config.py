import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC_DIR = Path(os.getenv("SPEC_DIR", ROOT / "spec"))
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))

ERP_MODE = os.getenv("ERP_MODE", "local")            # local | airgen
LOCAL_DB = Path(os.getenv("LOCAL_DB", DATA_DIR / "erp_local.sqlite"))
AIRGEN_BASE_URL = os.getenv("AIRGEN_BASE_URL", "")
AIRGEN_API_KEY = os.getenv("AIRGEN_API_KEY", "")     # read-only key scoped to the analytics objects
AIRGEN_APPEND_KEY = os.getenv("AIRGEN_APPEND_KEY", "")  # role arc-backend-append: read+insert on crmAgentAction & crmOpportunitySnapshot ONLY
AIRGEN_ADMIN_KEY = os.getenv("AIRGEN_ADMIN_KEY", "") # used only by /api/sync/* called by the healing agent
AS_OF = os.getenv("AS_OF", "")                        # ISO date; default = latest date seen in data
WATCH_INTERVAL_S = int(os.getenv("WATCH_INTERVAL_S", "60" if os.getenv("ERP_MODE") == "airgen" else "15"))   # backend-side fallback poller; 0 disables
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

AIRGEN_MAX_RPM = int(os.getenv("AIRGEN_MAX_RPM", "60"))       # self-throttle; the ERP allows 100 requests / 60 s per workspace. 0 = off (tests)
