# Dinheiro público e produtos GAFAM (Portugal)

Rastreia, em 2022–2026, contratos BASE, anúncios, modificações, apoios Portugal 2030
e (melhor esforço) SciPROJ cujo texto nomeia um produto GAFAM. Gera uma apresentação HTML
estática (`reports/index.html`) e um relatório do distrito de Leiria (`reports/leiria/`).

Não faz scraping a base.gov.pt: lê os ficheiros abertos oficiais (dados.gov.pt, PT2030).

## Corrida pequena (sem rede)

Usa fixtures em `tests/fixtures/`. Corre sem HTTP.

```bash
docker compose run --rm gafam
# ou localmente:
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
PYTHONPATH=src .venv/bin/python -m gafam_contratos
```

Saída: `reports/index.html` (apresentação), `reports/leiria/`, `data.json`, CSVs.

Se o contentor (utilizador `gafam`) não conseguir escrever nos volumes:

```bash
mkdir -p reports data/cache && chmod -R a+rwX reports data/cache
```

## Qualidade (CI local)

```bash
docker compose -f docker-compose.ci.yml run --rm quality
```

Ordem em `scripts/quality.sh`: ruff → mypy → bandit → vulture → pytest (100% branches)
→ hadolint → yamllint → actionlint. `pip-audit` corre no *build* da imagem `ci`.

## Corrida nacional

Só depois de `pytest` verde.

```bash
docker compose run --rm gafam python -m gafam_contratos --full
```

Descarrega 2022–2026 (cache em `data/cache/`), marca PRR, tenta SciPROJ e imprensa
(Arquivo.pt + GDELT). Reinícios HTTP: sequência Fibonacci 1…34 s.

## Relatório

- Apresentação nacional: um gráfico / mapa por slide, scroll com micro-animações.
- Distrito de Leiria: tabela detalhada + série e concelhos em `reports/leiria/`.
- Três totais distintos (não se somam): contrato assinado, pedido ao mercado, apoio aprovado.
- PRR é bandeira em contratos BASE, não um quarto total.
- Léxico: `data/lexicon.yml` (GAFAM + falsos amigos rejeitados).
- Esquema: `schema/report.schema.json`.
- UI: HTML estático + DaisyUI / Tailwind CDN + Chart.js; tipografia Archivo / Space Mono.

```nginx
root /caminho/para/reports;
index index.html;
```

### GitHub Pages

O workflow `.github/workflows/pages.yml` gera `reports/` (`--full` por omissão) e publica
em GitHub Pages em cada push a `main`, à segunda-feira (cron) ou via *Run workflow*.

1. No repositório: **Settings → Pages → Source → GitHub Actions**.
2. Após o primeiro deploy, o site fica em `https://<org-ou-user>.github.io/<repo>/`
   (nacional em `/`, Leiria em `/leiria/`).

## Segurança (práticas OWASP, em resumo)

- Relatório HTML: textos e `href` escapados; só ligações `http`/`https`.
- Contentor de runtime: utilizador não-root (`gafam`); Compose CI sem rede (`network_mode: none`).
- Dependências auditadas no build CI; SAST com bandit.
- Downloads: URLs de datasets conhecidos + cache local; TLS por omissão do `urllib`.

## Layout do código

| Caminho | Papel |
|---------|--------|
| `src/gafam_contratos/` | Pipeline (load → match → aggregate → report) |
| `data/` | Léxico, NUTS, domínios de imprensa, cache |
| `tests/` | Fixtures + pytest |
| `scripts/quality.sh` | Gate de qualidade |

## Licença dos dados

Os ficheiros oficiais têm as licenças indicadas nas fontes do relatório; o código
desta ferramenta é independente desses termos.
