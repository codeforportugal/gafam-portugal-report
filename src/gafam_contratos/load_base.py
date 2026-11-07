"""Carregamento de contratos, anúncios e modificações BASE."""

from __future__ import annotations

import json
import re
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from gafam_contratos.amounts import parse_amount, parse_date, year_in_scope
from gafam_contratos.classify import (
    classify_institution,
    infer_place_from_buyer,
    is_framework_ceiling,
    load_concelho_labels,
    place_parts,
    region_from_local,
)
from gafam_contratos.columns import pick_column
from gafam_contratos.constants import YEARS
from gafam_contratos.http_cache import cached_get
from gafam_contratos.lexicon import Keyword, MatchHit, find_match
from gafam_contratos.models import Record, SourceMeta
from gafam_contratos.paths import data_dir
from gafam_contratos.retry import http_get

_col = pick_column
DATASET_CONTRATOS = "contratos-publicos-portal-base-impic-contratos-de-2012-a-2026"
DATASET_ANUNCIOS = "contratos-publicos-portal-base-impic-anuncios-de-2012-a-2026"
DATASET_MODS = (
    "contratos-publicos-portal-base-impic-modificacoes-contratuais-de-2012-a-2026"
)
DADOS_API = "https://dados.gov.pt/api/1/datasets"


def _nif_and_name(raw: str) -> tuple[str, str]:
    text = str(raw or "").strip()
    desc = re.search(r"descEntContrato=([^|]+)", text)
    if desc:
        name = desc.group(1).strip()
        nif_m = re.search(r"nifEntContrato=(\d{9})", text)
        return (nif_m.group(1) if nif_m else ""), name
    match = re.search(r"(\d{9})", text)
    nif = match.group(1) if match else ""
    name = re.sub(r"[\(\[]?\d{9}[\)\]]?", "", text)
    name = re.sub(r"^\s*[-–]\s*", "", name).strip(" -–")
    return nif, name or text


def load_modifications(path: Path) -> dict[str, float]:
    """Mapa idContrato -> preço alterado (última modificação)."""
    frame = _read_table(path)
    id_col = _col(frame, "idcontrato", "idContrato")
    price_col = _col(frame, "modifContratoPrecoAlterado", "precoAlterado")
    if id_col is None or price_col is None:
        return {}
    result: dict[str, float] = {}
    for _, row in frame.iterrows():
        cid = str(row[id_col]).strip()
        amount = parse_amount(row[price_col])
        if cid and amount is not None:
            result[cid] = amount
    return result


def _read_table(path: Path) -> pd.DataFrame:
    """Lê xlsx, json ou zip que contenha xlsx/json."""
    suffix = path.suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            inner = next(
                (n for n in names if n.lower().endswith((".xlsx", ".xls", ".json"))),
                None,
            )
            if inner is None:
                message = f"ZIP sem tabela: {path}"
                raise FileNotFoundError(message)
            extracted = path.with_suffix(Path(inner).suffix)
            extracted.write_bytes(archive.read(inner))
            return _read_table(extracted)
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else data.get("data", data)
        return pd.DataFrame(rows)
    return pd.read_excel(path)


def load_contracts(
    path: Path,
    keywords: list[Keyword],
    concelho_map: dict[str, str],
    modifications: dict[str, float],
    prr_ids: set[str],
) -> list[Record]:
    frame = _read_table(path)
    id_col = _col(frame, "idcontrato", "idContrato", "IdContrato")
    obj_col = _col(frame, "objectocontrato", "objeto do contrato", "Objeto do Contrato")
    desc_col = _col(frame, "desccontrato", "descrição")
    buyer_col = _col(
        frame,
        "adjudicante",
        "entidade(s) adjudicante(s)",
        "Entidade(s) Adjudicante(s)",
    )
    price_col = _col(frame, "precocontratual", "preço contratual", "Preço Contratual")
    local_col = _col(frame, "localexecucao", "local de execução")
    date_col = _col(
        frame,
        "datacelebracaocontrato",
        "data de celebração do contrato",
        "Data de Celebração do Contrato",
    )
    cpv_col = _col(frame, "cpv")
    labels = load_concelho_labels(data_dir() / "concelho_nuts2.csv")
    records: list[Record] = []
    for _, row in frame.iterrows():
        obj = str(row[obj_col] if obj_col else "")
        desc = str(row[desc_col] if desc_col else "")
        buyer_raw = str(row[buyer_col] if buyer_col else "")
        cpv = str(row[cpv_col] if cpv_col else "")
        text = " ".join(part for part in (obj, desc, buyer_raw, cpv) if part)
        hit = find_match(text, keywords)
        if hit is None:
            continue
        when = parse_date(row[date_col] if date_col else None)
        if not year_in_scope(when, YEARS):
            continue
        amount = parse_amount(row[price_col] if price_col else None)
        if amount is None:
            continue
        cid = str(row[id_col]).strip() if id_col else ""
        if cid and cid in modifications:
            amount = modifications[cid]
        nif, buyer = _nif_and_name(buyer_raw)
        local = str(row[local_col] if local_col else "")
        region = _split_regions(local, amount, concelho_map)
        headline = not is_framework_ceiling(text)
        composite = ""
        if nif:
            composite = f"{nif}|{amount:.2f}|{hit.term.casefold()}"
        fundos = (
            "PRR"
            if cid in prr_ids or nif in prr_ids or (composite and composite in prr_ids)
            else ""
        )
        for reg, share, district, raw_place in region:
            place = raw_place or infer_place_from_buyer(buyer, labels)
            records.append(
                Record(
                    source_id=cid or f"c-{len(records)}",
                    channel="committed",
                    buyer=buyer,
                    excerpt=hit.excerpt,
                    amount_eur=share,
                    region=reg,
                    category=classify_institution(buyer),
                    vendor=hit.vendor,
                    fundos=fundos,
                    year=when.year if when else 0,
                    headline=headline,
                    product=hit.term,
                    place=place,
                    district=district,
                )
            )
    return records


def _split_regions(
    local: str,
    amount: float,
    concelho_map: dict[str, str],
) -> list[tuple[str, float, str, str]]:
    text = str(local)
    if "|" in text:
        parts = [p.strip() for p in text.split("|") if p.strip()]
    elif ";" in text:
        parts = [p.strip() for p in text.split(";") if p.strip()]
    else:
        parts = []
    if len(parts) <= 1:
        district, place = place_parts(local)
        return [(region_from_local(local, concelho_map), amount, district, place)]
    share = amount / len(parts)
    out: list[tuple[str, float, str, str]] = []
    for part in parts:
        district, place = place_parts(part)
        out.append((region_from_local(part, concelho_map), share, district, place))
    return out


def load_notices(
    path: Path,
    keywords: list[Keyword],
    concelho_map: dict[str, str],
) -> list[Record]:
    frame = _read_table(path)
    id_col = _col(frame, "nanuncio", "nAnuncio")
    desc_col = _col(frame, "descricaoanuncio", "descricaoAnuncio", "descrição")
    buyer_col = _col(frame, "designacaoentidade", "designacaoEntidade", "entidade")
    nif_col = _col(frame, "nifentidade", "nifEntidade")
    price_col = _col(frame, "precobase", "PrecoBase", "preço base")
    date_col = _col(frame, "datapublicacao", "dataPublicacao")
    cpv_col = _col(frame, "cpvs", "CPVs", "cpv")
    url_col = _col(frame, "url")
    records: list[Record] = []
    for _, row in frame.iterrows():
        desc = str(row[desc_col] if desc_col else "")
        buyer = str(row[buyer_col] if buyer_col else "")
        cpv = str(row[cpv_col] if cpv_col else "")
        text = " ".join(part for part in (desc, buyer, cpv) if part)
        hit = find_match(text, keywords)
        if hit is None:
            continue
        when = parse_date(row[date_col] if date_col else None)
        if not year_in_scope(when, YEARS):
            continue
        amount = parse_amount(row[price_col] if price_col else None)
        if amount is None:
            continue
        nid = str(row[id_col]).strip() if id_col else f"a-{len(records)}"
        nif = str(row[nif_col]).strip() if nif_col else ""
        _ = nif
        records.append(
            Record(
                source_id=nid,
                channel="requested",
                buyer=buyer,
                excerpt=hit.excerpt,
                amount_eur=amount,
                region="sem local",
                category=classify_institution(buyer),
                vendor=hit.vendor,
                fundos="",
                year=when.year if when else 0,
                headline=not is_framework_ceiling(text),
                product=hit.term,
                url=str(row[url_col]) if url_col else "",
            )
        )
    return records


def resolve_resource_urls(
    dataset_slug: str,
    *,
    sleeps: Sequence[int] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> list[dict[str, str]]:
    url = f"{DADOS_API}/{dataset_slug}/"
    raw = http_get(url, sleeps=sleeps, sleeper=sleeper)
    payload: dict[str, Any] = json.loads(raw.decode("utf-8"))
    resources = payload.get("resources") or []
    out: list[dict[str, str]] = []
    for res in resources:
        out.append(
            {
                "title": str(res.get("title") or ""),
                "format": str(res.get("format") or "").lower(),
                "url": str(res.get("url") or ""),
            }
        )
    return out


def download_year_file(
    dataset_slug: str,
    year: int,
    cache: Path,
    prefix: str,
    *,
    sleeps: Sequence[int] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> Path:
    resources = resolve_resource_urls(dataset_slug, sleeps=sleeps, sleeper=sleeper)
    year_token = str(year)
    preferred = [
        r
        for r in resources
        if year_token in r["title"].lower()
        and r["format"] in {"xlsx", "xls", "zip", "json"}
    ]
    if not preferred:
        preferred = [r for r in resources if year_token in r["url"]]
    if not preferred:
        message = f"Sem recurso {prefix}{year} em {dataset_slug}"
        raise FileNotFoundError(message)
    order = {"xlsx": 0, "xls": 1, "json": 2, "zip": 3}
    preferred.sort(key=lambda r: order.get(r["format"], 9))
    chosen = preferred[0]
    suffix = Path(chosen["url"].split("?", 1)[0]).suffix or f".{chosen['format']}"
    return cached_get(
        chosen["url"],
        cache,
        name=f"{prefix}{year}{suffix}",
        sleeps=sleeps,
        sleeper=sleeper,
    )


def base_sources() -> list[SourceMeta]:
    return [
        SourceMeta(
            id="base-contratos",
            publisher="IMPIC",
            title="Contratos Públicos - Portal Base - Contratos",
            url=f"https://dados.gov.pt/pt/datasets/{DATASET_CONTRATOS}/",
            file_name="contratos2022…2026.xlsx",
            licence="Domínio Público",
            coverage="Contratos celebrados 2022–2026",
            updated="2026-11-04",
        ),
        SourceMeta(
            id="base-anuncios",
            publisher="IMPIC",
            title="Contratos Públicos - Portal Base - Anúncios",
            url=f"https://dados.gov.pt/pt/datasets/{DATASET_ANUNCIOS}/",
            file_name="anuncios2022…2026",
            licence="Domínio Público",
            coverage="Anúncios publicados 2022–2026",
            updated="2026-10-25",
        ),
        SourceMeta(
            id="base-mods",
            publisher="IMPIC",
            title="Contratos Públicos - Portal Base - Modificações",
            url=f"https://dados.gov.pt/pt/datasets/{DATASET_MODS}/",
            file_name="modcontrats2022…2026",
            licence="Domínio Público",
            coverage="Alterações de preço 2022–2026",
            updated="2026-10-18",
        ),
    ]


def match_text(text: str, keywords: list[Keyword]) -> MatchHit | None:
    return find_match(text, keywords)
