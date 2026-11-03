# Requisitos: backend IA de atención TransLogix (KODO TAKAI 2026)

| Campo | Valor |
|---|---|
| Versión | 0.2, 2026-11-03 |
| Estado | Aprobado. Las decisiones `D-xx` (sección 9) están adoptadas |
| Alcance | **Solo backend.** El frontend lo construye otro grupo a partir de `docs/openapi.json` y `docs/frontend.md` |
| Fuentes | `KODOTAKAIINFO/` (dosier, manuales, CSV, JSON y rúbricas) |

Convenciones: `RF` es un requisito funcional, `RNF` uno no funcional, `D` una decisión y `T` un caso de prueba de referencia. Los commits y las pruebas citan estos IDs. Ante una contradicción entre fuentes manda la decisión `D` correspondiente.

---

## 1. Fuentes y qué aporta cada una

| Archivo | Contenido | Se usa para |
|---|---|---|
| `Dosier Completo del Reto Técnico - KODO TAKAI 2026.pdf` | Caso de negocio, arquitectura y los 5 módulos obligatorios | Alcance, arquitectura y fórmulas |
| `manual_de_mercanc_as_peligrosas_y_embalaje.md` (DOC-OPS-2026-03) | Clases ONU 1 a 9, documentos obligatorios, embalaje y prohibidos | Corpus RAG y RF-MP |
| `protocolo_de_pqrs_y_procedimiento_de_indemnizaciones.md` (DOC-PQRS-2026-04) | Tipología PQRS, plazos, checklist, liquidación y exoneraciones | Corpus RAG y RF-PQRS |
| `matriz_tarifas_y_fletes.csv` | 25 trayectos `TLX-XXX-YYY-NNN` con tarifas, mínimos, recargos y horas | RF-COT, como **dato estructurado** en la BD |
| `directorio_cobertura_y_tiempos.json` | 31 municipios (código DANE, hub, same day, refrigerado, peso y volumen máximos, restricciones) | RF-COT y RF-TRK, como dato estructurado; corpus RAG |
| `dataset_guias_simuladas_tms.json` | 5 guías completas con historial y prueba de entrega | Mock de `GET /api/v1/tracking/{guia}` y pruebas |
| `reglas_escalacion_humana.json` (v1.0.2026) | Umbral 0,75, criterios CRIT-001 a 005, mensajes literales y payload de transferencia | RF-ESC, como **configuración** cargada en la BD (no se copia al código) |
| `Rúbrica de Evaluación Técnica - Mejor equipo Back end.pdf` | 4 criterios con peso 30/25/25/20 | Mapa de rúbrica (§12) |
| `Rúbrica de Evaluación Mejor Proyecto - Kodo Takai 2026 beta.pdf` | 6 criterios de 10 puntos | Mapa de rúbrica (§12) y `docs/negocio.md` |

## 2. Contexto y objetivos

TransLogix atiende 18.000 interacciones diarias: WhatsApp 60 %, web 25 % y PBX 15 %. La espera en horas pico es de 14,5 min, el 78 % de las consultas son repetitivas y el abandono del chat es del 22 %.

| Dolor (dosier §3) | Dato | Qué debe lograr el agente | Indicador propuesto |
|---|---|---|---|
| «¿Dónde está mi guía?» | 55 % de las interacciones | Rastreo autoservicio en lenguaje natural | % de consultas de rastreo resueltas sin humano |
| Errores al cotizar | 12 % de las cotizaciones manuales | Cálculo determinista y auditable | 0 diferencias frente al cálculo de referencia en el set T-COT |
| Información dispersa | 4,5 min por búsqueda | Respuesta RAG con fuente citada | Recall@4 del set T-RAG y tiempo de respuesta |
| PQRS incompletas | 40 % radicadas incompletas | Checklist guiado antes de radicar | % de tickets creados con el checklist completo |

Los indicadores son una propuesta: el dosier no fija metas numéricas.

## 3. Arquitectura lógica

```
Frontend (otro grupo) ──HTTP + SSE──►  API FastAPI 127.0.0.1:8100  (/api/v1, Swagger en /docs)
                                        ├─ Auth (JWT + refresh rotado) y RBAC por rol
                                        ├─ Orquestador de chat: enrutador determinista → herramienta → artifact
                                        │    → LLM redacta → verificador → confianza → escalamiento
                                        ├─ Dominio puro (app/domain): tarifas, plazos, liquidación, CRIT, mercancías
                                        ├─ RAG híbrido (pgvector HNSW + texto completo en español, RRF)
                                        └─ ML autoentrenado (riesgo de retraso, demanda) sobre datos simulados
                                             │                 │                       │
                          PostgreSQL 17 + pgvector    Ollama bge-m3 (CPU)    LLM LFM3-1.7B vía HAProxy
                          127.0.0.1:5433 (Docker)     127.0.0.1:11434        127.0.0.1:8000/v1
```

**Principio rector:** las tarifas, los pesos, los plazos, las liquidaciones, los veredictos de mercancía y los criterios de escalamiento se calculan en código. El LLM no calcula ni decide: clasifica la intención, extrae campos con `json_schema` y redacta a partir de los hechos que le entrega el código. Toda respuesta pasa por un verificador.

## 4. Roles y permisos

| Rol | Cómo se obtiene | Puede |
|---|---|---|
| Invitado | Sin token | Chat, rastreo (vista pública: estado, línea de tiempo, ETA y ciudad), cotizar, cobertura, mercancías |
| Cliente | Registro o usuario demo; token JWT | Lo del invitado + PQRS propias (crear, adjuntar, consultar), historial de sus sesiones, detalle de sus guías con datos personales enmascarados |
| Cliente corporativo / VIP | **Atributo de la cuenta**, no un rol: `cuentas.tipo_cuenta` (`ESTANDAR`, `CORPORATIVO`, `CORPORATIVO_GOLD`) y `envios_mensuales` | Lo del cliente; dispara CRIT-004 (ejecutivo de cuenta) según D-11 |
| Asesor | Creado por admin | Cola de escalamientos, tomar (`SKIP LOCKED`), responder en la sesión del cliente, resolver |
| Admin | Usuario semilla | Todo lo anterior + chat administrativo, métricas, usuarios, RAG, ML y simulador |

- RBAC con `require_role(...)` y **control de propiedad**: un cliente solo ve sus tickets y sesiones (lo ajeno responde 404, no 403, para no revelar existencia).
- Las acciones de asesor y admin quedan en `auditoria`.

## 5. Requisitos funcionales

### RF-RAG: motor de ingesta vectorial
- RF-RAG-1. Indexar los dos manuales `.md` y la versión textual del directorio y de la matriz en chunks de 512 tokens con solapamiento de 64.
- RF-RAG-2. Cada chunk lleva como metadatos `doc_codigo` (DOC-OPS-2026-03…), `seccion`, `tipo` (`tarifa`, `cobertura`, `mercancia_peligrosa`, `embalaje`, `pqrs`, `prohibido`) y, cuando aplique, `zona` (p. ej. `costa_caribe`) y `clase_onu`.
- RF-RAG-3. La búsqueda es híbrida (coseno HNSW + `ts_rank` en español, fusionadas con RRF) y filtra por metadatos según la intención. Top-k = 4 (D-14).
- RF-RAG-4. La ingesta es idempotente por sha256: reindexar no duplica chunks.
- RF-RAG-5. La respuesta indica el documento y la sección de donde sale (artifact `citas`).
- Aceptación: recall@4 ≥ 0,9 en el set T-RAG.

### RF-COT: calculadora conversacional de cotizaciones
- RF-COT-1. Pide los datos hasta completarlos: origen, destino, alto, ancho y largo (cm), peso real (kg), valor declarado (COP) y servicio. No asume ningún valor que el usuario no haya dado. En el chat se materializa como el artifact `formulario_cotizacion`, con los valores ya extraídos del mensaje precargados.
- RF-COT-2. Fórmulas del dosier:
  - `peso_volumetrico = alto × ancho × largo / 4000` (el CSV trae `factor_divisitivas_volumetrico = 4000` en todas las rutas)
  - `peso_facturable = max(peso_real, peso_volumetrico)`
  - `flete_total = flete_base(origen, destino, peso_facturable) + max(0,01 × valor_declarado, seguro_minimo)`, con `seguro_minimo` según D-01 y `flete_base` según D-02 y D-03.
- RF-COT-3. El trayecto se busca en la matriz por par origen-destino. Si no existe, no cotiza, lo dice y ofrece un asesor (D-04).
- RF-COT-4. Valida contra el directorio: cobertura del destino, `peso_maximo_paquete_kg`, `servicio_refrigerado_disponible` si es cadena de frío (D-06) y máximo 50 kg en paquetería exprés (dosier §2.B).
- RF-COT-5. Si se declara mercancía peligrosa, consulta RF-MP antes de cotizar: un artículo prohibido no se cotiza.
- RF-COT-6. Devuelve el desglose (peso facturable, tarifa aplicada, flete base, seguro, recargos y total) y el tiempo estimado con las observaciones de la ruta (artifact `resultado_cotizacion`). Se persiste en `cotizaciones` con la versión de reglas.
- Aceptación: el set T-COT da el total esperado al peso.

### RF-TRK: rastreo inteligente de guías
- RF-TRK-1. Detecta guías con `TLX-\d{6}-CO`, sin importar mayúsculas y tolerando espacios. Si hay varias, pregunta cuál; si no hay, emite `formulario_guia`.
- RF-TRK-2. Consulta `GET /api/v1/tracking/{guia}`. Si no existe, lo dice sin inventar un estado (404).
- RF-TRK-3. Traduce el estado técnico a lenguaje natural con la fecha estimada y la última ubicación (artifacts `linea_tiempo_envio` y `mapa_ubicacion`). Estados conocidos:

  | Estado | Fuente |
  |---|---|
  | `SOLICITUD_GENERADA`, `RECOGIDO_EN_ORIGEN`, `EN_BODEGA_ORIGEN`, `EN_TRANSITO`, `EN_BODEGA_DESTINO`, `EN_REPARTO`, `ENTREGADO`, `RETENIDO_NOVEDAD` | dataset |
  | `RELECTURA_HUB_FONTIBON` | dosier §4.3 (con un ejemplo de redacción) |
  | `EN_INVESTIGACION_SINIESTRO` | protocolo PQRS §3 |

  Un estado desconocido responde de forma genérica y registra un aviso; no se inventa su significado.
- RF-TRK-4. Protección de datos (D-15): el invitado ve estado, ubicación y fechas. Cédula, teléfono del conductor, NIT y URL de firma solo los ve el titular autenticado o el admin, y siempre enmascarados.
- RF-TRK-5. Si la guía cumple un criterio de escalamiento (p. ej. CRIT-005), se aplica RF-ESC.

### RF-MP: asistente de normativa para cargas especiales
- RF-MP-1. Responde, a partir de los datos del manual cargados en la BD, si un producto está prohibido (§5, 9 categorías), en qué clase ONU cae y con qué modalidad (FTL, LTL o paquetería) y límites se acepta. El veredicto (`permitido`, `restringido`, `solo_ftl`, `prohibido`) es determinista (artifact `veredicto_mercancia`).
- RF-MP-2. Indica los documentos exigidos: MSDS/HDS SGA de 16 secciones, en español y con revisión de menos de 3 años; tarjeta de emergencia NTC 4532; manifiesto o remesa RNDC.
- RF-MP-3. Da las instrucciones de embalaje por categoría (§4 A a D) (artifact `guia_embalaje`).
- RF-MP-4. Si hay duda sobre la clasificación, no afirma: escala por confianza (CRIT-001).
- Aceptación: T-MP-1 a T-MP-3.

### RF-PQRS: radicación de PQRS e indemnizaciones
- RF-PQRS-1. Clasifica la solicitud como P, Q, R o S (protocolo §2).
- RF-PQRS-2. Valida el plazo **en días hábiles con los festivos de Colombia**: avería aparente, al momento de la entrega (anotada en la guía o POD); avería oculta, hasta 3 días hábiles después de la entrega; pérdida, 5 + 10 días hábiles (D-08). Si el plazo venció, informa la presunción del Art. 1028 (T-PQRS-2). Artifact `estado_plazo`.
- RF-PQRS-3. Guía el checklist de documentos (protocolo §4 + D-09) y permite adjuntar PDF o JPEG (≤ 10 MB, tipo verificado por *magic bytes*). Artifact `checklist_documentos`.
- RF-PQRS-4. Crea el ticket con `POST /api/v1/pqrs/crear-ticket` solo con el checklist completo, o lo marca explícitamente como incompleto. Ticket, documentos y escalamiento en una sola transacción; `Idempotency-Key` admitida. Artifact `ticket_pqrs`.
- RF-PQRS-5. Liquidación estimada: `min(valor_declarado, valor_factura)`, menos un deducible del 5 % si el declarado supera $2.000.000; más el 100 % del flete solo si hay pérdida o avería total por negligencia demostrada. Se presenta como estimación sujeta a aprobación (15 días hábiles).
- RF-PQRS-6. Informa las 4 causales de exoneración del protocolo §6 cuando apliquen.
- RF-PQRS-7. Si la reclamación supera $5.000.000, escala (CRIT-003, D-12).

### RF-ESC: escalamiento a humano (HITL)
- RF-ESC-1. Cada respuesta lleva `confianza` entre 0 y 1 (D-13).
- RF-ESC-2. El dominio evalúa en código los 5 criterios de `reglas_escalacion_humana.json`, cargados en la tabla `criterios_escalamiento`:

  | ID | Regla | Acción |
  |---|---|---|
  | CRIT-001 | `confidence_score < 0.75` | `ESCALAR_A_HUMANO` |
  | CRIT-002 | Palabra clave de molestia o petición de humano | `ESCALAR_PRIORIDAD_ALTA` |
  | CRIT-003 | `valor_declarado_cop > 5000000 or valor_reclamacion_cop > 5000000` (solo en el flujo PQRS, D-12) | `ESCALAR_A_DEPARTAMENTO_JURIDICO_Y_PQRS` |
  | CRIT-004 | `envios_mensuales_cuenta > 500 or tipo_cuenta == 'CORPORATIVO_GOLD'` (D-11) | `ESCALAR_A_EJECUTIVO_CUENTA_DEDICADO` |
  | CRIT-005 | `mercancia_peligrosa == true or (requiere_refrigeracion == true and estado == 'RETENIDO_NOVEDAD')` | `ESCALAR_Urgencia_OPERACIONES` |

- RF-ESC-3. Las palabras clave de CRIT-002 se comparan **como palabra o frase completa**, sin importar mayúsculas ni tildes: `sic` no dispara con «básico», «física» o «clásico».
- RF-ESC-4. El mensaje al cliente es el `mensaje_cliente` literal del criterio. Si se cumplen varios, gana el de mayor prioridad: 005 > 002 > 003 > 004 > 001 (D-13). Artifact `aviso_escalamiento` y evento SSE `escalamiento`.
- RF-ESC-5. El payload de transferencia lleva `session_id`, `numero_guia_consultada`, `confidence_score_promedio`, `sentimiento_detectado`, `intentos_previos`, el historial completo y un resumen generado por IA (`flujo_transferencia_pwa`).
- RF-ESC-6. Parámetros generales: inactividad de 5 min (se reofrece asesor o se cierra la sesión, D-13), máximo 2 intentos fallidos de entrega e idioma `es-CO`.
- RF-ESC-7. Si el LLM no está disponible (503 o timeout 504), se escala a humano con un aviso. Nunca queda una respuesta vacía.

### RF-SES: sesiones y contexto
- RF-SES-1. Cada sesión tiene `sesion_id` (uuid) y cada turno, `turno_id`. Se guardan el historial, los artifacts emitidos y los datos ya capturados (p. ej. una cotización a medio llenar).
- RF-SES-2. El contexto enviado al LLM cabe en el slot disponible (RNF-5): el historial antiguo se resume.

### RF-CHAT: chat con artifacts (generative UI) y SSE
- RF-CHAT-1. `POST /api/v1/chat/sesiones` crea la sesión (invitado o autenticado). `POST /api/v1/chat/sesiones/{id}/mensajes` responde por **SSE** (`text/event-stream`) por defecto y con JSON `ChatTurnResponse` con `?stream=false`.
- RF-CHAT-2. Eventos SSE: `meta`, `artifact`, `delta`, `reemplazo`, `citas`, `escalamiento`, `fin` (confianza y latencias por etapa) y `error` (problem+json). El protocolo está en `docs/frontend.md`.
- RF-CHAT-3. Los artifacts son una **unión discriminada por `tipo`**, versionada, con `acciones[]` genéricas (`submit`, `mensaje`, `enlace`), publicada en OpenAPI (`app/schemas/artifacts.py`). Catálogo de cliente: `formulario_cotizacion`, `resultado_cotizacion`, `formulario_guia`, `linea_tiempo_envio`, `mapa_ubicacion`, `veredicto_mercancia`, `guia_embalaje`, `ficha_cobertura`, `formulario_pqrs`, `estado_plazo`, `checklist_documentos`, `ticket_pqrs`, `aviso_escalamiento`, `citas`, `respuestas_rapidas`, `confirmacion`, `encuesta_satisfaccion`.
- RF-CHAT-4. El artifact determinista se emite **antes** que el texto del LLM.
- RF-CHAT-5. Los formularios se envían como `{"tipo": "artifact_submit", "artifact_id", "valores"}` y se **validan en el servidor** contra los campos del artifact emitido (tipo, obligatorio, rango, patrón y opciones). Los errores vuelven como 422 problem+json con `errores[]` por campo.
- RF-CHAT-6. Mensajes de texto: NFC, sin caracteres de control y máximo 2.000 caracteres. El contenido del usuario y de los documentos es dato, nunca instrucción (mitigación de inyección de prompts).
- RF-CHAT-7. `POST /chat/sesiones/{id}/calificacion` registra CSAT 1-5 (artifact `encuesta_satisfaccion`).

### RF-ASE: asesor humano
- RF-ASE-1. `GET /api/v1/asesor/escalamientos?estado=` lista la cola ordenada por prioridad y antigüedad.
- RF-ASE-2. `POST /asesor/escalamientos/{id}/tomar` asigna el caso sin carreras (`SELECT … FOR UPDATE SKIP LOCKED`); un segundo intento responde 409.
- RF-ASE-3. `POST /asesor/sesiones/{id}/mensajes` publica en la sesión del cliente, que lo recibe por `GET /chat/sesiones/{id}/eventos` (SSE).
- RF-ASE-4. `POST /asesor/escalamientos/{id}/resolver` cierra el caso. Todo queda en `auditoria`.

### RF-ADM: administración
- RF-ADM-1. `POST /api/v1/admin/chat` (y SSE) usa el mismo orquestador con **herramientas en lista blanca** y consultas parametrizadas; **no hay texto-a-SQL**. Intenciones: `kpis`, `escalamientos`, `envios_por_estado`, `envios_retenidos`, `pqrs_resumen`, `rendimiento_ia`, `riesgo_retraso`, `pronostico_demanda`, `estado_modelos`, `buscar_conversacion`.
- RF-ADM-2. Artifacts de admin: `tarjetas_kpi`, `grafico`, `tabla_datos`, `tarjeta_prediccion`, `metricas_modelo`, `cola_escalamientos`.
- RF-ADM-3. `GET /admin/metricas?desde=&hasta=`: interacciones, % automatizado, escalamientos por criterio, CSAT y latencias p50/p95, con SQL agregado e índices.
- RF-ADM-4. CRUD de usuarios, consulta de conversaciones, envíos y PQRS, gestión del corpus RAG (`/admin/rag/*`) y del ML (`/admin/ml/*`).

### RF-ML: predicciones autoentrenadas
- RF-ML-1. **Simulador etiquetado** (`origen_dato='simulado'`, semilla fija): ~12 meses de envíos sobre los 25 trayectos y 31 municipios reales; `POST /admin/simulador/avanzar?dias=N` genera envíos nuevos y cierra pendientes. Toda salida se rotula como datos simulados.
- RF-ML-2. Modelo `riesgo_retraso` (probabilidad de superar el SLA): `HistGradientBoostingClassifier` frente a regresión logística de base, partición temporal, ROC-AUC y Brier, factores por perturbación.
- RF-ML-3. Modelo `demanda` (despachos diarios por hub a 14 días): `HistGradientBoostingRegressor` frente a naive estacional, backtest walk-forward, MAE y MASE, intervalos por cuantiles.
- RF-ML-4. Autoentrenamiento: dispara por nuevas etiquetas, deriva o antigüedad (> 24 h); entrena el retador fuera del bucle de eventos y solo lo promueve si mejora la métrica en el mismo holdout (champion/challenger). Cada corrida queda en `ml_entrenamientos` con su motivo.

### RF-VOZ: canal de voz (fuera del alcance actual)
- Punto de integración futuro: el gateway de voz del clúster entregará el texto transcrito al mismo orquestador, sin lógica de negocio duplicada.

## 6. Requisitos no funcionales

| ID | Requisito |
|---|---|
| RNF-1 | Solo español de Colombia (`es-CO`) en las respuestas. |
| RNF-2 | El LLM y los embeddings corren en el equipo local. Ningún dato de la conversación va a APIs externas (Ley 1581 de 2012). |
| RNF-3 | Las respuestas se sustentan en el corpus o en el resultado de una herramienta. Si no hay sustento, se escala (CRIT-001); no se inventa. El verificador reemplaza cualquier texto que contradiga el contexto. |
| RNF-4 | **Latencia:** primer artifact en < 300 ms en la ruta rápida (enrutador determinista). Se miden y reportan p50 y p95 por etapa (`router`, `tool`, `retrieval`, `llm_first_token`, `llm_total`, `verify`, `total`) con 1, 4 y 8 conversaciones concurrentes (`tests/load.py`). LLM sin razonamiento (`enable_thinking=false`). |
| RNF-5 | Presupuesto de contexto por conversación ≤ 8.192 tokens (slot de llama.cpp con `-c 65536 -np 8`). Recalcularlo si cambian `-c` o `-np`. |
| RNF-6 | Concurrencia: hasta `NP` conversaciones generando a la vez (hoy 8). El excedente espera en la cola de HAProxy. |
| RNF-7 | Seguridad: JWT de acceso de 15 min + refresh rotado y guardado como hash; argon2; rate limit por IP y usuario; CORS con lista blanca; cabeceras de seguridad; errores RFC 9457 sin stack trace. La API key del LLM se lee del archivo indicado en `LLM_API_KEY_FILE` y no se versiona. |
| RNF-8 | Logs JSON con `request_id`, `sesion_id`, `turno_id`, intención, criterio de escalamiento y latencia por etapa. Sin cédulas, teléfonos, NIT ni adjuntos. |
| RNF-9 | Versiones fijadas (Python 3.13 con `uv`, `uv.lock` versionado, modelos y cuantización documentados). |
| RNF-10 | Datos de negocio (tarifas, cobertura, reglas, clases ONU) en la BD, cargados desde `KODOTAKAIINFO/`; no en el código ni en el prompt. |
| RNF-11 | Integridad: 3FN, FKs, `CHECK`, enums nativos, `numeric(14,2)` para dinero, migraciones Alembic, transacciones y `SKIP LOCKED` donde hay concurrencia. |

## 7. Contratos de la API e infraestructura

### 7.1 Contratos principales

Todo bajo `/api/v1`, documentado en Swagger (`/docs`) y exportado a `docs/openapi.json`. Las 3 rutas del dosier se mantienen literales.

| Método y ruta | Entrada | Salida |
|---|---|---|
| `GET /api/v1/tracking/{guia}` | guía `TLX-\d{6}-CO` | Guía con datos personales filtrados según rol (RF-TRK-4); 404 si no existe |
| `POST /api/v1/cotizar` | origen, destino, alto, ancho, largo, peso_kg, valor_declarado_cop, servicio | Desglose RF-COT-6, o 422 con el motivo (sin trayecto, sin cobertura, sobrepeso, prohibido) |
| `POST /api/v1/pqrs/crear-ticket` | tipo P/Q/R/S, guía, descripción, valor reclamado, novedad, estado del checklist | Radicado, fecha límite de respuesta (15 días hábiles) y escalamiento si aplica |

La lista completa de endpoints por rol está en `docs/frontend.md`.

### 7.2 Infraestructura

| Componente | Dónde | Nota |
|---|---|---|
| API FastAPI | `127.0.0.1:8100` | Swagger `/docs`, ReDoc `/redoc`, cliente de referencia `/demo` |
| PostgreSQL 17 + pgvector | `127.0.0.1:5433`, contenedor Docker propio (`pgvector/pgvector:pg17`) con volumen nombrado | El 5432 lo ocupa otro contenedor ajeno al proyecto (D-16) |
| Embeddings `bge-m3` | Ollama `127.0.0.1:11434`, en **CPU** | 1024 dimensiones, multilingüe, MIT; caché LRU de consultas (D-17) |
| LLM LFM3-1.7B Q4_K_M | HAProxy `127.0.0.1:8000/v1` → llama.cpp | Sin razonamiento; extracción con `response_format` + `json_schema`; LFM3 no emite `tool_calls` |
| GPU | RTX 3050 Laptop 6 GB | Compartida con el clúster de voz; los embeddings no consumen VRAM |
| Puertos reservados por el clúster de voz | 8081, 8082, 8083, 8090 | No se usan |

Mediciones de referencia (2026-11-03, LFM3 directo): con razonamiento 3,77 s; sin razonamiento 0,58 s; `json_schema` de intención 0,39 s; ~110 tokens/s. Sin RAG, «¿Puedo enviar un perro?» alucina «sí»: de ahí las reglas en código, el RAG con citas y el verificador.

Todos los servicios escuchan solo en loopback. Exponer la API a la LAN para el frontend es una decisión pendiente del usuario (D-18).

## 8. Casos de prueba de referencia (golden set)

Valores calculados desde los archivos fuente. Donde el resultado depende de una decisión, se indica cuál.

### Cotización (T-COT)

| ID | Entrada | Peso facturable | Resultado esperado |
|---|---|---|---|
| T-COT-1 | Bogotá→Medellín (TLX-BOG-MED-001), 40×50×60 cm, 45,5 kg, VD $12.500.000, cadena de frío (guía TLX-984021-CO) | vol. 30 → **45,5 kg (real)** | Flete base 45,5 × $1.450 = $65.975 + seguro $125.000 = **$190.975**. Con recargo de frío del 25 % sobre el flete base: **$207.468,75** (D-03) |
| T-COT-2 | Bogotá→Pereira (TLX-BOG-PEI-006), dimensiones de la guía TLX-551904-CO, 3,2 kg, VD $450.000 | vol. 6 → **6 kg (vol.)** | Flete base 6 × $1.580 (tarifa vol., D-02) = $9.480, por debajo del mínimo de $18.000 (D-03). Seguro $4.500. Total **$13.980** sin mínimo y **$22.500** con mínimo |
| T-COT-3 | Bogotá→Barranquilla, 30×30×30 cm, 2 kg, VD $200.000 | vol. 6,75 kg | Seguro 1 % = $2.000, así que aplica el mínimo: **$2.500** (dosier) o **$4.000** (CSV), según D-01 |
| T-COT-4 | Medellín→Cali (TLX-MED-CLO-012), 180×220×400 cm, 3.200 kg, VD $85.000.000 (TLX-752190-CO) | vol. **3.960 kg** (igual al dataset) | Seguro $850.000. Flete base 3.960 × $1.700 = $6.732.000 (D-02) |
| T-COT-5 | Barranquilla→Bucaramanga o Villavicencio→Florencia | — | **No hay trayecto en la matriz**: no cotiza, lo informa y ofrece un asesor (D-04) |
| T-COT-6 | Paquetería exprés de 60 kg | — | Rechaza la modalidad o sugiere carga (límite de 50 kg) |

### Rastreo y escalamiento (T-TRK)

| ID | Guía | Ruta / estado | Esperado |
|---|---|---|---|
| T-TRK-1 | TLX-984021-CO | BOG→MED, `EN_TRANSITO`, frío 2-8 °C | Explica el tránsito por el Alto de La Línea y la llegada estimada. CRIT-003 solo con D-12 literal |
| T-TRK-2 | TLX-752190-CO | MED→CLO, `ENTREGADO` | Confirma la entrega sin mostrar la cédula de quien recibió (RF-TRK-4) |
| T-TRK-3 | TLX-310482-CO | BAQ→BGA, `RETENIDO_NOVEDAD`, Clase 3 | Explica la retención de la POLFA y **escala por CRIT-005** |
| T-TRK-4 | TLX-551904-CO | BOG→PEI, `EN_REPARTO` | Informa que va en reparto. Mostrar o no el teléfono del conductor depende de D-15. No escala |
| T-TRK-5 | TLX-118493-CO | VVC→FLA (ZOMAC), `EN_BODEGA_ORIGEN` | Explica el despacho semanal del jueves. CRIT-003 solo con D-12 literal |
| T-TRK-6 | TLX-000000-CO | inexistente | «No encontramos la guía» sin inventar estado |

### Normativa, PQRS y escalamiento (T-MP, T-PQRS, T-ESC)

| ID | Entrada | Esperado |
|---|---|---|
| T-MP-1 | «¿Puedo enviar 5 litros de ácido clorhídrico de Bogotá a Cali?» | Respuesta equivalente a la del manual §6: Clase 8, límite de 5 L, embalaje, MSDS y NTC 4532 |
| T-MP-2 | «¿Puedo enviar un perro o gato de Bogotá a Medellín?» | No: animales vivos prohibidos (manual §5.5) |
| T-MP-3 | «Quiero enviar pólvora» / «dinero en efectivo» | Prohibido, sin cotizar |
| T-PQRS-1 | «Me llegó una caja aplastada y el producto adentro está roto» | Respuesta del protocolo §7, caso 1: anotación en la guía, 3 días hábiles y checklist |
| T-PQRS-2 | «Hace un mes me entregaron… falta la mitad» | Plazo vencido y presunción del Art. 1028 (protocolo §7, caso 2) |
| T-PQRS-3 | Reclamación de $6.000.000 | Escala por CRIT-003 |
| T-PQRS-4 | Indemnización con VD $3.000.000 y factura de $2.800.000 | Base min = $2.800.000 − deducible 5 % = **$2.660.000** |
| T-ESC-1 | «Esto es una estafa, voy a demandar» | CRIT-002, prioridad alta |
| T-ESC-2 | «Necesito un servicio básico de envío» | **No** escala (`sic` dentro de «básico») |
| T-ESC-3 | Pregunta sin respaldo en el corpus | `confidence_score < 0.75` → CRIT-001 |

T-RAG (recuperación): a definir con D-14, con al menos una consulta por documento y por `tipo`.

## 9. Decisiones

Todas adoptadas el 2026-11-03 con la propuesta original salvo que se indique.

| ID | Tema | Fuente A | Fuente B | Decisión | Estado |
|---|---|---|---|---|---|
| D-01 | Seguro mínimo | Dosier: $2.500 | CSV `seguro_minimo_cop`: $3.000 a $5.000 por ruta | Usar el CSV (dato por ruta, más específico) | Adoptada |
| D-02 | Tarifa cuando se factura por volumen | Dosier: un solo «flete base» | CSV: `tarifa_base_kg_real_cop` y `tarifa_base_kg_volumetrico_cop` | Tarifa real si gana el peso real; volumétrica si gana el volumen | Adoptada |
| D-03 | Mínimo y recargos | Dosier: no los menciona | CSV: `flete_minimo_cop`, `recargo_cadena_frio_pct`, `recargo_mercancia_peligrosa_cop` | `max(flete_base, flete_minimo)`, recargo de frío en % sobre el flete base y el de MP como suma fija | Adoptada |
| D-04 | Municipios sin trayecto | Directorio: 31 municipios | Matriz: no cubre Armenia, Bello, Dosquebradas, Envigado, Floridablanca, Girón, Itagüí, Palmira, Rionegro, Soledad ni Yumbo, ni BAQ→BGA ni VVC→FLA | No cotizar y ofrecer asesor | Adoptada |
| D-05 | Same Day a Santa Marta | CSV (BAQ-SMR): «Same Day disponible» | Directorio: `servicio_same_day_disponible: false` | El directorio manda (nivel municipio) | Adoptada |
| D-06 | Frío a zonas sin refrigerado | CSV: recargo de frío hacia Quibdó, Florencia e Ipiales | Directorio: `servicio_refrigerado_disponible: false` | Rechazar cadena de frío a esos destinos | Adoptada |
| D-07 | Nombre de cobertura | CSV: «Zona ZOMAC» | Directorio: «Zona ZOMAC / Difícil Acceso» | Normalizar a un mismo valor de metadato `zona` | Adoptada |
| D-08 | Plazo por pérdida total | Protocolo §3 (árbol): 10 días hábiles tras vencer la entrega | Protocolo §3 (texto): 5 días hábiles → `EN_INVESTIGACION_SINIESTRO`, luego 10 más | Usar el texto: 5 + 10 | Adoptada |
| D-09 | Documentos de indemnización | Dosier §3: guía, factura con IVA, fotos y acta con salvedad | Protocolo §4: guía, factura, carta con certificación bancaria, fotos y cédula/RUT | Checklist del protocolo + acta con salvedad cuando la avería es aparente | Adoptada |
| D-10 | Límite de corrosivos | Manual §2, clase 8: envases ≤ 5 L | Manual §6: «máximo de 5 litros por caja» | Envases ≤ 5 L (regla normativa) | Adoptada |
| D-11 | Cuenta VIP | Dosier: «Key Account / VIP» | JSON: `envios_mensuales_cuenta > 500 or tipo_cuenta == 'CORPORATIVO_GOLD'`; ningún dataset trae esos campos | Tabla `cuentas` asociada por NIT del remitente; PharmaSur como `CORPORATIVO_GOLD` | Adoptada |
| D-12 | Alcance de CRIT-003 | Dosier: «reclamaciones o PQRS con VD > $5M» | JSON literal: cualquier `valor_declarado_cop > 5000000` | Aplicarlo solo en el flujo PQRS | Adoptada |
| D-13 | Confianza, prioridad e inactividad | El dosier exige el puntaje | Ninguna fuente define cálculo, orden ni acción tras 5 min | Confianza = combinación de puntuación de recuperación, resultado del verificador y certeza del enrutador. Prioridad 005 > 002 > 003 > 004 > 001. Inactividad: reofrecer asesor y cerrar la sesión | Adoptada |
| D-14 | Evaluación RAG | — | — | k = 4; set T-RAG de ≥ 20 consultas (al menos una por documento y por `tipo`) con meta recall@4 ≥ 0,9 | Adoptada |
| D-15 | Datos personales en rastreo | El dataset expone cédula, teléfono, NIT y firma | — | Invitado: solo estado, ubicación y fechas. Titular autenticado o admin: detalle enmascarado | Adoptada |
| D-16 | Base vectorial | Dosier: «Vector Database» | El Postgres de 5432 es de otro proyecto | Contenedor propio `pgvector/pgvector:pg17` en `127.0.0.1:5433` con volumen nombrado | Adoptada |
| D-17 | Modelo de embeddings | — | Poca VRAM; Ollama ya corre | `bge-m3` vía Ollama en CPU; se prueba GPU solo si p50 > 150 ms por consulta | Adoptada |
| D-18 | Exposición para el frontend | Todo escucha en loopback | El frontend de otro grupo necesita alcanzar la API | Solo loopback por ahora; puerto, LAN o túnel **pendiente de decisión del usuario** | Adoptada (parcial) |
| D-19 | Lenguaje del backend | Dosier: Node.js, Python o Go | El gateway de voz del clúster es Python/FastAPI | Python 3.13 + FastAPI | Adoptada |
| D-20 | Licencias de modelos | LFM3, bge-m3 y modelos del clúster | — | Se resumen en el README; el uso comercial lo decide el usuario | Adoptada |

## 10. Fuera de alcance
- Frontend final: lo construye otro grupo. Este repositorio entrega el contrato (`docs/openapi.json`, `docs/frontend.md`) y un cliente mínimo de referencia en `/demo`.
- Integraciones reales con WhatsApp Business API, PBX, TMS, CRM o WMS: se usan mocks a partir de `KODOTAKAIINFO/`.
- Despliegue en producción, nube o pagos.
- Entrenar o ajustar el LLM. «Entrenado localmente» se entiende como RAG sobre un modelo local; el autoentrenamiento aplica a los modelos de ML tabulares (RF-ML).
- Canal de voz (RF-VOZ) y cambios en el clúster `~/llm-cluster`.

## 11. Modelo de datos (resumen)

| Dominio | Tablas |
|---|---|
| Catálogo | `departamentos`, `municipios`, `hubs`, `trayectos`, `estados_envio`, `festivos` |
| Cuentas | `cuentas`, `usuarios`, `refresh_tokens` |
| Envíos | `envios` (columnas generadas de peso volumétrico y facturable), `eventos_envio`, `pruebas_entrega` |
| Cotizaciones | `cotizaciones` |
| PQRS | `pqrs_tickets`, `pqrs_documentos` |
| Mercancías | `clases_onu`, `articulos_prohibidos` |
| Chat | `sesiones_chat`, `mensajes`, `criterios_escalamiento`, `escalamientos`, `calificaciones` |
| RAG | `documentos`, `chunks` (`vector(1024)` con HNSW, `tsvector` en español con GIN) |
| ML | `ml_modelos`, `ml_entrenamientos`, `ml_predicciones` |
| Auditoría | `auditoria` |

El diagrama ER (mermaid) está en `README.md`.

## 12. Mapa de rúbrica

### Rúbrica técnica de back-end (60 pts; 4 criterios de 15)

| Criterio | Peso | Requisitos y evidencia |
|---|---|---|
| 1. Tiempo de respuesta, rendimiento de IA local y latencia | 30 % | RNF-4 (p50/p95 por etapa, primer artifact < 300 ms), LLM sin razonamiento, enrutador determinista, `json_schema`, SSE, cachés; cero alucinaciones: RNF-3, verificador, RF-RAG con citas, RF-ESC (CRIT-001) |
| 2. Funcionalidad, endpoints y lógica de negocio | 25 % | RF-COT, RF-TRK, RF-MP, RF-PQRS, RF-ESC, RF-CHAT, RF-ASE, RF-ADM; rutas del dosier literales (§7); golden set §8 |
| 3. Validación de datos, seguridad y manejo de errores | 25 % | RNF-7, RNF-8, RF-CHAT-5/6, §4 (RBAC y propiedad), RFC 9457 con códigos semánticos, uploads por *magic bytes* |
| 4. Diseño de base de datos e integridad | 20 % | RNF-11, §11, Alembic, transacciones, `SKIP LOCKED`, índices btree/GIN/HNSW |

### Rúbrica de Mejor Proyecto (60 pts; 6 criterios de 10)

| Criterio | Cómo se cubre |
|---|---|
| 1. Funcionalidad e integración IA | RF-RAG, RF-CHAT, RF-ADM, RF-ML; IA 100 % local |
| 2. Experiencia de usuario (UI/UX) | Contrato de artifacts para el grupo de frontend (`docs/frontend.md`) y `/demo` |
| 3. Innovación y creatividad | Generative UI, verificador anti-alucinación, ML autoentrenado (`docs/negocio.md`) |
| 4. Viabilidad de negocio y potencial | `docs/negocio.md`: costo por interacción, SaaS por niveles, escalabilidad |
| 5. Sustentación (pitch) | Guion de 5 min en `docs/negocio.md` |
| 6. Preguntas del jurado | Preguntas probables y respuestas en `docs/negocio.md` |
