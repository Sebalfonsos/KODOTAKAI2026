"""Veredicto determinista sobre mercancías especiales (RF-MP), según DOC-OPS-2026-03 §2, §3, §4 y §5.

API:
- `evaluar_producto(texto, catalogo=CATALOGO) -> EvaluacionProducto` con `veredicto` en
  permitido | restringido | solo_ftl | prohibido | desconocido, `clase_onu`, `motivo`, `fuente`,
  `documentos_requeridos` y `categoria_embalaje` (A-D del manual §4, o None).
  Coincidencia por palabra/frase completa sin tildes ni mayúsculas (admite plural en s/es). Si hay
  varias coincidencias, se descartan las contenidas en otra más larga y gana la más severa.
  Sin coincidencias -> 'desconocido' (el orquestador consulta RAG con confianza baja).
- `CATALOGO`: tupla de `EntradaCatalogo`, datos de referencia transcritos del manual.

ponytail: catálogo de sinónimos cerrado; un producto fuera de la lista cae en 'desconocido' y lo
resuelve RAG/humano. No interpreta cantidades ("5 litros") contra los límites: los da en `motivo`.
"""

import re
from dataclasses import dataclass

from app.domain.sanitizar import normalizar_para_busqueda

DOCUMENTOS_MP = (
    "Hoja de Datos de Seguridad (MSDS/HDS) SGA de 16 secciones, en español y con revisión no mayor a 3 años",
    "Tarjeta de Emergencia NTC 4532",
    "Manifiesto de carga / Remesa terrestre de carga (RNDC), expedido por TransLogix",
)

SEVERIDAD = {"permitido": 0, "restringido": 1, "solo_ftl": 2, "prohibido": 3}


@dataclass(frozen=True)
class EntradaCatalogo:
    nombre: str
    sinonimos: tuple[str, ...]
    veredicto: str
    clase_onu: str | None
    motivo: str
    fuente: str
    categoria_embalaje: str | None = None

    @property
    def documentos(self) -> tuple[str, ...]:
        return DOCUMENTOS_MP if self.clase_onu and self.veredicto in ("restringido", "solo_ftl") else ()


@dataclass(frozen=True)
class EvaluacionProducto:
    veredicto: str
    producto: str | None
    clase_onu: str | None
    motivo: str
    fuente: str | None
    documentos_requeridos: tuple[str, ...]
    categoria_embalaje: str | None


def _e(nombre, sinonimos, veredicto, clase, motivo, fuente, embalaje=None):
    return EntradaCatalogo(nombre, tuple(sinonimos.split("|")), veredicto, clase, motivo, fuente, embalaje)


_PROHIBIDO = "Artículo de la lista de prohibidos: no se recibe ni se transporta bajo ninguna modalidad."
_M = "DOC-OPS-2026-03"

CATALOGO: tuple[EntradaCatalogo, ...] = (
    # §5 Lista negra
    _e(
        "dinero en efectivo y títulos valores",
        "dinero|dinero en efectivo|efectivo|billete|billetes|moneda|monedas|titulos valores|"
        "cheque al portador|lingote|lingote de oro|lingote de plata",
        "prohibido",
        None,
        _PROHIBIDO,
        f"{_M} §5.1",
    ),
    _e(
        "armas y municiones",
        "arma|arma de fuego|armas de fuego|pistola|revolver|escopeta|rifle|municion|municiones|silenciador|"
        "arma neumatica|pistola de fogueo|arma blanca|armamento",
        "prohibido",
        None,
        _PROHIBIDO,
        f"{_M} §5.2",
    ),
    _e(
        "estupefacientes",
        "estupefaciente|droga|drogas ilicitas|marihuana|cocaina|psicotropico|sustancias psicotropicas",
        "prohibido",
        None,
        _PROHIBIDO,
        f"{_M} §5.3",
    ),
    _e(
        "restos humanos o cadáveres animales",
        "restos humanos|cenizas|cenizas de cremacion|cadaver|cadaver animal",
        "prohibido",
        None,
        _PROHIBIDO,
        f"{_M} §5.4",
    ),
    _e(
        "animales vivos",
        "animal|animal vivo|animales vivos|mascota|perro|gato|cachorro|ave|pajaro|loro|gallina|pollito|"
        "reptil|serpiente|tortuga|iguana|insecto|pez|peces|conejo|hamster",
        "prohibido",
        None,
        _PROHIBIDO + " Incluye mamíferos, aves, reptiles, insectos y peces.",
        f"{_M} §5.5",
    ),
    _e(
        "joyas de alto valor y gemas",
        "joya|joyas|gema|gemas preciosas|diamante|esmeralda|obra de arte|obras de arte",
        "prohibido",
        None,
        _PROHIBIDO + " Aplica a joyas de alto valor, gemas sueltas y obras de arte de patrimonio no aseguradas.",
        f"{_M} §5.6",
    ),
    _e(
        "explosivos y pólvora",
        "polvora|polvora negra|fuegos artificiales|fuegos pirotecnicos|pirotecnia|voladores|explosivo|"
        "dinamita|detonador|nitroglicerina|mecha de ignicion",
        "prohibido",
        "1",
        _PROHIBIDO + " Clase 1 (explosivos) prohibida en su totalidad.",
        f"{_M} §2 Clase 1 y §5.7",
    ),
    _e(
        "material radiactivo",
        "material radiactivo|radiactivo|radioactivo|material radioactivo|uranio|yodo 131|equipo de gammagrafia",
        "prohibido",
        "7",
        _PROHIBIDO + " Clase 7 prohibida absolutamente.",
        f"{_M} §2 Clase 7 y §5.8",
    ),
    _e(
        "mercancía de contrabando",
        "contrabando",
        "prohibido",
        None,
        _PROHIBIDO,
        f"{_M} §5.9",
    ),
    # §2 Clases ONU
    _e(
        "gas inflamable (2.1)",
        "propano|butano|acetileno|gas inflamable|gas propano|pipeta de gas|cilindro de gas",
        "solo_ftl",
        "2.1",
        "Aceptado únicamente en FTL con vehículo certificado con blindaje de tanque y plan de contingencia "
        "avalado por el Ministerio de Transporte. Prohibido en paquetería express.",
        f"{_M} §2 Clase 2.1",
    ),
    _e(
        "gas no inflamable y no tóxico (2.2)",
        "nitrogeno|nitrogeno liquido|oxigeno|oxigeno comprimido|argon",
        "restringido",
        "2.2",
        "Aceptado con revisión previa de la MSDS y en cilindros con prueba hidrostática vigente (< 5 años).",
        f"{_M} §2 Clase 2.2",
    ),
    _e(
        "gas tóxico por inhalación (2.3)",
        "gas toxico|fosgeno|cloro gaseoso|gas cloro",
        "restringido",
        "2.3",
        "Restringido: requiere aprobación del Comité Operativo y custodia de escolta vehicular.",
        f"{_M} §2 Clase 2.3",
    ),
    _e(
        "líquido inflamable (3)",
        "gasolina|thinner|tiner|diluyente|acetona|alcohol|alcohol industrial|varsol|solvente|"
        "pintura a base de solvente|liquido inflamable",
        "restringido",
        "3",
        "FTL: hasta 15.000 litros en cisterna o tambores de 55 galones certificados (UN 1A1). "
        "Paquetería LTL: solo envases metálicos o HDPE de máximo 1 litro, en caja máster con material "
        "absorbente inerte "
        "(vermiculita) y rótulo Clase 3; punto de inflamación mínimo de 23 °C.",
        f"{_M} §2 Clase 3",
        "B",
    ),
    _e(
        "sólido inflamable (4.1)",
        "azufre|fosforos|cerillas|virutas de magnesio",
        "restringido",
        "4.1",
        "Aceptado en empaques sellados al vacío.",
        f"{_M} §2 Clase 4.1",
    ),
    _e(
        "sustancia espontáneamente combustible (4.2)",
        "carbon activado|fosforo blanco",
        "solo_ftl",
        "4.2",
        "Prohibido en paquetería. Solo FTL especializado.",
        f"{_M} §2 Clase 4.2",
    ),
    _e(
        "sustancia que con agua emite gases inflamables (4.3)",
        "sodio metalico|potasio metalico",
        "prohibido",
        "4.3",
        "Clase 4.3 prohibida.",
        f"{_M} §2 Clase 4.3",
    ),
    _e(
        "sustancia comburente (5.1)",
        "nitrato de amonio|peroxido de hidrogeno",
        "restringido",
        "5.1",
        "Aceptado con estibado separado de líquidos inflamables (peróxido de hidrógeno > 20 %).",
        f"{_M} §2 Clase 5.1",
    ),
    _e(
        "peróxido orgánico (5.2)",
        "peroxido organico",
        "restringido",
        "5.2",
        "Requiere control de temperatura constante: solo en flota de Cadena de Frío certificada.",
        f"{_M} §2 Clase 5.2",
        "C",
    ),
    _e(
        "sustancia tóxica (6.1)",
        "plaguicida|pesticida|insecticida|herbicida|fungicida|raticida|veneno|cianuro|plomo",
        "restringido",
        "6.1",
        "Aceptado con embalaje primario hermético. Prohibido consolidar en la misma unidad con alimentos, "
        "medicinas o cosméticos.",
        f"{_M} §2 Clase 6.1",
    ),
    _e(
        "muestra biológica de diagnóstico (6.2)",
        "muestra de sangre|muestra biologica|muestra de diagnostico|muestra de laboratorio",
        "restringido",
        "6.2",
        "Solo muestras de diagnóstico en triple contenedor según la instrucción P650 IATA/ONU "
        "(envase primario estanco, embalaje secundario estanco y exterior rígido).",
        f"{_M} §2 Clase 6.2",
    ),
    _e(
        "material infeccioso categoría A o residuos biológicos (6.2)",
        "cultivo de virus|residuos hospitalarios|residuos biologicos|material infeccioso|onu 2814|un 2814",
        "prohibido",
        "6.2",
        "Prohibidos los residuos biológicos peligrosos y el material infeccioso de Categoría A (ONU 2814).",
        f"{_M} §2 Clase 6.2",
    ),
    _e(
        "corrosivo líquido (8)",
        "acido clorhidrico|acido muriatico|acido sulfurico|hidroxido de sodio|soda caustica|corrosivo",
        "restringido",
        "8",
        "Líquidos corrosivos en envases no superiores a 5 litros en paquetería, en recipiente primario "
        "hermético, con sobre-empaque en caja de cartón corrugado de doble pared (7 capas).",
        f"{_M} §2 Clase 8 y §6",
        "B",
    ),
    _e(
        "batería de plomo-ácido húmeda (8)",
        "bateria de carro|bateria de plomo|bateria de plomo acido|bateria automotriz|bateria de vehiculo",
        "restringido",
        "8",
        "Debe viajar en guacal plástico antifugas con los bornes aislados con cinta dieléctrica.",
        f"{_M} §2 Clase 8",
    ),
    _e(
        "batería de litio suelta (9, ONU 3480)",
        "bateria de litio|pila de litio|baterias de litio sueltas|bateria de litio suelta|power bank|"
        "powerbank|onu 3480|un 3480",
        "restringido",
        "9",
        "Terminales protegidos contra cortocircuito y etiqueta de batería de litio ONU con teléfono de emergencia.",
        f"{_M} §2 Clase 9",
    ),
    _e(
        "hielo seco (9)",
        "hielo seco|dioxido de carbono solido",
        "restringido",
        "9",
        "Clase 9 (objetos peligrosos diversos): requiere la documentación de mercancía peligrosa.",
        f"{_M} §2 Clase 9",
    ),
    _e(
        "equipo con batería de litio instalada (9, ONU 3481)",
        "celular|telefono|smartphone|computador|portatil|laptop|tablet|herramienta electrica|"
        "bateria instalada|bateria de litio instalada|onu 3481|un 3481",
        "permitido",
        "9",
        "Equipos con batería instalada (ONU 3481) se aceptan sin recargo. Embalaje de electrónicos: bolsa "
        "antiestática y esquineras EPE.",
        f"{_M} §2 Clase 9 y §4.D",
        "D",
    ),
    # §4 Categorías de embalaje para carga general
    _e(
        "producto frágil",
        "vidrio|ceramica|porcelana|espejo|instrumento de medicion|cristaleria",
        "permitido",
        None,
        "Carga general frágil: sistema caja dentro de caja, burbuja de 3 cm, 5 cm a las paredes y rótulo FRÁGIL.",
        f"{_M} §4.A",
        "A",
    ),
    _e(
        "líquido no peligroso",
        "cosmetico|aceite comestible|bebida|jugo|gaseosa",
        "permitido",
        None,
        "Líquido no peligroso: sellar la tapa, bolsa calibre 4 hermética y material absorbente.",
        f"{_M} §4.B",
        "B",
    ),
    _e(
        "perecedero o medicamento (cadena de frío)",
        "medicamento|vacuna|insulina|alimento perecedero|alimentos perecederos|farmaco",
        "permitido",
        None,
        "Cadena de frío entre -20 °C y 8 °C: nevera de icopor de 30 mm, geles refrigerantes y caja exterior; "
        "conservación pasiva máxima de 48 horas.",
        f"{_M} §4.C",
        "C",
    ),
    _e(
        "equipo electrónico o de precisión",
        "servidor|equipo electronico|maquinaria de precision|electronico",
        "permitido",
        None,
        "Electrónicos: bolsa antiestática, esquineras EPE en las 8 esquinas y bloqueo del encendido.",
        f"{_M} §4.D",
        "D",
    ),
)


def _patron(sinonimo: str) -> re.Pattern:
    palabras = normalizar_para_busqueda(sinonimo).split()
    return re.compile(r"(?<!\w)" + r"\s+".join(rf"{re.escape(p)}(?:e?s)?" for p in palabras) + r"(?!\w)")


_PATRONES: dict[str, re.Pattern] = {}


def _buscar(sinonimo: str, texto_norm: str):
    if sinonimo not in _PATRONES:
        _PATRONES[sinonimo] = _patron(sinonimo)
    return _PATRONES[sinonimo].finditer(texto_norm)


def evaluar_producto(texto: str, catalogo: tuple[EntradaCatalogo, ...] = CATALOGO) -> EvaluacionProducto:
    norm = normalizar_para_busqueda(texto)
    hallazgos = [
        (m.start(), m.end(), entrada) for entrada in catalogo for s in entrada.sinonimos for m in _buscar(s, norm)
    ]
    # Una coincidencia contenida en otra más larga no cuenta ("bateria de litio" dentro de "... instalada").
    hallazgos = [
        h
        for h in hallazgos
        if not any(o[0] <= h[0] and h[1] <= o[1] and (o[1] - o[0]) > (h[1] - h[0]) for o in hallazgos)
    ]
    if not hallazgos:
        return EvaluacionProducto(
            "desconocido", None, None, "El producto no está en el catálogo de referencia.", None, (), None
        )
    _, _, e = max(hallazgos, key=lambda h: (SEVERIDAD[h[2].veredicto], h[1] - h[0]))
    return EvaluacionProducto(
        e.veredicto, e.nombre, e.clase_onu, e.motivo, e.fuente, e.documentos, e.categoria_embalaje
    )
