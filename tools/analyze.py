import json
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config
import stats

COLORS = {"python": "#3776AB", "ruby": "#CC342D"}
LABELS = {"python": "Python", "ruby": "Ruby"}
CACHE_TITLE = {"on": "Com cache", "off": "Sem cache"}
FILE_PATTERN = re.compile(r"^(python|ruby)_(on|off)_(\d+)_r(\d+)\.json$")

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titleweight": "bold",
    "axes.titlesize": 13,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "legend.frameon": False,
})


def load_raw():
    rows = []
    for path in sorted(config.RESULTS_DIR.glob("*.json")):
        match = FILE_PATTERN.match(path.name)
        if not match:
            continue
        version, cache, users, rep = match.groups()
        users = int(users)
        data = json.loads(path.read_text())
        rows.append({
            "versao": version,
            "cache": cache,
            "usuarios": users,
            "rep": int(rep),
            "requisicoes": data["requisicoes"],
            "falhas": data["falhas"],
            "timeouts": data["timeouts"],
            "taxa_falha_pct": stats.failure_rate(data, users),
            "media_ms": data["media_ms"],
            "mediana_ms": data["mediana_ms"],
            "p95_ms": data["p95_ms"],
            "p99_ms": data["p99_ms"],
            "max_ms": data["max_ms"],
            "req_s": data["req_s"],
            "procs": data["procs"],
            "gerador_cpu_alta": data["gerador_cpu_alta"],
            "dbsize": data["dbsize"],
            "aprovado": stats.approved(data, users),
        })
    if not rows:
        sys.exit("Nenhum resultado em results\\. Rode antes: python tools\\run.py")
    return pd.DataFrame(rows).sort_values(["versao", "cache", "usuarios", "rep"]).reset_index(drop=True)


def summarize(raw):
    summary = raw.groupby(["versao", "cache", "usuarios"]).agg(
        reps=("rep", "count"),
        reps_aprovadas=("aprovado", "sum"),
        requisicoes=("requisicoes", "mean"),
        falhas=("falhas", "mean"),
        timeouts=("timeouts", "mean"),
        taxa_falha_pct=("taxa_falha_pct", "mean"),
        media_ms=("media_ms", "mean"),
        media_ms_dp=("media_ms", "std"),
        mediana_ms=("mediana_ms", "mean"),
        p95_ms=("p95_ms", "mean"),
        p99_ms=("p99_ms", "mean"),
        max_ms=("max_ms", "max"),
        req_s=("req_s", "mean"),
        procs=("procs", "max"),
        cpu_alta=("gerador_cpu_alta", "max"),
    ).reset_index()
    summary["media_ms_dp"] = summary["media_ms_dp"].fillna(0)
    summary["aprovado"] = summary["reps_aprovadas"] == summary["reps"]
    return summary


def capacity(summary):
    rows = []
    for (version, cache), group in summary.groupby(["versao", "cache"]):
        group = group.sort_values("usuarios")
        failed = group[~group["aprovado"]]
        first_fail = int(failed["usuarios"].min()) if len(failed) else None
        below = group if first_fail is None else group[group["usuarios"] < first_fail]
        passed = below[below["aprovado"]]
        best = passed.iloc[-1] if len(passed) else None
        pool = group[group["aprovado"]]
        peak = (pool if len(pool) else group).sort_values("req_s").iloc[-1]
        suspect = bool(best is not None and best["cpu_alta"])
        if first_fail is not None:
            suspect = suspect or bool(group[group["usuarios"] == first_fail]["cpu_alta"].iloc[0])
        rows.append({
            "versao": version,
            "cache": cache,
            "usuarios_max_ok": int(best["usuarios"]) if best is not None else 0,
            "primeira_reprovada": first_fail,
            "media_ms_no_max": best["media_ms"] if best is not None else None,
            "p95_ms_no_max": best["p95_ms"] if best is not None else None,
            "req_s_no_max": best["req_s"] if best is not None else None,
            "vazao_pico_req_s": peak["req_s"],
            "usuarios_no_pico": int(peak["usuarios"]),
            "gerador_suspeito": suspect,
        })
    return pd.DataFrame(rows)


def cache_gain(summary):
    ok = summary[summary["aprovado"]]
    on = ok[ok["cache"] == "on"].set_index(["versao", "usuarios"])
    off = ok[ok["cache"] == "off"].set_index(["versao", "usuarios"])
    gain = pd.DataFrame({
        "media_com_cache_ms": on["media_ms"],
        "media_sem_cache_ms": off["media_ms"],
        "p95_com_cache_ms": on["p95_ms"],
        "p95_sem_cache_ms": off["p95_ms"],
    }).dropna().reset_index()
    gain["ganho_media"] = gain["media_sem_cache_ms"] / gain["media_com_cache_ms"]
    gain["ganho_p95"] = gain["p95_sem_cache_ms"] / gain["p95_com_cache_ms"]
    return gain.sort_values(["versao", "usuarios"])


def version_comparison(summary):
    ok = summary[summary["aprovado"]]
    table = ok.pivot_table(index=["cache", "usuarios"], columns="versao", values="media_ms").dropna().reset_index()
    if {"python", "ruby"} <= set(table.columns):
        table["razao_ruby_python"] = table["ruby"] / table["python"]
    return table


def draw_series(ax, data, position, column, version, error):
    color = COLORS[version]
    ax.plot([position[u] for u in data["usuarios"]], data[column], color=color, linewidth=1, linestyle=":", alpha=0.5)
    ok = data[data["aprovado"]]
    bad = data[~data["aprovado"]]
    ax.errorbar(
        [position[u] for u in ok["usuarios"]], ok[column],
        yerr=ok[error] if error else None,
        color=color, marker="o", markersize=6, linewidth=2.2, capsize=3, label=LABELS[version],
    )
    if len(bad):
        ax.scatter([position[u] for u in bad["usuarios"]], bad[column], marker="X", s=130,
                   color=color, edgecolors="black", linewidths=1, zorder=5)


def line_panels(summary, column, ylabel, title, filename, error=None, limit=None):
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.8))
    for ax, cache in zip(axes, config.CACHES):
        subset = summary[summary["cache"] == cache]
        loads = sorted(subset["usuarios"].unique())
        position = {users: index for index, users in enumerate(loads)}
        for version in config.HOSTS:
            data = subset[subset["versao"] == version].sort_values("usuarios")
            if len(data):
                draw_series(ax, data, position, column, version, error)
        if limit is not None:
            ax.axhline(limit, color="#555555", linestyle="--", linewidth=1, label=f"limite de {limit}%")
        if (~subset["aprovado"]).any():
            ax.scatter([], [], marker="X", s=130, color="lightgray", edgecolors="black",
                       label=f"reprovado (> {config.FAIL_LIMIT_PCT}% de falhas)")
        ax.set_xticks(range(len(loads)))
        ax.set_xticklabels(loads, rotation=45 if len(loads) > 10 else 0)
        ax.set_xlabel("Usuários virtuais")
        ax.set_ylabel(ylabel)
        ax.set_title(CACHE_TITLE[cache])
        ax.set_ylim(bottom=0)
        ax.grid(True, axis="y", alpha=0.3)
        ax.legend()
    fig.suptitle(title, fontsize=15, fontweight="bold")
    fig.tight_layout()
    fig.savefig(config.CHARTS_DIR / filename, dpi=160)
    plt.close(fig)


def gain_chart(gain):
    fig, ax = plt.subplots(figsize=(11, 5.8))
    if len(gain):
        loads = sorted(gain["usuarios"].unique())
        position = {users: index for index, users in enumerate(loads)}
        width = 0.38
        for offset, version in zip((-0.5, 0.5), config.HOSTS):
            data = gain[gain["versao"] == version]
            bars = ax.bar([position[u] + offset * width for u in data["usuarios"]], data["ganho_media"],
                          width, color=COLORS[version], label=LABELS[version])
            ax.bar_label(bars, fmt="%.1fx", fontsize=8, padding=2)
        ax.set_xticks(range(len(loads)))
        ax.set_xticklabels(loads, rotation=45 if len(loads) > 10 else 0)
        ax.legend()
    else:
        ax.text(0.5, 0.5, "Nenhuma carga aprovada com e sem cache", ha="center", transform=ax.transAxes)
    ax.set_xlabel("Usuários virtuais")
    ax.set_ylabel("Ganho (tempo sem cache ÷ tempo com cache)")
    ax.set_title("Ganho de desempenho obtido pelo cache (cargas aprovadas nos dois modos)")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(config.CHARTS_DIR / "07_ganho_cache.png", dpi=160)
    plt.close(fig)


def versions_chart(table):
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.8))
    for ax, cache in zip(axes, config.CACHES):
        data = table[table["cache"] == cache] if len(table) else table
        if len(data) and {"python", "ruby"} <= set(data.columns):
            position = {users: index for index, users in enumerate(data["usuarios"])}
            width = 0.38
            for offset, version in zip((-0.5, 0.5), config.HOSTS):
                bars = ax.bar([position[u] + offset * width for u in data["usuarios"]], data[version],
                              width, color=COLORS[version], label=LABELS[version])
                ax.bar_label(bars, fmt="%.0f", fontsize=8, padding=2)
            ax.set_xticks(range(len(data)))
            ax.set_xticklabels(data["usuarios"])
            ax.legend()
        else:
            ax.text(0.5, 0.5, "Sem cargas aprovadas nas duas versões", ha="center", transform=ax.transAxes)
        ax.set_title(CACHE_TITLE[cache])
        ax.set_xlabel("Usuários virtuais")
        ax.set_ylabel("Tempo médio de resposta (ms)")
        ax.grid(True, axis="y", alpha=0.3)
    fig.suptitle("Python x Ruby (cargas aprovadas nas duas versões)", fontsize=15, fontweight="bold")
    fig.tight_layout()
    fig.savefig(config.CHARTS_DIR / "08_python_vs_ruby.png", dpi=160)
    plt.close(fig)


def capacity_chart(cap):
    fig, ax = plt.subplots(figsize=(10, 5.8))
    width = 0.36
    for offset, version in zip((-0.5, 0.5), config.HOSTS):
        values = []
        suspects = []
        for cache in config.CACHES:
            row = cap[(cap["versao"] == version) & (cap["cache"] == cache)]
            values.append(int(row["usuarios_max_ok"].iloc[0]) if len(row) else 0)
            suspects.append(bool(row["gerador_suspeito"].iloc[0]) if len(row) else False)
        bars = ax.bar([index + offset * width for index in range(len(config.CACHES))], values,
                      width, color=COLORS[version], label=LABELS[version])
        for bar, suspect in zip(bars, suspects):
            if suspect:
                bar.set_hatch("//")
        ax.bar_label(bars, padding=3, fontweight="bold")
    ax.set_xticks(range(len(config.CACHES)))
    ax.set_xticklabels([CACHE_TITLE[cache] for cache in config.CACHES])
    ax.set_ylabel("Máximo de usuários virtuais")
    ax.set_title(f"Capacidade máxima por cenário (até {config.FAIL_LIMIT_PCT}% de falhas)")
    ax.margins(y=0.12)
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend()
    fig.text(0.99, 0.01, "hachurado: CPU do gerador de carga alta", ha="right", fontsize=8, color="#555555")
    fig.tight_layout()
    fig.savefig(config.CHARTS_DIR / "09_capacidade.png", dpi=160)
    plt.close(fig)


def main():
    config.CHARTS_DIR.mkdir(exist_ok=True)
    raw = load_raw()
    summary = summarize(raw)
    cap = capacity(summary)
    gain = cache_gain(summary)
    versions = version_comparison(summary)

    raw.to_csv(config.RESULTS_DIR / "resultados_brutos.csv", index=False)
    summary.to_csv(config.RESULTS_DIR / "resultados_consolidados.csv", index=False)
    gain.to_csv(config.RESULTS_DIR / "comparativo_cache.csv", index=False)
    versions.to_csv(config.RESULTS_DIR / "comparativo_versoes.csv", index=False)
    cap.to_csv(config.RESULTS_DIR / "capacidade_maxima.csv", index=False)

    line_panels(summary, "media_ms", "Tempo médio de resposta (ms)", "Tempo médio de resposta",
                "01_tempo_medio.png", error="media_ms_dp")
    line_panels(summary[summary["usuarios"] <= 220], "media_ms", "Tempo médio de resposta (ms)",
                "Tempo médio de resposta (até 220 usuários)", "10_tempo_medio_zoom.png", error="media_ms_dp")
    line_panels(summary, "mediana_ms", "Mediana do tempo de resposta (ms)", "Mediana do tempo de resposta", "02_mediana.png")
    line_panels(summary, "p95_ms", "Percentil 95 (ms)", "Percentil 95 do tempo de resposta", "03_p95.png")
    line_panels(summary, "p99_ms", "Percentil 99 (ms)", "Percentil 99 do tempo de resposta", "04_p99.png")
    line_panels(summary, "req_s", "Requisições por segundo", "Vazão", "05_vazao.png")
    line_panels(summary, "taxa_falha_pct", "Taxa de falhas (%)", "Taxa de falhas", "06_falhas.png",
                limit=config.FAIL_LIMIT_PCT)
    gain_chart(gain)
    versions_chart(versions)
    capacity_chart(cap)

    print("RESUMO CONSOLIDADO")
    print(summary.round(1).to_string(index=False))
    print("\nGANHO DO CACHE")
    print(gain.round(2).to_string(index=False))
    print("\nPYTHON x RUBY (tempo medio, ms)")
    print(versions.round(2).to_string(index=False))
    print(f"\nCAPACIDADE MAXIMA (ate {config.FAIL_LIMIT_PCT}% de falhas)")
    print(cap.round(1).to_string(index=False))
    print(f"\nGraficos em: {config.CHARTS_DIR}")


if __name__ == "__main__":
    main()