import sys

import pandas as pd

import config

LIMIT_FOR_BASE_CHECK = 50
errors = []
warnings = []

missing = []
for name in config.CSV_FILES:
    path = config.RESULTS_DIR / name
    if not path.is_file() or path.stat().st_size == 0:
        missing.append(str(path))
for name in config.CHART_FILES:
    path = config.CHARTS_DIR / name
    if not path.is_file() or path.stat().st_size == 0:
        missing.append(str(path))
if missing:
    print("ARQUIVOS AUSENTES")
    for path in missing:
        print("-", path)
    sys.exit("Rode antes: python tools\\analyze.py")

raw = pd.read_csv(config.RESULTS_DIR / "resultados_brutos.csv")
summary = pd.read_csv(config.RESULTS_DIR / "resultados_consolidados.csv")
gain = pd.read_csv(config.RESULTS_DIR / "comparativo_cache.csv")
cap = pd.read_csv(config.RESULTS_DIR / "capacidade_maxima.csv")

files = [p for p in config.RESULTS_DIR.glob("*_r*.json")]
if len(files) != len(raw):
    errors.append(f"{len(files)} arquivos de resultado, mas {len(raw)} linhas em resultados_brutos.csv")

counts = raw.groupby(["versao", "cache", "usuarios"]).size()
if counts.nunique() != 1:
    errors.append(f"repeticoes diferentes entre cargas: {counts[counts != counts.max()].to_dict()}")

for _, row in raw.iterrows():
    tag = f"{row['versao']}/{row['cache']}/{int(row['usuarios'])} usuarios/r{int(row['rep'])}"
    expected = int(row["usuarios"]) * config.CALLS_PER_USER
    if int(row["requisicoes"]) != expected:
        warnings.append(f"{tag}: {int(row['requisicoes'])} requisicoes registradas, esperado {expected}")
    if int(row["usuarios"]) <= LIMIT_FOR_BASE_CHECK and not row["aprovado"]:
        errors.append(f"{tag}: reprovado com carga baixa ({row['taxa_falha_pct']:.1f}% de falhas); verifique o ambiente")
    if row["cache"] == "on" and int(row["dbsize"]) > 10:
        warnings.append(f"{tag}: Redis com {int(row['dbsize'])} chaves com cache ligado, esperado 10")
    if row["cache"] == "off" and int(row["dbsize"]) > expected:
        warnings.append(f"{tag}: Redis com {int(row['dbsize'])} chaves, mais que as {expected} requisicoes")

for _, row in gain.iterrows():
    if row["ganho_media"] <= 1:
        message = f"{row['versao']}/{int(row['usuarios'])} usuarios: cache nao foi mais rapido (ganho {row['ganho_media']:.2f})"
        (errors if int(row["usuarios"]) <= LIMIT_FOR_BASE_CHECK else warnings).append(message)

for _, row in cap.iterrows():
    tag = f"{row['versao']}/{row['cache']}"
    if pd.isna(row["primeira_reprovada"]):
        warnings.append(f"{tag}: nenhuma carga reprovada, o limite nao foi alcancado")
    if int(row["usuarios_max_ok"]) == 0:
        errors.append(f"{tag}: nenhuma carga aprovada")
    if row["gerador_suspeito"]:
        warnings.append(f"{tag}: CPU do gerador alta perto do limite, resultado pode ser limite do gerador")

flagged = int(raw["gerador_cpu_alta"].astype(str).eq("True").sum())
if flagged:
    warnings.append(f"gerador de carga com CPU alta em {flagged} execucoes")

print("ARQUIVOS GERADOS")
for name in config.CSV_FILES:
    print(f"OK  {config.RESULTS_DIR / name}")
for name in config.CHART_FILES:
    print(f"OK  {config.CHARTS_DIR / name}")

print()
for message in warnings:
    print("AVISO:", message)

print(f"\nCAPACIDADE MAXIMA (ate {config.FAIL_LIMIT_PCT}% de falhas)")
print(cap.round(1).to_string(index=False))

if errors:
    print("\nPROBLEMAS ENCONTRADOS")
    for message in errors:
        print("-", message)
    sys.exit(1)

print(f"\nTUDO OK: {len(raw)} execucoes, {summary['usuarios'].nunique()} cargas distintas, {len(config.CHART_FILES)} graficos")