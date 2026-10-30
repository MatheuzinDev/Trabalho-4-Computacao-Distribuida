# Trabalho 4: Realização de Testes de Desempenho com a Aplicação Link Extractor

**Disciplina:** Computação Distribuída

Testes de carga com [Locust](https://locust.io) sobre as duas versões do serviço de extração de links do [Link Extractor](https://github.com/ibnesayeed/linkextractor) (Python/Flask e Ruby/Sinatra), com e sem cache Redis.

## Máquina de teste

Todos os resultados foram obtidos na máquina **matheus-h** (`probe/maquina.json`):

| Item | Valor |
|---|---|
| Sistema operacional | Windows 11 |
| Processador | Intel64 Family 6 Model 158 Stepping 10 (GenuineIntel) |
| Núcleos | 6 físicos, 6 lógicos |
| RAM | 15,9 GB |
| Docker | 29.8.2, com 6 CPUs e 7,7 GB de RAM |
| Python | 3.14.5 |
| Locust | 2.47.0 |

## Como o teste funciona

- Cada usuário virtual faz **10 chamadas sequenciais** ao serviço, cada uma com uma URL diferente (`load/urls.py`), e então termina.
- Variações: número de usuários virtuais, versão do serviço (Python ou Ruby) e modo de cache (com ou sem).
- **Com cache:** o Redis é limpo e aquecido com as 10 URLs antes de cada execução.
- **Sem cache:** cada chamada recebe `?nc=<uuid>`, forçando um cache miss.
- **Falha:** resposta diferente de HTTP 200, corpo inválido, erro de conexão ou timeout de 10 s.
- **Carga aprovada:** taxa de falhas de até 5% em todas as repetições.
- Métricas: média, mediana, p95, p99, máximo, vazão e taxa de falhas.

### Duas fases

1. **Sondagem** (`tools/probe.py`): 1 repetição por carga. Sobe a carga até a primeira reprovada e refina entre a última aprovada e a reprovada. Define a capacidade máxima da máquina em cada um dos 4 cenários.
2. **Teste real** (`tools/run.py`): 3 repetições por carga, usando as mesmas cargas nas duas versões, indo até alguns níveis acima da capacidade encontrada.

## Pré-requisitos

- Git
- Docker Desktop (com Docker Compose)
- Python 3.11 ou superior

## Como replicar

Os comandos abaixo são para PowerShell, na raiz do repositório.

```powershell
git clone https://github.com/MatheuzinDev/Trabalho-4-Computacao-Distribuida.git
cd Trabalho-4-Computacao-Distribuida

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

docker compose up -d --build
python tools/smoke.py

python tools/probe.py --maquina minha-maquina
python tools/run.py --maquina minha-maquina
python tools/analyze.py
python tools/verify.py

docker compose down
```

No Linux ou macOS, ative o ambiente com `source .venv/bin/activate`.

Observações:

- Substitua `minha-maquina` pelo nome da sua máquina. Ele é gravado em `probe/maquina.json`.
- A sondagem e o teste real podem levar bastante tempo. Ambos retomam de onde pararam: execuções já salvas são puladas.
- `python tools/run.py --plan` mostra o plano de execuções sem rodar nada.
- `python tools/probe.py --summarize` recalcula a capacidade a partir de `probe/sondagem.csv`.
- Para rodar só parte dos cenários, use `--versions`, `--cache` e `--users`.
- Feche outros programas pesados durante o teste. Se o gerador de carga atingir CPU alta, o resultado é marcado como possivelmente limitado pelo gerador.

## Estrutura

```
.
├── docker-compose.yml     Redis + serviço Python (5001) + serviço Ruby (5002)
├── requirements.txt
├── services/
│   ├── python/            Link Extractor (versão Python/Flask)
│   └── ruby/              Link Extractor (versão Ruby/Sinatra)
├── load/
│   ├── locustfile.py      Script do usuário virtual (10 chamadas)
│   └── urls.py            URLs usadas nas chamadas
├── tools/
│   ├── config.py          Parâmetros do experimento
│   ├── smoke.py           Teste rápido dos dois serviços
│   ├── probe.py           Sondagem (capacidade da máquina)
│   ├── run.py             Teste real
│   ├── analyze.py         Tabelas CSV e gráficos PNG
│   └── verify.py          Conferência dos resultados
├── probe/                 Resultados da sondagem
├── results/               Resultados do teste real (JSON, CSV)
└── charts/                Gráficos PNG
```

## Resultados (máquina matheus-h)

Maior carga aprovada (até 5% de falhas em todas as repetições):

| Cenário | Usuários máx. | Primeira reprovada |
|---|---|---|
| Python, com cache | 4000* | 4500 |
| Python, sem cache | 220 | 300 |
| Ruby, com cache | 120 | 150 |
| Ruby, sem cache | 110 | 120 |

\* O gerador de carga ficou com CPU alta a partir de 1000 usuários, então esse valor pode ser limite do gerador e não do serviço.

Arquivos gerados em `results/`: `resultados_brutos.csv`, `resultados_consolidados.csv`, `comparativo_cache.csv`, `comparativo_versoes.csv` e `capacidade_maxima.csv`.

Gráficos em `charts/`: tempo médio (completo e até 220 usuários), mediana, p95, p99, vazão, taxa de falhas, ganho do cache, Python vs Ruby e capacidade máxima.

## Créditos

Aplicação original: [ibnesayeed/linkextractor](https://github.com/ibnesayeed/linkextractor) (versões `step5` e `step6`, sem modificações).
