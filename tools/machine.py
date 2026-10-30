import json
import os
import platform
import subprocess
from importlib.metadata import version


def collect(name=None):
    info = {
        "nome": name or platform.node(),
        "so": f"{platform.system()} {platform.release()}",
        "processador": platform.processor() or platform.machine(),
        "nucleos_logicos": os.cpu_count(),
        "python": platform.python_version(),
        "locust": version("locust"),
    }
    try:
        import psutil

        info["nucleos_fisicos"] = psutil.cpu_count(logical=False)
        info["ram_gb"] = round(psutil.virtual_memory().total / 1024 ** 3, 1)
    except ImportError:
        pass
    try:
        output = subprocess.run(
            ["docker", "info", "--format", "{{.NCPU}};{{.MemTotal}};{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip().split(";")
        info["docker_cpus"] = int(output[0])
        info["docker_ram_gb"] = round(int(output[1]) / 1024 ** 3, 1)
        info["docker_versao"] = output[2]
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    return info


def save(directory, name=None):
    directory.mkdir(parents=True, exist_ok=True)
    info = collect(name)
    (directory / "maquina.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    return info