"""Pruebas puras del RAG: chunking, metadatos, fichas y RRF (sin BD ni red)."""

import json

import pytest

from app.ai.rag import (
    MANUALES,
    _sha,
    cobertura_normalizada,
    corpus,
    dividir_markdown,
    fichas_cobertura,
    fusionar_rrf,
    metadatos_seccion,
    ventanas,
    zona_de,
)
from tests.unit.conftest import INFO

MD = """# Título del documento
**Código: DOC-X** (preámbulo que no se indexa)

---

## 1. MARCO LEGAL
Ley 1.

## 2. CLASIFICACIÓN
Intro.

### Clase 8: Corrosivos
Ácidos.

```
## esto no es un encabezado
```

#### Detalle
Más.

## 3. Vacía

## 4. EMBALAJE DE MERCANCÍA
Caja.
"""


def test_dividir_markdown_rutas_y_cuerpos():
    secciones = dividir_markdown(MD)
    assert [r for r, _ in secciones] == [
        "1. MARCO LEGAL",
        "2. CLASIFICACIÓN",
        "2. CLASIFICACIÓN > Clase 8: Corrosivos",
        "2. CLASIFICACIÓN > Clase 8: Corrosivos > Detalle",
        "4. EMBALAJE DE MERCANCÍA",
    ]
    cuerpos = dict(secciones)
    assert "## esto no es un encabezado" in cuerpos["2. CLASIFICACIÓN > Clase 8: Corrosivos"]
    assert "preámbulo" not in "".join(cuerpos.values())


def test_metadatos_por_encabezado():
    assert metadatos_seccion("D", "pqrs", "1. MARCO LEGAL")["tipo"] == "legal"
    m = metadatos_seccion("D", "mercancia_peligrosa", "2. CLASIFICACIÓN > Clase 8: Corrosivos")
    assert m == {
        "doc_codigo": "D",
        "seccion": "2. CLASIFICACIÓN > Clase 8: Corrosivos",
        "tipo": "mercancia_peligrosa",
        "clase_onu": "8",
    }
    assert metadatos_seccion("D", "x", "4. EMBALAJE DE MERCANCÍA")["tipo"] == "embalaje"
    assert metadatos_seccion("D", "x", "5. LISTA DE ARTÍCULOS PROHIBIDOS")["tipo"] == "prohibido"
    assert metadatos_seccion("D", "pqrs", "7. CASOS DE USO")["tipo"] == "pqrs"


def test_ventanas_con_solape():
    texto = " ".join(f"p{i}" for i in range(100))
    assert ventanas(texto, n_tokens=100, max_tokens=512) == [texto]
    partes = ventanas(texto, n_tokens=100, max_tokens=40, solape=10)
    assert partes[0].split()[0] == "p0" and len(partes[0].split()) == 40
    assert partes[1].split()[0] == "p30"  # 10 palabras de solape
    assert partes[-1].split()[-1] == "p99"
    assert all(len(p.split()) <= 40 for p in partes)


def test_ventanas_solape_nunca_atasca():
    partes = ventanas("a b c", n_tokens=3000, max_tokens=512, solape=64)
    assert partes[-1].endswith("c") and len(partes) == 3


def test_rrf():
    fusion = fusionar_rrf([[1, 2, 3], [3, 4]], k=60)
    assert [i for i, _ in fusion] == [3, 1, 2, 4]
    assert fusion[0][1] == pytest.approx(1 / 63 + 1 / 61)
    assert fusionar_rrf([[], []]) == []


def test_zonas_y_cobertura():
    assert zona_de("Atlántico") == "costa_caribe" and zona_de("Caquetá") == "amazonia"
    assert zona_de("Chocó") == "pacifico" and zona_de("Meta") == "orinoquia"
    assert zona_de("Cundinamarca") == "andina" and zona_de("Narnia") is None
    assert cobertura_normalizada("Zona ZOMAC / Difícil Acceso") == cobertura_normalizada("Zona ZOMAC") == "zomac"
    assert cobertura_normalizada("Urbana Principal") == "urbana_principal"


def test_corpus_completo_y_sin_tarifas():
    docs = {codigo: secciones for codigo, *_, secciones in corpus(INFO)}
    assert set(docs) == {c for c, *_ in MANUALES} | {"FICHAS-TRAYECTOS", "FICHAS-COBERTURA", "POLITICAS-GENERALES"}
    assert len(docs["FICHAS-TRAYECTOS"]) == 25 and len(docs["FICHAS-COBERTURA"]) == 31
    ficha = next(s for s in docs["FICHAS-TRAYECTOS"] if s.metadatos["codigo_trayecto"] == "TLX-BOG-MED-001")
    assert "1450" not in ficha.cuerpo and "18500" not in ficha.cuerpo  # tarifas fuera del corpus
    assert ficha.metadatos["zona"] == "andina"
    clases = {s.metadatos.get("clase_onu") for s in docs["DOC-OPS-2026-03"]}
    assert {str(i) for i in range(1, 10)} <= clases
    tipos = {s.metadatos["tipo"] for secs in docs.values() for s in secs}
    assert tipos == {
        "legal",
        "mercancia_peligrosa",
        "embalaje",
        "prohibido",
        "pqrs",
        "trayecto",
        "cobertura",
        "politica",
    }


def test_ficha_cobertura_quibdo():
    municipios = json.loads((INFO / "directorio_cobertura_y_tiempos.json").read_text(encoding="utf-8"))
    quibdo = next(s for s in fichas_cobertura(municipios) if s.metadatos["municipio"] == "Quibdó")
    assert "refrigerado (cadena de frío): no disponible" in quibdo.cuerpo
    assert quibdo.metadatos["cobertura"] == "zomac" and quibdo.metadatos["zona"] == "pacifico"


def test_sha_estable_y_sensible():
    _, titulo, _, _, secciones = corpus(INFO)[0]
    assert _sha(secciones, titulo) == _sha(list(secciones), titulo)
    assert _sha(secciones[:-1], titulo) != _sha(secciones, titulo)
