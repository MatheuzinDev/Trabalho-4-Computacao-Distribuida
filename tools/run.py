import argparse
import csv
import sys

import config
import machine
import runner
import stats

CACHE_LABEL = {"on": "com cache", "off": "sem cache"}


def parse_args():
    parser = argparse.ArgumentParser(description="Teste final de desempenho")
    parser.add_argument("--reps", type=int, default=config.DEFAULT_REPS)
    parser.add_argument("--users", nargs="+", type=int)
    parser.add_argument("--versions", nargs="+", choices=list(config.HOSTS), default=list(config.HOSTS))
    parser.add_argument("--cache", choices=["on", "off", "both"], default="both")
    parser.add_argument("--procs", type=int)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--maquina")
    parser.add_argument("--plan", action="store_true")
    return parser.parse_args()


def read_capacities():
    path = config.PROBE_DIR / "capacidade.csv"
    if not path.is_file():
        sys.exit("Sondagem nao encontrada. Rode antes: python tools\\probe.py")
    with path.open(newline="") as handle:
        return {
            (row["versao"], row["cache"]): (
                int(row["usuarios_max_ok"]),
                int(row["primeira_reprovada"]) if row["primeira_reprovada"] else None,
            )
            for row in csv.DictReader(handle)
        }


def loads_for(max_ok, first_fail):
    loads = {users for users in config.LADDER if users <= max_ok}
    loads.update([users for users in config.LADDER if users > max_ok][: config.MARGIN_LEVELS])
    if max_ok:
        loads.add(max_ok)
    if first_fail:
        loads.add(first_fail)
    return sorted(loads)

def build_plan(args):
    caches = config.CACHES if args.cache == "both" else [args.cache]
    capacities = {} if args.users else read_capacities()
    plan = []
    for rep in range(1, args.reps + 1):
        for version in args.versions:
            for cache in caches:
                if args.users:
                    loads = sorted(args.users)
                elif (version, cache) in capacities:
                    loads = loads_for(*capacities[(version, cache)])
                else:
                    sys.exit(f"Sem sondagem para {version} {CACHE_LABEL[cache]}")
                plan.extend((rep, version, cache, users) for users in loads)
    return plan


def print_plan(plan):
    print(f"{len(plan)} execucoes")
    scenarios = {}
    for _, version, cache, users in plan:
        scenarios.setdefault((version, cache), set()).add(users)
    for (version, cache), loads in scenarios.items():
        print(f"  {version} {CACHE_LABEL[cache]}: {sorted(loads)}")


def main():
    args = parse_args()
    plan = build_plan(args)
    print_plan(plan)
    if args.plan:
        return
    config.RESULTS_DIR.mkdir(exist_ok=True)
    machine.save(config.RESULTS_DIR, args.maquina)
    for done, (rep, version, cache, users) in enumerate(plan, start=1):
        stats_file = config.RESULTS_DIR / f"{version}_{cache}_{users}_r{rep}.json"
        prefix = f"[{done}/{len(plan)}] {version} {CACHE_LABEL[cache]} | {users:>5} usuarios | rep {rep}"
        if stats_file.is_file():
            print(f"{prefix} | ja existe, pulando", flush=True)
            continue
        data = runner.measure(version, cache, users, stats_file, args.procs, args.verbose)
        rate = stats.failure_rate(data, users)
        flag = " | CPU do gerador alta" if data["gerador_cpu_alta"] else ""
        print(
            f"{prefix} | falhas {rate:5.1f}% | timeouts {data['timeouts']:>4}"
            f" | media {data['media_ms']:7.0f} ms | {data['req_s']:6.0f} req/s | procs {data['procs']}{flag}"
            f" -> {'OK' if stats.approved(data, users) else 'REPROVADO'}",
            flush=True,
        )


if __name__ == "__main__":
    main()