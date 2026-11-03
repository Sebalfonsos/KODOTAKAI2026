"""Exporta el esquema OpenAPI a docs/openapi.json.

python -m app.openapi           # escribe el archivo
python -m app.openapi --check   # sale con 1 si el archivo versionado está desactualizado
"""

import argparse
import json
import sys

from app.config import RAIZ

RUTA = RAIZ / "docs" / "openapi.json"


def generar() -> str:
    from app.main import app

    # sort_keys + indent: diffs estables y legibles en Git.
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="no escribe; falla si docs/openapi.json difiere")
    args = p.parse_args(argv)
    nuevo = generar()
    if args.check:
        if not RUTA.exists() or RUTA.read_text(encoding="utf-8") != nuevo:
            print(f"{RUTA.relative_to(RAIZ)} está desactualizado: ejecuta `make openapi`.", file=sys.stderr)
            return 1
        return 0
    RUTA.write_text(nuevo, encoding="utf-8")
    print(f"escrito {RUTA.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
