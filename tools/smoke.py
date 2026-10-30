import sys
import time
import uuid
from pathlib import Path

import requests

sys.path.append(str(Path(__file__).resolve().parent.parent / "load"))

import config
from urls import URLS


def fetch(host, url):
    start = time.perf_counter()
    response = requests.get(f"{host}/api/{url}", timeout=30)
    return response, (time.perf_counter() - start) * 1000


def main():
    problems = 0
    for version, host in config.HOSTS.items():
        print(f"\n{version} ({host})")
        for url in URLS:
            target = f"{url}?nc={uuid.uuid4().hex}"
            try:
                first, miss_ms = fetch(host, target)
                second, hit_ms = fetch(host, target)
            except requests.RequestException as error:
                print(f"ERRO   {url}: {error}")
                problems += 1
                continue
            links = len(first.json()) if first.ok else 0
            good = first.ok and second.ok and links > 0 and first.json() == second.json()
            problems += 0 if good else 1
            status = "OK  " if good else "ERRO"
            print(f"{status} {url} | {links} links | miss {miss_ms:.0f} ms | hit {hit_ms:.0f} ms")
    print("\nTUDO OK" if problems == 0 else f"\n{problems} problema(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()