from datetime import date, datetime

from gafam_contratos.amounts import (
    format_eur,
    format_eur_compact,
    parse_amount,
    parse_date,
    year_in_scope,
)
from gafam_contratos.classify import (
    classify_institution,
    fold,
    in_distrito,
    infer_place_from_buyer,
    is_framework_ceiling,
    load_concelho_labels,
    load_concelho_map,
    load_distrito_concelhos,
    normalize_distrito_place,
    place_parts,
    region_from_local,
)
from gafam_contratos.paths import data_dir


def test_parse_amount_variants():
    assert parse_amount("1.234,56") == 1234.56
    assert parse_amount("1234.56") == 1234.56
    assert parse_amount("10,00") == 10.0
    assert parse_amount(None) is None
    assert parse_amount("abc") is None
    assert parse_amount(10) == 10.0


def test_parse_date_variants():
    assert parse_date("15/03/2025") == date(2025, 3, 15)
    assert parse_date("2025-03-15") == date(2025, 3, 15)
    assert parse_date(datetime(2026, 1, 2)) == date(2026, 1, 2)
    assert parse_date(date(2026, 1, 2)) == date(2026, 1, 2)
    assert parse_date(45658).year == 2025
    assert parse_date(None) is None
    assert parse_date("nope") is None
    assert year_in_scope(date(2025, 1, 1), {2025, 2026})
    assert not year_in_scope(None, {2025})


def test_format_eur():
    assert format_eur(1234.5) == "1 234,50 €"
    assert format_eur(-2) == "-2,00 €"


def test_format_eur_compact():
    assert format_eur_compact(54_071_735.04) == "54 milhões €"
    assert format_eur_compact(1_000_000) == "1 milhão €"
    assert format_eur_compact(1_250_000) == "1 milhão €"
    assert format_eur_compact(1_600_000) == "1 milhão €"
    assert format_eur_compact(537_597.01) == "537 mil €"
    assert format_eur_compact(850_000) == "850 mil €"
    assert format_eur_compact(12.5) == "12 €"
    assert format_eur_compact(-2_000_000) == "-2 milhões €"


def test_classify_and_region():
    assert classify_institution("Universidade de Lisboa") == "ensino superior"
    assert "saúde" in classify_institution("Unidade Local de Saúde do Algarve, E.P.E")
    assert classify_institution("Município de Faro") == "administração local"
    assert classify_institution("ACME LDA") == "privado"
    assert classify_institution("Entidade X") == "outra entidade pública"
    assert is_framework_ceiling("Acordo quadro Microsoft")
    mapping = load_concelho_map(data_dir() / "concelho_nuts2.csv")
    assert region_from_local("Portugal, Lisboa, Lisboa", mapping) == (
        "Área Metropolitana de Lisboa"
    )
    assert region_from_local("Norte", mapping) == "Norte"
    assert region_from_local("-", mapping) == "sem local"
    assert region_from_local("", mapping) == "sem local"
    assert place_parts("Portugal, Leiria, Pombal") == ("Leiria", "Pombal")
    assert place_parts("só-concelho") == ("", "só-concelho")
    assert place_parts("distrito, concelho") == ("", "concelho")
    assert place_parts("") == ("", "")
    assert place_parts("Portugal\nPortugal\nPortugal\nPortugal") == ("", "")
    assert region_from_local("Portugal, Foo, Vila Inventada", mapping) == "sem local"
    assert region_from_local(" , , ", mapping) == "sem local"
    mun = load_distrito_concelhos(data_dir() / "distrito_leiria.txt")
    assert "leiria" in mun and "pombal" in mun
    assert "pedrogao grande" in mun
    assert in_distrito(
        district="Leiria", place="", buyer="X", municipios=mun
    )
    assert in_distrito(
        district="", place="Marinha Grande", buyer="X", municipios=mun
    )
    assert in_distrito(
        district="", place="", buyer="Câmara Municipal de Peniche", municipios=mun
    )
    assert not in_distrito(
        district="Lisboa", place="Lisboa", buyer="Estado", municipios=mun
    )
    assert not in_distrito(
        district="Lisboa",
        place="Lisboa",
        buyer="Unidade Local de Saúde da Região de Leiria, EPE",
        municipios=mun,
    )
    labels = load_concelho_labels(data_dir() / "concelho_nuts2.csv")
    leiria_labels = {k: labels[k] for k in mun if k in labels}
    for name in ("Pedrógão Grande", "Leiria", "Peniche", "Óbidos"):
        leiria_labels.setdefault(fold(name), name)
    assert (
        infer_place_from_buyer("Município de Peniche", leiria_labels) == "Peniche"
    )
    assert infer_place_from_buyer("Estado Maior da Força Aérea", leiria_labels) == ""
    assert (
        normalize_distrito_place(
            place="Pedrógão Grande",
            buyer="X",
            labels=leiria_labels,
            municipios=mun,
        )
        == "Pedrógão Grande"
    )
    assert (
        normalize_distrito_place(
            place="Portugal Portugal Portugal Portugal",
            buyer="Universidade de Leiria e Oeste",
            labels=leiria_labels,
            municipios=mun,
        )
        == "Leiria"
    )
    assert (
        normalize_distrito_place(
            place="Lisboa",
            buyer="Município de Óbidos",
            labels=leiria_labels,
            municipios=mun,
        )
        == "Óbidos"
    )
    assert (
        normalize_distrito_place(
            place="Lisboa",
            buyer="Estado",
            labels=leiria_labels,
            municipios=mun,
        )
        == ""
    )
