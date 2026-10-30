import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOAD_DIR = ROOT / "load"
PROBE_DIR = ROOT / "probe"
RESULTS_DIR = ROOT / "results"
CHARTS_DIR = ROOT / "charts"

sys.path.append(str(LOAD_DIR))

HOSTS = {
    "python": "http://localhost:5001",
    "ruby": "http://localhost:5002",
}
CACHES = ["on", "off"]
CALLS_PER_USER = 10
FAIL_LIMIT_PCT = 5
REQUEST_TIMEOUT = 10
RUN_TIME = "30m"
USERS_PER_PROCESS = 250
MAX_PROCESSES = 1
DEFAULT_REPS = 3
MARGIN_LEVELS = 2
LADDER = [1, 5, 10, 25, 50, 100, 110, 120, 150, 200, 220, 300, 500, 750, 1000, 1500, 2000, 3000, 4000, 5000]
CSV_FILES = [
    "resultados_brutos.csv",
    "resultados_consolidados.csv",
    "comparativo_cache.csv",
    "comparativo_versoes.csv",
    "capacidade_maxima.csv",
]
CHART_FILES = [
    "01_tempo_medio.png",
    "02_mediana.png",
    "03_p95.png",
    "04_p99.png",
    "05_vazao.png",
    "06_falhas.png",
    "07_ganho_cache.png",
    "08_python_vs_ruby.png",
    "09_capacidade.png",
    "10_tempo_medio_zoom.png",
]
PROBE_LOADS = {
    "on": [10, 50, 100, 200, 500, 1000, 2000, 3000, 4000, 5000],
    "off": [5, 10, 25, 50, 100, 150, 200, 300],
}