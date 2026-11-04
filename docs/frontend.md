# Guía para el frontend: API TransLogix

Esta guía es para el grupo que construye el frontend. El backend expone una API REST + SSE; el contrato exacto (esquemas, ejemplos y códigos de error de cada endpoint) está en **`docs/openapi.json`**, que manda sobre esta guía si algo difiere.

- Swagger (probar endpoints con el botón *Authorize*): http://127.0.0.1:8100/docs
- ReDoc: http://127.0.0.1:8100/redoc
- Cliente de referencia mínimo (no es el frontend final): http://127.0.0.1:8100/demo

## 1. Arquitectura en una página

```
Frontend ──HTTP JSON──► /api/v1/*            REST: auth, rastreo, cotización, catálogos, PQRS, asesor, admin
         ──HTTP + SSE─► /api/v1/chat/...     chat: el servidor emite artifacts (UI) + texto en streaming
```

Idea central: **generative UI**. El chat no devuelve solo texto: devuelve *artifacts*, objetos JSON tipados (formulario de cotización, línea de tiempo de una guía, veredicto de mercancía…) que el frontend pinta como componentes. Todas las cifras y veredictos salen de código determinista; el LLM local solo redacta el texto que acompaña. El artifact llega **antes** que el texto.

Convenciones:

| Tema | Regla |
|---|---|
| Base | Todo bajo `/api/v1`. JSON UTF-8 |
| Dinero | COP como **string decimal**: `"190975"`, `"207468.75"`. No usar `parseFloat` para sumar; para mostrar: `new Intl.NumberFormat('es-CO', {style:'currency', currency:'COP'}).format(Number(v))` |
| Otros decimales | Pesos, probabilidades y métricas también llegan como string decimal (`"45.5"`). Latencias, coordenadas y puntuaciones de cita son `number` |
| Fechas | ISO 8601 con zona `-05:00` (`2026-11-03T16:00:00-05:00`) o fecha sola (`2026-11-05`) |
| Guías | `TLX-######-CO` (regex `^TLX-\d{6}-CO$`) |
| Idioma | Español de Colombia |
| Datos simulados | Los artifacts de ML traen `datos_simulados: true`: mostrarlo siempre |

## 2. Autenticación y roles

- `POST /api/v1/auth/login` → `access_token` (JWT, **15 min**) + `refresh_token`.
- Enviar `Authorization: Bearer <access_token>` en cada petición.
- Ante un 401 por expiración: `POST /api/v1/auth/refresh` con el refresh token. **El refresh rota**: cada uso devuelve un par nuevo y el anterior queda inválido; guarda siempre el último. Si el refresh falla con 401, volver al login.
- `POST /api/v1/auth/logout` revoca el refresh. `GET /api/v1/auth/me` devuelve usuario y rol.
- Guarda el access token en memoria; el refresh, donde vuestra política de seguridad lo permita (evitad `localStorage` si podéis).

| Rol | Cómo | Ve |
|---|---|---|
| `invitado` | Sin token | Chat, rastreo público, cotizar, cobertura, mercancías |
| `cliente` | Registro / login | + sus PQRS, sus sesiones y el detalle de sus guías (datos personales enmascarados) |
| `asesor` | Creado por admin | + cola de escalamientos y respuesta en sesiones escaladas |
| `admin` | Usuario semilla | Todo, incluido chat administrativo, métricas, RAG y ML |

Cliente corporativo / VIP no es un rol: es un atributo de la cuenta (`CORPORATIVO`, `CORPORATIVO_GOLD`) que puede escalar el chat a un ejecutivo (CRIT-004).

Un recurso ajeno responde **404** (no 403) para no revelar que existe.

## 3. Endpoints por rol

| Grupo | Endpoints | Rol mínimo |
|---|---|---|
| Auth | `POST /auth/registro`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` | público / autenticado |
| Chat | `POST /chat/sesiones`, `POST /chat/sesiones/{id}/mensajes` (SSE; `?stream=false` → JSON), `GET /chat/sesiones/{id}`, `GET /chat/sesiones/{id}/eventos` (SSE del asesor), `POST /chat/sesiones/{id}/calificacion` | invitado (dueño de la sesión) |
| Rastreo | `GET /tracking/{guia}` | invitado (vista pública); dueño o admin (detalle) |
| Cotización | `POST /cotizar` (admite `Idempotency-Key`), `GET /cotizaciones/{id}` | invitado |
| Catálogos | `GET /cobertura/municipios?q=&page=`, `GET /cobertura/municipios/{dane}`, `GET /trayectos/origenes`, `GET /trayectos/destinos?origen=` | invitado |
| Mercancías | `GET /mercancias/consultar?producto=`, `GET /mercancias/clases` | invitado |
| PQRS | `POST /pqrs/crear-ticket` (admite `Idempotency-Key`), `GET /pqrs/{radicado}`, `POST /pqrs/{radicado}/documentos` (multipart), `GET /pqrs/plazo?guia=&tipo=`, `POST /pqrs/liquidacion-estimada` | cliente (dueño) |
| Asesor | `GET /asesor/escalamientos?estado=`, `POST /asesor/escalamientos/{id}/tomar`, `GET /asesor/sesiones/{id}`, `GET /asesor/sesiones/{id}/eventos` (SSE), `POST /asesor/sesiones/{id}/mensajes`, `POST /asesor/escalamientos/{id}/resolver` | asesor |
| Admin | `/admin/usuarios` (CRUD), `GET /admin/metricas?desde=&hasta=`, `/admin/conversaciones`, `/admin/envios`, `/admin/pqrs`, `/admin/rag/*`, `/admin/ml/*` (incluye `GET /admin/ml/estado`: reglas y medición del autoentrenamiento), `POST /admin/simulador/avanzar?dias=`, `POST /admin/chat` (mismo protocolo SSE que el chat) | admin |

Todas las rutas van con el prefijo `/api/v1`. Salud: `GET /health` y `GET /health/ready` (sin prefijo).

## 4. Chat: flujo y protocolo SSE

### 4.1 Flujo

1. `POST /api/v1/chat/sesiones` → `{ "id": "<uuid>", ... }`. Con token, la sesión queda asociada al usuario.
2. Por cada mensaje: `POST /api/v1/chat/sesiones/{id}/mensajes` con `Accept: text/event-stream` y uno de estos cuerpos:

```json
{ "tipo": "texto", "texto": "¿Dónde está la TLX-984021-CO?" }
```

```json
{
  "tipo": "artifact_submit",
  "artifact_id": "art-cot-01",
  "valores": {
    "origen": "Bogotá D.C.", "destino": "Medellín",
    "alto_cm": 40, "ancho_cm": 50, "largo_cm": 60,
    "peso_kg": 45.5, "valor_declarado_cop": 12500000, "servicio": "paqueteria"
  }
}
```

   - `texto`: 1 a 2.000 caracteres.
   - `artifact_submit`: `artifact_id` es el `id` del formulario recibido; `valores` lleva una clave por `campo.nombre`. Números como number o string; fechas `AAAA-MM-DD`; booleanos `true/false`; `seleccion` con un `opcion.valor`; `archivo` con el id devuelto por la carga.
   - El servidor valida contra el formulario que él emitió. Si hay errores responde **422** `application/problem+json` con `errores: [{campo, mensaje, tipo}]` (antes de abrir el stream): pinta cada mensaje junto a su campo.
3. Leer el stream hasta el evento `fin` (o `error`).

Sin streaming: `?stream=false` devuelve un `ChatTurnResponse` con lo mismo que los eventos (artifacts, texto final, citas, escalamiento, confianza y latencias).

### 4.2 Formato de cable

`Content-Type: text/event-stream`. Cada evento es:

```text
event: <nombre>
data: <JSON en una línea>
<línea en blanco>
```

Las líneas que empiezan por `:` son comentarios de keep-alive: ignóralas.

| Evento | `data` | Qué hacer |
|---|---|---|
| `meta` | `{turno_id, sesion_id, intencion, confianza_enrutador?}` | Abrir la burbuja del turno |
| `artifact` | `{artifact: Artifact}` | Pintar el componente según `artifact.tipo`. Puede haber varios por turno |
| `delta` | `{texto}` | Concatenar al texto de la burbuja |
| `reemplazo` | `{texto, motivo}` | **Sustituir** todo el texto emitido en el turno por `texto` (el verificador detectó una contradicción) |
| `citas` | `{citas: [Cita]}` | Fuentes del texto |
| `escalamiento` | `{escalamiento_id, criterio, prioridad, mensaje, espera_estimada_s}` | Mostrar aviso y abrir `GET /chat/sesiones/{id}/eventos` |
| `fin` | `{turno_id, confianza, latencias_ms}` | Cerrar el turno; habilitar el input |
| `error` | problem+json (`type, title, status, detail, codigo, request_id`) | Mostrar `title`/`detail`; el turno termina |

Orden típico: `meta` → `artifact`* → `delta`* → (`reemplazo`) → (`citas`) → (`escalamiento`) → `fin`. Si el turno escala por palabra clave (CRIT-002) puede no haber `delta`.

`latencias_ms` trae milisegundos por etapa (`router`, `tool`, `retrieval`, `llm_first_token`, `llm_total`, `verify`, `total`); las etapas que no se ejecutaron no aparecen.

### 4.3 Leer el stream con `fetch`

`EventSource` no sirve: el mensaje es `POST` y lleva cabecera `Authorization`. Usa `fetch` + `ReadableStream`:

```js
async function enviar(sesionId, cuerpo, token, onEvento) {
  const r = await fetch(`/api/v1/chat/sesiones/${sesionId}/mensajes`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream",
               ...(token && { Authorization: `Bearer ${token}` }) },
    body: JSON.stringify(cuerpo),
  });
  if (!r.ok) throw await r.json();               // problem+json (422, 429, 503…)
  const lector = r.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  for (;;) {
    const { value, done } = await lector.read();
    if (done) break;
    buf += value;
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const bloque = buf.slice(0, i); buf = buf.slice(i + 2);
      let evento = "message", data = "";
      for (const linea of bloque.split("\n")) {
        if (linea.startsWith(":")) continue;
        if (linea.startsWith("event:")) evento = linea.slice(6).trim();
        else if (linea.startsWith("data:")) data += linea.slice(5).trim();
      }
      if (data) onEvento(evento, JSON.parse(data));
    }
  }
}
```

### 4.4 Cortes y reconexión

- **Turno (`POST …/mensajes`)**: no reenvíes el mensaje si la conexión se corta (duplicarías el turno). Haz `GET /api/v1/chat/sesiones/{id}`: devuelve el historial persistido con los artifacts y el texto final de cada turno; reconcilia por `turno_id`.
- **Eventos del asesor (`GET …/eventos`)**: también con `fetch` (lleva token). Si se corta, reintenta con espera exponencial (1 s, 2 s, 4 s… máx. 30 s) y, al reconectar, consulta `GET /chat/sesiones/{id}` para recuperar lo que llegó mientras tanto.
- **Eventos del lado del asesor (`GET /asesor/sesiones/{id}/eventos`)**: además de `mensaje_asesor` y `escalamiento_resuelto` entrega `mensaje_cliente`. Mismo criterio de reconexión; al reconectar, `GET /asesor/sesiones/{id}`.
- **Mientras la sesión está escalada**, cada `POST …/mensajes` del cliente responde `meta` con `intencion: "asesor_humano"`: es un acuse de que llegó al asesor, no una respuesta de la IA.
- **429** trae `Retry-After` (segundos). **503/504** (LLM caído o lento) también; el backend escala a humano en ese caso y nunca deja la respuesta vacía.

### 4.5 Ejemplo completo: «quiero cotizar»

Petición:

```http
POST /api/v1/chat/sesiones/3f6c0a52-8e1b-4d7a-9c2e-5b1d0f9a7e41/mensajes
Content-Type: application/json
Accept: text/event-stream

{"tipo": "texto", "texto": "quiero cotizar"}
```

Respuesta (cable SSE):

```text
event: meta
data: {"turno_id":"t-0001","sesion_id":"3f6c0a52-8e1b-4d7a-9c2e-5b1d0f9a7e41","intencion":"cotizar","confianza_enrutador":1.0}

event: artifact
data: {"artifact":{"id":"art-cot-01","version":1,"titulo":"Cotiza tu envío","acciones":[{"id":"enviar","etiqueta":"Cotizar","tipo":"submit","metodo":"POST","endpoint":"/api/v1/chat/sesiones/3f6c0a52-8e1b-4d7a-9c2e-5b1d0f9a7e41/mensajes","estilo":"primario"}],"campos":[{"nombre":"origen","etiqueta":"Ciudad de origen","tipo":"seleccion","requerido":true,"opciones":[{"valor":"Bogotá D.C.","etiqueta":"Bogotá D.C."}],"valor":"Bogotá D.C."},{"nombre":"destino","etiqueta":"Ciudad de destino","tipo":"seleccion","requerido":true,"opciones":[{"valor":"Medellín","etiqueta":"Medellín"},{"valor":"Cali","etiqueta":"Cali"}],"valor":"Medellín"},{"nombre":"alto_cm","etiqueta":"Alto","tipo":"numero","requerido":true,"min":"1","max":"400","opciones":[],"unidad":"cm"},{"nombre":"ancho_cm","etiqueta":"Ancho","tipo":"numero","requerido":true,"min":"1","max":"400","opciones":[],"unidad":"cm"},{"nombre":"largo_cm","etiqueta":"Largo","tipo":"numero","requerido":true,"min":"1","max":"1400","opciones":[],"unidad":"cm"},{"nombre":"peso_kg","etiqueta":"Peso real","tipo":"numero","requerido":true,"min":"0.1","max":"2500","opciones":[],"unidad":"kg"},{"nombre":"valor_declarado_cop","etiqueta":"Valor declarado","tipo":"moneda","requerido":true,"min":"0","max":"1000000000","opciones":[],"unidad":"COP"},{"nombre":"servicio","etiqueta":"Tipo de servicio","tipo":"seleccion","requerido":true,"opciones":[{"valor":"paqueteria","etiqueta":"Paquetería exprés (hasta 50 kg)"},{"valor":"carga","etiqueta":"Carga (LTL / FTL)"},{"valor":"cadena_frio","etiqueta":"Cadena de frío"},{"valor":"mercancia_peligrosa","etiqueta":"Mercancía peligrosa"}],"valor":"paqueteria"}],"tipo":"formulario_cotizacion"}}

event: delta
data: {"texto":"¡Claro! Completa los datos del envío "}

event: delta
data: {"texto":"y te doy el valor exacto."}

event: fin
data: {"turno_id":"t-0001","confianza":0.95,"latencias_ms":{"router":0.8,"tool":6.1,"llm_first_token":180.4,"llm_total":402.7,"verify":0.9,"total":415.2}}
```

El usuario llena el formulario y el frontend envía el `artifact_submit` de §4.1. El servidor responde otro turno con `meta` (intencion `cotizar`), un `artifact` `resultado_cotizacion` (total `"190975"` para Bogotá→Medellín, 40×50×60 cm, 45,5 kg, valor declarado $12.500.000 en paquetería; con cadena de frío se suma el recargo del 25 % sobre el flete base y el total es `"207468.75"`), el texto y `fin`.

### 4.6 Ejemplo completo: «TLX-984021-CO»

```http
POST /api/v1/chat/sesiones/3f6c0a52-8e1b-4d7a-9c2e-5b1d0f9a7e41/mensajes
Content-Type: application/json
Accept: text/event-stream

{"tipo": "texto", "texto": "TLX-984021-CO"}
```

```text
event: meta
data: {"turno_id":"t-0002","sesion_id":"3f6c0a52-8e1b-4d7a-9c2e-5b1d0f9a7e41","intencion":"rastrear","confianza_enrutador":1.0}

event: artifact
data: {"artifact":{"id":"art-trk-01","version":1,"titulo":"Guía TLX-984021-CO","acciones":[],"tipo":"linea_tiempo_envio","guia":"TLX-984021-CO","origen":"Bogotá D.C.","destino":"Medellín","servicio":"Transporte Cadena de Frío (2°C a 8°C)","estado_actual":"EN_TRANSITO","estado_texto":"En camino a la ciudad de destino","progreso_pct":60,"eta":"2026-11-03T16:00:00-05:00","eventos":[{"ts":"2026-11-02T11:15:00-05:00","estado":"SOLICITUD_GENERADA","estado_texto":"Guía generada","ubicacion":"Portal Web Clientes TransLogix","descripcion":"Orden de despacho creada y guía generada exitosamente."},{"ts":"2026-11-03T08:30:00-05:00","estado":"EN_TRANSITO","estado_texto":"En camino a la ciudad de destino","ubicacion":"Corredor Calarcá - Pereira","descripcion":"Vehículo en ruta regular. Arribo estimado a Hub Itagüí a las 12:30 PM."}]}}

event: artifact
data: {"artifact":{"id":"art-trk-02","version":1,"acciones":[],"tipo":"mapa_ubicacion","guia":"TLX-984021-CO","latitud":5.06889,"longitud":-75.51738,"referencia":"Paso de Montaña Alto de la Línea - Sentido Bogotá-Ibague-Medellín","actualizado":"2026-11-03T08:30:00-05:00"}}

event: delta
data: {"texto":"Tu envío TLX-984021-CO va en tránsito por el corredor Calarcá - Pereira "}

event: delta
data: {"texto":"y la entrega estimada es hoy, 3 de noviembre, hacia las 4:00 p. m."}

event: fin
data: {"turno_id":"t-0002","confianza":0.93,"latencias_ms":{"router":1.1,"tool":12.6,"llm_first_token":205.3,"llm_total":590.8,"verify":1.2,"total":612.4}}
```

### 4.7 Otros eventos de ejemplo

```text
event: reemplazo
data: {"texto":"Según el manual de TransLogix, los animales vivos están prohibidos.","motivo":"polaridad_contradice_veredicto"}

event: citas
data: {"citas":[{"doc_codigo":"DOC-PQRS-2026-04","documento":"Protocolo de PQRS e indemnizaciones","seccion":"3. Tiempos y plazos legales de radicación","puntuacion":0.88}]}

event: escalamiento
data: {"escalamiento_id":"b7c1d2e3-4f50-4a6b-8c7d-9e0f1a2b3c4d","criterio":"CRIT-002","prioridad":"alta","mensaje":"Lamento profundamente la molestia ocasionada. Estoy transfiriendo tu chat de inmediato a un supervisor de servicio al cliente para resolver tu situación.","espera_estimada_s":45}
```

## 4.1 Voz (opcional)
La voz no tiene un chat propio: el audio se convierte en texto y ese texto se envía al mismo chat de la sección 4.
- `POST /api/v1/voz/transcribir`: multipart con el campo `audio` (wav, mp3, ogg o el webm/opus de `MediaRecorder`). Responde `{"texto": "..."}`; ese texto va a `POST /chat/sesiones/{id}/mensajes` como `{"tipo":"texto"}`.
- `POST /api/v1/voz/sintetizar`: `{"texto": "frase", "voz": "female" | "male"}` → `audio/wav` (mono, 24 kHz).
- Errores: `413` si el audio supera el tamaño máximo, `422` si el audio o el texto vienen vacíos, `503 VOZ_NO_DISPONIBLE` si el clúster de voz no responde y `504 VOZ_TIMEOUT` si tarda demasiado. Si falla la voz, muestra la respuesta solo en texto.
- Envía solo audio con voz: con silencio o ruido, el STT inventa frases. Pide la síntesis frase por frase y en orden, porque el TTS genera una frase a la vez.
- El micrófono exige un contexto seguro (`https` o `http://localhost`). La demo `/demo` trae un botón 🎙️ y la casilla «Leer respuestas».

## 5. Acciones de los artifacts

Todos los artifacts tienen `id`, `tipo`, `version` (hoy `1`), `titulo` opcional y `acciones[]`:

| `accion.tipo` | Qué hace el frontend |
|---|---|
| `submit` | Recoge los valores del formulario y envía `{"tipo":"artifact_submit","artifact_id":<artifact.id>,"valores":{…}}` con `accion.metodo` a `accion.endpoint` (normalmente el endpoint de mensajes de la sesión), leyendo la respuesta como SSE |
| `mensaje` | Envía `accion.mensaje` como mensaje de texto normal (chips, sí/no) |
| `enlace` | Llama o abre `accion.endpoint` con `accion.metodo` (por defecto `GET`); si es `POST`, el cuerpo es `accion.payload` más lo que el componente recoja (p. ej. la calificación) |

`accion.estilo` (`primario`, `secundario`, `peligro`, `enlace`) es una pista visual. Ignora con elegancia un `tipo` de artifact desconocido (versión futura): muestra el texto del turno y registra el aviso.

### Campos de formulario

| `campo.tipo` | Control sugerido | Validación (la misma que aplica el servidor) |
|---|---|---|
| `texto` | `<input type=text>` / `<textarea>` si `max` > 200 | longitud entre `min` y `max` (por defecto 0-2000), `patron` (regex completa) |
| `numero` | `<input type=number inputmode=decimal step=any>` | rango `min`/`max` |
| `moneda` | `<input inputmode=numeric>` con formato COP | ≥ 0, máximo 2 decimales, rango |
| `seleccion` | `<select>` o radios (≤ 4 opciones) | debe ser uno de `opciones[].valor` |
| `fecha` | `<input type=date>` | `AAAA-MM-DD` |
| `booleano` | checkbox / switch | `true` o `false` |
| `archivo` | `<input type=file accept=…>` | sube primero por multipart (≤ `max_bytes`, tipo `accept`); en `valores` va el id devuelto |

`requerido` por defecto es `true`. `ayuda` va como texto de ayuda enlazado con `aria-describedby`; `unidad` como sufijo visible.

## 6. Catálogo de artifacts

Los JSON de esta sección se generan desde los modelos de `app/schemas/artifacts.py` y pasan su validación. El esquema formal de cada uno está en `docs/openapi.json` (`components.schemas`), con la unión discriminada por `tipo`.

Accesibilidad para todos: cada artifact es una región (`<section aria-labelledby>`) con su `titulo`; el texto que llega por `delta` va en una zona `aria-live="polite"`; ningún estado se comunica solo con color; todos los controles son operables con teclado.

### 6.1 Cliente

#### `formulario_cotizacion`

- **Cuándo aparece:** Intención `cotizar` («quiero cotizar», «cuánto cuesta enviar…»). Los valores extraídos del mensaje vienen en `valor`.
- **Renderizado:** Formulario nativo: `<select>` para `seleccion`, `<input type=number inputmode=decimal>` con `min`/`max` y la `unidad` como sufijo. Precargar `valor`. Validar en cliente con los mismos límites, pero el servidor manda.

```json
{
  "id": "art-cot-01",
  "version": 1,
  "titulo": "Cotiza tu envío",
  "acciones": [
    {
      "id": "enviar",
      "etiqueta": "Cotizar",
      "tipo": "submit",
      "metodo": "POST",
      "endpoint": "/api/v1/chat/sesiones/3f6c0a52-8e1b-4d7a-9c2e-5b1d0f9a7e41/mensajes",
      "estilo": "primario"
    }
  ],
  "campos": [
    {
      "nombre": "origen",
      "etiqueta": "Ciudad de origen",
      "tipo": "seleccion",
      "requerido": true,
      "opciones": [
        {
          "valor": "Bogotá D.C.",
          "etiqueta": "Bogotá D.C."
        }
      ],
      "valor": "Bogotá D.C."
    },
    {
      "nombre": "destino",
      "etiqueta": "Ciudad de destino",
      "tipo": "seleccion",
      "requerido": true,
      "opciones": [
        {
          "valor": "Medellín",
          "etiqueta": "Medellín"
        },
        {
          "valor": "Cali",
          "etiqueta": "Cali"
        }
      ],
      "valor": "Medellín"
    },
    {
      "nombre": "alto_cm",
      "etiqueta": "Alto",
      "tipo": "numero",
      "requerido": true,
      "min": "1",
      "max": "400",
      "opciones": [],
      "unidad": "cm"
    },
    {
      "nombre": "ancho_cm",
      "etiqueta": "Ancho",
      "tipo": "numero",
      "requerido": true,
      "min": "1",
      "max": "400",
      "opciones": [],
      "unidad": "cm"
    },
    {
      "nombre": "largo_cm",
      "etiqueta": "Largo",
      "tipo": "numero",
      "requerido": true,
      "min": "1",
      "max": "1400",
      "opciones": [],
      "unidad": "cm"
    },
    {
      "nombre": "peso_kg",
      "etiqueta": "Peso real",
      "tipo": "numero",
      "requerido": true,
      "min": "0.1",
      "max": "2500",
      "opciones": [],
      "unidad": "kg"
    },
    {
      "nombre": "valor_declarado_cop",
      "etiqueta": "Valor declarado",
      "tipo": "moneda",
      "requerido": true,
      "min": "0",
      "max": "1000000000",
      "opciones": [],
      "unidad": "COP"
    },
    {
      "nombre": "servicio",
      "etiqueta": "Tipo de servicio",
      "tipo": "seleccion",
      "requerido": true,
      "opciones": [
        {
          "valor": "paqueteria",
          "etiqueta": "Paquetería exprés (hasta 50 kg)"
        },
        {
          "valor": "carga",
          "etiqueta": "Carga (LTL / FTL)"
        },
        {
          "valor": "cadena_frio",
          "etiqueta": "Cadena de frío"
        },
        {
          "valor": "mercancia_peligrosa",
          "etiqueta": "Mercancía peligrosa"
        }
      ],
      "valor": "paqueteria"
    }
  ],
  "tipo": "formulario_cotizacion"
}
```

#### `resultado_cotizacion`

- **Cuándo aparece:** Tras un `artifact_submit` válido del formulario de cotización o un mensaje con todos los datos.
- **Renderizado:** Tabla de desglose (peso facturable, tarifa, flete base, seguro, recargos, **total** destacado) y tiempo estimado. Formatear dinero con `Intl.NumberFormat('es-CO', {style:'currency', currency:'COP'})`. `advertencias` como avisos.

```json
{
  "id": "art-cot-02",
  "version": 1,
  "titulo": "Cotización Bogotá D.C. → Medellín",
  "acciones": [
    {
      "id": "nueva",
      "etiqueta": "Nueva cotización",
      "tipo": "mensaje",
      "mensaje": "Quiero cotizar",
      "estilo": "primario"
    }
  ],
  "tipo": "resultado_cotizacion",
  "cotizacion_id": "8d1e2f30-6a7b-4c8d-9e0f-1a2b3c4d5e6f",
  "trayecto": "TLX-BOG-MED-001",
  "origen": "Bogotá D.C.",
  "destino": "Medellín",
  "servicio": "paqueteria",
  "peso_real_kg": "45.5",
  "peso_volumetrico_kg": "30",
  "peso_facturable_kg": "45.5",
  "base_facturacion": "real",
  "tarifa_kg": "1450",
  "flete_base": "65975",
  "flete_minimo_aplicado": false,
  "seguro": "125000",
  "recargos": [],
  "total": "190975",
  "tiempo_estimado_horas": 24,
  "observaciones": "Ruta de alto flujo por Corredor Bogotá-Medellín. Admite Same Day si se despacha antes de las 09:00 AM.",
  "advertencias": []
}
```

#### `formulario_guia`

- **Cuándo aparece:** Intención `rastrear` sin número de guía en el mensaje.
- **Renderizado:** Un solo `<input>` con `pattern` = `patron`, `autocapitalize=characters`. Convertir a mayúsculas antes de enviar.

```json
{
  "id": "art-trk-00",
  "version": 1,
  "titulo": "¿Cuál es tu número de guía?",
  "acciones": [
    {
      "id": "enviar",
      "etiqueta": "Rastrear",
      "tipo": "submit",
      "metodo": "POST",
      "endpoint": "/api/v1/chat/sesiones/3f6c0a52-8e1b-4d7a-9c2e-5b1d0f9a7e41/mensajes",
      "estilo": "primario"
    }
  ],
  "campos": [
    {
      "nombre": "guia",
      "etiqueta": "Número de guía",
      "tipo": "texto",
      "requerido": true,
      "patron": "^TLX-\\d{6}-CO$",
      "opciones": [],
      "ayuda": "Formato TLX-123456-CO"
    }
  ],
  "tipo": "formulario_guia"
}
```

#### `linea_tiempo_envio`

- **Cuándo aparece:** Intención `rastrear` con guía existente (el texto del usuario contiene `TLX-######-CO`).
- **Renderizado:** Lista ordenada (`<ol>`) cronológica; el último evento es el paso actual (`aria-current=step`). Barra de progreso con `progreso_pct` (`role=progressbar`). ETA visible. `alerta` en un banner con color por `nivel` y texto (no solo color).

```json
{
  "id": "art-trk-01",
  "version": 1,
  "titulo": "Guía TLX-984021-CO",
  "acciones": [],
  "tipo": "linea_tiempo_envio",
  "guia": "TLX-984021-CO",
  "origen": "Bogotá D.C.",
  "destino": "Medellín",
  "servicio": "Transporte Cadena de Frío (2°C a 8°C)",
  "estado_actual": "EN_TRANSITO",
  "estado_texto": "En camino a la ciudad de destino",
  "progreso_pct": 60,
  "eta": "2026-11-03T16:00:00-05:00",
  "eventos": [
    {
      "ts": "2026-11-02T11:15:00-05:00",
      "estado": "SOLICITUD_GENERADA",
      "estado_texto": "Guía generada",
      "ubicacion": "Portal Web Clientes TransLogix",
      "descripcion": "Orden de despacho creada y guía generada exitosamente."
    },
    {
      "ts": "2026-11-03T08:30:00-05:00",
      "estado": "EN_TRANSITO",
      "estado_texto": "En camino a la ciudad de destino",
      "ubicacion": "Corredor Calarcá - Pereira",
      "descripcion": "Vehículo en ruta regular. Arribo estimado a Hub Itagüí a las 12:30 PM."
    }
  ]
}
```

#### `mapa_ubicacion`

- **Cuándo aparece:** Junto a `linea_tiempo_envio` cuando la guía tiene GPS.
- **Renderizado:** Mapa (Leaflet/OSM u otro) con un marcador; siempre mostrar también `referencia` en texto como alternativa accesible.

```json
{
  "id": "art-trk-02",
  "version": 1,
  "acciones": [],
  "tipo": "mapa_ubicacion",
  "guia": "TLX-984021-CO",
  "latitud": 5.06889,
  "longitud": -75.51738,
  "referencia": "Paso de Montaña Alto de la Línea - Sentido Bogotá-Ibague-Medellín",
  "actualizado": "2026-11-03T08:30:00-05:00"
}
```

#### `veredicto_mercancia`

- **Cuándo aparece:** Intención `mercancia` («¿puedo enviar…?»). El veredicto es determinista; el texto del LLM solo lo explica.
- **Renderizado:** Insignia grande por `veredicto` (prohibido = rojo + icono + palabra). Listas de condiciones, documentos y embalaje. Fuentes al pie.

```json
{
  "id": "art-mp-01",
  "version": 1,
  "acciones": [],
  "tipo": "veredicto_mercancia",
  "producto": "perro",
  "veredicto": "prohibido",
  "categoria": "Animales vivos",
  "motivo": "Los animales vivos están en la lista de artículos prohibidos de TransLogix.",
  "condiciones": [],
  "documentos": [],
  "embalaje": [],
  "fuentes": [
    {
      "doc_codigo": "DOC-OPS-2026-03",
      "documento": "Manual de mercancías peligrosas y embalaje",
      "seccion": "5. Lista expresa de artículos prohibidos"
    }
  ]
}
```

#### `plan_envio`

- **Cuándo aparece:** Intención `enviar` («quiero enviar clavos de Bogotá a Medellín»), seguido de `formulario_cotizacion` con producto y ciudades precargados. Se resuelve sin LLM. Un producto prohibido no llega aquí: responde `veredicto_mercancia`.
- **Renderizado:** Insignia por `estado`, `resumen` y `pasos` numerados con sus `items`. `sin_registro` significa que el catálogo no clasifica el producto: **no** es una aprobación ni debe pintarse como tal. `sin_producto` significa que aún no se sabe qué se envía.

```json
{
  "id": "art-plan-01",
  "version": 1,
  "titulo": "Plan para enviar clavos",
  "acciones": [],
  "tipo": "plan_envio",
  "producto": "clavos",
  "estado": "sin_registro",
  "resumen": "No aparece en nuestro catálogo de prohibidos y mercancías peligrosas. No es una aprobación.",
  "pasos": [
    {
      "titulo": "Embala",
      "detalle": "El remitente responde por un embalaje que resista vibración, frenado y apilamiento.",
      "items": []
    }
  ],
  "fuentes": [
    {
      "doc_codigo": "DOC-OPS-2026-03",
      "documento": "Manual de mercancías peligrosas y embalaje",
      "seccion": "§4 Estándares de embalaje"
    }
  ]
}
```

#### `guia_embalaje`

- **Cuándo aparece:** Intención `embalaje` («cómo empaco…»).
- **Renderizado:** Pasos numerados (`<ol>`), requisito resaltado, fuentes al pie.

```json
{
  "id": "art-emb-01",
  "version": 1,
  "acciones": [],
  "tipo": "guia_embalaje",
  "categoria": "A",
  "nombre_categoria": "Productos frágiles (vidrio, cerámica, instrumentos de medición)",
  "requisito": "Sistema de protección «caja dentro de caja».",
  "pasos": [
    "Envuelve cada producto con plástico burbuja de al menos 3 cm de espesor.",
    "Deja mínimo 5 cm entre el producto y las paredes internas de la caja exterior.",
    "Rellena el espacio libre con maní de poliestireno o espuma inyectada.",
    "Marca la caja con cinta roja «FRÁGIL - MANEJE CON CUIDADO» y flechas «ESTE LADO ARRIBA»."
  ],
  "fuentes": [
    {
      "doc_codigo": "DOC-OPS-2026-03",
      "documento": "Manual de mercancías peligrosas y embalaje",
      "seccion": "4.A Productos Frágiles"
    }
  ]
}
```

#### `ficha_cobertura`

- **Cuándo aparece:** Intención `cobertura` («¿llegan a…?», «¿cuánto tarda a…?»).
- **Renderizado:** Ficha con chips sí/no para same day y refrigerado, límites de peso/volumen, hub, frecuencia y restricciones.

```json
{
  "id": "art-cob-01",
  "version": 1,
  "acciones": [],
  "tipo": "ficha_cobertura",
  "municipio": "Medellín",
  "departamento": "Antioquia",
  "codigo_dane": "05001",
  "tipo_cobertura": "Urbana Principal",
  "hub": "Hub Regional Itagüí - Antioquia",
  "same_day": true,
  "refrigerado": true,
  "peso_maximo_kg": "2000",
  "volumen_maximo_m3": "40",
  "tiempo_estandar_horas": 24,
  "frecuencia_despacho": "Continuo (4 salidas diarias)",
  "restricciones": "Restricción de ingreso al centro urbano para camiones de más de 2 ejes entre 06:00 y 20:00."
}
```

#### `formulario_pqrs`

- **Cuándo aparece:** Intención `pqrs` («me llegó la caja rota», «quiero poner un reclamo»).
- **Renderizado:** Igual que los demás formularios. `booleano` = checkbox o switch; `fecha` = `<input type=date>`.

```json
{
  "id": "art-pqrs-01",
  "version": 1,
  "titulo": "Radicar reclamo",
  "acciones": [
    {
      "id": "enviar",
      "etiqueta": "Continuar",
      "tipo": "submit",
      "metodo": "POST",
      "endpoint": "/api/v1/chat/sesiones/3f6c0a52-8e1b-4d7a-9c2e-5b1d0f9a7e41/mensajes",
      "estilo": "primario"
    }
  ],
  "campos": [
    {
      "nombre": "tipo",
      "etiqueta": "Tipo de solicitud",
      "tipo": "seleccion",
      "requerido": true,
      "opciones": [
        {
          "valor": "P",
          "etiqueta": "Petición"
        },
        {
          "valor": "Q",
          "etiqueta": "Queja"
        },
        {
          "valor": "R",
          "etiqueta": "Reclamo"
        },
        {
          "valor": "S",
          "etiqueta": "Sugerencia"
        }
      ],
      "valor": "R"
    },
    {
      "nombre": "guia",
      "etiqueta": "Número de guía",
      "tipo": "texto",
      "requerido": true,
      "patron": "^TLX-\\d{6}-CO$",
      "opciones": []
    },
    {
      "nombre": "novedad",
      "etiqueta": "¿Qué pasó?",
      "tipo": "seleccion",
      "requerido": true,
      "opciones": [
        {
          "valor": "averia_aparente",
          "etiqueta": "Daño visible al recibir"
        },
        {
          "valor": "averia_oculta",
          "etiqueta": "Daño descubierto al abrir"
        },
        {
          "valor": "perdida",
          "etiqueta": "Pérdida o extravío"
        }
      ],
      "valor": "averia_oculta"
    },
    {
      "nombre": "fecha_entrega",
      "etiqueta": "Fecha de entrega",
      "tipo": "fecha",
      "requerido": false,
      "opciones": []
    },
    {
      "nombre": "descripcion",
      "etiqueta": "Descripción",
      "tipo": "texto",
      "requerido": true,
      "min": "10",
      "max": "2000",
      "opciones": []
    },
    {
      "nombre": "valor_reclamado_cop",
      "etiqueta": "Valor reclamado",
      "tipo": "moneda",
      "requerido": true,
      "opciones": [],
      "unidad": "COP"
    },
    {
      "nombre": "anotada_en_guia",
      "etiqueta": "¿Dejaste anotación en la guía o POD al recibir?",
      "tipo": "booleano",
      "requerido": false,
      "opciones": []
    }
  ],
  "tipo": "formulario_pqrs"
}
```

#### `estado_plazo`

- **Cuándo aparece:** Después del `formulario_pqrs` o con intención `plazo_reclamo`. Calculado en días hábiles con festivos.
- **Renderizado:** Semáforo: vigente (verde) o vencido (rojo), siempre con texto. Fecha límite y días restantes. `fundamento` en letra pequeña.

```json
{
  "id": "art-pqrs-02",
  "version": 1,
  "acciones": [],
  "tipo": "estado_plazo",
  "guia": "TLX-752190-CO",
  "novedad": "averia_oculta",
  "fecha_referencia": "2026-11-02",
  "fecha_limite": "2026-11-05",
  "dias_habiles_plazo": 3,
  "dias_habiles_restantes": 2,
  "vigente": true,
  "mensaje": "Estás dentro del plazo: tienes hasta el 5 de noviembre de 2026 para radicar.",
  "fundamento": "Protocolo PQRS §3: avería oculta, 3 días hábiles tras la entrega."
}
```

#### `checklist_documentos`

- **Cuándo aparece:** Cuando el plazo está vigente y hay que reunir documentos (protocolo §4).
- **Renderizado:** Lista de casillas; cada ítem no completado tiene un `<input type=file accept=…>` que sube a `endpoint_carga` (multipart, campo `archivo`, `tipo_documento` = `item.id`). Al subir, marcar completado. Cuando todos los requeridos estén, habilitar la acción `submit`.

```json
{
  "id": "art-pqrs-03",
  "version": 1,
  "acciones": [
    {
      "id": "radicar",
      "etiqueta": "Radicar",
      "tipo": "submit",
      "metodo": "POST",
      "endpoint": "/api/v1/chat/sesiones/3f6c0a52-8e1b-4d7a-9c2e-5b1d0f9a7e41/mensajes",
      "estilo": "primario"
    }
  ],
  "tipo": "checklist_documentos",
  "radicado": "PQRS-2026-000123",
  "endpoint_carga": "/api/v1/pqrs/PQRS-2026-000123/documentos",
  "items": [
    {
      "id": "guia",
      "etiqueta": "Número de guía de transporte",
      "requerido": true,
      "completado": true,
      "max_bytes": 10485760
    },
    {
      "id": "factura",
      "etiqueta": "Factura comercial de venta (con IVA)",
      "requerido": true,
      "completado": false,
      "accept": "application/pdf,image/jpeg",
      "max_bytes": 10485760
    },
    {
      "id": "carta_reclamacion",
      "etiqueta": "Carta de reclamación formal",
      "descripcion": "Firmada, con valor reclamado, descripción y certificación bancaria (no mayor a 30 días).",
      "requerido": true,
      "completado": false,
      "accept": "application/pdf,image/jpeg",
      "max_bytes": 10485760
    },
    {
      "id": "fotos",
      "etiqueta": "Registro fotográfico (empaque, daño y amortiguación)",
      "requerido": true,
      "completado": false,
      "accept": "application/pdf,image/jpeg",
      "max_bytes": 10485760
    },
    {
      "id": "identidad",
      "etiqueta": "Cédula o RUT",
      "requerido": true,
      "completado": false,
      "accept": "application/pdf,image/jpeg",
      "max_bytes": 10485760
    }
  ],
  "completo": false
}
```

#### `ticket_pqrs`

- **Cuándo aparece:** Al radicar (`POST /pqrs/crear-ticket` vía chat).
- **Renderizado:** Tarjeta de confirmación con el **radicado** copiable, fecha límite de respuesta y, si existe, la liquidación estimada con la nota de que está sujeta a aprobación.

```json
{
  "id": "art-pqrs-04",
  "version": 1,
  "acciones": [],
  "tipo": "ticket_pqrs",
  "radicado": "PQRS-2026-000123",
  "tipo_pqrs": "R",
  "estado": "radicado",
  "guia": "TLX-551904-CO",
  "fecha_radicacion": "2026-11-03T10:12:00-05:00",
  "fecha_limite_respuesta": "2026-11-25",
  "checklist_completo": true,
  "liquidacion_estimada": {
    "base": "420000",
    "deducible": "0",
    "flete_devuelto": "0",
    "total": "420000",
    "nota": "Estimación sujeta a aprobación (15 días hábiles)."
  }
}
```

#### `aviso_escalamiento`

- **Cuándo aparece:** Cuando se cumple un criterio CRIT-001…005. Llega también el evento SSE `escalamiento`.
- **Renderizado:** Banner persistente «Te estamos transfiriendo» con `mensaje` literal, cuenta regresiva de `espera_estimada_s` y posición en cola. Abrir `GET /chat/sesiones/{id}/eventos` para recibir al asesor.

```json
{
  "id": "art-esc-01",
  "version": 1,
  "acciones": [],
  "tipo": "aviso_escalamiento",
  "escalamiento_id": "b7c1d2e3-4f50-4a6b-8c7d-9e0f1a2b3c4d",
  "criterio": "CRIT-002",
  "prioridad": "alta",
  "mensaje": "Lamento profundamente la molestia ocasionada. Estoy transfiriendo tu chat de inmediato a un supervisor de servicio al cliente para resolver tu situación.",
  "espera_estimada_s": 45,
  "posicion_cola": 2
}
```

#### `citas`

- **Cuándo aparece:** Respuestas sustentadas en el corpus RAG (mercancías, PQRS, embalaje).
- **Renderizado:** Notas al pie o un desplegable «Fuentes» con documento y sección.

```json
{
  "id": "art-cit-01",
  "version": 1,
  "acciones": [],
  "tipo": "citas",
  "citas": [
    {
      "doc_codigo": "DOC-PQRS-2026-04",
      "documento": "Protocolo de PQRS e indemnizaciones",
      "seccion": "3. Tiempos y plazos legales de radicación",
      "puntuacion": 0.88
    }
  ]
}
```

#### `respuestas_rapidas`

- **Cuándo aparece:** Saludo, arranque de sesión o al terminar un flujo.
- **Renderizado:** Chips/botones; al pulsar, enviar `accion.mensaje` como mensaje de texto. Navegables con teclado.

```json
{
  "id": "art-rr-01",
  "version": 1,
  "acciones": [
    {
      "id": "rastrear",
      "etiqueta": "Rastrear una guía",
      "tipo": "mensaje",
      "mensaje": "Quiero rastrear",
      "estilo": "primario"
    },
    {
      "id": "cotizar",
      "etiqueta": "Cotizar un envío",
      "tipo": "mensaje",
      "mensaje": "Quiero cotizar",
      "estilo": "primario"
    },
    {
      "id": "pqrs",
      "etiqueta": "Radicar un reclamo",
      "tipo": "mensaje",
      "mensaje": "Quiero radicar un reclamo",
      "estilo": "primario"
    }
  ],
  "tipo": "respuestas_rapidas"
}
```

#### `confirmacion`

- **Cuándo aparece:** Cuando el agente necesita un sí/no (p. ej. ofrecer asesor si no hay trayecto).
- **Renderizado:** Pregunta + botones de las acciones (tipo `mensaje`).

```json
{
  "id": "art-conf-01",
  "version": 1,
  "acciones": [
    {
      "id": "si",
      "etiqueta": "Sí",
      "tipo": "mensaje",
      "mensaje": "Sí, quiero un asesor",
      "estilo": "primario"
    },
    {
      "id": "no",
      "etiqueta": "No",
      "tipo": "mensaje",
      "mensaje": "No, gracias",
      "estilo": "secundario"
    }
  ],
  "tipo": "confirmacion",
  "mensaje": "¿Quieres que te conecte con un asesor?"
}
```

#### `encuesta_satisfaccion`

- **Cuándo aparece:** Al cerrar la conversación o tras resolver un escalamiento.
- **Renderizado:** 1-5 estrellas (radio group accesible) + comentario opcional. Envía `{puntaje, comentario}` al `endpoint` de la acción.

```json
{
  "id": "art-csat-01",
  "version": 1,
  "acciones": [
    {
      "id": "calificar",
      "etiqueta": "Enviar",
      "tipo": "enlace",
      "metodo": "POST",
      "endpoint": "/api/v1/chat/sesiones/3f6c0a52-8e1b-4d7a-9c2e-5b1d0f9a7e41/calificacion",
      "estilo": "primario"
    }
  ],
  "tipo": "encuesta_satisfaccion",
  "pregunta": "¿Qué tan satisfecho quedaste con la atención?",
  "escala_min": 1,
  "escala_max": 5,
  "permite_comentario": true
}
```

### 6.2 Administración (chat admin)

Llegan por `POST /api/v1/admin/chat` con el mismo protocolo SSE.

#### `tarjetas_kpi`

- **Cuándo aparece:** Chat admin, intención `kpis` o `rendimiento_ia`.
- **Renderizado:** Grid de tarjetas; formatear por `formato` (porcentaje, moneda, `duracion_ms` → «1,85 s»). Flecha por `tendencia`.

```json
{
  "id": "art-kpi-01",
  "version": 1,
  "titulo": "Últimos 7 días",
  "acciones": [],
  "tipo": "tarjetas_kpi",
  "periodo": {
    "desde": "2026-10-27",
    "hasta": "2026-11-03"
  },
  "tarjetas": [
    {
      "id": "interacciones",
      "etiqueta": "Interacciones",
      "valor": "1284",
      "formato": "numero",
      "tendencia": "sube"
    },
    {
      "id": "automatizado",
      "etiqueta": "Resuelto sin humano",
      "valor": "81.4",
      "formato": "porcentaje"
    },
    {
      "id": "p95",
      "etiqueta": "Latencia p95",
      "valor": "1850",
      "formato": "duracion_ms"
    },
    {
      "id": "csat",
      "etiqueta": "CSAT",
      "valor": "4.3",
      "formato": "numero",
      "unidad": "/5"
    }
  ]
}
```

#### `grafico`

- **Cuándo aparece:** Chat admin, `pronostico_demanda`, `envios_por_estado` y series temporales.
- **Renderizado:** Línea o barras según `tipo_grafico`; `y_inf`/`y_sup` como banda de intervalo; serie `punteada` = pronóstico. Si `datos_simulados`, rótulo visible «Datos simulados». Incluir tabla alternativa para lectores de pantalla.

```json
{
  "id": "art-graf-01",
  "version": 1,
  "titulo": "Pronóstico de despachos — Hub Central Zona Franca Fontibón",
  "acciones": [],
  "tipo": "grafico",
  "tipo_grafico": "linea",
  "eje_x": {
    "etiqueta": "Fecha",
    "tipo": "fecha"
  },
  "eje_y": {
    "etiqueta": "Despachos",
    "tipo": "numero",
    "unidad": "envíos"
  },
  "series": [
    {
      "nombre": "Histórico",
      "puntos": [
        {
          "x": "2026-11-02",
          "y": "142"
        },
        {
          "x": "2026-11-03",
          "y": "151"
        }
      ],
      "estilo": "solida"
    },
    {
      "nombre": "Pronóstico",
      "puntos": [
        {
          "x": "2026-11-04",
          "y": "148",
          "y_inf": "131",
          "y_sup": "166"
        }
      ],
      "estilo": "punteada"
    }
  ],
  "datos_simulados": true
}
```

#### `tabla_datos`

- **Cuándo aparece:** Chat admin: `envios_retenidos`, `pqrs_resumen`, `buscar_conversacion`, `escalamientos`.
- **Renderizado:** `<table>` con `<th scope=col>`; formatear por `columna.tipo`; `estado` como insignia. Paginación con `paginacion`.

```json
{
  "id": "art-tab-01",
  "version": 1,
  "titulo": "Envíos retenidos",
  "acciones": [],
  "tipo": "tabla_datos",
  "columnas": [
    {
      "clave": "guia",
      "etiqueta": "Guía",
      "tipo": "texto"
    },
    {
      "clave": "ruta",
      "etiqueta": "Ruta",
      "tipo": "texto"
    },
    {
      "clave": "estado",
      "etiqueta": "Estado",
      "tipo": "estado"
    },
    {
      "clave": "declarado",
      "etiqueta": "Valor declarado",
      "tipo": "moneda"
    }
  ],
  "filas": [
    {
      "guia": "TLX-310482-CO",
      "ruta": "Barranquilla → Bucaramanga",
      "estado": "RETENIDO_NOVEDAD",
      "declarado": "34000000"
    }
  ],
  "paginacion": {
    "pagina": 1,
    "tamano": 20,
    "total": 1
  }
}
```

#### `tarjeta_prediccion`

- **Cuándo aparece:** Chat admin, `riesgo_retraso` de una guía.
- **Renderizado:** Medidor de probabilidad con `nivel` en texto, intervalo y lista de factores (barra +/−). Rótulo «Datos simulados».

```json
{
  "id": "art-pred-01",
  "version": 1,
  "acciones": [],
  "tipo": "tarjeta_prediccion",
  "modelo": "riesgo_retraso",
  "version_modelo": 3,
  "guia": "TLX-984021-CO",
  "probabilidad": "0.34",
  "intervalo": {
    "inferior": "0.26",
    "superior": "0.42"
  },
  "nivel": "medio",
  "factores": [
    {
      "nombre": "paso_montana",
      "efecto": "0.12",
      "descripcion": "Ruta por el Alto de La Línea"
    },
    {
      "nombre": "cadena_frio",
      "efecto": "0.05",
      "descripcion": "Requiere refrigeración"
    }
  ],
  "datos_simulados": true
}
```

#### `metricas_modelo`

- **Cuándo aparece:** Chat admin, `estado_modelos`.
- **Renderizado:** Tabla por modelo: versión, estado, métricas frente a línea base, n de entrenamiento y fecha.

```json
{
  "id": "art-ml-01",
  "version": 1,
  "acciones": [],
  "tipo": "metricas_modelo",
  "modelos": [
    {
      "nombre": "riesgo_retraso",
      "version": 3,
      "algoritmo": "HistGradientBoostingClassifier",
      "estado": "activo",
      "metricas": {
        "roc_auc": "0.81",
        "brier": "0.162"
      },
      "linea_base": {
        "roc_auc": "0.72",
        "brier": "0.191"
      },
      "n_train": 8420,
      "entrenado_en": "2026-11-03T06:00:00-05:00"
    }
  ],
  "datos_simulados": true
}
```

#### `cola_escalamientos`

- **Cuándo aparece:** Chat admin `escalamientos`; también útil en la vista de asesor.
- **Renderizado:** Lista ordenada por prioridad y espera; botón «Tomar» → `POST /asesor/escalamientos/{id}/tomar`.

```json
{
  "id": "art-cola-01",
  "version": 1,
  "acciones": [],
  "tipo": "cola_escalamientos",
  "items": [
    {
      "escalamiento_id": "b7c1d2e3-4f50-4a6b-8c7d-9e0f1a2b3c4d",
      "sesion_id": "3f6c0a52-8e1b-4d7a-9c2e-5b1d0f9a7e41",
      "criterio": "CRIT-005",
      "prioridad": "alta",
      "estado": "pendiente",
      "creado": "2026-11-03T10:05:00-05:00",
      "espera_s": 38,
      "resumen": "Cliente consulta guía retenida por la POLFA con mercancía Clase 3.",
      "guia": "TLX-310482-CO"
    }
  ]
}
```

## 7. Errores (RFC 9457)

Todo error responde `Content-Type: application/problem+json`:

```json
{
  "type": "https://translogix.demo/errores/formulario-invalido",
  "title": "Datos inválidos",
  "status": 422,
  "detail": "El formulario tiene 1 campo con error.",
  "instance": "/api/v1/chat/sesiones/3f6c0a52-8e1b-4d7a-9c2e-5b1d0f9a7e41/mensajes",
  "request_id": "01JBX7Q2M8Z3K4V5N6P7R8S9T0",
  "codigo": "FORMULARIO_INVALIDO",
  "errores": [{ "campo": "peso_kg", "mensaje": "Debe ser mayor o igual a 0.1", "tipo": "invalido" }]
}
```

- Muestra `title` (y `detail` si existe). `codigo` es un identificador estable (MAYÚSCULAS_CON_GUION_BAJO) para ramificar la lógica; `type` es la misma clave en kebab-case bajo `https://translogix.demo/errores/`.
- `errores[]` solo aparece en validaciones (422): `{campo, mensaje, tipo}`; asocia cada `mensaje` a su `campo`.
- Incluye `request_id` en los reportes de fallo: es el mismo de la cabecera `X-Request-ID` y de los logs.
- Nunca llega un stack trace.

| Código | Cuándo | Qué hacer en el frontend |
|---|---|---|
| 400 | Petición mal formada | Error genérico |
| 401 | Sin token, token vencido o inválido | Refrescar una vez; si falla, login |
| 403 | Rol insuficiente (p. ej. cliente → `/admin`) | Ocultar la opción; mensaje «sin permiso» |
| 404 | No existe **o no es tuyo** (guía, ticket, sesión) | «No encontrado» |
| 409 | Duplicado, conflicto o `Idempotency-Key` reutilizada con otro cuerpo; escalamiento ya tomado | Refrescar el estado |
| 413 | Archivo > 10 MB | Avisar el límite |
| 415 | Tipo de archivo no permitido (solo PDF o JPEG, verificado por contenido) | Avisar los tipos válidos |
| 422 | Validación de campos (`errores[]`) | Marcar los campos |
| 429 | Límite de peticiones; trae `Retry-After` | Esperar y reintentar |
| 503 | LLM o dependencia no disponible; trae `Retry-After` | Aviso; el chat escala a humano |
| 504 | El LLM tardó demasiado | Igual que 503 |

## 8. Tipos TypeScript

```bash
npx openapi-typescript docs/openapi.json -o api.d.ts
```

```ts
import type { components } from "./api";
type Artifact = components["schemas"]["ChatTurnResponse"]["artifacts"][number];

function pintar(a: Artifact) {
  switch (a.tipo) {               // unión discriminada: TS estrecha el tipo en cada rama
    case "linea_tiempo_envio": return <LineaTiempo eventos={a.eventos} progreso={a.progreso_pct} />;
    case "resultado_cotizacion": return <Cotizacion total={a.total} />;
    // …
  }
}
```

El cuerpo SSE es un stream, así que OpenAPI no lo tipa por evento: usa la tabla de §4.2. Los modelos de cada evento están en `app/schemas/chat.py` (`EventoMeta`, `EventoArtifact`, `EventoDelta`, `EventoReemplazo`, `EventoCitas`, `EventoEscalamiento`, `EventoFin`, `Latencias`) y el `data` de `artifact` es exactamente el tipo `Artifact` de `ChatTurnResponse`.

`docs/openapi.json` se regenera con `make openapi`; una prueba falla si queda desactualizado, así que el archivo versionado siempre refleja la API.
