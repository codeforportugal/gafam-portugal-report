"""CLI: `python -m gafam_contratos` (fixtures) ou `--full` (ficheiros nacionais)."""

from __future__ import annotations

import argparse
import sys

from gafam_contratos.pipeline import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rastreia dinheiro público ligado a produtos GAFAM.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Descarrega ficheiros nacionais 2022–2026 (só após pytest).",
    )
    args = parser.parse_args(argv)
    out = run(full=args.full)
    print(f"Relatório em {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
