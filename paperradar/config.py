import os
from dotenv import load_dotenv

# Load .env from CWD, v05/.env, then package-level .env (first wins)
load_dotenv()
try:
    here = os.path.dirname(__file__)
    v05_root = os.path.abspath(os.path.join(here, os.pardir))
    dotenv_v05 = os.path.join(v05_root, ".env")
    if os.path.exists(dotenv_v05):
        load_dotenv(dotenv_v05, override=False)
    dotenv_pkg = os.path.join(here, ".env")
    if os.path.exists(dotenv_pkg):
        load_dotenv(dotenv_pkg, override=False)
except Exception:
    pass

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
DATA_ROOT = os.getenv("DATA_ROOT", "data")

DEFAULT_POLL_INTERVAL_MIN = float(os.getenv("POLL_INTERVAL_MIN", "2"))
POLL_DAILY_TIME = os.getenv("POLL_DAILY_TIME", "").strip()
DEFAULT_SIM_THRESHOLD     = float(os.getenv("SIM_THRESHOLD", "0.55"))
DEFAULT_TOP_N             = int(os.getenv("TOP_N", "12"))
DEFAULT_MAX_AGE_HOURS     = int(os.getenv("MAX_AGE_HOURS", "0"))

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "").strip()
LLM_MODEL       = os.getenv("LLM_MODEL", "gpt-4o-mini")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
DEFAULT_LLM_THRESHOLD    = float(os.getenv("LLM_THRESHOLD", "0.70"))
DEFAULT_LLM_MAX_PER_TICK = int(os.getenv("LLM_MAX_PER_TICK", "2"))
DEFAULT_LLM_ONDEMAND_MAX_PER_HOUR = int(os.getenv("LLM_ONDEMAND_MAX_PER_HOUR", "5"))
DEFAULT_JOURNAL_TOPN = int(os.getenv("JOURNAL_TOP_N", "9"))
DEFAULT_JOURNAL_LLM_TOP = int(os.getenv("JOURNAL_LLM_TOP", "4"))
DEFAULT_PAPER_EMBED_MAX = int(os.getenv("PAPER_EMBED_MAX", "12"))

TELEGRAM_MAX_DOC_MB    = 49
TELEGRAM_MAX_DOC_BYTES = TELEGRAM_MAX_DOC_MB * 1024 * 1024

LUCKY_MIN_SIM = 0.01

# Optional external APIs for extra sources
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
SPRINGER_API_KEY         = os.getenv("SPRINGER_API_KEY", "").strip()
SERPAPI_API_KEY          = os.getenv("SERPAPI_API_KEY", "").strip()
CROSSREF_MAILTO          = os.getenv("CROSSREF_MAILTO", "").strip()

# Per-source limits (defaults are conservative)
MAX_ARXIV_RESULTS            = int(os.getenv("MAX_ARXIV_RESULTS", "100"))
MAX_CROSSREF_RESULTS         = int(os.getenv("MAX_CROSSREF_RESULTS", "50"))
MAX_SEMANTIC_SCHOLAR_RESULTS = int(os.getenv("MAX_SEMANTIC_SCHOLAR_RESULTS", "60"))
MAX_SPRINGER_RESULTS         = int(os.getenv("MAX_SPRINGER_RESULTS", "60"))
MAX_SCHOLAR_RESULTS          = int(os.getenv("MAX_SCHOLAR_RESULTS", "50"))

# Enable/disable sources via .env flags (default True)
ENABLE_ARXIV    = os.getenv("ENABLE_ARXIV", "true").strip().lower() in ("1", "true", "yes", "on")
ENABLE_CROSSREF = os.getenv("ENABLE_CROSSREF", "true").strip().lower() in ("1", "true", "yes", "on")
ENABLE_SEMANTIC = os.getenv("ENABLE_SEMANTIC", "true").strip().lower() in ("1", "true", "yes", "on")
ENABLE_SPRINGER = os.getenv("ENABLE_SPRINGER", "true").strip().lower() in ("1", "true", "yes", "on")
ENABLE_SCHOLAR  = os.getenv("ENABLE_SCHOLAR", "true").strip().lower() in ("1", "true", "yes", "on")
