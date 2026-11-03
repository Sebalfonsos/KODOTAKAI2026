"""Fixtures con los datos reales de KODOTAKAIINFO (no se duplican números en las pruebas)."""

import csv
import json
from pathlib import Path

import pytest

from app.domain.cotizador import MunicipioCobertura, Trayecto

INFO = Path(__file__).resolve().parents[2] / "KODOTAKAIINFO"


def _json(nombre: str):
    return json.loads((INFO / nombre).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def trayectos() -> list[Trayecto]:
    with (INFO / "matriz_tarifas_y_fletes.csv").open(encoding="utf-8-sig", newline="") as f:
        return [Trayecto.desde_fila(fila) for fila in csv.DictReader(f)]


@pytest.fixture(scope="session")
def municipios() -> list[MunicipioCobertura]:
    return [MunicipioCobertura(**m) for m in _json("directorio_cobertura_y_tiempos.json")]


@pytest.fixture(scope="session")
def reglas() -> dict:
    return _json("reglas_escalacion_humana.json")


@pytest.fixture(scope="session")
def guias() -> dict[str, dict]:
    return {g["numero_guia"]: g for g in _json("dataset_guias_simuladas_tms.json")}
