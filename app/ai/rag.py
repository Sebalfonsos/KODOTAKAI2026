"""RAG híbrido sobre PostgreSQL + pgvector (RF-RAG-1..5).

API:
- `async ingestar_corpus(session, datos_dir) -> dict`: indexa los 2 manuales de KODOTAKAIINFO, las fichas de
  trayectos (sin tarifas), las fichas de cobertura y las políticas generales del dosier. Es idempotente por
  sha256: un documento igual no se re-embebe; uno que cambió reemplaza sus chunks en la misma transacción.
  Devuelve {"documentos", "chunks_nuevos", "omitidos"}.
- `async ingestar_documento(session, codigo, titulo, tipo, texto_markdown, fuente) -> dict`: un documento
  markdown suelto (POST /admin/rag/documentos). Devuelve {"codigo", "chunks", "omitido"}.
- `async buscar(session, consulta, k=4, tipos=None, embeddings=None) -> list[ResultadoRag]`: búsqueda
  híbrida (vector coseno top 20 + texto `spanish` top 20) con fusión RRF (k=60). `score_vector` es la
  similitud coseno (1 - distancia) y sirve para el confidence score.
- Funciones puras: `dividir_markdown`, `ventanas`, `metadatos_seccion`, `zona_de`, `fusionar_rrf`,
  `fichas_trayectos`, `fichas_cobertura`, `politicas_generales`.

Metadatos de cada chunk: doc_codigo, seccion, tipo (mercancia_peligrosa | embalaje | prohibido | pqrs |
cobertura | trayecto | politica | legal), clase_onu ("1".."9", si el encabezado nombra una clase), y en las
fichas: zona (región natural del departamento, ver `ZONAS`), cobertura (urbana_principal | frontera |
trayecto_especial | zomac, D-07), municipio u origen/destino.
El commit lo hace quien llama (el endpoint o el seed); aquí solo `flush`.
"""

import csv
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import ClienteEmbeddings, get_embeddings
from app.domain.sanitizar import normalizar_para_busqueda
from app.models.rag import Chunk, Documento

log = logging.getLogger(__name__)

MAX_TOKENS = 512
SOLAPE = 64
LOTE_EMBEDDINGS = 16
CANDIDATOS = 20
RRF_K = 60
# ponytail: tokenizador del llama-server local (LFM3), solo para contar; bge-m3 admite 8k, así que la
# diferencia de tokenizadores no corta nada.
TOKENIZE_URL = "http://127.0.0.1:8081/tokenize"

MANUALES = (
    ("DOC-OPS-2026-03", "manual_de_mercanc_as_peligrosas_y_embalaje.md", "mercancia_peligrosa"),
    ("DOC-PQRS-2026-04", "protocolo_de_pqrs_y_procedimiento_de_indemnizaciones.md", "pqrs"),
)

# Región natural por departamento (simplificación por departamento, no por municipio).
ZONAS = {
    "costa_caribe": ("Atlántico", "Bolívar", "Magdalena", "Córdoba", "Cesar", "La Guajira", "Sucre"),
    "andina": (
        "Cundinamarca",
        "Antioquia",
        "Santander",
        "Norte de Santander",
        "Risaralda",
        "Caldas",
        "Quindío",
        "Huila",
        "Tolima",
        "Boyacá",
    ),
    "pacifico": ("Valle del Cauca", "Chocó", "Nariño", "Cauca"),
    "orinoquia": ("Meta", "Casanare", "Arauca", "Vichada"),
    "amazonia": ("Caquetá", "Putumayo", "Amazonas", "Guaviare", "Vaupés", "Guainía"),
}
_ZONA_POR_DEPTO = {normalizar_para_busqueda(d): z for z, deptos in ZONAS.items() for d in deptos}

# Tipo de sección por palabras del encabezado de primer nivel (se revisan en orden).
_TIPOS_ENCABEZADO = (
    ("marco legal", "legal"),
    ("embalaje", "embalaje"),
    ("prohibido", "prohibido"),
    ("clasificacion", "mercancia_peligrosa"),
    ("documentacion", "mercancia_peligrosa"),
)


@dataclass(frozen=True)
class Seccion:
    ruta: str
    cuerpo: str
    metadatos: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ResultadoRag:
    chunk_id: int
    doc_codigo: str
    titulo_doc: str
    seccion: str
    contenido: str
    score_vector: float
    score_texto: float
    score_rrf: float
    metadatos: dict


# ---------------------------------------------------------------- funciones puras


def dividir_markdown(texto: str) -> list[tuple[str, str]]:
    """Secciones (ruta "H2 > H3", cuerpo) de un markdown. El H1 es el título del documento y el preámbulo
    antes del primer H2 (código y aplicabilidad del documento) no se indexa."""
    secciones: list[tuple[str, str]] = []
    pila: list[tuple[int, str]] = []
    cuerpo: list[str] = []
    en_codigo = False

    def cerrar():
        contenido = "\n".join(cuerpo).strip().strip("-").strip()
        if pila and contenido:
            secciones.append((" > ".join(t for _, t in pila), contenido))
        cuerpo.clear()

    for linea in texto.splitlines():
        if linea.lstrip().startswith("```"):
            en_codigo = not en_codigo
        m = None if en_codigo else re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", linea)
        if not m:
            cuerpo.append(linea)
            continue
        cerrar()
        nivel = len(m.group(1))
        if nivel == 1:
            pila.clear()
            continue
        while pila and pila[-1][0] >= nivel:
            pila.pop()
        pila.append((nivel, m.group(2).replace("**", "")))
    cerrar()
    return secciones


def ventanas(texto: str, n_tokens: int, max_tokens: int = MAX_TOKENS, solape: int = SOLAPE) -> list[str]:
    """Parte `texto` (de `n_tokens` tokens) en ventanas de ~max_tokens con ~solape tokens repetidos."""
    if n_tokens <= max_tokens:
        return [texto]
    palabras = re.findall(r"\S+\s*", texto)
    # ponytail: corta por palabras con la razón tokens/palabra media del texto; una ventana puede pasarse
    # unos pocos tokens del máximo. Cortar por token exacto si algún día importa.
    por_palabra = n_tokens / len(palabras)
    paso_max = max(1, int(max_tokens / por_palabra))
    paso_solape = min(paso_max - 1, int(solape / por_palabra))
    salida = []
    inicio = 0
    while True:
        salida.append("".join(palabras[inicio : inicio + paso_max]).strip())
        if inicio + paso_max >= len(palabras):
            return salida
        inicio += paso_max - paso_solape


def zona_de(departamento: str) -> str | None:
    return _ZONA_POR_DEPTO.get(normalizar_para_busqueda(departamento))


def cobertura_normalizada(tipo_cobertura: str) -> str:
    """D-07: 'Zona ZOMAC' y 'Zona ZOMAC / Difícil Acceso' -> 'zomac'."""
    norm = normalizar_para_busqueda(tipo_cobertura)
    return "zomac" if "zomac" in norm else norm.replace(" ", "_")


def metadatos_seccion(doc_codigo: str, tipo_doc: str, ruta: str) -> dict:
    primer_nivel = normalizar_para_busqueda(ruta.split(" > ")[0])
    tipo = next((t for clave, t in _TIPOS_ENCABEZADO if clave in primer_nivel), tipo_doc)
    meta = {"doc_codigo": doc_codigo, "seccion": ruta, "tipo": tipo}
    if m := re.search(r"\bClase (\d)\b", ruta):
        meta["clase_onu"] = m.group(1)
    return meta


def fusionar_rrf(listas: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion: sum(1 / (k + rango)) con rango desde 1. Orden descendente y estable."""
    puntajes: dict[int, float] = {}
    for lista in listas:
        for rango, ident in enumerate(lista, start=1):
            puntajes[ident] = puntajes.get(ident, 0.0) + 1.0 / (k + rango)
    return sorted(puntajes.items(), key=lambda p: -p[1])


def _si_no(valor: bool) -> str:
    return "disponible" if valor else "no disponible"


def fichas_trayectos(filas: list[dict]) -> list[Seccion]:
    """Una ficha por trayecto de la matriz, SIN cifras de tarifa (las da el cotizador)."""
    fichas = []
    for f in filas:
        f = {k.lstrip("﻿"): v for k, v in f.items()}
        ruta = f"Trayecto {f['ciudad_origen']} → {f['ciudad_destino']}"
        cuerpo = (
            f"Trayecto {f['codigo_trayecto']}: de {f['ciudad_origen']} ({f['departamento_origen']}) a "
            f"{f['ciudad_destino']} ({f['departamento_destino']}). Tipo de cobertura: {f['tipo_cobertura']}. "
            f"Tiempo de entrega estimado: {f['tiempo_entrega_estimado_horas']} horas. "
            f"Observaciones de la ruta: {f['observaciones_ruta']} "
            "La tarifa, el seguro y los recargos de esta ruta se calculan con el cotizador."
        )
        meta = {
            "tipo": "trayecto",
            "codigo_trayecto": f["codigo_trayecto"],
            "origen": f["ciudad_origen"],
            "destino": f["ciudad_destino"],
            "zona": zona_de(f["departamento_destino"]),
            "cobertura": cobertura_normalizada(f["tipo_cobertura"]),
        }
        fichas.append(Seccion(ruta, cuerpo, meta))
    return fichas


def fichas_cobertura(municipios: list[dict]) -> list[Seccion]:
    """Una ficha por municipio del directorio de cobertura."""
    fichas = []
    for m in municipios:
        cuerpo = (
            f"Cobertura en {m['municipio']} ({m['departamento']}), código DANE {m['codigo_dane']}: sí llegamos. "
            f"Tipo de cobertura: {m['tipo_cobertura']}. Hub operativo asignado: {m['hub_operativo_asignado']}. "
            f"Tiempo de entrega estándar: {m['tiempo_entrega_estandar_horas']} horas. "
            f"Servicio Same Day (mismo día): {_si_no(m['servicio_same_day_disponible'])}. "
            f"Servicio refrigerado (cadena de frío): {_si_no(m['servicio_refrigerado_disponible'])}. "
            f"Peso máximo por paquete: {m['peso_maximo_paquete_kg']} kg. Volumen máximo: {m['volumen_maximo_m3']} m³. "
            f"Frecuencia de despacho: {m['frecuencia_despacho']}. "
            f"Restricciones operativas: {m['restricciones_operativas']}"
        )
        meta = {
            "tipo": "cobertura",
            "municipio": m["municipio"],
            "codigo_dane": m["codigo_dane"],
            "zona": zona_de(m["departamento"]),
            "cobertura": cobertura_normalizada(m["tipo_cobertura"]),
        }
        fichas.append(Seccion(f"Cobertura {m['municipio']}", cuerpo, meta))
    return fichas


def politicas_generales() -> list[Seccion]:
    """Políticas para el cliente redactadas desde el dosier §1, §2 y §4 (con D-01 para el seguro)."""
    textos = {
        "Paquetería exprés y Same Day (dosier §2.B)": (
            "La paquetería empresarial y mensajería exprés de última milla recibe documentos, muestras "
            "comerciales y paquetes de hasta 50 kg por envío, con tiempos de entrega de 24 a 48 horas a nivel "
            "nacional. El servicio Same Day (entrega el mismo día) opera en Bogotá, Medellín y Cali. Para más "
            "de 50 kg se usa la modalidad de carga."
        ),
        "Carga masiva y semimasiva FTL / LTL (dosier §2.A)": (
            "Transporte de contenedores de 20 y 40 pies y carga suelta intermunicipal en tractocamiones y "
            "camiones de gran tonelaje. Incluye precintado de seguridad, póliza de cobertura por trayecto y "
            "monitoreo GPS 24/7 desde el centro de control."
        ),
        "Cadena de frío certificada (dosier §2.D)": (
            "Flota con refrigeración multitemperatura entre -20 °C y 8 °C y registradores digitales de "
            "temperatura, para los sectores farmacéutico, hospitalario, biológico y de alimentos perecederos. "
            "No todos los municipios tienen servicio refrigerado: se confirma en la ficha de cobertura."
        ),
        "Peso volumétrico y peso a facturar (dosier §4.2)": (
            "El peso volumétrico en kilogramos es el alto por el ancho por el largo del paquete en centímetros, "
            "dividido entre 4000. Se factura el mayor entre el peso real en báscula y el peso volumétrico. Para "
            "cotizar se necesitan origen, destino, alto, ancho y largo en centímetros, peso real en kilogramos "
            "y valor declarado en pesos."
        ),
        "Seguro de la mercancía (dosier §3 y §4.2)": (
            "Todo envío lleva un seguro del 1 % sobre el valor declarado, con un valor mínimo que depende de la "
            "ruta. El cotizador muestra el seguro exacto en el desglose."
        ),
        "Almacenamiento y logística inversa (dosier §2.C y §2.E)": (
            "TransLogix ofrece almacenamiento con WMS en bodegas de ambiente controlado y zonas francas, pick & "
            "pack, etiquetado e integración con Shopify, WooCommerce y VTEX. También recoge devoluciones en "
            "puntos de venta o en el domicilio del consumidor, inspecciona, re-empaca y consolida el retorno."
        ),
        "Sede y centros logísticos (dosier §1)": (
            "La sede principal está en la Calle 26 # 96J-15, Zona Franca Fontibón, Bogotá. Hay centros "
            "logísticos en Rionegro (Medellín), Yumbo (Cali) y Malambo (Barranquilla). TransLogix cubre 32 "
            "departamentos y más de 650 municipios."
        ),
    }
    return [Seccion(ruta, cuerpo, {"tipo": "politica"}) for ruta, cuerpo in textos.items()]


def _secciones_markdown(codigo: str, tipo: str, texto: str) -> list[Seccion]:
    return [Seccion(r, c, metadatos_seccion(codigo, tipo, r)) for r, c in dividir_markdown(texto)]


def _sha(secciones: list[Seccion], titulo: str) -> str:
    canon = json.dumps([titulo] + [[s.ruta, s.cuerpo, s.metadatos] for s in secciones], ensure_ascii=False)
    return hashlib.sha256(canon.encode()).hexdigest()


# ---------------------------------------------------------------- E/S


async def contar_tokens(textos: list[str]) -> list[int]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            cuentas = []
            for t in textos:
                r = await http.post(TOKENIZE_URL, json={"content": t})
                r.raise_for_status()
                cuentas.append(len(r.json()["tokens"]))
            return cuentas
    except httpx.HTTPError as e:
        log.warning("tokenize_no_disponible_aproximando", extra={"error": type(e).__name__})
        return [max(1, len(t) // 4) for t in textos]


async def _guardar(
    session: AsyncSession,
    codigo: str,
    titulo: str,
    tipo: str,
    fuente: str,
    secciones: list[Seccion],
    embeddings: ClienteEmbeddings,
) -> tuple[int, bool]:
    """Inserta o reemplaza un documento. Devuelve (chunks_insertados, omitido)."""
    sha = _sha(secciones, titulo)
    doc = (await session.execute(select(Documento).where(Documento.codigo == codigo))).scalar_one_or_none()
    if doc and doc.sha256 == sha:
        return 0, True

    cuentas = await contar_tokens([s.cuerpo for s in secciones])
    piezas: list[tuple[Seccion, str]] = [
        (s, v) for s, n in zip(secciones, cuentas, strict=True) for v in ventanas(s.cuerpo, n)
    ]
    tokens = await contar_tokens([p for _, p in piezas])
    vectores: list[list[float]] = []
    for i in range(0, len(piezas), LOTE_EMBEDDINGS):
        lote = piezas[i : i + LOTE_EMBEDDINGS]
        vectores += await embeddings.embeber([f"{titulo} > {s.ruta}\n{p}" for s, p in lote])

    if doc:
        await session.execute(delete(Chunk).where(Chunk.documento_id == doc.id))
        doc.titulo, doc.tipo, doc.fuente, doc.sha256, doc.activo = titulo, tipo, fuente, sha, True
    else:
        doc = Documento(codigo=codigo, titulo=titulo, tipo=tipo, fuente=fuente, sha256=sha)
        session.add(doc)
    await session.flush()
    session.add_all(
        Chunk(
            documento_id=doc.id,
            orden=orden,
            seccion=s.ruta[:300],
            contenido=pieza,
            tokens=n,
            metadatos={"doc_codigo": codigo, "seccion": s.ruta, "tipo": tipo} | s.metadatos,
            embedding=vector,
        )
        for orden, ((s, pieza), n, vector) in enumerate(zip(piezas, tokens, vectores, strict=True))
    )
    await session.flush()
    log.info("rag_documento_indexado", extra={"codigo": codigo, "chunks": len(piezas)})
    return len(piezas), False


async def ingestar_documento(
    session: AsyncSession,
    codigo: str,
    titulo: str,
    tipo: str,
    texto_markdown: str,
    fuente: str,
    embeddings: ClienteEmbeddings | None = None,
) -> dict:
    secciones = _secciones_markdown(codigo, tipo, texto_markdown)
    n, omitido = await _guardar(session, codigo, titulo, tipo, fuente, secciones, embeddings or get_embeddings())
    return {"codigo": codigo, "chunks": n, "omitido": omitido}


def corpus(datos_dir: Path) -> list[tuple[str, str, str, str, list[Seccion]]]:
    """(codigo, titulo, tipo, fuente, secciones) de todo el corpus base. Pura salvo lectura de archivos."""
    docs = []
    for codigo, archivo, tipo in MANUALES:
        texto = (datos_dir / archivo).read_text(encoding="utf-8")
        titulo = re.search(r"^#\s+(.+)$", texto, re.M).group(1).strip()
        docs.append((codigo, titulo, tipo, archivo, _secciones_markdown(codigo, tipo, texto)))
    with (datos_dir / "matriz_tarifas_y_fletes.csv").open(encoding="utf-8-sig", newline="") as f:
        trayectos = fichas_trayectos(list(csv.DictReader(f)))
    municipios = json.loads((datos_dir / "directorio_cobertura_y_tiempos.json").read_text(encoding="utf-8"))
    docs += [
        ("FICHAS-TRAYECTOS", "Fichas de trayectos", "trayecto", "matriz_tarifas_y_fletes.csv", trayectos),
        (
            "FICHAS-COBERTURA",
            "Fichas de cobertura",
            "cobertura",
            "directorio_cobertura_y_tiempos.json",
            fichas_cobertura(municipios),
        ),
        ("POLITICAS-GENERALES", "Políticas generales", "politica", "Dosier KODO TAKAI 2026", politicas_generales()),
    ]
    return docs


async def ingestar_corpus(session: AsyncSession, datos_dir: Path, embeddings: ClienteEmbeddings | None = None) -> dict:
    emb = embeddings or get_embeddings()
    resumen = {"documentos": 0, "chunks_nuevos": 0, "omitidos": 0}
    for codigo, titulo, tipo, fuente, secciones in corpus(Path(datos_dir)):
        n, omitido = await _guardar(session, codigo, titulo, tipo, fuente, secciones, emb)
        resumen["documentos"] += 1
        resumen["chunks_nuevos"] += n
        resumen["omitidos"] += omitido
    return resumen


# Re-parseo con 'simple' para no volver a aplicar el stemmer a lexemas ya normalizados.
_TSQUERY = "to_tsquery('simple', replace(websearch_to_tsquery('spanish', :q)::text, ' & ', ' | '))"


def _json(valor) -> dict:
    return json.loads(valor) if isinstance(valor, str) else valor


async def buscar(
    session: AsyncSession,
    consulta: str,
    k: int = 4,
    tipos: list[str] | None = None,
    embeddings: ClienteEmbeddings | None = None,
) -> list[ResultadoRag]:
    vector = await (embeddings or get_embeddings()).embeber_consulta(consulta)
    v = "[" + ",".join(map(str, vector)) + "]"
    filtro = "AND c.metadatos->>'tipo' = ANY(:tipos)" if tipos else ""
    params = {"v": v, "q": consulta, "n": CANDIDATOS} | ({"tipos": tipos} if tipos else {})
    base = f"FROM chunks c JOIN documentos d ON d.id = c.documento_id WHERE d.activo {filtro}"

    await session.execute(text("SET LOCAL hnsw.ef_search = 40"))
    por_vector = (
        await session.execute(text(f"SELECT c.id {base} ORDER BY c.embedding <=> CAST(:v AS vector) LIMIT :n"), params)
    ).scalars()
    # ponytail: websearch_to_tsquery exige TODAS las palabras; se convierte a OR para preguntas en lenguaje
    # natural y ts_rank_cd premia la cobertura. Sin unaccent: "acido" no casa con "ácido" (lo cubre el vector).
    por_texto = (
        await session.execute(
            text(f"SELECT c.id {base} AND c.tsv @@ {_TSQUERY} ORDER BY ts_rank_cd(c.tsv, {_TSQUERY}) DESC LIMIT :n"),
            params,
        )
    ).scalars()
    fusion = fusionar_rrf([list(por_vector), list(por_texto)])[:k]
    if not fusion:
        return []

    ids = [i for i, _ in fusion]
    filas = (
        await session.execute(
            text(
                # Fragmentos SQL constantes del módulo; los valores van como parámetros enlazados.
                "SELECT c.id, d.codigo, d.titulo, c.seccion, c.contenido, c.metadatos, "  # noqa: S608
                "1 - (c.embedding <=> CAST(:v AS vector)) AS sim, "
                f"COALESCE(ts_rank_cd(c.tsv, {_TSQUERY}), 0) AS rank "
                "FROM chunks c JOIN documentos d ON d.id = c.documento_id WHERE c.id = ANY(:ids)"
            ),
            {"v": v, "q": consulta, "ids": ids},
        )
    ).all()
    por_id = {f.id: f for f in filas}
    return [
        ResultadoRag(
            chunk_id=i,
            doc_codigo=por_id[i].codigo,
            titulo_doc=por_id[i].titulo,
            seccion=por_id[i].seccion,
            contenido=por_id[i].contenido,
            score_vector=float(por_id[i].sim),
            score_texto=float(por_id[i].rank),
            score_rrf=rrf,
            metadatos=_json(por_id[i].metadatos),
        )
        for i, rrf in fusion
    ]
