"""Categoria da entidade e região NUTS II."""

from __future__ import annotations

import csv
from pathlib import Path

from gafam_contratos.lexicon import fold

_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "ensino superior",
        (
            "universidade",
            "instituto politecnico",
            "instituto politécnico",
            "iscte",
            "escola superior",
            "faculdade",
        ),
    ),
    (
        "saúde",
        (
            "unidade local de saude",
            "uls ",
            "hospital",
            "centro hospitalar",
            "ars ",
            "administracao regional de saude",
        ),
    ),
    (
        "administração local",
        (
            "municipio",
            "município",
            "camara municipal",
            "câmara municipal",
            "junta de freguesia",
        ),
    ),
    (
        "educação não superior",
        (
            "agrupamento de escolas",
            "escola secundaria",
            "escola secundária",
            "escola basica",
            "escola básica",
            "dgeste",
        ),
    ),
    (
        "administração central",
        (
            "ministerio",
            "ministério",
            "secretaria-geral",
            "direcao-geral",
            "direção-geral",
            "instituto ",
            "agencia ",
            "agência ",
            ", i.p",
            ", ip",
        ),
    ),
    (
        "empresas públicas",
        (", e.p.e", ", epe", "empresa publica", "empresa pública", "sgps"),
    ),
)


def classify_institution(name: str) -> str:
    folded = fold(name)
    for category, needles in _CATEGORY_RULES:
        for needle in needles:
            if fold(needle) in folded:
                return category
    if _looks_private(folded):
        return "privado"
    return "outra entidade pública"


def _looks_private(folded: str) -> bool:
    private_markers = (" lda", " unipessoal", " s.a", ", sa", " crl")
    if any(marker in folded for marker in private_markers):
        return True
    return folded.endswith((" sa", " sa."))


def load_concelho_map(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            mapping[fold(row["concelho"])] = row["nuts2"]
    return mapping


def load_concelho_labels(path: Path) -> dict[str, str]:
    """fold(concelho) → rótulo canónico."""
    labels: dict[str, str] = {}
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            labels[fold(row["concelho"])] = row["concelho"].strip()
    return labels


_PLACE_JUNK = frozenset(
    {
        "portugal",
        "continente",
        "nacional",
        "-",
        "nan",
        "n/a",
        "na",
    }
)


def _clean_place_token(raw: str) -> str:
    text = " ".join(str(raw).replace("\n", " ").replace("\r", " ").split())
    return text.strip(" ,;|")


def _is_junk_place(name: str) -> bool:
    folded = fold(name)
    if not folded or folded in _PLACE_JUNK:
        return True
    # «Portugal Portugal Portugal…»
    tokens = [t for t in folded.split() if t]
    return bool(tokens) and all(t == "portugal" for t in tokens)


def place_parts(local: str) -> tuple[str, str]:
    """Devolve (distrito, concelho) a partir de «Portugal, Distrito, Concelho»."""
    if not local or not str(local).strip():
        return "", ""
    parts = [
        _clean_place_token(p)
        for p in str(local).replace("\n", ",").split(",")
        if _clean_place_token(p)
    ]
    if not parts:
        return "", ""
    if len(parts) >= 3:
        district, place = parts[-2], parts[-1]
    elif len(parts) == 1:
        district, place = "", parts[0]
    else:
        district, place = "", parts[-1]
    if _is_junk_place(place):
        place = ""
    if _is_junk_place(district):
        district = ""
    return district, place


def infer_place_from_buyer(
    buyer: str,
    labels: dict[str, str],
) -> str:
    """Concelho mencionado no nome do adjudicante (melhor esforço)."""
    folded_buyer = fold(buyer)
    for key in sorted(labels, key=len, reverse=True):
        if key and key in folded_buyer:
            return labels[key]
    return ""


def region_from_local(local: str, concelho_map: dict[str, str]) -> str:
    """Interpreta «Portugal, Distrito, Concelho»."""
    if not local or not str(local).strip():
        return "sem local"
    _district, concelho = place_parts(local)
    if concelho:
        nuts = concelho_map.get(fold(concelho))
        if nuts is not None:
            return nuts
    # PT2030 already has NUTS II labels
    folded = fold(local)
    known = {
        "norte": "Norte",
        "centro": "Centro",
        "area metropolitana de lisboa": "Área Metropolitana de Lisboa",
        "alentejo": "Alentejo",
        "algarve": "Algarve",
        "acores": "Açores",
        "regiao autonoma dos acores": "Açores",
        "madeira": "Madeira",
        "regiao autonoma da madeira": "Madeira",
    }
    if folded in known:
        return known[folded]
    if folded in {"-", "nan"}:
        return "sem local"
    return "sem local"


def load_concelhos_by_distrito(path: Path) -> dict[str, dict[str, str]]:
    """fold(distrito) -> {fold(concelho): nome do concelho}."""
    grouped: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            distrito = row["distrito"].strip()
            concelho = row["concelho"].strip()
            grouped.setdefault(fold(distrito), {})[fold(concelho)] = concelho
    return grouped


def load_distrito_concelhos(path: Path) -> set[str]:
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            names.add(fold(stripped))
    return names


def in_distrito(
    *,
    district: str,
    place: str,
    buyer: str,
    municipios: set[str],
    district_name: str = "leiria",
) -> bool:
    if fold(district) == fold(district_name):
        return True
    place_fold = fold(place)
    if place_fold in municipios:
        return True
    # Execução fora do distrito: só conta se a entidade for do distrito
    # e o «place» não for outro concelho português explícito.
    if place and not _is_junk_place(place) and place_fold not in municipios:
        return False
    folded_buyer = fold(buyer)
    return any(name in folded_buyer for name in municipios)


def normalize_distrito_place(
    *,
    place: str,
    buyer: str,
    labels: dict[str, str],
    municipios: set[str],
) -> str:
    """Concelho do distrito para agregação/UI; vazio se desconhecido."""
    cleaned = _clean_place_token(place)
    if fold(cleaned) in municipios:
        return labels.get(fold(cleaned), cleaned)
    if _is_junk_place(cleaned) or not cleaned:
        return infer_place_from_buyer(buyer, labels)
    # Place fora do distrito (ex.: Lisboa): tentar entidade
    inferred = infer_place_from_buyer(buyer, labels)
    if fold(inferred) in municipios:
        return inferred
    return ""


def is_framework_ceiling(text: str) -> bool:
    folded = fold(text)
    return "acordo quadro" in folded or "acordo-quadro" in folded
