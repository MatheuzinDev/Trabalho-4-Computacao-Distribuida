import argparse
import csv

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config
import machine
import runner
import stats

RUN_FIELDS = [
    "versao", "cache", "usuarios", "rep", "requisicoes", "falhas", "taxa_falha_pct",
    "timeouts", "media_ms", "p95_ms", "req_s", "procs", "gerador_cpu_alta", "aprovado",
]
CAPACITY_FIELDS = [
    "versao", "cache", "usuarios_max_ok", "primeira_reprovada",
    "vazao_pico_req_s", "usuarios_no_pico", "gerador_cpu_alta",
]
CACHE_LABEL = {"on": "com cache", "off": "sem cache"}
COLORS = {"python": "tab:blue", "ruby": "tab:red"}


def parse_args():
    parser = argparse.ArgumentParser(description="Sondagem da capacidade maxima de cada cenario")
    parser.add_argument("--versions", nargs="+", choices=list(config.HOSTS), default=list(config.HOSTS))
    parser.add_argument("--cache", choices=["on", "off", "both"], default="both")
    parser.add_argument("--loads", nargs="+", type=int)
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--refine", type=int, default=2)
    parser.add_argument("--procs", type=int)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--maquina")
    parser.add_argument("--summarize", action="store_true")
    return parser.parse_args()


def average(rows, key):
    return sum(float(row[key]) for row in rows) / len(rows)


def run_load(version, cache, users, args, writer, handle):
    rows = []
    for rep in range(1, args.reps + 1):
        stats_file = config.PROBE_DIR / f"{version}_{cache}_{users}_r{rep}.json"
        data = runner.measure(version, cache, users, stats_file, args.procs, args.verbose)
        row = {
            "versao": version,
            "cache": cache,
            "usuarios": users,
            "rep": rep,
            "requisicoes": data["requisicoes"],
            "falhas": data["falhas"],
            "taxa_falha_pct": round(stats.failure_rate(data, users), 2),
            "timeouts": data["timeouts"],
            "media_ms": round(data["media_ms"], 1),
            "p95_ms": data["p95_ms"],
            "req_s": round(data["req_s"], 1),
            "procs": data["procs"],
            "gerador_cpu_alta": data["gerador_cpu_alta"],
            "aprovado": stats.approved(data, users),
        }
        writer.writerow(row)
        handle.flush()
        rows.append(row)
    ok = all(row["aprovado"] for row in rows)
    flag = " | CPU do gerador alta" if any(row["gerador_cpu_alta"] for row in rows) else ""
    print(
        f"[{version} {CACHE_LABEL[cache]}] {users:>5} usuarios | falhas {average(rows, 'taxa_falha_pct'):5.1f}%"
        f" | timeouts {sum(row['timeouts'] for row in rows):>4} | media {average(rows, 'media_ms'):7.0f} ms"
        f" | {average(rows, 'req_s'):6.0f} req/s | procs {rows[0]['procs']}{flag}"
        f" -> {'OK' if ok else 'REPROVADO'}",
        flush=True,
    )
    return ok, rows


def probe_version(version, cache, loads, args, writer, handle):
    points = {}

    def test(users):
        ok, rows = run_load(version, cache, users, args, writer, handle)
        points[users] = rows
        return ok

    last_ok = None
    first_fail = None
    for users in sorted(loads):
        if test(users):
            last_ok = users
        else:
            first_fail = users
            break
    if last_ok and first_fail:
        low, high = last_ok, first_fail
        for _ in range(args.refine):
            step = 5 if high <= 100 else 10
            middle = round((low + high) / 2 / step) * step
            if middle <= low or middle >= high:
                break
            if test(middle):
                low = middle
            else:
                high = middle
    return points


def read_runs():
    path = config.PROBE_DIR / "sondagem.csv"
    latest = {}
    if path.is_file():
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                latest[(row["versao"], row["cache"], int(row["usuarios"]), int(row["rep"]))] = row
    return list(latest.values())


def is_approved(row):
    complete = int(row["requisicoes"]) == int(row["usuarios"]) * config.CALLS_PER_USER
    return complete and float(row["taxa_falha_pct"]) <= config.FAIL_LIMIT_PCT


def summarize():
    groups = {}
    for row in read_runs():
        loads = groups.setdefault((row["versao"], row["cache"]), {})
        loads.setdefault(int(row["usuarios"]), []).append(row)
    capacities = []
    for (version, cache), loads in sorted(groups.items()):
        approved = {u: all(is_approved(r) for r in rows) for u, rows in loads.items()}
        failed = [u for u, ok in approved.items() if not ok]
        first_fail = min(failed) if failed else None
        passed = [u for u, ok in approved.items() if ok and (first_fail is None or u < first_fail)]
        pool = [u for u, ok in approved.items() if ok] or list(loads)
        peak = max(pool, key=lambda u: average(loads[u], "req_s"))
        capacities.append({
            "versao": version,
            "cache": cache,
            "usuarios_max_ok": max(passed) if passed else 0,
            "primeira_reprovada": first_fail or "",
            "vazao_pico_req_s": round(average(loads[peak], "req_s"), 1),
            "usuarios_no_pico": peak,
            "gerador_cpu_alta": any(r["gerador_cpu_alta"] == "True" for rows in loads.values() for r in rows),
        })
    with (config.PROBE_DIR / "capacidade.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CAPACITY_FIELDS)
        writer.writeheader()
        writer.writerows(capacities)
    return capacities


def print_capacity(capacities):
    print(f"\nCAPACIDADE MAXIMA (ate {config.FAIL_LIMIT_PCT}% de falhas)")
    for row in capacities:
        reason = f"reprovou com {row['primeira_reprovada']}" if row["primeira_reprovada"] else "limite nao encontrado, aumente --loads"
        warning = " | CPU do gerador alta: resultado pode ser limite do gerador" if row["gerador_cpu_alta"] else ""
        print(
            f"- {row['versao']} {CACHE_LABEL[row['cache']]}: {row['usuarios_max_ok']} usuarios ({reason});"
            f" pico {row['vazao_pico_req_s']} req/s com {row['usuarios_no_pico']}{warning}"
        )


def draw_charts():
    groups = {}
    for row in read_runs():
        points = groups.setdefault(row["cache"], {}).setdefault(row["versao"], {})
        points.setdefault(int(row["usuarios"]), []).append(row)
    for cache, series in groups.items():
        loads = sorted({users for points in series.values() for users in points})
        index = {users: position for position, users in enumerate(loads)}
        fig, (ax_throughput, ax_failures) = plt.subplots(1, 2, figsize=(13, 5))
        for version, points in sorted(series.items()):
            users = sorted(points)
            xs = [index[u] for u in users]
            color = COLORS[version]
            ax_throughput.plot(xs, [average(points[u], "req_s") for u in users], marker="o", color=color, label=version.capitalize())
            ax_failures.plot(xs, [average(points[u], "taxa_falha_pct") for u in users], marker="o", color=color, label=version.capitalize())
        ax_failures.axhline(config.FAIL_LIMIT_PCT, color="gray", linestyle="--", label=f"limite de {config.FAIL_LIMIT_PCT}%")
        ax_throughput.set_ylabel("Vazão (req/s)")
        ax_failures.set_ylabel("Taxa de falhas (%)")
        ax_throughput.set_title(f"Vazão ({CACHE_LABEL[cache]})")
        ax_failures.set_title(f"Falhas ({CACHE_LABEL[cache]})")
        for ax in (ax_throughput, ax_failures):
            ax.set_xticks(range(len(loads)))
            ax.set_xticklabels([str(u) for u in loads], rotation=45)
            ax.set_xlabel("Usuários virtuais")
            ax.set_ylim(bottom=0)
            ax.grid(True, alpha=0.3)
            ax.legend()
        fig.tight_layout()
        fig.savefig(config.PROBE_DIR / f"sondagem_{cache}.png", dpi=150)
        plt.close(fig)


def main():
    args = parse_args()
    config.PROBE_DIR.mkdir(exist_ok=True)
    if not args.summarize:
        info = machine.save(config.PROBE_DIR, args.maquina)
        print(f"Maquina: {info}", flush=True)
        caches = config.CACHES if args.cache == "both" else [args.cache]
        runs_path = config.PROBE_DIR / "sondagem.csv"
        is_new = not runs_path.is_file() or runs_path.stat().st_size == 0
        with runs_path.open("a", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=RUN_FIELDS)
            if is_new:
                writer.writeheader()
            for cache in caches:
                loads = args.loads or config.PROBE_LOADS[cache]
                for version in args.versions:
                    print(f"\n== {version} ({CACHE_LABEL[cache]}) ==", flush=True)
                    probe_version(version, cache, loads, args, writer, handle)
                    summarize()
    draw_charts()
    print_capacity(summarize())


if __name__ == "__main__":
    main()