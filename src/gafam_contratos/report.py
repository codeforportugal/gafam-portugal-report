"""Escrita de data.json, CSVs e apresentações HTML."""

from __future__ import annotations

import csv
import html
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator

from gafam_contratos.aggregate import breakdowns, national_totals, prr_subtotal
from gafam_contratos.amounts import format_eur, format_eur_compact
from gafam_contratos.constants import YEAR_LIST
from gafam_contratos.classify import fold
from gafam_contratos.lexicon import keywords_for_report
from gafam_contratos.models import PressLink, Record, SourceMeta
from gafam_contratos.paths import data_dir, schema_path

_BRAND_FILES = (
    "favicon.png",
    "logo.png",
    "logo-text.png",
    "cc-by-sa.png",
    "agplv3.png",
)


def _brand_asset_prefix(*, scope: str) -> str:
    return "../assets/" if scope == "leiria" else "assets/"


def _copy_brand_assets(reports_root: Path) -> None:
    src = data_dir() / "brand"
    dest = reports_root / "assets"
    dest.mkdir(parents=True, exist_ok=True)
    for name in _BRAND_FILES:
        shutil.copy2(src / name, dest / name)


def _brand_head(asset_prefix: str) -> str:
    return (
        '<link rel="preconnect" href="https://fonts.googleapis.com" />\n'
        '  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />\n'
        '  <link href="https://fonts.googleapis.com/css2?family=Courier+Prime:wght@400;700'
        '&family=Inter:wght@500;700;800&display=swap" rel="stylesheet" />\n'
        f'  <link rel="icon" href="{asset_prefix}favicon.png" type="image/png" />'
    )


def _brand_tokens_css() -> str:
    return """
    :root {
      --ink: #010101;
      --paper: #f4f4f0;
      --coral: #fd5288;
      --teal: #72e123;
      --lime: #72e123;
      --gold: #f4ea15;
      --sky: #eb5423;
      --violet: #eb5423;
      --muted: #6a6a6a;
      --font: "Inter", system-ui, sans-serif;
      --mono: "Courier Prime", "Courier New", monospace;
      --cfp-bar: 3.5rem;
    }
    """.strip()


def _brand_footer_css() -> str:
    return """
    body { padding-bottom: var(--cfp-bar); }
    .cfp-bar {
      position: fixed; left: 0; right: 0; bottom: 0; z-index: 50;
      display: flex; justify-content: center; align-items: center;
      flex-wrap: wrap; gap: 0.75rem 1.25rem;
      min-height: var(--cfp-bar);
      background: var(--ink);
      border-top: 2px solid var(--lime);
      padding: 0.4rem 1rem;
    }
    .cfp-bar .cfp-brand {
      display: inline-flex; align-items: center; gap: 0.7rem;
      text-decoration: none; color: var(--paper);
      font-family: var(--mono); font-size: 0.72rem; font-weight: 700;
      letter-spacing: 0.05em; text-transform: uppercase;
    }
    .cfp-bar .cfp-brand:hover { color: var(--gold); }
    .cfp-bar .mark {
      width: 28px; height: 28px; border-radius: 4px;
      object-fit: cover; flex: 0 0 auto;
      box-shadow: 0 0 0 1px rgba(244,234,21,.35);
    }
    .cfp-bar .name { color: inherit; }
    .cfp-bar .soon { color: var(--lime); opacity: 0.95; font-weight: 400; }
    .cfp-lic {
      display: inline-flex; align-items: center; gap: 0.45rem;
    }
    .cfp-lic a { display: inline-flex; line-height: 0; opacity: 0.95; }
    .cfp-lic a:hover { opacity: 1; }
    .cfp-lic img { height: 22px; width: auto; display: block; }
    @media (max-width: 520px) {
      .cfp-bar .soon { display: none; }
    }
    """.strip()


def _cfp_footer(asset_prefix: str) -> str:
    mark = f"{asset_prefix}favicon.png"
    cc = f"{asset_prefix}cc-by-sa.png"
    agpl = f"{asset_prefix}agplv3.png"
    return (
        '<footer class="cfp-bar">'
        '<a class="cfp-brand" href="https://codefor.pt" rel="noopener noreferrer" '
        'title="Realização: code for portugal — codefor.pt (em breve)">'
        f'<img class="mark" src="{mark}" width="28" height="28" '
        'alt="code for portugal" />'
        '<span class="name">Realização: code for portugal</span>'
        '<span class="soon">codefor.pt · em breve</span>'
        "</a>"
        '<span class="cfp-lic">'
        '<a href="https://creativecommons.org/licenses/by-sa/4.0/" '
        'rel="noopener noreferrer license" title="Conteúdo · CC BY-SA 4.0">'
        f'<img src="{cc}" width="88" height="31" alt="CC BY-SA 4.0" />'
        "</a>"
        '<a href="https://www.gnu.org/licenses/agpl-3.0.html" '
        'rel="noopener noreferrer license" title="Código · AGPL-3.0">'
        f'<img src="{agpl}" width="88" height="31" alt="AGPL-3.0" />'
        "</a>"
        "</span>"
        "</footer>"
    )


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _safe_href(url: object) -> str:
    text = str(url or "").strip()
    scheme = urlparse(text).scheme.lower()
    if scheme not in {"http", "https"}:
        return "#"
    return _esc(text)


def build_report_payload(
    *,
    records: list[Record],
    sources: list[SourceMeta],
    keywords: list[Any],
    press: list[PressLink],
    press_errors: dict[str, str],
    skipped: dict[str, int],
) -> dict[str, Any]:
    sciproj_rows = [r for r in records if r.channel == "sciproj" and r.headline]
    private_grants = [
        r for r in records if r.channel == "grant" and not r.headline
    ]
    notes: list[str] = []
    if press_errors:
        soft: list[str] = []
        hard: list[str] = []
        for key, value in press_errors.items():
            if "429" in value or "Too Many Requests" in value:
                soft.append(
                    f"{key} pediu espera (limite de pedidos). "
                    "As ligações voltam na próxima geração com intervalo maior."
                )
            else:
                hard.append(f"{key}: {value}")
        notes.extend(soft)
        if hard:
            notes.append("Falhou: " + "; ".join(hard))
    if press and len(press) < 10:
        notes.append(f"Só {len(press)} ligações seguras (mínimo pretendido: 10).")
    return {
        "sources": [s.to_dict() for s in sources],
        "keywords": keywords_for_report(keywords),
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "totals": national_totals(records),
        "breakdowns": breakdowns(records),
        "prr": prr_subtotal(records),
        "sciproj": {
            "total": sum(r.amount_eur for r in sciproj_rows),
            "count": len(sciproj_rows),
        },
        "private_grants_count": len(private_grants),
        "skipped": skipped,
        "press": [p.to_dict() for p in press],
        "press_errors": press_errors,
        "press_note": " ".join(notes),
        "records": [r.to_dict() for r in records],
    }


def validate_report(payload: dict[str, Any], schema_file: Path | None = None) -> None:
    path = schema_file or schema_path()
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)


def write_csv(path: Path, records: list[Record], channel: str) -> None:
    rows = [r for r in records if r.channel == channel]
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "source_id",
        "buyer",
        "excerpt",
        "amount_eur",
        "region",
        "district",
        "place",
        "category",
        "vendor",
        "fundos",
        "year",
        "headline",
        "product",
        "url",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in rows:
            writer.writerow({key: getattr(record, key) for key in fieldnames})


def _embed_payload(payload: dict[str, Any]) -> str:
    embed = json.loads(json.dumps(payload, ensure_ascii=False))
    for item in embed.get("press") or []:
        if urlparse(str(item.get("url") or "")).scheme.lower() not in {
            "http",
            "https",
        }:
            item["url"] = ""
    return json.dumps(embed, ensure_ascii=False)


def _fmt_date(iso: str) -> str:
    if len(iso) >= 10 and iso[4] == "-":
        year, month, day = iso[:10].split("-")
        return f"{day}-{month}-{year}"
    return iso


def eur(value: object) -> str:
    return format_eur(float(value or 0))


def eur_compact(value: object) -> str:
    return format_eur_compact(float(value or 0))


def render_html(payload: dict[str, Any], *, scope: str = "national") -> str:
    if scope == "leiria":
        return render_leiria_html(payload)
    return render_presentation_html(payload)


def render_presentation_html(payload: dict[str, Any]) -> str:
    totals = payload["totals"]
    years = [str(y) for y in YEAR_LIST]
    match_kw = [k for k in payload["keywords"] if k["kind"] == "match"]
    by_vendor: dict[str, list[str]] = {}
    for item in match_kw:
        by_vendor.setdefault(item["vendor"], []).append(item["pattern"])
    kw_cols = "".join(
        "<div class='kw-col reveal'>"
        f"<h3>{_esc(vendor)}</h3><ul>"
        + "".join(f"<li>{_esc(term)}</li>" for term in terms)
        + "</ul></div>"
        for vendor, terms in sorted(by_vendor.items())
    )
    sources_html = "".join(
        "<li class='reveal'>"
        f'<a href="{_safe_href(s["url"])}" rel="noopener noreferrer">'
        f"{_esc(s['title'])}</a>"
        f"<span> · {_esc(s.get('coverage') or '')}</span></li>"
        for s in payload.get("sources") or []
    )
    def year_total(y: str) -> dict[str, float]:
        row = totals.get(y) or {}
        return {
            "committed": float(row.get("committed") or 0),
            "requested": float(row.get("requested") or 0),
            "grants": float(row.get("grants") or 0),
        }

    def year_card(y: str) -> str:
        row = year_total(y)
        committed = float(row["committed"] or 0)
        requested = float(row["requested"] or 0)
        if committed > 0 and requested > 0:
            pct = round((requested / committed - 1.0) * 100)
            if pct > 0:
                pedido = f"pedido estava {pct}% maior"
            elif pct < 0:
                pedido = f"pedido estava {abs(pct)}% menor"
            else:
                pedido = "pedido ao nível do contrato"
        elif requested > 0:
            pedido = "só pedido ao mercado"
        else:
            pedido = "sem pedido ao mercado"
        grants = (
            f"<p class='s'>apoio aprovado {_esc(eur(row['grants']))}</p>"
            if row["grants"] > 0
            else ""
        )
        return (
            "<article class='year-card reveal'>"
            f"<p class='y'>{_esc(y)}</p>"
            f"<p class='n'>{_esc(eur_compact(committed))}</p>"
            "<p class='c'>contrato assinado</p>"
            f"<p class='s'>{_esc(pedido)}</p>"
            f"{grants}</article>"
        )

    year_cards = "".join(year_card(y) for y in years)
    algema_html = _algema_cards_html(_committed_top100(payload))
    data_json = _escape_json(_embed_payload(payload))
    nuts_geo = _escape_json(
        (data_dir() / "nuts2_pt.geojson").read_text(encoding="utf-8")
    )
    year_labels = json.dumps(years)
    assets = _brand_asset_prefix(scope="national")
    brand_head = _brand_head(assets)
    brand_tokens = _brand_tokens_css()
    brand_footer_css = _brand_footer_css()
    cfp_footer = _cfp_footer(assets)
    return f"""<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Dinheiro público e produtos GAFAM (2022–2026)</title>
  {brand_head}
  <link href="https://cdn.jsdelivr.net/npm/remixicon@4.3.0/fonts/remixicon.css" rel="stylesheet" />
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
  <script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    {brand_tokens}
    * {{ box-sizing: border-box; }}
    html {{ scroll-snap-type: y mandatory; scroll-behavior: smooth; }}
    body {{
      margin: 0;
      font-family: var(--font);
      font-weight: 500;
      color: var(--ink);
      background: var(--ink);
      overflow-x: hidden;
    }}
    {brand_footer_css}
    ::selection {{ background: var(--lime); color: var(--ink); }}
    a {{ color: inherit; }}
    .deck {{
      scroll-snap-type: y mandatory;
    }}
    .slide {{
      min-height: 100vh;
      min-height: 100dvh;
      scroll-snap-align: start;
      scroll-snap-stop: always;
      padding: clamp(1.5rem, 4vw, 3rem);
      padding-bottom: calc(clamp(1.5rem, 4vw, 3rem) + var(--cfp-bar));
      display: flex;
      flex-direction: column;
      justify-content: center;
      position: relative;
      overflow: hidden;
    }}
    .slide h1, .slide h2 {{
      margin: 0 0 0.4em;
      font-weight: 800;
      letter-spacing: -0.03em;
      line-height: 1.05;
      max-width: 18ch;
    }}
    .slide h1 {{ font-size: clamp(2.4rem, 7vw, 5rem); }}
    .slide h2 {{ font-size: clamp(1.8rem, 5vw, 3.4rem); }}
    .lead {{
      font-size: clamp(1rem, 2.2vw, 1.35rem);
      max-width: 42rem;
      line-height: 1.45;
      margin: 0 0 1.5rem;
    }}
    .meta {{
      font-family: var(--mono);
      font-size: 0.75rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      opacity: 0.75;
    }}
    .slide--hero {{
      background:
        radial-gradient(circle at 80% 20%, rgba(253,82,136,.5), transparent 42%),
        radial-gradient(circle at 12% 78%, rgba(114,225,35,.35), transparent 38%),
        linear-gradient(145deg, #010101 0%, #1a1216 55%, #2a0a14 100%);
      color: var(--paper);
    }}
    .slide--years {{
      background: var(--paper);
      color: var(--ink);
    }}
    .slide--chart {{
      background: #fff;
      color: var(--ink);
    }}
    .slide--chart:nth-of-type(odd) {{
      background: linear-gradient(180deg, #fff 0%, #f7f7f2 100%);
    }}
    .slide--map {{
      background: #010101;
      color: #f4f4f0;
    }}
    .slide--map .lead {{ opacity: 0.85; }}
    .slide--map .map-legend {{ color: #c8c4b8; }}
    .slide--map .map-legend span {{
      border-color: rgba(244,244,240,.25);
    }}
    .slide--kw {{
      background: linear-gradient(160deg, #fd5288 0%, #eb5423 55%, #f4ea15 100%);
      color: #010101;
    }}
    .slide--press {{
      background: #010101;
      color: var(--paper);
    }}
    .slide--end {{
      background: var(--coral);
      color: #fff;
    }}
    .year-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(9.5rem, 1fr));
      gap: 1rem;
      margin-top: 1rem;
    }}
    .year-card {{
      background: var(--ink);
      color: var(--paper);
      padding: 1rem 1.1rem;
      border-radius: 1rem;
      transform: translateY(18px);
      opacity: 0;
      transition: transform .7s cubic-bezier(.2,.8,.2,1), opacity .7s cubic-bezier(.2,.8,.2,1);
    }}
    .year-card.is-in {{ transform: none; opacity: 1; }}
    .year-card:nth-child(2) {{ background: var(--coral); }}
    .year-card:nth-child(3) {{ background: var(--teal); }}
    .year-card:nth-child(4) {{ background: var(--violet); }}
    .year-card:nth-child(5) {{ background: var(--gold); color: var(--ink); }}
    .year-card .y {{
      font-family: var(--mono);
      font-size: 0.75rem;
      margin: 0 0 0.5rem;
      letter-spacing: 0.06em;
    }}
    .year-card .n {{
      font-size: clamp(1rem, 2.4vw, 1.35rem);
      font-weight: 800;
      margin: 0;
      letter-spacing: -0.02em;
    }}
    .year-card .c, .year-card .s {{
      margin: 0.35rem 0 0;
      font-size: 0.78rem;
      opacity: 0.9;
    }}
    .algema-stack {{
      display: flex; flex-direction: column; gap: 1.25rem; margin-top: 1rem;
    }}
    .algema-vendor {{
      margin: 0 0 .55rem;
      font-family: var(--mono); font-size: .72rem; font-weight: 700;
      letter-spacing: .06em; text-transform: uppercase; opacity: .7;
    }}
    .algema-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 1rem;
    }}
    @media (max-width: 860px) {{ .algema-grid {{ grid-template-columns: 1fr; }} }}
    .algema {{
      background: #fff;
      border-radius: 1.25rem;
      padding: 1.25rem 1.35rem 1.4rem;
      border: 1px solid #e5dfd2;
      position: relative;
      overflow: hidden;
    }}
    .algema:nth-child(1) {{ background: linear-gradient(160deg, #010101, #222); color: var(--paper); border: 0; }}
    .algema:nth-child(2) {{ background: linear-gradient(160deg, #fd5288, #eb5423); color: #fff; border: 0; }}
    .algema:nth-child(3) {{ background: linear-gradient(160deg, #72e123, #3d8f12); color: #010101; border: 0; }}
    .algema i {{
      font-size: 2.2rem;
      display: block;
      margin-bottom: .65rem;
      opacity: .95;
    }}
    .algema h3 {{ margin: 0; font-size: 1.35rem; letter-spacing: -0.02em; }}
    .algema .anos {{
      margin: .55rem 0 .85rem;
      font-size: clamp(1.15rem, 2.4vw, 1.45rem);
      font-weight: 800;
      letter-spacing: -0.02em;
      line-height: 1.2;
    }}
    .algema .chain {{
      display: flex; gap: .35rem; align-items: center; margin-bottom: .35rem;
    }}
    .algema .bead {{
      width: 14px; height: 14px; border-radius: 999px;
      background: rgba(255,255,255,.2);
      box-shadow: 0 0 0 1px rgba(255,255,255,.25);
    }}
    .algema .bead.is-on {{
      background: var(--gold);
      box-shadow: 0 0 0 1px rgba(244,234,21,.55), 0 0 10px rgba(244,234,21,.45);
    }}
    .handcuff-mark {{
      position: absolute; right: -0.4rem; bottom: -0.6rem;
      font-size: 6rem; opacity: .12; transform: rotate(-18deg); pointer-events: none;
    }}
    .chart-box {{
      flex: 1;
      min-height: 280px;
      max-height: 62vh;
      position: relative;
      margin-top: 1rem;
    }}
    .chart-box canvas, #mapRegion {{
      width: 100% !important;
      height: 100% !important;
    }}
    #mapRegion {{
      border-radius: 1.25rem;
      background:
        radial-gradient(ellipse 55% 45% at 48% 42%,
          #1a1520 0%, #0a0a0e 55%, #010101 100%);
      min-height: 420px;
      box-shadow: inset 0 0 80px rgba(0,0,0,.65);
    }}
    #mapRegion .leaflet-interactive {{
      filter: drop-shadow(0 0 1px rgba(244, 234, 21, 0.15));
    }}
    #mapRegion .night-lit {{
      filter:
        drop-shadow(0 0 6px rgba(244, 234, 21, 0.55))
        drop-shadow(0 0 14px rgba(253, 82, 136, 0.35));
    }}
    .map-legend {{
      margin-top: 0.75rem;
      font-family: var(--mono);
      font-size: 0.7rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .map-legend span {{
      display: inline-block;
      width: 14px; height: 10px;
      margin-right: 4px;
      vertical-align: middle;
      border: 1px solid rgba(1,1,1,.25);
    }}
    .kw-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
      gap: 1rem;
      margin-top: 1rem;
    }}
    .kw-col {{
      background: rgba(255,255,255,.12);
      border-radius: 1rem;
      padding: 1rem;
    }}
    .kw-col h3 {{ margin: 0 0 0.6rem; font-size: 1.1rem; }}
    .kw-col ul {{ margin: 0; padding: 0; list-style: none; }}
    .kw-col li {{
      font-family: var(--mono);
      font-size: 0.8rem;
      padding: 0.2rem 0;
      border-bottom: 1px solid rgba(255,255,255,.15);
    }}
    .list {{
      list-style: none;
      margin: 0;
      padding: 0;
      max-width: 52rem;
    }}
    .list li {{
      padding: 0.65rem 0;
      border-bottom: 1px solid rgba(246,241,231,.2);
      font-size: 1.05rem;
    }}
    .list span {{ opacity: 0.7; font-family: var(--mono); font-size: 0.8rem; }}
    .note {{
      max-width: 42rem;
      background: rgba(6,42,50,.06);
      padding: 0.85rem 1rem;
      border-radius: 0.75rem;
    }}
    .note a {{ color: var(--coral); font-weight: 700; }}
    .progress {{
      position: fixed;
      top: 0; left: 0; height: 4px;
      width: 0;
      background: linear-gradient(90deg, var(--coral), var(--lime), var(--sky));
      z-index: 40;
      transition: width .15s linear;
    }}
    .dots {{
      position: fixed;
      right: 1rem;
      top: 50%;
      transform: translateY(-50%);
      display: flex;
      flex-direction: column;
      gap: 0.45rem;
      z-index: 30;
    }}
    .dots a {{
      width: 10px; height: 10px;
      border-radius: 999px;
      background: rgba(255,255,255,.35);
      border: 1px solid rgba(6,42,50,.2);
    }}
    .dots a.is-active {{
      background: var(--coral);
      transform: scale(1.25);
    }}
    .reveal {{
      opacity: 0;
      transform: translateY(22px) scale(0.98);
      filter: blur(4px);
      transition:
        opacity .8s cubic-bezier(.2,.8,.2,1),
        transform .8s cubic-bezier(.2,.8,.2,1),
        filter .8s cubic-bezier(.2,.8,.2,1);
    }}
    .reveal.is-in {{
      opacity: 1;
      transform: none;
      filter: none;
    }}
    .linkbar {{
      margin-top: 1.5rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
    }}
    .linkbar a {{
      display: inline-block;
      padding: 0.7rem 1rem;
      border-radius: 999px;
      background: var(--ink);
      color: var(--paper);
      text-decoration: none;
      font-weight: 700;
    }}
    .linkbar a.alt {{
      background: var(--lime);
      color: var(--ink);
    }}
    @media (max-width: 700px) {{
      .dots {{ display: none; }}
      #mapRegion {{ min-height: 300px; }}
    }}
  </style>
</head>
<body>
  <div class="progress" id="progress"></div>
  <nav class="dots" id="dots" aria-label="Slides"></nav>
  <main class="deck">
    <section class="slide slide--hero" id="s0" data-title="Início">
      <p class="meta reveal">Apresentação · 2022–2026</p>
      <h1 class="reveal">Dinheiro público e produtos GAFAM</h1>
      <p class="lead reveal">As big tech americanas operam sob o Cloud Act dos EUA:
      no «dia 0», uma decisão política em Washington pode cortar o serviço —
      ou as agências (FBI e outras) podem aceder aos dados sem notificar
      o Estado português. Este relatório rastreia contratos e pedidos públicos
      com nomes GAFAM nos ficheiros oficiais, 2022–2026, para medir essa
      dependência.</p>
      <div class="linkbar reveal">
        <a href="leiria/">Distrito de Leiria</a>
        <a class="alt" href="#s1">Começar</a>
      </div>
    </section>

    <section class="slide slide--years" id="s1" data-title="Anos">
      <h2 class="reveal">Cinco anos com Google, Amazon, Facebook, Apple, Microsoft</h2>
      <div class="year-grid">{year_cards}</div>
    </section>

    <section class="slide slide--chart" id="s2" data-title="Série">
      <h2 class="reveal">Assinatura VS pedidos</h2>
      <p class="lead reveal">Contrato assinado vs pedido ao mercado (2022–2026).</p>
      <div class="chart-box reveal"><canvas id="chartYears"></canvas></div>
    </section>

    <section class="slide slide--map" id="s3" data-title="Dia 0">
      <h2 class="reveal">Portugal no dia 0</h2>
      <p class="lead reveal">Imagina que os EUA desligam os produtos GAFAM.
      Quais regiões seriam mais impactadas? As zonas claras dependem pouco;
      as escuras ficam com problemas sérios (contrato assinado 2025, continente).</p>
      <div class="chart-box reveal">
        <div id="mapRegion" role="img" aria-label="Mapa NUTS II continental 2025 — impacto no dia 0"></div>
      </div>
      <div class="map-legend" id="mapLegend"></div>
    </section>

    <section class="slide slide--chart" id="s4" data-title="Categoria">
      <h2 class="reveal">Por categoria · 2025</h2>
      <div class="chart-box reveal"><canvas id="chartCategory"></canvas></div>
    </section>

    <section class="slide slide--chart" id="s5" data-title="Fornecedor">
      <h2 class="reveal">Por fornecedor · 2022–2026</h2>
      <div class="chart-box reveal"><canvas id="chartVendor"></canvas></div>
    </section>

    <section class="slide slide--years" id="s6" data-title="Lock-in">
      <h2 class="reveal">As algemas das Big Techs</h2>
      <p class="lead reveal">Nos 100 maiores contratos nacionais, Microsoft e Google
      voltam ano após ano — algemas medidas em anos distintos com despesa.</p>
      {algema_html}
    </section>

    <section class="slide slide--kw" id="s7" data-title="Léxico">
      <h2 class="reveal">Palavras-chave</h2>
      <p class="lead reveal">Uma coluna por big tech.</p>
      <div class="kw-grid">{kw_cols}</div>
    </section>

    <section class="slide slide--end" id="s8" data-title="Fontes">
      <h2 class="reveal">Fontes</h2>
      <ul class="list">{sources_html}</ul>
      <div class="linkbar reveal">
        <a href="data.json">data.json</a>
        <a href="contratos.csv">contratos.csv</a>
        <a class="alt" href="leiria/">Abrir Leiria</a>
      </div>
      <p class="meta reveal" style="margin-top:1.5rem">2026 incompleto até à data dos ficheiros.
      Contrato e pedido não se somam.</p>
    </section>
  </main>
  <script id="report-data" type="application/json">{data_json}</script>
  <script>
    const payload = JSON.parse(document.getElementById('report-data').textContent);
    const yearLabels = {year_labels};
    const ink = '#010101';
    const coral = '#fd5288';
    const teal = '#72e123';
    const gold = '#f4ea15';
    const violet = '#eb5423';
    const slides = [...document.querySelectorAll('.slide')];
    const dots = document.getElementById('dots');
    const progress = document.getElementById('progress');
    slides.forEach((slide, i) => {{
      const a = document.createElement('a');
      a.href = '#' + slide.id;
      a.title = slide.dataset.title || ('Slide ' + (i + 1));
      dots.appendChild(a);
    }});
    const dotLinks = [...dots.querySelectorAll('a')];
    const io = new IntersectionObserver((entries) => {{
      entries.forEach((entry) => {{
        if (entry.isIntersecting) {{
          entry.target.querySelectorAll('.reveal, .year-card').forEach((el, idx) => {{
            el.style.transitionDelay = (idx * 60) + 'ms';
            el.classList.add('is-in');
          }});
          const i = slides.indexOf(entry.target);
          dotLinks.forEach((d, j) => d.classList.toggle('is-active', j === i));
        }}
      }});
    }}, {{ threshold: 0.45 }});
    slides.forEach((s) => io.observe(s));
    window.addEventListener('scroll', () => {{
      const max = document.documentElement.scrollHeight - window.innerHeight;
      progress.style.width = (max > 0 ? (window.scrollY / max) * 100 : 0) + '%';
    }}, {{ passive: true }});

    function sortedPairs(obj) {{
      return Object.entries(obj || {{}}).sort((a, b) => b[1] - a[1]);
    }}
    function eurTick(v) {{
      return Number(v).toLocaleString('pt-PT', {{ maximumFractionDigits: 0 }}) + ' €';
    }}
    const eurTooltip = {{
      callbacks: {{
        label: function (ctx) {{
          const label = ctx.dataset.label ? ctx.dataset.label + ': ' : '';
          const v = ctx.chart.options.indexAxis === 'y' ? ctx.parsed.x : ctx.parsed.y;
          return label + eurTick(v != null ? v : ctx.raw);
        }}
      }}
    }};
    const totals = payload.totals;
    new Chart(document.getElementById('chartYears'), {{
      type: 'bar',
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
          legend: {{ position: 'bottom', labels: {{ font: {{ family: 'Courier Prime' }} }} }},
          tooltip: eurTooltip
        }},
        scales: {{
          x: {{ ticks: {{ font: {{ family: 'Courier Prime' }} }}, grid: {{ display: false }} }},
          y: {{
            beginAtZero: true,
            ticks: {{
              font: {{ family: 'Courier Prime' }},
              callback: function (v) {{ return eurTick(v); }}
            }}
          }}
        }}
      }},
      data: {{
        labels: yearLabels,
        datasets: [
          {{
            label: 'contrato assinado',
            data: yearLabels.map((y) => (totals[y] || {{}}).committed || 0),
            backgroundColor: coral,
            borderRadius: 8
          }},
          {{
            label: 'pedido ao mercado',
            data: yearLabels.map((y) => (totals[y] || {{}}).requested || 0),
            backgroundColor: teal,
            borderRadius: 8
          }}
        ]
      }}
    }});
    const categoryPairs = sortedPairs(payload.breakdowns.committed_by_category['2025']);
    new Chart(document.getElementById('chartCategory'), {{
      type: 'bar',
      options: {{
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }}, tooltip: eurTooltip }},
        scales: {{
          x: {{
            beginAtZero: true,
            ticks: {{
              font: {{ family: 'Courier Prime', size: 11 }},
              callback: function (v) {{ return eurTick(v); }}
            }}
          }},
          y: {{ ticks: {{ autoSkip: false, font: {{ family: 'Courier Prime', size: 11 }} }} }}
        }}
      }},
      data: {{
        labels: categoryPairs.map((p) => p[0]),
        datasets: [{{
          data: categoryPairs.map((p) => p[1]),
          backgroundColor: [coral, teal, gold, violet, ink, '#72e123'],
          borderRadius: 6
        }}]
      }}
    }});
    const vendorByYear = Object.fromEntries(
      yearLabels.map((y) => [y, payload.breakdowns.committed_by_vendor[y] || {{}}])
    );
    // Greyscale by year: lightest = earliest, darkest = latest (2026).
    const vendorColors = yearLabels.map((_, i) => {{
      const t = yearLabels.length <= 1 ? 1 : i / (yearLabels.length - 1);
      const shade = Math.round(210 - t * 185);
      return 'rgb(' + shade + ',' + shade + ',' + shade + ')';
    }});
    const vendorLabels = [...new Set(
      yearLabels.flatMap((y) => Object.keys(vendorByYear[y]))
    )].sort((a, b) => {{
      const sum = (name) => yearLabels.reduce(
        (acc, y) => acc + (vendorByYear[y][name] || 0), 0
      );
      return sum(b) - sum(a);
    }});
    new Chart(document.getElementById('chartVendor'), {{
      type: 'bar',
      options: {{
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
          legend: {{ position: 'bottom' }},
          tooltip: eurTooltip
        }},
        scales: {{
          x: {{
            beginAtZero: true,
            ticks: {{
              font: {{ family: 'Courier Prime', size: 11 }},
              callback: function (v) {{ return eurTick(v); }}
            }}
          }},
          y: {{ ticks: {{ autoSkip: false, font: {{ family: 'Courier Prime', size: 11 }} }} }}
        }}
      }},
      data: {{
        labels: vendorLabels,
        datasets: yearLabels.map((y, i) => ({{
          label: y,
          data: vendorLabels.map((k) => vendorByYear[y][k] || 0),
          backgroundColor: vendorColors[i],
          borderRadius: 6
        }}))
      }}
    }});

    (function drawRegionMap() {{
      const regionData = payload.breakdowns.committed_by_region['2025'] || {{}};
      const islands = {{ PT20: 1, PT30: 1 }};
      const rawGeo = {nuts_geo};
      const geo = {{
        type: 'FeatureCollection',
        features: (rawGeo.features || []).filter(function (f) {{
          return !islands[(f.properties && f.properties.id) || ''];
        }})
      }};
      // 3 quartis: claro → médio → escuro (mais GAFAM = mais impacto no dia 0)
      const night = ['#ffe9a0', '#c4782a', '#0a0a0c'];
      function fold(s) {{
        return (s || '').toLowerCase()
          .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
          .replace(/região autónoma d[oa]s?\\s+/g, '')
          .replace(/\\s*\\(pt\\)\\s*/g, '')
          .trim();
      }}
      function amountFor(geoName) {{
        const g = fold(geoName);
        for (const [k, v] of Object.entries(regionData)) {{
          if (k === 'sem local') continue;
          const kk = fold(k);
          if (g === kk || g.indexOf(kk) >= 0 || kk.indexOf(g) >= 0) return v;
        }}
        return 0;
      }}
      function eurLabel(v) {{
        return Number(v).toLocaleString('pt-PT', {{ maximumFractionDigits: 0 }}) + ' €';
      }}
      const values = geo.features.map((f) => amountFor(f.properties.name))
        .filter((v) => v > 0).sort((a, b) => a - b);
      const cuts = [];
      if (values.length) {{
        for (let i = 1; i <= 3; i++) {{
          const idx = Math.min(values.length - 1, Math.ceil((i / 3) * values.length) - 1);
          cuts.push(values[idx]);
        }}
      }}
      function bin(v) {{
        if (!cuts.length || v <= 0) return 0;
        for (let i = 0; i < cuts.length; i++) {{
          if (v <= cuts[i]) return i + 1;
        }}
        return cuts.length;
      }}
      function binLabel(i) {{
        if (!cuts.length) return '—';
        if (i === 1) return '< ' + eurLabel(cuts[0]);
        if (i === cuts.length) return '≥ ' + eurLabel(cuts[Math.max(0, cuts.length - 2)]);
        return '≤ ' + eurLabel(cuts[i - 1]);
      }}
      function color(v) {{
        const b = bin(v);
        return b === 0 ? '#121218' : night[b - 1];
      }}
      const map = L.map('mapRegion', {{
        zoomControl: false, attributionControl: false,
        dragging: false, scrollWheelZoom: false,
        doubleClickZoom: false, boxZoom: false, keyboard: false
      }});
      const layer = L.geoJSON(geo, {{
        style: function (feat) {{
          const v = amountFor(feat.properties.name);
          const b = bin(v);
          return {{
            color: b === 1 ? '#ffe9a0' : '#1c1c22',
            weight: b === 1 ? 1.5 : 1,
            fillColor: color(v),
            fillOpacity: 0.98,
            className: b === 1 ? 'night-lit' : ''
          }};
        }},
        onEachFeature: function (feat, lyr) {{
          const v = amountFor(feat.properties.name);
          lyr.bindTooltip(
            feat.properties.name + ' — ' + eurLabel(v)
          );
        }}
      }}).addTo(map);
      map.fitBounds(layer.getBounds(), {{ padding: [16, 16], maxZoom: 7 }});
      const sem = regionData['sem local'] || 0;
      document.getElementById('mapLegend').innerHTML =
        night.map((c, i) =>
          '<span style="background:' + c + '"></span>' + binLabel(i + 1)
        ).join(' · ') +
        (sem ? ' · sem local: ' + eurLabel(sem) : '');
    }})();
  </script>
{cfp_footer}
</body>
</html>
"""


def _lockin_from_top(
    records: list[dict[str, Any]],
) -> list[tuple[str, str, int, int, int, float]]:
    """Produto → (vendor, n, anos distintos, janela anos, montante) nos 100 maiores."""
    by_product: dict[str, dict[str, Any]] = {}
    for row in records[:100]:
        product = str(row.get("product") or "—")
        year = int(row.get("year") or 0)
        bucket = by_product.setdefault(
            product,
            {
                "vendor": str(row.get("vendor") or "—"),
                "years": set(),
                "n": 0,
                "amount": 0.0,
            },
        )
        if year:
            bucket["years"].add(year)
        bucket["n"] += 1
        bucket["amount"] += float(row.get("amount_eur") or 0)
        if row.get("vendor"):
            bucket["vendor"] = str(row["vendor"])
    rows: list[tuple[str, str, int, int, int, float]] = []
    for product, bucket in by_product.items():
        years = sorted(bucket["years"])
        span = (years[-1] - years[0] + 1) if years else 0
        rows.append(
            (
                product,
                str(bucket["vendor"]),
                int(bucket["n"]),
                len(years),
                span,
                float(bucket["amount"]),
            )
        )
    rows.sort(key=lambda item: item[5], reverse=True)
    return rows


_ALGEMA_ROWS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Microsoft", ("Office 365", "Microsoft", "Teams")),
    ("Google", ("Google", "Google Cloud", "Android")),
)
_ALGEMA_ICONS = {
    "Office 365": "ri-file-word-2-fill",
    "Microsoft": "ri-windows-fill",
    "Teams": "ri-team-fill",
    "Google": "ri-google-fill",
    "Google Cloud": "ri-cloud-fill",
    "Android": "ri-android-fill",
}


def _committed_top100(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = [
        r
        for r in payload.get("records") or []
        if r.get("channel") == "committed" and r.get("headline")
    ]
    records.sort(key=lambda r: float(r.get("amount_eur") or 0), reverse=True)
    return records


def _algema_card(product: str, years_n: int) -> str:
    chain = "".join(
        f"<span class='bead{' is-on' if i < years_n else ''}'></span>"
        for i in range(5)
    )
    anos = (
        f"{years_n} ano de algemas"
        if years_n == 1
        else f"{years_n} anos de algemas"
    )
    return (
        "<article class='algema reveal'>"
        f"<i class='{_ALGEMA_ICONS.get(product, 'ri-lock-2-fill')}' aria-hidden='true'></i>"
        "<i class='ri-link handcuff-mark' aria-hidden='true'></i>"
        f"<h3>{_esc(product)}</h3>"
        f"<p class='anos'>{_esc(anos)}</p>"
        f"<div class='chain' aria-hidden='true'>{chain}</div>"
        "</article>"
    )


def _algema_cards_html(records: list[dict[str, Any]]) -> str:
    lockin_by_name = {row[0]: row for row in _lockin_from_top(records)}
    rows_html: list[str] = []
    any_hit = False
    for vendor, products in _ALGEMA_ROWS:
        cards: list[str] = []
        for name in products:
            row = lockin_by_name.get(name)
            years_n = int(row[3]) if row else 0
            if row:
                any_hit = True
            cards.append(_algema_card(name, years_n))
        rows_html.append(
            "<div class='algema-row'>"
            f"<p class='algema-vendor'>{_esc(vendor)}</p>"
            f"<div class='algema-grid'>{''.join(cards)}</div>"
            "</div>"
        )
    if not any_hit:
        return (
            "<p class='reveal'>Sem Microsoft / Google no top 100 "
            "(Office 365, Teams, Google Cloud, Android…).</p>"
        )
    return f"<div class='algema-stack'>{''.join(rows_html)}</div>"


def render_leiria_html(payload: dict[str, Any]) -> str:
    totals = payload["totals"]
    years = [str(y) for y in YEAR_LIST]
    mun_labels = {
        line.strip()
        for line in (data_dir() / "distrito_leiria.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    mun_fold = {fold(name) for name in mun_labels}
    records = _committed_top100(payload)
    rows = "".join(
        "<tr class='reveal'>"
        f"<td>{_esc(r.get('year'))}</td>"
        f"<td>{_esc(r.get('place') or '—')}</td>"
        f"<td>{_esc(r.get('buyer'))}</td>"
        f"<td>{_esc(r.get('product'))}</td>"
        f"<td class='num'>{eur(r.get('amount_eur'))}</td>"
        f"<td>{_esc((r.get('excerpt') or '')[:120])}</td>"
        "</tr>"
        for r in records[:100]
    ) or "<tr><td colspan='6'>Sem contratos no distrito neste período.</td></tr>"
    place_year = (
        (payload.get("breakdowns") or {})
        .get("committed_by_place", {})
        .get("2025", {})
    )
    place_pairs = sorted(
        (
            (name, value)
            for name, value in place_year.items()
            if fold(str(name)) in mun_fold
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:10]
    place_list = "".join(
        f"<li class='reveal'><strong>{_esc(name)}</strong> — {eur(value)}</li>"
        for name, value in place_pairs
    ) or "<li class='reveal'>Sem repartição por concelho.</li>"
    vendor_pairs = sorted(
        (
            (payload.get("breakdowns") or {})
            .get("committed_by_vendor", {})
            .get("2025", {})
            .items()
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    algema_html = _algema_cards_html(records)
    year_cards = "".join(
        "<article class='year-card reveal'>"
        f"<p class='y'>{_esc(y)}</p>"
        f"<p class='n'>{_esc(eur_compact(totals[y]['committed']))}</p>"
        "<p class='c'>€ contratado GAFAM</p>"
        "</article>"
        for y in years
    )
    data_json = _escape_json(_embed_payload(payload))
    year_labels = json.dumps(years)
    place_all = {
        name: value
        for name, value in place_year.items()
        if fold(str(name)) in mun_fold
    }
    place_json = json.dumps(place_all, ensure_ascii=False)
    vendor_json = json.dumps(vendor_pairs, ensure_ascii=False)
    assets = _brand_asset_prefix(scope="leiria")
    brand_head = _brand_head(assets)
    brand_tokens = _brand_tokens_css()
    brand_footer_css = _brand_footer_css()
    cfp_footer = _cfp_footer(assets)
    return f"""<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>GAFAM · Distrito de Leiria (2022–2026)</title>
  {brand_head}
  <link href="https://cdn.jsdelivr.net/npm/remixicon@4.3.0/fonts/remixicon.css" rel="stylesheet" />
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
  <script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    {brand_tokens}
    * {{ box-sizing: border-box; }}
    html {{ scroll-snap-type: y mandatory; scroll-behavior: smooth; }}
    body {{
      margin: 0; font-family: var(--font); font-weight: 500; color: var(--ink);
      background: var(--paper); overflow-x: hidden;
    }}
    {brand_footer_css}
    .progress {{
      position: fixed; top: 0; left: 0; height: 4px; width: 0; z-index: 40;
      background: linear-gradient(90deg, var(--coral), var(--lime), var(--gold), var(--sky));
      transition: width .15s linear;
    }}
    .dots {{
      position: fixed; right: 1rem; top: 50%; transform: translateY(-50%);
      display: flex; flex-direction: column; gap: .45rem; z-index: 30;
    }}
    .dots a {{
      width: 10px; height: 10px; border-radius: 999px;
      background: rgba(1,1,1,.25); border: 1px solid rgba(1,1,1,.2);
    }}
    .dots a.is-active {{ background: var(--coral); transform: scale(1.25); }}
    .slide {{
      min-height: 100vh; min-height: 100dvh;
      scroll-snap-align: start; scroll-snap-stop: always;
      padding: clamp(1.25rem, 4vw, 2.5rem);
      padding-bottom: calc(clamp(1.25rem, 4vw, 2.5rem) + var(--cfp-bar));
      display: flex; flex-direction: column; justify-content: center;
      max-width: 1100px; margin: 0 auto;
    }}
    .slide--hero {{
      max-width: none; color: var(--paper);
      background:
        radial-gradient(circle at 82% 18%, rgba(253,82,136,.45), transparent 40%),
        radial-gradient(circle at 10% 80%, rgba(114,225,35,.3), transparent 35%),
        linear-gradient(135deg, #010101, #2a0a14 70%, #1a1a1a);
      padding-left: max(clamp(1.25rem, 4vw, 2.5rem), calc(50vw - 550px));
      padding-right: max(clamp(1.25rem, 4vw, 2.5rem), calc(50vw - 550px));
    }}
    .slide--map {{
      max-width: none; color: #f4f4f0; background: #010101;
      padding-left: max(clamp(1.25rem, 4vw, 2.5rem), calc(50vw - 550px));
      padding-right: max(clamp(1.25rem, 4vw, 2.5rem), calc(50vw - 550px));
    }}
    h1 {{ font-size: clamp(2rem, 5vw, 3.4rem); letter-spacing: -0.03em; margin: 0 0 .4em; font-weight: 800; }}
    h2 {{ font-size: clamp(1.6rem, 4vw, 2.4rem); margin: 0 0 .6em; letter-spacing: -0.02em; font-weight: 800; }}
    .lead {{
      max-width: 42rem; font-size: 1.1rem; line-height: 1.45; margin: 0 0 1rem;
      text-align: left; text-wrap: pretty;
    }}
    .meta {{ font-family: var(--mono); font-size: .75rem; letter-spacing: .04em; text-transform: uppercase; opacity: .8; }}
    .year-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(9.5rem, 1fr));
      gap: 1rem;
      margin-top: 1.25rem;
    }}
    .year-card {{
      background: rgba(5, 8, 12, .45);
      color: var(--paper);
      padding: 1rem 1.1rem;
      border-radius: 1rem;
      border: 1px solid rgba(246,241,231,.12);
    }}
    .year-card:nth-child(2) {{ background: var(--coral); border-color: transparent; }}
    .year-card:nth-child(3) {{ background: var(--teal); border-color: transparent; }}
    .year-card:nth-child(4) {{ background: var(--violet); border-color: transparent; }}
    .year-card:nth-child(5) {{ background: var(--gold); color: var(--ink); border-color: transparent; }}
    .year-card .y {{
      font-family: var(--mono); font-size: .75rem; margin: 0 0 .5rem; letter-spacing: .06em;
    }}
    .year-card .n {{
      font-size: clamp(1.05rem, 2.6vw, 1.45rem); font-weight: 800; margin: 0;
      letter-spacing: -0.02em;
    }}
    .year-card .c {{ margin: .4rem 0 0; font-size: .78rem; opacity: .9; }}
    .algema-stack {{
      display: flex; flex-direction: column; gap: 1.25rem; margin-top: 1rem;
    }}
    .algema-vendor {{
      margin: 0 0 .55rem;
      font-family: var(--mono); font-size: .72rem; font-weight: 700;
      letter-spacing: .06em; text-transform: uppercase; opacity: .7;
    }}
    .algema-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 1rem;
    }}
    @media (max-width: 860px) {{ .algema-grid {{ grid-template-columns: 1fr; }} }}
    .algema {{
      background: #fff;
      border-radius: 1.25rem;
      padding: 1.25rem 1.35rem 1.4rem;
      border: 1px solid #e5dfd2;
      position: relative;
      overflow: hidden;
    }}
    .algema:nth-child(1) {{ background: linear-gradient(160deg, #010101, #222); color: var(--paper); border: 0; }}
    .algema:nth-child(2) {{ background: linear-gradient(160deg, #fd5288, #eb5423); color: #fff; border: 0; }}
    .algema:nth-child(3) {{ background: linear-gradient(160deg, #72e123, #3d8f12); color: #010101; border: 0; }}
    .algema i {{
      font-size: 2.2rem;
      display: block;
      margin-bottom: .65rem;
      opacity: .95;
    }}
    .algema h3 {{ margin: 0; font-size: 1.35rem; letter-spacing: -0.02em; }}
    .algema .anos {{
      margin: .55rem 0 .85rem;
      font-size: clamp(1.15rem, 2.4vw, 1.45rem);
      font-weight: 800;
      letter-spacing: -0.02em;
      line-height: 1.2;
    }}
    .algema .chain {{
      display: flex; gap: .35rem; align-items: center; margin-bottom: .35rem;
    }}
    .algema .bead {{
      width: 14px; height: 14px; border-radius: 999px;
      background: rgba(255,255,255,.2);
      box-shadow: 0 0 0 1px rgba(255,255,255,.25);
    }}
    .algema .bead.is-on {{
      background: var(--gold);
      box-shadow: 0 0 0 1px rgba(244,234,21,.55), 0 0 10px rgba(244,234,21,.45);
    }}
    .handcuff-mark {{
      position: absolute; right: -0.4rem; bottom: -0.6rem;
      font-size: 6rem; opacity: .12; transform: rotate(-18deg); pointer-events: none;
    }}
    .chart-box {{ height: min(42vh, 320px); background: #fff; border-radius: 1rem; padding: 1rem; }}
    .slide--map .chart-box, .map-panel {{
      background: transparent; padding: 0; height: auto;
    }}
    .map-panel {{
      background: #0a0a0e;
      color: #f4f4f0;
      border-radius: 1.25rem;
      padding: 1rem;
    }}
    #mapLeiria {{
      height: min(48vh, 420px);
      border-radius: 1rem;
      background: radial-gradient(ellipse 55% 45% at 48% 42%, #1a1520 0%, #010101 100%);
    }}
    #mapLeiria .night-lit {{
      filter: drop-shadow(0 0 6px rgba(244,234,21,.55)) drop-shadow(0 0 14px rgba(253,82,136,.35));
    }}
    .map-legend {{
      margin-top: .75rem;
      font-family: var(--mono);
      font-size: .7rem;
      letter-spacing: .04em;
      text-transform: uppercase;
      color: #c8c4b8;
    }}
    .map-legend span {{
      display: inline-block; width: 14px; height: 10px; margin-right: 4px;
      vertical-align: middle; border: 1px solid rgba(244,244,240,.25);
    }}
    .split {{
      display: grid;
      grid-template-columns: 1.2fr .8fr;
      gap: 1.25rem;
      align-items: start;
    }}
    @media (max-width: 860px) {{
      .split {{ grid-template-columns: 1fr; }}
      .dots {{ display: none; }}
    }}
    table {{
      width: 100%; border-collapse: collapse; font-size: .92rem;
      background: #fff; border-radius: 1rem; overflow: hidden;
    }}
    th, td {{
      text-align: left; padding: .65rem .7rem;
      border-bottom: 1px solid #e5dfd2; vertical-align: top;
    }}
    th {{
      font-family: var(--mono); font-size: .7rem; letter-spacing: .05em;
      text-transform: uppercase; background: #010101; color: #f4f4f0;
    }}
    td.num {{ font-family: var(--mono); white-space: nowrap; }}
    ul {{ padding-left: 1.1rem; margin: 0; }}
    a {{ color: var(--coral); font-weight: 700; }}
    .slide--hero a {{ color: var(--lime); }}
    .reveal {{
      opacity: 0; transform: translateY(16px);
      transition: opacity .6s ease, transform .6s ease;
    }}
    .reveal.is-in {{ opacity: 1; transform: none; }}
  </style>
</head>
<body>
  <div class="progress" id="progress"></div>
  <nav class="dots" id="dots" aria-label="Slides"></nav>
  <main class="deck">
  <section class="slide slide--hero" id="s0" data-title="Início">
      <p class="meta reveal"><a href="../">← apresentação nacional</a></p>
      <h1 class="reveal">Distrito de Leiria</h1>
      <p class="lead reveal">As big tech americanas operam sob o Cloud Act dos EUA:
      no «dia 0», uma decisão política em Washington pode cortar o serviço —
      ou as agências (FBI e outras) podem aceder aos dados sem notificar
      o Estado português. Aqui medimos essa dependência no distrito de Leiria:
      análise dos 16 concelhos (2022–2026), contrato e pedido GAFAM por município,
      com leitura dos apoios (grants) e da concentração da despesa local.</p>
      <div class="year-grid">{year_cards}</div>
  </section>
  <section class="slide" id="s1" data-title="Série">
    <h2 class="reveal">Assinatura VS Pedidos</h2>
    <div class="chart-box reveal"><canvas id="chartLeiriaYears"></canvas></div>
  </section>
  <section class="slide slide--map" id="s2" data-title="Concelhos">
    <h2 class="reveal">Uso nos conselhos</h2>
    <div class="split">
      <div class="map-panel reveal">
        <div id="mapLeiria" role="img" aria-label="Mapa dos concelhos do distrito de Leiria 2025"></div>
        <div class="map-legend" id="mapLeiriaLegend"></div>
      </div>
      <div>
        <p class="meta reveal">10 maiores concelhos · gastos</p>
        <ul>{place_list}</ul>
      </div>
    </div>
  </section>
  <section class="slide" id="s3" data-title="Big tech">
    <h2 class="reveal">As Big Tech quem mandam</h2>
    <div class="chart-box reveal"><canvas id="chartLeiriaVendor"></canvas></div>
  </section>
  <section class="slide" id="s4" data-title="Lock-in">
    <h2 class="reveal">As algemas das Big Techs</h2>
    <p class="lead reveal">Nos 100 maiores contratos do distrito, Microsoft e Google
    voltam ano após ano — algemas medidas em anos distintos com despesa.</p>
    {algema_html}
  </section>
  <section class="slide" id="s5" data-title="Contratos">
    <h2 class="reveal">Top 100 das maiores algemas</h2>
    <div style="overflow:auto; max-height:62vh">
      <table>
        <thead>
          <tr>
            <th>Ano</th><th>Concelho</th><th>Entidade</th>
            <th>Produto</th><th>Montante</th><th>Excerto</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    <p class="meta" style="margin-top:1rem">
      <a href="contratos.csv">contratos.csv</a> ·
      <a href="anuncios.csv">anuncios.csv</a> ·
      <a href="data.json">data.json</a>
    </p>
  </section>
  </main>
  <script id="report-data" type="application/json">{data_json}</script>
  <script>
    const payload = JSON.parse(document.getElementById('report-data').textContent);
    const yearLabels = {year_labels};
    const placeData = {place_json};
    const vendorPairs = {vendor_json};
    function eurTick(v) {{
      return Number(v).toLocaleString('pt-PT', {{ maximumFractionDigits: 0 }}) + ' €';
    }}
    const slides = [...document.querySelectorAll('.slide')];
    const dots = document.getElementById('dots');
    const progress = document.getElementById('progress');
    slides.forEach((slide) => {{
      const a = document.createElement('a');
      a.href = '#' + slide.id;
      a.title = slide.dataset.title || slide.id;
      dots.appendChild(a);
    }});
    const dotLinks = [...dots.querySelectorAll('a')];
    const io = new IntersectionObserver((entries) => {{
      entries.forEach((entry) => {{
        if (!entry.isIntersecting) return;
        entry.target.querySelectorAll('.reveal').forEach((el, idx) => {{
          el.style.transitionDelay = (idx * 50) + 'ms';
          el.classList.add('is-in');
        }});
        const i = slides.indexOf(entry.target);
        if (i >= 0) {{
          dotLinks.forEach((d, j) => d.classList.toggle('is-active', j === i));
          progress.style.width = (((i + 1) / slides.length) * 100) + '%';
          if (entry.target.id === 's2' && window.__fitLeiriaMap) window.__fitLeiriaMap();
        }}
      }});
    }}, {{ threshold: 0.45 }});
    slides.forEach((slide) => io.observe(slide));
    new Chart(document.getElementById('chartLeiriaYears'), {{
      type: 'bar',
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{
          legend: {{ position: 'bottom' }},
          tooltip: {{ callbacks: {{ label: (c) => (c.dataset.label || '') + ': ' + eurTick(c.parsed.y) }} }}
        }},
        scales: {{
          y: {{ beginAtZero: true, ticks: {{ callback: (v) => eurTick(v) }} }}
        }}
      }},
      data: {{
        labels: yearLabels,
        datasets: [
          {{
            label: 'contrato assinado',
            data: yearLabels.map((y) => payload.totals[y].committed),
            backgroundColor: '#fd5288', borderRadius: 6
          }},
          {{
            label: 'pedido ao mercado',
            data: yearLabels.map((y) => payload.totals[y].requested),
            backgroundColor: '#72e123', borderRadius: 6
          }}
        ]
      }}
    }});
    new Chart(document.getElementById('chartLeiriaVendor'), {{
      type: 'bar',
      options: {{
        indexAxis: 'y',
        responsive: true, maintainAspectRatio: false,
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{ callbacks: {{ label: (c) => eurTick(c.parsed.x) }} }}
        }},
        scales: {{
          x: {{ beginAtZero: true, ticks: {{ callback: (v) => eurTick(v) }} }}
        }}
      }},
      data: {{
        labels: vendorPairs.map((p) => p[0]),
        datasets: [{{
          data: vendorPairs.map((p) => p[1]),
          backgroundColor: ['#fd5288','#72e123','#f4ea15','#eb5423','#010101'],
          borderRadius: 6
        }}]
      }}
    }});
    (function drawLeiriaMap() {{
      const night = ['#f4ea15', '#fd5288', '#eb5423', '#3a2a22', '#0a0a0c'];
      const zeroFill = '#f4f4f0';
      function fold(s) {{
        return (s || '').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').trim();
      }}
      function eurLabel(v) {{
        return Number(v).toLocaleString('pt-PT', {{ maximumFractionDigits: 0 }}) + ' €';
      }}
      function amountFor(name) {{
        const g = fold(name);
        for (const [k, v] of Object.entries(placeData)) {{
          if (fold(k) === g) return v;
        }}
        return 0;
      }}
      function paint(munGeo) {{
        const values = Object.values(placeData).filter((v) => v > 0).sort((a, b) => a - b);
        const cuts = [];
        if (values.length) {{
          for (let i = 1; i <= 5; i++) {{
            const idx = Math.min(values.length - 1, Math.ceil((i / 5) * values.length) - 1);
            cuts.push(values[idx]);
          }}
        }}
        function bin(v) {{
          if (!cuts.length || v <= 0) return 0;
          for (let i = 0; i < cuts.length; i++) {{
            if (v <= cuts[i]) return i + 1;
          }}
          return cuts.length;
        }}
        function binLabel(i) {{
          if (!cuts.length) return '—';
          if (i === 1) return '< ' + eurLabel(cuts[0]);
          if (i === cuts.length) return '≥ ' + eurLabel(cuts[Math.max(0, cuts.length - 2)]);
          return '≤ ' + eurLabel(cuts[i - 1]);
        }}
        const map = L.map('mapLeiria', {{
          zoomControl: false, attributionControl: false,
          dragging: false, scrollWheelZoom: false,
          doubleClickZoom: false, boxZoom: false, keyboard: false
        }});
        const layer = L.geoJSON(munGeo, {{
          style: function (feat) {{
            const v = amountFor(feat.properties.name);
            const b = bin(v);
            if (b === 0) {{
              return {{
                color: '#9a9588', weight: 1,
                fillColor: zeroFill, fillOpacity: 1
              }};
            }}
            return {{
              color: b <= 2 ? '#ffe9a0' : '#1c1c22',
              weight: 1.2,
              fillColor: night[b - 1],
              fillOpacity: 0.98,
              className: b <= 2 ? 'night-lit' : ''
            }};
          }},
          onEachFeature: function (feat, lyr) {{
            const v = amountFor(feat.properties.name);
            lyr.bindTooltip(feat.properties.name + ' — ' + eurLabel(v));
          }}
        }}).addTo(map);
        function fit() {{
          map.invalidateSize();
          const bounds = layer.getBounds();
          if (bounds.isValid()) map.fitBounds(bounds, {{ padding: [12, 12] }});
        }}
        window.__fitLeiriaMap = fit;
        fit();
        requestAnimationFrame(fit);
        setTimeout(fit, 200);
        document.getElementById('mapLeiriaLegend').innerHTML =
          'CAOP2025 DGT · <span style="background:' + zeroFill + '"></span>0 € · ' +
          night.map((c, i) => '<span style="background:' + c + '"></span>' + binLabel(i + 1)).join(' · ');
      }}
      fetch('concelhos_leiria.geojson')
        .then((r) => r.json())
        .then(paint)
        .catch(function () {{
          document.getElementById('mapLeiriaLegend').textContent =
            'Mapa indisponível (falha a carregar CAOP).';
        }});
    }})();
  </script>
{cfp_footer}
</body>
</html>
"""


def _escape_json(raw: str) -> str:
    return raw.replace("<", "\\u003c")


def write_report(
    out_dir: Path,
    payload: dict[str, Any],
    records: list[Record],
    *,
    scope: str = "national",
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    validate_report(payload)
    reports_root = out_dir if scope == "national" else out_dir.parent
    _copy_brand_assets(reports_root)
    (out_dir / "data.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "index.html").write_text(
        render_html(payload, scope=scope),
        encoding="utf-8",
    )
    write_csv(out_dir / "contratos.csv", records, "committed")
    write_csv(out_dir / "anuncios.csv", records, "requested")
    write_csv(out_dir / "pt2030.csv", records, "grant")
    if scope == "leiria":
        geo_src = data_dir() / "concelhos_leiria.geojson"
        (out_dir / "concelhos_leiria.geojson").write_text(
            geo_src.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
