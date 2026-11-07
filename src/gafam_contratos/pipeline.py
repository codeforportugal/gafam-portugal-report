"""Orquestração: fixtures ou corrida nacional."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

from gafam_contratos.classify import (
    in_distrito,
    load_concelho_map,
    load_concelhos_by_distrito,
    normalize_distrito_place,
)
from gafam_contratos.constants import YEAR_LIST
from gafam_contratos.http_cache import cached_get
from gafam_contratos.lexicon import Keyword, fold, load_lexicon
from gafam_contratos.load_base import (
    DATASET_ANUNCIOS,
    DATASET_CONTRATOS,
    DATASET_MODS,
    base_sources,
    download_year_file,
    load_contracts,
    load_modifications,
    load_notices,
    resolve_resource_urls,
)
from gafam_contratos.load_prr import load_prr_flags, prr_source
from gafam_contratos.load_pt2030 import PT2030_URL, load_pt2030, pt2030_source
from gafam_contratos.models import PressLink, Record, SourceMeta
from gafam_contratos.paths import (
    cache_dir,
    data_dir,
    fixtures_dir,
    reports_dir,
)
from gafam_contratos.press import gather_press, load_press_domains
from gafam_contratos.report import AREA_PAGES, build_report_payload, write_report
from gafam_contratos.sciproj import (
    sciproj_source,
    sciproj_terms_from_keywords,
    search_sciproj,
)


def run(
    *,
    full: bool = False,
    sleeps: Sequence[int] | None = None,
    sleeper: Callable[[float], None] | None = None,
    out_dir: Path | None = None,
) -> Path:
    root_data = data_dir()
    keywords = load_lexicon(root_data / "lexicon.yml")
    concelho_map = load_concelho_map(root_data / "concelho_nuts2.csv")
    domains = load_press_domains(root_data / "press_domains.txt")
    out = out_dir or reports_dir()

    if full:
        records, sources, skipped, press, press_errors = _run_full(
            keywords,
            concelho_map,
            domains,
            sleeps=sleeps,
            sleeper=sleeper,
        )
    else:
        records, sources, skipped, press, press_errors = _run_fixtures(
            keywords,
            concelho_map,
            domains,
        )

    payload = build_report_payload(
        records=records,
        sources=sources,
        keywords=keywords,
        press=press,
        press_errors=press_errors,
        skipped=skipped,
    )
    write_report(out, payload, records)

    _write_area_reports(
        out,
        records=records,
        sources=sources,
        keywords=keywords,
        skipped=skipped,
        root_data=root_data,
    )
    return out


def _write_area_reports(
    out: Path,
    *,
    records: list[Record],
    sources: list[SourceMeta],
    keywords: list[Keyword],
    skipped: dict[str, int],
    root_data: Path,
) -> None:
    by_district = load_concelhos_by_distrito(root_data / "concelho_distrito.csv")
    for area in AREA_PAGES:
        picked: list[Record] = []
        for record in records:
            if area.unit == "regiao":
                if fold(record.region) != fold(area.name):
                    continue
                picked.append(record)
                continue
            labels = by_district[fold(area.button)]
            municipios = set(labels)
            if not in_distrito(
                district=record.district,
                place=record.place,
                buyer=record.buyer,
                municipios=municipios,
                district_name=area.button,
            ):
                continue
            picked.append(
                replace(
                    record,
                    place=normalize_distrito_place(
                        place=record.place,
                        buyer=record.buyer,
                        labels=labels,
                        municipios=municipios,
                    ),
                )
            )
        payload = build_report_payload(
            records=picked,
            sources=sources,
            keywords=keywords,
            press=[],
            press_errors={},
            skipped=skipped,
        )
        write_report(out / area.slug, payload, picked, scope=area.slug)


def _run_fixtures(
    keywords: list[Keyword],
    concelho_map: dict[str, str],
    domains: set[str],
) -> tuple[
    list[Record],
    list[SourceMeta],
    dict[str, int],
    list[PressLink],
    dict[str, str],
]:
    fix = fixtures_dir()
    mods = load_modifications(fix / "modificacoes.xlsx")
    prr_ids = load_prr_flags(fix / "prr.xlsx", keywords)
    contracts = load_contracts(
        fix / "contratos.xlsx",
        keywords,
        concelho_map,
        mods,
        prr_ids,
    )
    notices = load_notices(fix / "anuncios.xlsx", keywords, concelho_map)
    grants = load_pt2030(fix / "pt2030.xlsx", keywords, concelho_map)
    records = contracts + notices + grants
    sources = [*base_sources(), pt2030_source(), prr_source()]
    press, press_errors = gather_press(
        records,
        keywords,
        domains,
        arquivo_fetch=_fixture_arquivo,
        gdelt_fetch=_fixture_gdelt,
        sleeper=lambda _s: None,
    )
    skipped = {"sem montante": 0, "correspondência incerta": 0}
    return records, sources, skipped, press, press_errors


def _fixture_arquivo(
    query: str,
    **_kwargs: object,
) -> list[dict[str, str]]:
    _ = query
    return [
        {
            "title": "Universidade compra licenças Microsoft Excel",
            "url": "https://www.publico.pt/2025/03/01/excel-contrato",
            "date": "20250301120000",
            "snippet": "contrato de aquisição de Microsoft Excel pela universidade",
            "origin": "arquivo.pt",
        },
        {
            "title": "Sem data útil",
            "url": "https://www.publico.pt/sem-data",
            "date": "",
            "snippet": "Excel",
            "origin": "arquivo.pt",
        },
        {
            "title": "Meta vaga",
            "url": "https://www.publico.pt/meta",
            "date": "20250301120000",
            "snippet": "atingir a meta do contrato",
            "origin": "arquivo.pt",
        },
    ]


def _fixture_gdelt(
    query: str,
    **_kwargs: object,
) -> list[dict[str, str]]:
    _ = query
    return [
        {
            "title": "Concurso público Azure na administração",
            "url": "https://eco.sapo.pt/2026/09/01/azure",
            "date": "20260901T120000Z",
            "snippet": "aquisição Azure",
            "origin": "gdelt",
        }
    ]


def _run_full(
    keywords: list[Keyword],
    concelho_map: dict[str, str],
    domains: set[str],
    *,
    sleeps: Sequence[int] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> tuple[
    list[Record],
    list[SourceMeta],
    dict[str, int],
    list[PressLink],
    dict[str, str],
]:
    cache = cache_dir()
    mods: dict[str, float] = {}
    for year in YEAR_LIST:
        try:
            path = download_year_file(
                DATASET_MODS,
                year,
                cache,
                "modcontrats",
                sleeps=sleeps,
                sleeper=sleeper,
            )
            mods.update(load_modifications(path))
        except (OSError, FileNotFoundError, ValueError):
            continue

    prr_ids: set[str] = set()
    try:
        resources = resolve_resource_urls(
            "dataset-estrutura-de-missao-prr-contratos-publicos",
            sleeps=sleeps,
            sleeper=sleeper,
        )
        xlsx = next((r for r in resources if "xls" in r["format"]), None)
        if xlsx:
            prr_path = cached_get(
                xlsx["url"],
                cache,
                name="prr.xlsx",
                sleeps=sleeps,
                sleeper=sleeper,
            )
            prr_ids = load_prr_flags(prr_path, keywords)
    except (OSError, StopIteration, ValueError):
        prr_ids = set()

    contracts: list[Record] = []
    for year in YEAR_LIST:
        try:
            path = download_year_file(
                DATASET_CONTRATOS,
                year,
                cache,
                "contratos",
                sleeps=sleeps,
                sleeper=sleeper,
            )
            contracts.extend(
                load_contracts(path, keywords, concelho_map, mods, prr_ids)
            )
        except (OSError, FileNotFoundError, ValueError):
            continue

    notices: list[Record] = []
    for year in YEAR_LIST:
        try:
            path = download_year_file(
                DATASET_ANUNCIOS,
                year,
                cache,
                "anuncios",
                sleeps=sleeps,
                sleeper=sleeper,
            )
            notices.extend(load_notices(path, keywords, concelho_map))
        except (OSError, FileNotFoundError, ValueError):
            continue

    grants: list[Record] = []
    try:
        pt_path = cached_get(
            PT2030_URL,
            cache,
            name="pt2030.xlsx",
            sleeps=sleeps,
            sleeper=sleeper,
        )
        grants = load_pt2030(pt_path, keywords, concelho_map)
    except (OSError, FileNotFoundError, ValueError):
        grants = []

    terms = sciproj_terms_from_keywords(keywords)
    sciproj_rows, skipped = search_sciproj(
        terms,
        keywords,
        sleeps=sleeps,
        sleeper=sleeper,
    )

    records = contracts + notices + grants + sciproj_rows
    press, press_errors = gather_press(
        records,
        keywords,
        domains,
        sleeps=sleeps,
        sleeper=sleeper,
    )
    sources = [
        *base_sources(),
        pt2030_source(),
        prr_source(),
        sciproj_source(),
    ]
    return records, sources, skipped, press, press_errors
