"""Escrita de data.json, CSVs e apresentações HTML."""

from __future__ import annotations

import csv
import html
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator

from gafam_contratos.aggregate import breakdowns, national_totals, prr_subtotal
from gafam_contratos.amounts import format_eur, format_eur_compact
from gafam_contratos.classify import fold, load_concelhos_by_distrito
from gafam_contratos.constants import YEAR_LIST
from gafam_contratos.lexicon import keywords_for_report
from gafam_contratos.models import PressLink, Record, SourceMeta
from gafam_contratos.paths import data_dir, project_root, schema_path

_BRAND_FILES = (
    "favicon.png",
    "logo.png",
    "logo-text.png",
    "cc-by-sa.png",
    "agplv3.png",
)


def _brand_asset_prefix(*, scope: str) -> str:
    return "assets/" if scope == "national" else "../assets/"


def _brand_dir() -> Path:
    shared = project_root().parent / "assets"
    if (shared / "favicon.png").is_file():
        return shared
    return data_dir() / "brand"


def _copy_brand_assets(reports_root: Path) -> None:
    src = _brand_dir()
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
        '<a href="https://github.com/codeforportugal/gafam-portugal-report" '
        'rel="noopener noreferrer" title="Código · AGPL-3.0">'
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
    private_grants = [r for r in records if r.channel == "grant" and not r.headline]
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


@dataclass(frozen=True, slots=True)
class AreaPage:
    slug: str
    name: str
    button: str
    where: str
    nuts_name: str = ""
    geojson: str = ""
    unit: str = "distrito"


def _district_pages() -> tuple[AreaPage, ...]:
    seen: list[str] = []
    with (data_dir() / "concelho_distrito.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            name = row["distrito"].strip()
            if name not in seen:
                seen.append(name)
    pages = []
    for name in seen:
        slug = fold(name).replace(" ", "-")
        pages.append(
            AreaPage(
                slug,
                f"Distrito de {name}",
                name,
                "do distrito",
            )
        )
    pages.append(
        AreaPage(
            "acores",
            "Açores",
            "Açores",
            "da região",
            "Região Autónoma dos Açores",
            unit="regiao",
        )
    )
    pages.append(
        AreaPage(
            "madeira",
            "Madeira",
            "Madeira",
            "da região",
            "Região Autónoma da Madeira",
            unit="regiao",
        )
    )
    return tuple(pages)


AREA_PAGES: tuple[AreaPage, ...] = _district_pages()
_AREAS = {area.slug: area for area in AREA_PAGES}


def area_by_slug(slug: str) -> AreaPage:
    return _AREAS[slug]


def render_html(payload: dict[str, Any], *, scope: str = "national") -> str:
    if scope == "national":
        return render_presentation_html(payload)
    return render_leiria_html(payload, area=area_by_slug(scope))


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
    algema_records = _committed_top100(payload)
    algema_html = _algema_cards_html(algema_records)
    algema_lead = _algema_lead("do país", algema_records)
    base_href = _base_contratos_href(payload)
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
    region_buttons = "".join(
        f'<a class="alt" href="{area.slug}/">{_esc(area.button)}</a>'
        for area in AREA_PAGES
    )
    return f"""<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Dinheiro público em cinco empresas americanas (2022–2026)</title>
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
    .chart-title {{
      font-size: 1.05rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      line-height: 1.3;
      margin: 0.25rem 0 0.75rem;
    }}
    .chart-box {{
      flex: 1;
      min-height: 280px;
      max-height: 62vh;
      position: relative;
      margin-top: 0.25rem;
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
      <h1 class="reveal">Dinheiro público em cinco empresas americanas</h1>
      <p class="lead reveal">Google, Amazon, Facebook, Apple e Microsoft vendem
      serviços ao Estado. Os Estados Unidos controlam essas empresas e podem
      obrigá-las a cortar o serviço. O Cloud Act é outra lei: obriga-as a
      entregar dados que tenham sob controlo, estejam onde estiverem. O aviso
      ao cliente pode ser adiado. Esta conta mostra só o dinheiro público em
      que esses nomes aparecem.</p>
      <div class="linkbar reveal">
        {region_buttons}
        <a href="#s1">Começar</a>
      </div>
    </section>

    <section class="slide slide--years" id="s1" data-title="Anos">
      <h2 class="reveal">Cinco anos de contratos assinados</h2>
      <p class="lead reveal">A soma dos contratos assinados de 2022 a 2026.
      Pedidos ao mercado ficam fora da conta.</p>
      <p class="chart-title reveal">Contratos assinados, por ano</p>
      <div class="year-grid">{year_cards}</div>
    </section>

    <section class="slide slide--chart" id="s2" data-title="Série">
      <h2 class="reveal">O que foi assinado e o que foi pedido</h2>
      <p class="lead reveal">A barra rosa é dinheiro de contratos já assinados.
      A verde é o valor pedido ao mercado, que pode ainda não ter sido assinado.
      Não some as duas.</p>
      <p class="chart-title reveal">Contratos assinados e pedidos ao mercado, por ano</p>
      <div class="chart-box reveal"><canvas id="chartYears" aria-label="Contratos assinados e pedidos ao mercado, por ano"></canvas></div>
    </section>

    <section class="slide slide--map" id="s3" data-title="Dia 0">
      <h2 class="reveal">Onde um corte doeria mais</h2>
      <p class="lead reveal">Se os Estados Unidos desligarem estes serviços, as
      regiões mais escuras são as que mais contrataram em 2025. As claras
      dependem menos. O mapa é o continente.</p>
      <p class="lead reveal">Esta conta é só dinheiro público. As empresas privadas
      também dependem muito destas tecnologias, e isso não entra no mapa.</p>
      <p class="chart-title reveal">Contratos assinados em 2025, por região</p>
      <div class="chart-box reveal">
        <div id="mapRegion" role="img" aria-label="Contratos assinados em 2025, por região do continente"></div>
      </div>
      <div class="map-legend" id="mapLegend"></div>
    </section>

    <section class="slide slide--chart" id="s4" data-title="Categoria">
      <h2 class="reveal">Quem gastou o dinheiro em 2025</h2>
      <p class="lead reveal">Cada barra é um tipo de entidade pública. O valor é
      a soma dos contratos assinados nesse ano.</p>
      <p class="chart-title reveal">Contratos assinados por categoria, 2025</p>
      <div class="chart-box reveal"><canvas id="chartCategory" aria-label="Contratos assinados por categoria em 2025"></canvas></div>
    </section>

    <section class="slide slide--chart" id="s5" data-title="Fornecedor">
      <h2 class="reveal">Quem levou os contratos</h2>
      <p class="lead reveal">Cada linha é um fornecedor. Na legenda, cada tom de
      cinzento é um ano: o mais claro é o mais antigo e o mais escuro é 2026.</p>
      <p class="chart-title reveal">Contratos assinados por fornecedor e por ano</p>
      <div class="chart-box reveal"><canvas id="chartVendor" aria-label="Contratos assinados por fornecedor e por ano"></canvas></div>
    </section>

    <section class="slide slide--years" id="s6" data-title="Lock-in">
      <h2 class="reveal">As algemas</h2>
      <p class="lead reveal">{algema_lead}</p>
      <p class="chart-title reveal">Anos com contratos assinados no setor público, 2022–2026</p>
      {algema_html}
      <p class="meta reveal" style="margin-top:1rem">Fonte: Portal Base, contratos
      públicos celebrados (IMPIC), 2022–2026.
      <a href="{base_href}">dados.gov.pt</a></p>
    </section>

    <section class="slide slide--kw" id="s7" data-title="Léxico">
      <h2 class="reveal">O que procurámos</h2>
      <p class="lead reveal">Cada coluna é uma empresa. Se um destes nomes aparece
      no documento oficial, o contrato entra na conta.</p>
      <div class="kw-grid">{kw_cols}</div>
    </section>

    <section class="slide slide--end" id="s8" data-title="Fontes">
      <h2 class="reveal">Fontes</h2>
      <p class="lead reveal">São os ficheiros oficiais usados nesta conta. O ano
      de 2026 vai só até à data desses ficheiros. Contrato assinado e pedido ao
      mercado não se somam.</p>
      <ul class="list">{sources_html}</ul>
      <p class="meta reveal">Contagem das algemas</p>
      <ul class="list">{_algema_source_html(base_href)}</ul>
      <p class="meta reveal">Leis citadas no início</p>
      <ul class="list">{_legal_sources_html()}</ul>
      <div class="linkbar reveal">
        <a href="data.json">data.json</a>
        <a href="contratos.csv">contratos.csv</a>
        {region_buttons}
      </div>
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
        plugins: {{ legend: {{ position: 'bottom' }}, tooltip: eurTooltip }},
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
          label: 'contrato assinado',
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


_LEGAL_SOURCES: tuple[tuple[str, str, str], ...] = (
    (
        "18 U.S.C. § 2713 (CLOUD Act)",
        "https://uscode.house.gov/us/usc/t18/s2713/",
        "entrega de dados sob controlo da empresa, em qualquer país",
    ),
    (
        "18 U.S.C. § 2705",
        "https://uscode.house.gov/us/usc/t18/s2705/",
        "o aviso ao cliente pode ser adiado",
    ),
    (
        "50 U.S.C. § 1702 (IEEPA)",
        "https://uscode.house.gov/us/usc/t50/s1702/",
        "o Presidente pode proibir serviços de empresas americanas",
    ),
)


def _algema_source_html(href: str) -> str:
    return (
        "<li class='reveal'>"
        f'<a href="{href}" rel="noopener noreferrer">'
        "Portal Base, contratos públicos celebrados (IMPIC)</a>"
        "<span> · anos com contratos assinados no setor público, 2022–2026</span>"
        "</li>"
    )


def _legal_sources_html() -> str:
    return "".join(
        "<li class='reveal'>"
        f'<a href="{_safe_href(url)}" rel="noopener noreferrer">{_esc(title)}</a>'
        f"<span> · {_esc(note)}</span></li>"
        for title, url, note in _LEGAL_SOURCES
    )


def _base_contratos_href(payload: dict[str, Any]) -> str:
    fallback = (
        "https://dados.gov.pt/pt/datasets/"
        "contratos-publicos-portal-base-impic-contratos-de-2012-a-2026/"
    )
    for source in payload.get("sources") or []:
        if source.get("id") == "base-contratos" and source.get("url"):
            return _safe_href(source["url"])
    return _safe_href(fallback)


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
        f"<span class='bead{' is-on' if i < years_n else ''}'></span>" for i in range(5)
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


def _algema_years(records: list[dict[str, Any]]) -> dict[str, int]:
    """Anos distintos com despesa, em todos os contratos assinados — não só no top 100."""
    by_product: dict[str, set[int]] = {}
    for row in records:
        product = str(row.get("product") or "")
        year = int(row.get("year") or 0)
        if product and year:
            by_product.setdefault(product, set()).add(year)
    years: dict[str, int] = {}
    for _vendor, products in _ALGEMA_ROWS:
        for name in products:
            years[name] = len(by_product.get(name, ()))
    return years


def _algema_lead(where: str, records: list[dict[str, Any]]) -> str:
    years = _algema_years(records)
    present = [
        vendor
        for vendor, products in _ALGEMA_ROWS
        if any(years[name] > 0 for name in products)
    ]
    if not present:
        return (
            f"Nos contratos assinados {where}, entre 2022 e 2026, "
            "não há Microsoft nem Google."
        )
    names = " e ".join(present)
    verb = "aparece" if len(present) == 1 else "aparecem"
    return (
        f"Nos contratos assinados {where}, {names} {verb} em vários anos. "
        "No setor público a repetição é longa: cada cartão conta esses anos, "
        "não a duração de um único contrato."
    )


def _algema_cards_html(records: list[dict[str, Any]]) -> str:
    years = _algema_years(records)
    rows_html: list[str] = []
    for vendor, products in _ALGEMA_ROWS:
        cards = [
            _algema_card(name, years[name]) for name in products if years[name] > 0
        ]
        if not cards:
            continue
        rows_html.append(
            "<div class='algema-row'>"
            f"<p class='algema-vendor'>{_esc(vendor)}</p>"
            f"<div class='algema-grid'>{''.join(cards)}</div>"
            "</div>"
        )
    if not rows_html:
        return (
            "<p class='reveal'>Sem Microsoft nem Google nos contratos assinados "
            "deste período (Office 365, Teams, Google Cloud, Android…).</p>"
        )
    return f"<div class='algema-stack'>{''.join(rows_html)}</div>"


def render_leiria_html(
    payload: dict[str, Any],
    area: AreaPage | None = None,
) -> str:
    area = area or area_by_slug("leiria")
    totals = payload["totals"]
    years = [str(y) for y in YEAR_LIST]
    if area.unit == "distrito":
        mun_fold: set[str] | None = set(
            load_concelhos_by_distrito(data_dir() / "concelho_distrito.csv")[
                fold(area.button)
            ]
        )
    else:
        mun_fold = None
    records = _committed_top100(payload)
    rows = (
        "".join(
            "<tr class='reveal'>"
            f"<td>{_esc(r.get('year'))}</td>"
            f"<td>{_esc(r.get('place') or '—')}</td>"
            f"<td>{_esc(r.get('buyer'))}</td>"
            f"<td>{_esc(r.get('product'))}</td>"
            f"<td class='num'>{eur(r.get('amount_eur'))}</td>"
            f"<td>{_esc((r.get('excerpt') or '')[:120])}</td>"
            "</tr>"
            for r in records[:100]
        )
        or "<tr><td colspan='6'>Sem contratos neste período.</td></tr>"
    )
    place_year = (
        (payload.get("breakdowns") or {}).get("committed_by_place", {}).get("2025", {})
    )
    place_pairs = sorted(
        (
            (name, value)
            for name, value in place_year.items()
            if mun_fold is None or fold(str(name)) in mun_fold
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:10]
    place_list = (
        "".join(
            f"<li class='reveal'><strong>{_esc(name)}</strong> — {eur(value)}</li>"
            for name, value in place_pairs
        )
        or "<li class='reveal'>Sem repartição por concelho.</li>"
    )
    algema_html = _algema_cards_html(records)
    algema_lead = _algema_lead(area.where, records)
    base_href = _base_contratos_href(payload)
    sources_html = "".join(
        "<li class='reveal'>"
        f'<a href="{_safe_href(s["url"])}" rel="noopener noreferrer">'
        f"{_esc(s['title'])}</a>"
        f"<span> · {_esc(s.get('coverage') or '')}</span></li>"
        for s in payload.get("sources") or []
    )
    year_cards = "".join(
        "<article class='year-card reveal'>"
        f"<p class='y'>{_esc(y)}</p>"
        f"<p class='n'>{_esc(eur_compact(totals[y]['committed']))}</p>"
        "<p class='c'>contrato assinado</p>"
        "</article>"
        for y in years
    )
    data_json = _escape_json(_embed_payload(payload))
    year_labels = json.dumps(years)
    place_all = {
        name: value
        for name, value in place_year.items()
        if mun_fold is None or fold(str(name)) in mun_fold
    }
    place_json = json.dumps(place_all, ensure_ascii=False)
    assets = _brand_asset_prefix(scope=area.slug)
    geo_file = f"{area.slug}.geojson"
    map_credit = "CAOP2025 DGT" if area.unit == "distrito" else "NUTS II"
    paint_name = area.nuts_name or area.name
    local_phrase = "do distrito" if area.unit == "distrito" else "desta região"
    if area.unit == "distrito":
        map_lead = (
            "Se os Estados Unidos desligarem estes serviços, os "
            "concelhos mais escuros são os que mais contrataram em 2025. Os claros "
            "dependem menos."
        )
        map_title = "Contratos assinados em 2025, por concelho"
        map_aria = f"Contratos assinados em 2025, por concelho do distrito de {area.button}"
    else:
        map_lead = (
            "Se os Estados Unidos desligarem estes serviços, o mapa mostra "
            "quanto esta região contratou em 2025."
        )
        map_title = "Contratos assinados em 2025, nesta região"
        map_aria = f"Contratos assinados em 2025, {area.name}"
    map_html = (
        "<div class='split'>"
        "<div class='map-panel reveal'>"
        f"<div id='mapLeiria' role='img' aria-label='{_esc(map_aria)}'></div>"
        "</div><div>"
        "<p class='meta reveal'>Os dez concelhos com mais contratos assinados</p>"
        f"<ul>{place_list}</ul></div></div>"
        "<div class='map-legend' id='mapLeiriaLegend'></div>"
    )
    fora = "e isso não entra no mapa."
    brand_head = _brand_head(assets)
    brand_tokens = _brand_tokens_css()
    brand_footer_css = _brand_footer_css()
    cfp_footer = _cfp_footer(assets)
    return f"""<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>GAFAM · {_esc(area.name)} (2022–2026)</title>
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
    .slide--hero {{
      color: var(--paper);
      background:
        radial-gradient(circle at 82% 18%, rgba(253,82,136,.45), transparent 40%),
        radial-gradient(circle at 10% 80%, rgba(114,225,35,.3), transparent 35%),
        linear-gradient(135deg, #010101, #2a0a14 70%, #1a1a1a);
    }}
    .slide--map {{
      color: #f4f4f0; background: #010101;
    }}
    .slide--map .lead {{ opacity: 0.85; }}
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
    .chart-title {{
      font-size: 1.05rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      line-height: 1.3;
      margin: 0.25rem 0 0.75rem;
    }}
    .chart-box {{
      flex: 1;
      min-height: 280px;
      max-height: 62vh;
      position: relative;
      margin-top: 0.25rem;
      background: #fff;
      border-radius: 1rem;
      padding: 1rem;
    }}
    .chart-box canvas {{
      width: 100% !important;
      height: 100% !important;
    }}
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
      <h1 class="reveal">{_esc(area.name)}</h1>
      <p class="lead reveal">Entre 2022 e 2026, câmaras, escolas e hospitais {local_phrase}
      assinaram contratos com grandes tecnológicas americanas. Os Estados Unidos
      podem obrigar essas empresas a cortar o serviço. O Cloud Act é outra lei:
      obriga-as a entregar dados sob o seu controlo, estejam onde estiverem.
      O aviso ao cliente pode ser adiado. Os números são só dinheiro público.</p>
      <p class="chart-title reveal">Contratos assinados, por ano</p>
      <div class="year-grid">{year_cards}</div>
  </section>
  <section class="slide" id="s1" data-title="Série">
    <h2 class="reveal">O que foi assinado e o que foi pedido</h2>
    <p class="lead reveal">A barra rosa é dinheiro de contratos já assinados.
    A verde é o valor pedido ao mercado, que pode ainda não ter sido assinado.
    Não some as duas.</p>
    <p class="chart-title reveal">Contratos assinados e pedidos ao mercado, por ano</p>
    <div class="chart-box reveal"><canvas id="chartLeiriaYears" aria-label="Contratos assinados e pedidos ao mercado, por ano"></canvas></div>
  </section>
  <section class="slide slide--map" id="s2" data-title="Dia 0">
    <h2 class="reveal">Onde um corte doeria mais</h2>
    <p class="lead reveal">{_esc(map_lead)}</p>
    <p class="lead reveal">Esta conta é só dinheiro público. As empresas privadas
    também dependem muito destas tecnologias, {fora}</p>
    <p class="chart-title reveal">{_esc(map_title)}</p>
    {map_html}
  </section>
  <section class="slide" id="s3" data-title="Fornecedor">
    <h2 class="reveal">Quem levou os contratos</h2>
    <p class="lead reveal">Cada linha é um fornecedor. Na legenda, cada tom de
    cinzento é um ano: o mais claro é o mais antigo e o mais escuro é 2026.</p>
    <p class="chart-title reveal">Contratos assinados por fornecedor e por ano</p>
    <div class="chart-box reveal"><canvas id="chartLeiriaVendor" aria-label="Contratos assinados por fornecedor e por ano"></canvas></div>
  </section>
  <section class="slide" id="s4" data-title="Lock-in">
    <h2 class="reveal">As algemas</h2>
    <p class="lead reveal">{algema_lead}</p>
    <p class="chart-title reveal">Anos com contratos assinados no setor público, 2022–2026</p>
    {algema_html}
    <p class="meta reveal" style="margin-top:1rem">Fonte: Portal Base, contratos
    públicos celebrados (IMPIC), 2022–2026.
    <a href="{base_href}">dados.gov.pt</a></p>
  </section>
  <section class="slide" id="s5" data-title="Contratos">
    <h2 class="reveal">Os 100 maiores contratos</h2>
    <p class="lead reveal">Os maiores contratos assinados {local_phrase}, do mais
    caro para o mais barato. O excerto é a frase do documento oficial onde o
    produto aparece.</p>
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
  <section class="slide" id="s6" data-title="Fontes">
    <h2 class="reveal">Fontes</h2>
    <p class="lead reveal">São os ficheiros oficiais usados nesta conta. O ano
    de 2026 vai só até à data desses ficheiros. Contrato assinado e pedido ao
    mercado não se somam.</p>
    <ul class="list">{sources_html}</ul>
    <p class="meta reveal">Contagem das algemas</p>
    <ul class="list">{_algema_source_html(base_href)}</ul>
    <p class="meta reveal">Leis citadas no início</p>
    <ul class="list">{_legal_sources_html()}</ul>
  </section>
  </main>
  <script id="report-data" type="application/json">{data_json}</script>
  <script>
    const payload = JSON.parse(document.getElementById('report-data').textContent);
    const yearLabels = {year_labels};
    const placeData = {place_json};
    const eurTooltip = {{
      callbacks: {{
        label: function (ctx) {{
          const label = ctx.dataset.label ? ctx.dataset.label + ': ' : '';
          const v = ctx.chart.options.indexAxis === 'y' ? ctx.parsed.x : ctx.parsed.y;
          return label + eurTick(v != null ? v : ctx.raw);
        }}
      }}
    }};
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
          tooltip: eurTooltip
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
    const vendorByYear = Object.fromEntries(
      yearLabels.map((y) => [y, (payload.breakdowns.committed_by_vendor || {{}})[y] || {{}}])
    );
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
    new Chart(document.getElementById('chartLeiriaVendor'), {{
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
          x: {{ beginAtZero: true, ticks: {{ callback: (v) => eurTick(v) }} }},
          y: {{ ticks: {{ autoSkip: false }} }}
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
    (function drawLeiriaMap() {{
      if (!document.getElementById('mapLeiria')) return;
      const bands = ['#f4ea15', '#eb5423', '#010101'];
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
        if (g === fold({json.dumps(paint_name)})) {{
          return Object.values(placeData).reduce((sum, v) => sum + Number(v), 0);
        }}
        return 0;
      }}
      function paint(munGeo) {{
        const values = Object.values(placeData).filter((v) => v > 0).sort((a, b) => a - b);
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
              color: b === 1 ? '#ffe9a0' : '#1c1c22',
              weight: 1.2,
              fillColor: bands[b - 1],
              fillOpacity: 0.98,
              className: b === 1 ? 'night-lit' : ''
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
          '{map_credit} · <span style="background:' + zeroFill + '"></span>0 € · ' +
          bands.map((c, i) => '<span style="background:' + c + '"></span>' + binLabel(i + 1)).join(' · ');
      }}
      fetch('{geo_file}')
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


def _write_area_geojson(out_dir: Path, area: AreaPage) -> None:
    if area.unit == "distrito":
        raw = json.loads(
            (data_dir() / "concelhos_continente.geojson").read_text(encoding="utf-8")
        )
        wanted = fold(area.button)
        features = []
        for feat in raw["features"]:
            props = feat["properties"]
            if fold(props["distrito"]) != wanted:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "id": props["name"],
                        "name": props["name"],
                        "source": props["source"],
                    },
                    "geometry": feat["geometry"],
                }
            )
        (out_dir / f"{area.slug}.geojson").write_text(
            json.dumps(
                {"type": "FeatureCollection", "features": features},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        return
    raw = json.loads((data_dir() / "nuts2_pt.geojson").read_text(encoding="utf-8"))
    wanted = fold(area.nuts_name)
    features = [
        feat
        for feat in raw.get("features") or []
        if fold(str((feat.get("properties") or {}).get("name") or "")) == wanted
    ]
    (out_dir / f"{area.slug}.geojson").write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": features},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


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
    if scope != "national":
        _write_area_geojson(out_dir, area_by_slug(scope))
