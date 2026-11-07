#!/usr/bin/env python3
"""Gera ficheiros xlsx de teste com nomes de colunas reais."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"


def _write(name: str, headers: list[str], rows: list[list[object]]) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(headers)
    for row in rows:
        ws.append(row)
    FIX.mkdir(parents=True, exist_ok=True)
    wb.save(FIX / name)


def main() -> None:
    _write(
        "contratos.xlsx",
        [
            "idContrato",
            "objectoContrato",
            "descContrato",
            "adjudicante",
            "precoContratual",
            "localExecucao",
            "dataCelebracaoContrato",
            "cpv",
        ],
        [
            [
                "1001",
                "Aquisição de licenças Microsoft Excel",
                "Pacote Office para serviços académicos",
                "500046117 - Universidade de Lisboa",
                "10000,00",
                "Portugal, Lisboa, Lisboa",
                "15/03/2025",
                "48000000-8 - Pacotes de software",
            ],
            [
                "1002",
                "Acordo quadro Microsoft 365",
                "Teto do acordo quadro",
                "600000000 - Ministério da Educação",
                "500000,00",
                "Portugal, Lisboa, Lisboa",
                "20/04/2025",
                "48000000-8",
            ],
            [
                "1003",
                "Projecto de excelência académica",
                "Sem software proprietário",
                "501442600 - Município do Porto",
                "3000,00",
                "Portugal, Porto, Porto",
                "10/05/2025",
                "73000000-2",
            ],
            [
                "1004",
                "Serviços Azure",
                "Cloud Microsoft Azure",
                "508085888 - Unidade Local de Saúde do Alentejo Central, E.P.E",
                "25000,00",
                "Portugal, Évora, Évora",
                "12/02/2026",
                "72000000-5",
            ],
        ],
    )
    _write(
        "modificacoes.xlsx",
        ["idcontrato", "modifContratoPrecoAlterado", "Ano"],
        [["1001", 12000.0, 2025]],
    )
    _write(
        "anuncios.xlsx",
        [
            "nAnuncio",
            "descricaoAnuncio",
            "designacaoEntidade",
            "nifEntidade",
            "PrecoBase",
            "dataPublicacao",
            "CPVs",
            "url",
        ],
        [
            [
                "10/2025",
                "Aquisição de iPhone para equipas de terreno",
                "Município de Faro",
                "506333504",
                8000.0,
                "2025-06-01",
                "32250000-0",
                "https://example.pt/anuncio/10-2025",
            ]
        ],
    )
    _write(
        "pt2030.xlsx",
        [
            "Código da Operação | Operation Code",
            "Nome do Beneficiário | Beneficiary s name",
            "Nome da operação | Name of the operation",
            "Finalidade da operação | Purpose of the Operation",
            "Data Início | Start Date",
            "Fundo Total Aprovado | Total Approved Fund [€ - EUR]",
            "Custo Total da Operação | Total Cost of the Operation [€ - EUR]",
            "NUTS II | NUTS 2",
        ],
        [
            [
                "NORTE-FEDER-0001",
                "Universidade do Porto",
                "Modernização com Google Workspace",
                "Migração para Google Workspace",
                45658,  # ~2025-01-01 excel serial approx - use string instead
                50000.0,
                60000.0,
                "Norte",
            ],
            [
                "LISBOA-FEDER-0002",
                "ACME SOFTWARE LDA",
                "Compra de AWS para PME",
                "Amazon Web Services",
                "2025-03-01",
                20000.0,
                20000.0,
                "Área Metropolitana de Lisboa",
            ],
        ],
    )
    # Fix start date for first row to proper date string
    from openpyxl import load_workbook

    wb = load_workbook(FIX / "pt2030.xlsx")
    ws = wb.active
    assert ws is not None
    ws["E2"] = "2025-01-15"
    wb.save(FIX / "pt2030.xlsx")

    _write(
        "prr.xlsx",
        ["idContrato", "NIF", "Objeto", "Valor"],
        [["1001", "500046117", "Licenças Microsoft Excel PRR", 12000.0]],
    )
    print(f"Fixtures em {FIX}")


if __name__ == "__main__":
    main()
