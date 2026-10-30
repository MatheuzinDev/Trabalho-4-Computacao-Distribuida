import json
import os
import subprocess
import sys

import requests

import config
import stats
from urls import URLS

EMPTY_RESULT = {
    "requisicoes": 0, "falhas": 0, "timeouts": 0, "erros": {}, "media_ms": 0,
    "mediana_ms": 0, "p95_ms": 0, "p99_ms": 0, "max_ms": 0, "req_s": 0,
}


def redis(*command):
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "redis", "redis-cli", *command],
        cwd=config.ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"redis-cli falhou: {result.stderr.strip()}")
    return result.stdout.strip()


def prepare(cache, host):
    redis("FLUSHALL")
    if cache == "on":
        for url in URLS:
            try:
                requests.get(f"{host}/api/{url}", timeout=60)
            except requests.RequestException:
                pass


def auto_procs(users):
    cores = os.cpu_count() or 2
    return max(1, min(users // config.USERS_PER_PROCESS, cores - 1, config.MAX_PROCESSES))


def split(users, procs):
    base, extra = divmod(users, procs)
    return [share for share in (base + (1 if i < extra else 0) for i in range(procs)) if share > 0]


def run_locust(host, cache, users, stats_file, procs, verbose):
    jobs = []
    for index, share in enumerate(split(users, procs)):
        part = stats_file.with_name(f"{stats_file.name}.part{index}")
        log = part.with_name(f"{part.name}.log")
        part.unlink(missing_ok=True)
        env = {
            **os.environ,
            "CACHE": cache,
            "USERS": str(share),
            "STATS_FILE": str(part),
            "REQUEST_TIMEOUT": str(config.REQUEST_TIMEOUT),
        }
        command = [
            sys.executable, "-m", "locust",
            "-f", str(config.LOAD_DIR / "locustfile.py"),
            "--headless", "-u", str(share), "-r", str(share),
            "--host", host, "--run-time", config.RUN_TIME, "--only-summary",
        ]
        handle = None if verbose else open(log, "w")
        process = subprocess.Popen(
            command, env=env, cwd=config.ROOT, stdout=handle,
            stderr=None if verbose else subprocess.STDOUT,
        )
        jobs.append((process, handle, part, log))
    output = ""
    parts = []
    for process, handle, part, log in jobs:
        process.wait()
        if handle:
            handle.close()
            output += log.read_text(errors="replace")
            log.unlink()
        if part.is_file():
            parts.append(json.loads(part.read_text()))
            part.unlink()
    if parts:
        stats_file.write_text(json.dumps(stats.merge(parts)))
    return output


def measure(version, cache, users, stats_file, procs=None, verbose=False):
    host = config.HOSTS[version]
    prepare(cache, host)
    procs = procs or auto_procs(users)
    stats_file.unlink(missing_ok=True)
    output = run_locust(host, cache, users, stats_file, procs, verbose)
    data = json.loads(stats_file.read_text()) if stats_file.is_file() else dict(EMPTY_RESULT)
    data["procs"] = procs
    data["gerador_cpu_alta"] = "CPU usage above" in output
    data["dbsize"] = int(redis("DBSIZE"))
    stats_file.write_text(json.dumps(data))
    return data