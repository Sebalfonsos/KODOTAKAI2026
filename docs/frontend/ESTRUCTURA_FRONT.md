# Estructura del front: PWA TransLogix con RUTI

Especificación para construir la PWA de KODO TAKAI 2026 cuando el backend esté disponible. Alinea la propuesta del equipo con la rúbrica, el dosier, las reglas de negocio y el kit de RUTI.

- **Estado:** backend integrado en `main` (`902eaa3`). La base del front está en `frontend/`; las pantallas se completan según la sección 13.
- **Contrato:** `docs/openapi.json` manda, y `docs/frontend.md` lo explica. Si esta especificación los contradice, ganan ellos.
- **Dirección aprobada:** `~/Downloads/Entrega_Frontend_TransLogix_RUTI_Para_Equipo/Propuesta_Frontend_TransLogix_RUTI_KodoTakai2026.md`, v1.0.
- **Kit de mascota:** `RUTI_Kit_Animacion_Kodo_Takai_2026.zip` dentro de esa entrega; se versiona en el repo al empezar (sección 13).
- **Referencia de interacción:** https://anoma.ly/hex/ (solo inspiración: no se copian su identidad, sus animaciones exactas ni sus recursos).

**Orden de autoridad si hay conflicto:** 1) dosier y rúbrica; 2) `docs/openapi.json`, `docs/frontend.md` y las decisiones `D-xx` de `docs/requisitos.md`; 3) esta especificación; 4) propuesta del equipo; 5) moodboard, que es referencia de ambiente y no una pantalla final.

---

## 0. Ajustes frente a la propuesta del equipo

La propuesta se mantiene: portada inmersiva oscura, aplicación clara, centro de servicios y RUTI ligado a estados reales. Estos ajustes la alinean con los requisitos:

| # | Tema | Propuesta o moodboard | Ajuste | Motivo |
|---|---|---|---|---|
| 1 | **Rastreo y cotización** | Formularios con endpoints del TMS | Todo pasa por el chat: el servidor emite el formulario como artifact (sección 9) | Solo el chat da lenguaje natural, confianza y escalación |
| 2 | **Traspaso** | Dentro de la pantalla PQRS; "señal visual" en P0 | Capa global en todas las pantallas; flujo completo en P0 | El dosier exige transferir de inmediato en cualquier condición |
| 3 | **Prioridades** | PWA y RUTI inline en fase 2; normativa en P1 | Pasan a P0, en versión mínima | La PWA es requisito del reto y la normativa es el módulo 4 |
| 4 | **Colores** | La propuesta y el moodboard traen paletas distintas | Se usa la de la propuesta, con ajustes de contraste (sección 6) | Evita dos identidades |
| 5 | **Contraste** | Verde, rojo, ámbar y violeta del moodboard | Tonos más oscuros para texto; teal sin texto sobre blanco | Calculados: fallan AA sobre blanco |
| 6 | **Personaje** | El moodboard muestra otro robot, blanco y azul | Solo se usa el SVG del kit | No se puede reproducir el render con el kit |
| 7 | **Barra "Consultando"** | Barra de progreso parcial | Actividad indeterminada | Una barra sin datos reales simula progreso |
| 8 | **Línea de tiempo** | Recibido, En proceso, En tránsito, Entregado | Estados reales del TMS (sección 8.1) | El mockup no coincide con el dataset |
| 9 | **Formato de guía** | `TLX-45892` en el mockup | `TLX-XXXXXX-CO` | Es el formato real del dataset y del dosier |
| 10 | **Iniciar sesión** | Visible en el mockup | **Se mantiene** (corrige una versión anterior) | Ya hay caso real: PQRS exige cuenta, y existen los roles asesor y admin |
| 11 | **Portada** | "Ver cómo funciona" y "Explorar servicios" | "Conversar con RUTI" y "Explorar servicios" | Es lo que define el texto de la propuesta |
| 12 | **Estados** | Nombres en inglés y español | Solo los del kit, más `reposo` | Es lo que usa `data-state` |
| 13 | **Escuchando** | "Te escucho", usuario "escribe o habla" | "Te leo" al escribir; "Te escucho" solo si se añade el micrófono opcional | El kit advierte no aparentar captura de micrófono |
| 14 | **Enlace roto** | Cita `a_highly_detailed_polished_ui_design_proposal_for.png` | El archivo real es `Moodboard_y_Mockups_TransLogix.png` | Corregir al compartir |
| 15 | **Omnicanal** | No se aborda | Decisión expresa (sección 10) | El dosier pide una PWA "ligera y omnicanal" |

---

## 1. Qué se evalúa y cómo responde el front

Rúbrica **Mejor Proyecto**: 6 criterios, 10 puntos cada uno, 60 en total.

| # | Criterio | Peso del front | Qué debe mostrar el front para llegar a Excelente |
|---|---|---|---|
| 2 | **Experiencia de Usuario** | **Directo** | Interfaz intuitiva, responsive profesional, navegación fluida y conexión impecable con endpoints |
| 1 | Funcionalidad e Integración IA | Alto | Respuestas reales del backend, estados de error y latencia bien manejados, estabilidad en vivo |
| 3 | Innovación y Creatividad | Alto | RUTI reacciona a datos reales (confianza, escalación); no es una copia de Hex ni un chat genérico |
| 5 | Sustentación Pitch | Medio | Demo ensayada y corta, con RUTI como hilo narrativo |
| 4 | Viabilidad de Negocio | Bajo | La demo muestra el valor: menos espera, menos errores de cotización, menos PQRS incompletas. El front no debe inventar métricas |
| 6 | Preguntas | Bajo | Poder explicar cómo se decide cada estado. **La fila está cortada en el PDF:** revisar el original |

Lectura práctica del criterio 2. Cada frase de "Excelente" se convierte en una comprobación de la sección 15:

| Frase de la rúbrica | Se demuestra con |
|---|---|
| "Interfaz intuitiva" | Una persona nueva rastrea una guía sin ayuda desde el primer intento |
| "Diseño responsive profesional" | Sin desbordes de 360 a 1440 px, con layouts propios para móvil y escritorio |
| "Navegación fluida" | Sin saltos de layout, foco correcto, historial conservado y animaciones a 60 fps |
| "Conexión impecable con endpoints" | Cada estado de la petición tiene representación: enviando, respondiendo, error, reintento |

**Riesgo de la rúbrica:** el criterio 3 da "Insuficiente" a una "copia directa de modelos existentes sin adaptación real". Por eso no se copian de Hex su personaje, su texto ni su secuencia de explosiones.

---

## 2. Principios

1. **El texto manda.** Toda información importante existe como texto y estado accesible. RUTI la acompaña y nunca es el único canal (README del kit).
2. **La animación nunca miente.** RUTI no aparenta conexión con un asesor antes de confirmarla ni oculta un error real.
3. **Primero la tarea, después el espectáculo.** Un foco por pantalla y una sola acción principal. La animación nunca retrasa consultar, cotizar o escribir.
4. **Movimiento con significado.** Cada animación comunica un estado, confirma una acción o guía la atención.
5. **RUTI nunca tapa** campos, botones ni contenido.
6. **El backend decide.** El front no calcula fletes, no aplica reglas de escalación y no deduce intenciones del texto.
7. **Nada se presenta como real sin confirmación del servidor:** cotizaciones, estados, tickets y transferencias. Si la tarea es simulada para la demo, se etiqueta.

---

## 3. Mascota: integración técnica

### 3.1 Archivos del kit

| Archivo | Uso |
|---|---|
| `RUTI_animable.svg` (18 KB) | **Recurso principal**, insertado inline en la app |
| `estados/RUTI_*.svg` | Mismo vector con otro `data-state` guardado: no hace falta cargarlos en la app |
| `estados/RUTI_*.png` (~110 KB) | Vistas previas, material del pitch, respaldo estático |
| `capas_y_estados.json` | Inventario de capas y pivotes |
| `referencias/RUTI_referencia_original.png` | Solo referencia. El SVG es una versión redibujada y más simple |

### 3.2 Reglas de uso

- **Inline obligatorio.** Con `<img>` no se pueden controlar los grupos internos.
- **Una sola instancia inline por página.** El SVG usa IDs globales (`ojos`, `teal`, `titulo`). Dos copias los duplican. Para otros tamaños se reubica la misma instancia o se usa un PNG/WebP estático.
- **Encuadre por `viewBox`:**

| Encuadre | `viewBox` | Dónde |
|---|---|---|
| Cuerpo completo | `0 0 1122 1402` | Panel de escritorio |
| Cabeza y pin | `100 0 940 780` (oculta cuerpo, brazos y piernas) | Portada, cabecera móvil y formularios |

- **`overflow: visible`** en el SVG para que los gestos de brazo no se recorten.
- **Accesibilidad:** el SVG es decorativo dentro del chat (`aria-hidden="true"`). El estado se anuncia por una región de texto aparte (sección 7.4). El `<title>` solo se conserva si RUTI aparece solo.

### 3.3 Jerarquía real del SVG

Comprobada en navegador. Determina cómo se anima:

```text
#ruti [data-state]
└── #flotacion
    ├── #piernas      → pierna_izquierda, pierna_derecha, pie_izquierdo, pie_derecho
    ├── #brazos       → brazo_izquierdo, brazo_derecho
    ├── #cuerpo       → franjas_ruta, insignia_paquete
    ├── #manos        → mano_izquierda, mano_derecha
    ├── #pin_ubicacion
    ├── #cabeza       → auricular_*, casco, visor, rostro
    │                   rostro → cejas, ojos (ojos_abiertos, ojos_cerrados), mejillas, boca
    └── #indicadores_estado → barras_audio, puntos_ambar, check_ambar,
                              derivacion_humana, sin_conexion
```

### 3.4 Consecuencias que el kit no resuelve solo

| Hallazgo | Efecto si se ignora | Solución |
|---|---|---|
| `#pin_ubicacion` es hermano de `#cabeza`, no hijo | Al inclinar la cabeza, el pin se queda quieto y se ve despegado | Aplicar la misma inclinación y pivote a ambos |
| `#mano_*` está en otro grupo que `#brazo_*` | Al girar el brazo, la mano no lo sigue | Aplicar la misma rotación a brazo y mano desde el hombro; el gesto propio de la mano va en un `<g>` nuevo dentro de `#mano_*` |
| El CSS del kit ya usa `transform` en pupilas (`pensando`) y cejas (`error`) | Una animación de mirada o ceja lo reemplaza | Envolver con un `<g>` de animación o llevar el valor a variables CSS |
| Los cambios de estado usan `display` | No hay transición posible entre piezas | Usar animaciones de entrada que corren al aparecer; para la boca, un fundido corto |
| `escalamiento` y `error` comparten boca e indicador ámbar del mismo tamaño | Parecen el mismo estado (ver `RUTI_estados_preview.jpg`) | Diferenciar con cejas, gesto y texto (sección 5.3) |
| El estado por defecto muestra barras de audio | RUTI aparenta escuchar cuando nadie interactúa | Añadir `data-state="reposo"` (sección 4) |
| El anillo de la antena no tiene ID propio | No se puede animar por separado sin editar el SVG | Usar `pin_ubicacion` y `visor` como señales de actividad |
| `sombraSutil` está definido pero sin uso | Ninguno | Se puede eliminar al optimizar con SVGO, conservando los IDs |

**Sobre fondo claro** (probado sobre blanco y `#F5F8FC`): el personaje se ve bien, pero las barras y los puntos pierden visibilidad. Con `[data-tema="claro"]` se oscurecen en la copia del SVG: barras en `#0E7C7B` y puntos en `#B45309`.

Hay que editar el SVG una vez (añadir `<g>` de animación). Se hace en una copia dentro del repo, no en el kit original.

### 3.5 Pivotes

Coordenadas del `viewBox`, con `transform-box: view-box`:

| Pieza | Pivote | Origen | Nota |
|---|---|---|---|
| Brazo y mano izquierdos | `356, 810` | Kit | Probado: la mano sigue al brazo |
| Brazo y mano derechos | `763, 810` | Kit | Probado a -28°; mano toca el auricular. Usar hasta -22° |
| Muñeca izquierda (mano sola) | `214, 812` | Kit | Sin probar aún |
| Muñeca derecha (mano sola) | `909, 812` | Kit | Sin probar aún |
| Cabeza y pin | `552, 766` | Propio (cuello) | Probado a 3°. El kit sugiere `560, 511`, que gira desde el centro |
| Pin solo | `552, 250` | Kit | Base del pin |
| Cejas | `412, 432` y `671, 432` | CSS del kit | Ya usados en `error` |
| Elementos pequeños | `transform-box: fill-box; transform-origin: center` | Kit | Ojos, barras, puntos, check |

---

## 4. Máquina de estados

El kit trae cinco estados. Los nombres de la propuesta se unifican así: `idle` = `reposo`, `listening` = `escuchando`, `thinking` = `pensando`, `success` = `resuelto`, `escalation` = `escalamiento`. Se añade `reposo`, que no requiere CSS nuevo: al no coincidir con ninguna regla, muestra ojos abiertos y boca normal sin indicador (comprobado).

| Estado | `data-state` | Entra cuando | Sale cuando |
|---|---|---|---|
| **Reposo** | `reposo` | Se abre la app, o pasan 4 s desde `resuelto` | El usuario escribe o envía |
| **Escuchando** | `escuchando` | Hay texto en el campo y actividad en los últimos 2 s | Envía, o deja de escribir |
| **Pensando** | `pensando` | Se envió la consulta y no hay respuesta final | Llega resultado, escalación o error |
| **Resuelto** | `resuelto` | Evento `fin` sin escalamiento y sin formulario pendiente | 4 s, o el usuario escribe |
| **Escalamiento** | `escalamiento` | Llega el evento SSE `escalamiento` | Evento `escalamiento_resuelto` |
| **Error** | `error` | Falla de red, tiempo de espera o respuesta 5xx | Reintento o conexión recuperada |

**Prioridad cuando coinciden:** `escalamiento` > `error` > `pensando` > `resuelto` > `escuchando` > `reposo`.

**Reglas:**
- El estado se deriva de datos de la conversación, nunca de un temporizador que simule progreso.
- `escuchando` por teclado es señal de actividad. No se presenta como captura de micrófono (advertencia del kit).
- Permanencia mínima de 300 ms para evitar parpadeos en respuestas muy rápidas.
- `resuelto` no se activa si el turno emite un formulario: todavía faltan datos. En ese caso vuelve a `reposo`.
- **No existe un estado "con dudas".** Corrige una propuesta anterior: `CRIT-001` escala de inmediato con confianza menor a 0.75, así que ese caso entra directo a `escalamiento`.

**Subfases de `escalamiento`,** en `data-fase`:

| Fase | Texto | Condición en el backend |
|---|---|---|
| `transfiriendo` | "Estoy solicitando la ayuda de un asesor." + `mensaje` literal, espera y posición en la fila | Evento `escalamiento` y artifact `aviso_escalamiento` |
| `conectado` | "Un asesor ya está contigo." | **Primer `mensaje_asesor`.** No hay evento al tomar el caso |
| `resuelto` | "El asesor cerró tu caso." + encuesta | Evento `escalamiento_resuelto` |

Si `POST /chat/.../mensajes` responde 503 o 504, el backend escala con aviso (RF-ESC-7): se trata como escalamiento y no como error definitivo. No se usa un estado `no_disponible`: el backend no lo emite.

---

## 5. Catálogo de animaciones

**Técnica:** CSS para bucles y entradas, y Web Animations API para secuencias o gestos que se interrumpen. La propuesta deja GSAP como opción; solo se añade si estas dos no alcanzan para la transición de la portada. Solo se animan `transform` y `opacity`.

**Curvas:**

| Token | Valor | Uso |
|---|---|---|
| `--ease-out` | `cubic-bezier(.2, .9, .2, 1)` | Entradas (de Hex) |
| `--ease-spring` | `cubic-bezier(.22, 1.35, .36, 1)` | Rebotes, tecla (de Hex) |
| `--ease-soft` | `cubic-bezier(.45, 0, .55, 1)` | Bucles suaves |

### 5.1 Vida de fondo (se mantiene en todos los estados)

| Animación | Pieza | Movimiento | Tiempo | Repetición |
|---|---|---|---|---|
| Flotación | `flotacion` | `translateY` de 0 a -8 px | 3.2 s, `--ease-soft` | Infinita, alternada |
| Parpadeo | `ojos_abiertos` | `scaleY` 1 → 0.08 → 1 | 140 ms | Aleatorio cada 3–6 s |
| Doble parpadeo | `ojos_abiertos` | El mismo, dos veces | 400 ms | 1 de cada 5 |
| Oscilación del pin | `pin_ubicacion` | `rotate` ±2° | 4 s, `--ease-soft` | Infinita, desfasada de la flotación |

### 5.2 Entradas y gestos

| Gesto | Cuándo | Piezas | Movimiento | Tiempo |
|---|---|---|---|---|
| **Aparición** | Primera carga | `#ruti` | `translateY` 24 px → 0, `opacity` 0 → 1 | 420 ms, `--ease-out` |
| **Caída del pin** | Tras la aparición | `pin_ubicacion` | `translateY` -60 → 0 con rebote | 480 ms, `--ease-spring` |
| **Saludo** | Tras la caída, una vez por sesión | `brazo_derecho` + `mano_derecha`; mano sola | Brazo a -22°; muñeca ±14° dos veces; regreso | 1.1 s |
| **Mirada al campo** | Foco en el campo | Pupilas | Desplazamiento hasta 6 px hacia el campo | 200 ms |
| **Señalar tarjeta** | Llega una tarjeta (solo escritorio) | Brazo y mano del lado del chat | Rotación de 10°, se sostiene 600 ms | 900 ms |
| **Celebración** | Se crea un ticket o termina una cotización | `flotacion` | Salto de -18 px con rebote | 420 ms |

### 5.3 Animación propia de cada estado

**Reposo**
- Solo vida de fondo. Mirada que cambia cada 5–8 s, máximo 6 px.

**Escuchando**
- `barras_audio`: cada barra hace `scaleY` entre 0.5 y 1.25, 700 ms en bucle, con desfases de 0, 120 y 240 ms.
- Atado a la escritura: las barras se pausan si deja de escribir.
- Cabeza y pin: inclinación de 2° hacia el campo, 240 ms.
- Pupilas: siguen al campo.

**Pensando**
- `puntos_ambar`: `opacity` 0.25 → 1 por turno, 1.1 s, desfases de 0, 180 y 360 ms.
- Pupilas: suben 10 px (CSS del kit) con vaivén horizontal de ±4 px cada 1.8 s, mediante un envoltorio.
- `pin_ubicacion`: pulso de `scale` 1 → 1.06, 1.2 s.
- Cabeza y pin: inclinación de 3°.
- A los **8 s** el texto de apoyo cambia a "Sigo buscando, ya casi". A los **20 s**: "Esto está tardando más de lo normal", con opción de reintentar. Nunca finge progreso.

**Resuelto**
- `check_ambar`: `scale` 0 → 1.15 → 1, 420 ms, `--ease-spring`.
- `ojos_cerrados` y `boca_resuelto`: aparecen con fundido de 150 ms.
- `flotacion`: salto único de -14 px.
- Tras 4 s, vuelve a `reposo`.

**Escalamiento** (tono tranquilo; no es una alarma)
- `derivacion_humana`: entra con `scale` de 0.7 a 1 y fundido, 400 ms, `--ease-out`.
- Cabeza y pin: inclinación de 4° hacia el mensaje, para mostrar atención.
- Brazo y mano: suben a -14° como gesto de apoyo.
- Cejas: **ligeramente levantadas por dentro** (±6°), para no confundirse con `error`.
- Una onda circular sale una sola vez desde la tarjeta de traspaso (`scale` 0.8 → 1.6, `opacity` 0.5 → 0, 900 ms), en violeta. Es el momento memorable de la demo.
- Fase `conectado`: `derivacion_humana` hace un rebote único; RUTI baja el brazo y queda en un costado.

**Error**
- `sin_conexion`: pulso lento de `opacity` 0.6 → 1, 1.8 s.
- Cejas: 13° (CSS del kit).
- Flotación reducida a 3 px y a 5 s.
- Sin sacudidas: no debe sentirse como un regaño.
- El mensaje y el botón "Reintentar" son obligatorios.

**Cómo se distinguen escalamiento y error:**

| Rasgo | Escalamiento | Error |
|---|---|---|
| Cejas | Levantadas, 6° | Fruncidas, 13° |
| Cuerpo | Se inclina y levanta el brazo | Quieto, flotación baja |
| Indicador | Persona, entrada única | Exclamación, pulso lento |
| Color del indicador | Violeta, en la copia del SVG | Rojo, en la copia del SVG |
| Interfaz | Tarjeta de traspaso | Banda de error |
| Acción | Seguir esperando | Reintentar |

### 5.4 Transiciones

| De → a | Comportamiento |
|---|---|
| Cualquiera → `pensando` | Cambio inmediato: confirma que se recibió el envío |
| `pensando` → `resuelto` | Fundido de 150 ms en cara y entrada del check. La tarjeta aparece 120 ms después |
| `pensando` → `escalamiento` | Pausa de 200 ms con la cara neutra, luego el gesto. El tono no debe ser brusco |
| Cualquiera → `error` | Cambio inmediato, sin onda ni salto |
| `error` → `pensando` | Inmediato al pulsar Reintentar |

Al interrumpir un gesto, se cancela con WAAPI y regresa a su pose base en 180 ms.

### 5.5 Animaciones de la interfaz

| Elemento | Animación | Tiempo |
|---|---|---|
| **Botón enviar** (tecla física de Hex) | Hover: baja 1.5 px. Presión: baja 3 px, `scale(1.03, .94)`, brillo turquesa. Soltar: rebote | 110 ms, `--ease-spring` |
| **Mensaje del usuario** | Sube 8 px y aparece | 180 ms |
| **Respuesta de RUTI** | Las palabras se materializan: `opacity`, `blur` 4 → 0 y 4 px de desplazamiento, por lotes de 3–5 palabras | 220 ms por lote |
| **Tarjeta de resultado** | Sube 12 px y aparece; las filas entran con 40 ms de desfase | 320 ms, `--ease-out` |
| **Línea de ruta de la guía** | La línea se dibuja hasta el estado actual; ese punto late | 600 ms |
| **Totales de cotización** | El total aparece al final del desglose, sin conteo falso | 200 ms |
| **Portada → Centro de servicios** | RUTI viaja y se reduce con FLIP; el fondo oscuro cede al claro con un fundido. Sin bloquear la interacción | 420–600 ms |
| **Tarjeta de servicio** | Sube 2 px al pasar el cursor; presión física | 160 ms |
| **Pasos** | El siguiente paso entra desde la dirección de avance; al volver, desde la contraria | 240 ms |
| **Actividad en consulta** | Indicador indeterminado. **Nunca barra parcial sin datos reales** | Bucle |
| **Copiar guía** | El icono cambia a check durante 1.5 s | 160 ms |

El `blur` puede costar en móviles de gama baja. Se limita a respuestas de hasta 80 palabras y se quita si baja el rendimiento en la prueba de la sección 15.

### 5.6 Movimiento reducido

Con `prefers-reduced-motion: reduce`, y también con un interruptor "Reducir movimiento" en la app, guardado en `localStorage`:

| Normal | Reducido |
|---|---|
| Flotación, pin, mirada aleatoria | Desactivados |
| Parpadeo | Desactivado |
| Cambio de expresión | Se mantiene, con corte directo |
| Indicadores | Visibles, sin bucle |
| Saludo, salto, onda | Desactivados |
| Materialización del texto | Aparece completo |
| Tarjetas | Solo fundido de 120 ms |

Lo que nunca cambia: estado, texto y acciones.

### 5.7 Rendimiento

- Mientras el usuario llena un formulario, RUTI queda en movimiento mínimo y nunca desplaza controles.
- Se pausa todo con `document.hidden` y cuando RUTI queda fuera de pantalla (`IntersectionObserver`).
- Sin animar `filter` en bucle ni propiedades de layout.
- Máximo 6 animaciones en bucle a la vez.
- Se prueba con CPU limitada a 4x en Chrome.

---

## 6. Sistema visual

Dos ambientes y una identidad, según la propuesta. Contrastes calculados; ver ajuste 5 de la sección 0.

**Marca y portada**

| Token | Valor | Uso | Contraste |
|---|---|---|---|
| `--navy-950` | `#081B2F` | Fondo de portada | — |
| `--navy-800` | `#123B57` | Superficies oscuras | Blanco encima: 11.74 |
| `--teal-500` | `#18C7C2` | Rutas, RUTI y acentos | Sobre navy: 8.27. **Sobre blanco: 2.1, nunca como texto** |
| `--amber-400` | `#FFBD59` | Botón de portada | Texto `--navy-950` encima: 10.49. **Blanco encima: 1.66, prohibido** |

**Aplicación clara**

| Token | Valor | Uso | Contraste |
|---|---|---|---|
| `--bg` | `#F5F8FC` | Fondo | — |
| `--card` | `#FFFFFF` | Tarjetas y formularios | — |
| `--ink` | `#11243D` | Texto principal | 14.67 sobre `--bg` |
| `--muted` | `#60748A` | Texto secundario | 4.52 sobre `--bg`, 4.81 sobre blanco. Es el límite: no usar más claro |
| `--primary` | `#2563EB` | Acción principal | Blanco encima: 5.17 |
| `--teal-700` | `#0E7C7B` | Teal para texto e iconos pequeños | 5.01 sobre blanco |

**Semánticos,** siempre con icono y texto:

| Estado | Del moodboard, solo como fondo decorativo | Para texto e iconos (cumple AA) | Contraste sobre blanco: moodboard / ajuste |
|---|---|---|---|
| Éxito | `#10B981` | `#047857` | 2.54 / 5.48 |
| Error | `#EF4444` | `#B91C1C` | 3.76 / 6.47 |
| Advertencia | `#F59E0B` | `#B45309` | 2.15 / 5.02 |
| Asesor | `#8B5CF6` | `#6D28D9` | 4.23 / 7.1 |
| Información | `#2563EB` | `#1D4ED8` | 5.17 / 6.7 |

**Tipografía:** Inter Variable, autoalojada y con `font-display: swap`; fallback del sistema. Guías y montos con `ui-monospace` y cifras tabulares.

| Uso | Tamaño |
|---|---|
| H1 de portada | `clamp(2.5rem, 6vw, 4.75rem)`, peso 700, tracking `-.03em`, máximo 3 líneas |
| Títulos de pantalla | `clamp(1.5rem, 3vw, 2rem)`, peso 600 |
| Texto y mensajes | `1rem` mínimo |
| Etiquetas | `.875rem`, peso 500 |
| Metadatos | `.75rem`, nunca para información crítica |

**Otros:** radios de 12 a 20 px, sombras discretas y bordes ligeros. Espaciado en base 4 px. Áreas táctiles de 44 px como mínimo. Una sola familia de iconos lineales: caja, camión, ubicación, conversación y documento. Sin Lottie, sin 3D y sin audio automático.

**Fondo de portada:** ruta luminosa fina en SVG y luz tenue con CSS. Las fotos e imágenes del moodboard no se usan en la app sin confirmar su origen y licencia.

---

## 7. Estructura de la interfaz

### 7.1 Pantallas

| Pantalla | Contenido | RUTI |
|---|---|---|
| **A. Portada** | H1, subtítulo, 2 botones y opción de saltar la intro | Protagonista, saludo |
| **B. Centro de servicios** | "¡Hola! Soy RUTI, ¿qué necesitas hoy?" y 4 tarjetas | Tamaño medio |
| **C. Consultar envío** | Campo de guía → actividad → `TrackingCard` | Pequeño, reacciona |
| **D. Cotizar** | Origen y destino → medidas y peso → valor → resumen → `QuoteCard` | Pequeño, sin desplazar controles |
| **E. Resolver dudas** | Chat con sugerencias, fuentes y campo persistente | Cabecera o panel |
| **F. PQRS** | Tipo de caso → requisitos → formulario → `TicketCard` | Pequeño |
| **Capa global: traspaso** | `HandoffCard` sobre cualquier pantalla, conservando historial | `escalamiento` |
| **Capa global: conexión** | Banda superior; se conserva lo escrito | `error` |

**Navegación:** `Inicio`, `Consultar envío`, `Cotizar`, `Ayuda` y `PQRS`. Acceso a "Hablar con RUTI" y a "Hablar con un asesor" siempre visible; este último envía la solicitud al backend (`CRIT-002` incluye "hablar con humano"). Rutas con URL propia para que funcione el botón Atrás y el refresco.

**Textos de la portada:**
- H1: **Tu logística, más simple e inteligente.**
- Subtítulo: **Consulta tus envíos, cotiza y resuelve dudas con la ayuda de RUTI.**
- Botón principal: **Conversar con RUTI**
- Botón secundario: **Explorar servicios**

La portada no bloquea el contenido: el texto se pinta de inmediato y el SVG va inline. Se recuerda en la sesión si el usuario ya la vio.

### 7.2 Layouts

| Ancho | Disposición | RUTI |
|---|---|---|
| **360–767 px** | Una columna, sin desplazamiento horizontal; menú compacto. Campo del chat fijo con `safe-area-inset-bottom` y `dvh` | Portada: 180 px. Flujos: 56 px, se puede minimizar |
| **768–1023 px** | Tarjetas en una o dos columnas | Portada: 280 px. Flujos: 72 px |
| **1024 px o más** | Portada dividida; flujos con columna principal y área de ayuda | Portada: hasta 480 px. Flujos: 200 px en el área de ayuda |

Dispositivos de prueba: **390×844, 768×1024 y 1440×900**, más 360 px. Se reubica la misma instancia del SVG entre pantallas con FLIP.

### 7.3 Componentes

| Componente | Función |
|---|---|
| `Ruti` | SVG inline, recibe `state`, `fase`, `encuadre` |
| `RutiStatus` | Texto del estado: "Buscando la mejor respuesta…" |
| `ChatThread`, `Message`, `Composer` | Conversación, mensajes y campo con botón físico |
| `HeroLanding`, `ServiceCenter`, `ServiceCard` | Portada y centro de servicios |
| `GuidedForm`, `Stepper`, `FieldError` | Formularios por pasos |
| `SuggestionChips` | Sugerencias iniciales del chat |
| `AssistantPanel` | Área de ayuda con RUTI en escritorio |
| `TrackingCard` | Rastreo |
| `QuoteCard` | Cotización |
| `ComplianceCard` | Normativa |
| `PqrsChecklist`, `TicketCard` | PQRS |
| `HandoffCard` | Traspaso |
| `ErrorBanner`, `ConnectionStatus` | Errores y conexión |
| `InstallPrompt` | Instalar la PWA |

### 7.4 Accesibilidad

- El historial es `role="log"` con `aria-live="polite"`.
- `RutiStatus` anuncia los cambios: máximo un anuncio cada 2 s, sin anunciar `escuchando`.
- Errores y escalación usan `role="alert"`.
- Navegación completa por teclado: `Enter` envía, `Shift+Enter` crea línea nueva, foco siempre visible.
- Al llegar una respuesta, el foco se queda en el campo.
- Los errores van junto al campo afectado, con etiqueta asociada; se conserva lo escrito.
- Los montos se leen completos: "$ 49.900 pesos colombianos".
- Objetivo: WCAG 2.2 AA.

### 7.5 Copy de RUTI

Español de Colombia, tuteo, frases cortas y sin promesas falsas.

| Estado | Texto |
|---|---|
| Reposo | "¿En qué te ayudo?" |
| Escuchando | "Te leo." |
| Pensando | "Estoy consultando la información…" |
| Resuelto | "¡Listo! Aquí tienes el resultado." |
| Error de red | "No pude completar la consulta. ¿Reintentamos?" + **Reintentar** |
| Mensajes de escalación | Se usan los de `reglas_escalacion_humana.json`, sin reescribirlos |

---

## 8. Módulos y tarjetas

Cada flujo indica la secuencia de RUTI. Los datos vienen de `KODOTAKAIINFO/`.

**Regla común:** cada servicio se puede iniciar desde su pantalla o desde el chat, y ambos caminos muestran la misma tarjeta. Es la forma de cumplir el pedido de una IA conversacional sin perder la claridad de los formularios. Cualquier respuesta puede activar el traspaso.

**Correspondencia con el contrato:** `TrackingCard` = `linea_tiempo_envio` + `mapa_ubicacion`; `QuoteCard` = `formulario_cotizacion` + `resultado_cotizacion`; `ComplianceCard` = `veredicto_mercancia` + `guia_embalaje`; `PqrsChecklist` = `formulario_pqrs` + `estado_plazo` + `checklist_documentos`; `TicketCard` = `ticket_pqrs`; `HandoffCard` = `aviso_escalamiento`. Además: `ficha_cobertura`, `citas`, `respuestas_rapidas`, `confirmacion` y `encuesta_satisfaccion`. Las etiquetas de estado de 8.1 solo son respaldo: el backend envía `estado_texto`.

**Cotización por pasos:** el servidor emite un solo formulario y valida un solo envío. Los pasos son una agrupación visual de sus campos en la interfaz, no peticiones separadas.

**Mapa:** `mapa_ubicacion` siempre muestra `referencia` en texto. Un mapa con teselas externas depende de internet y envía coordenadas a terceros, en contra de la idea de IA local. Se recomienda un mapa esquemático propio; Leaflet con OSM queda como opción.

### 8.1 Rastreo

- **Disparador:** pantalla "Consultar envío", o un texto en el chat con el patrón `TLX-XXXXXX-CO`.
- **Flujo:** `Datos → Consultando → Resultado`; botón deshabilitado durante el envío y dato conservado si falla.
- **Secuencia:** `escuchando → pensando → resuelto`, o `escalamiento`.
- **Validación:** si el formato es inválido, el mensaje lo dice antes de enviarlo y da un ejemplo.

`TrackingCard`:

| Bloque | Fuente en el dataset |
|---|---|
| Guía y botón copiar | `numero_guia` |
| Estado en lenguaje natural | Generado por el backend |
| Línea de ruta | `historial_trazabilidad[]` |
| Origen → destino | `remitente.ciudad_origen`, `destinatario.ciudad_destino` |
| Ubicación actual | `ubicacion_gps_actual.referencia` |
| Fecha estimada | `fecha_estimada_entrega` |
| Servicio | `especificaciones_carga.tipo_servicio` |
| Prueba de entrega | `prueba_entrega` (si existe) |

Los datos personales no se muestran completos sin que el backend lo autorice.

| Estado técnico | Etiqueta | Tono |
|---|---|---|
| `SOLICITUD_GENERADA` | Solicitud creada | Neutro |
| `RECOGIDO_EN_ORIGEN` | Recogido | Neutro |
| `EN_BODEGA_ORIGEN` | En bodega de origen | Neutro |
| `EN_TRANSITO` | En camino | Activo |
| `EN_BODEGA_DESTINO` | En bodega de destino | Activo |
| `EN_REPARTO` | En reparto | Activo |
| `ENTREGADO` | Entregado | Éxito |
| `RETENIDO_NOVEDAD` | Retenido con novedad | Alerta |
| `EN_INVESTIGACION_SINIESTRO` | En investigación | Alerta |
| Desconocido | "Actualización en proceso", y se registra en consola | Neutro |

### 8.2 Cotización

- **Datos:** origen, destino, alto, ancho y largo en cm, peso real en kg y valor declarado en COP. Con unidades visibles.
- **En formulario:** `Origen y destino → Medidas y peso → Valor declarado → Resultado`, con Atrás, Continuar y resumen editable.
- **En chat:** RUTI pide los datos de forma iterativa, como exige el módulo 2 del dosier.
- **Sin cobertura o datos inconsistentes:** explicación concreta, sin prometer el servicio.
- **Secuencia:** `pensando → reposo` en cada pregunta, y `resuelto` con la tarjeta final.
- **Regla:** el backend calcula todo. El front solo valida que los valores sean positivos y de formato correcto.

`QuoteCard`, con cada fila explicable:

| Fila | Contenido |
|---|---|
| Ruta | Origen → destino y tiempo estimado |
| Peso volumétrico | `(alto × ancho × largo) / 4000` |
| Peso a facturar | Máximo entre real y volumétrico, marcando cuál se usó |
| Flete base | Desde la matriz de tarifas |
| Seguro | Máximo entre 1 % y mínimo aplicable |
| Recargos | Cadena de frío o mercancía peligrosa, si aplica |
| **Total** | Destacado, en monoespaciada y formato COP |

Acción: **Nueva cotización**. Mostrar el cálculo responde al dolor del 12 % de errores en cotizaciones manuales.

### 8.3 Normativa de cargas especiales

- **Secuencia:** `pensando → resuelto`, o `escalamiento` si el backend lo decide.

`ComplianceCard` tiene tres veredictos:

| Veredicto | Ejemplo | Muestra |
|---|---|---|
| **Permitido** | Producto sin restricción | Requisitos de embalaje |
| **Con requisitos** | Ácido clorhídrico, Clase 8 | Clase ONU, límite, MSDS/HDS, tarjeta de emergencia NTC 4532 y remesa |
| **Prohibido** | Animales vivos, efectivo, armas, joyas, explosivos | Motivo, sin alternativa inventada |

También muestra la fuente: nombre del documento y sección, si el backend la envía. Esto refuerza la confianza en la demo.

### 8.4 PQRS

- **Primero:** tipo de caso (avería visible, avería oculta o pérdida) y guía.
- **Plazos:** el backend los valida; el front los explica:

| Caso | Plazo |
|---|---|
| Avería visible | Al momento de la entrega, anotada en la guía |
| Avería oculta | 3 días hábiles tras la entrega |
| Pérdida o siniestro | 10 días hábiles tras vencer la fecha de entrega |

`PqrsChecklist`, que ataca el 40 % de solicitudes incompletas:

| Documento | Formato |
|---|---|
| Número de guía | `TLX-XXXXXX-CO` |
| Factura comercial con IVA | PDF o JPG |
| Carta de reclamación firmada, con valor y descripción | PDF o JPG |
| Certificación bancaria de menos de 30 días | PDF o JPG |
| Fotos: empaque con etiqueta, daño y amortiguación | JPG |
| Documento de identidad o RUT | PDF o JPG |

- **Acción:** **Crear ticket** se activa cuando el backend confirma lo necesario. Si falta algo, RUTI dice qué.
- **`TicketCard`:** número de ticket, estado y plazo de respuesta (15 días hábiles). Con `Celebración`.
- **Alcance a confirmar:** subir archivos depende de que el backend lo soporte. Si no, la lista funciona como guía.

### 8.5 Traspaso a un asesor

Es obligación expresa de la PWA según el dosier. Es una capa global, no parte de PQRS. El front aplica la decisión del backend:

| Criterio | Regla | Destino | Prioridad |
|---|---|---|---|
| `CRIT-001` | `confidence_score < 0.75` | Especialista | Normal |
| `CRIT-002` | Lenguaje agresivo o palabras clave | Supervisor | Alta |
| `CRIT-003` | Valor mayor a $5.000.000 COP, **solo en el flujo PQRS** (D-12) | Gestor senior de PQRS | Media |
| `CRIT-004` | Más de 500 envíos al mes o `CORPORATIVO_GOLD` | Ejecutivo de cuenta | Dedicada |
| `CRIT-005` | Mercancía peligrosa, o refrigerada retenida | Coordinador de operaciones | Urgente |

`HandoffCard`:

| Bloque | Contenido |
|---|---|
| Motivo | `mensaje_cliente` exacto de la regla |
| Destino | Quién toma el caso |
| Espera | Estimada en 45 s, según las reglas |
| Resumen | Resumen de contexto generado por el backend |
| Garantía | "Tu conversación completa pasa al asesor" |

El payload para el asesor (`session_id`, guía, confianza promedio, sentimiento e intentos) lo arma el backend; el front no lo expone. El historial siempre se conserva.

---

## 9. Contrato con el backend

**Ya no es una propuesta: es lo que está en `main`.** El contrato completo está en `docs/frontend.md` y `docs/openapi.json`; los tipos TypeScript se generan con `npm run gen:api`, y el build falla si un tipo de artifact queda sin registrar.

**Idea central: generative UI.** El chat responde con artifacts, objetos tipados que el front pinta como componentes. Las cifras y los veredictos salen de código; el LLM solo redacta. Esto resuelve la decisión pendiente: **todo pasa por el chat**. Rastreo, cotización y PQRS no llaman a los REST del TMS desde la interfaz, porque esos no evalúan escalación.

```text
POST /api/v1/chat/sesiones                    → crea la sesión
POST /api/v1/chat/sesiones/{id}/mensajes      → SSE: meta, artifact, delta, reemplazo, citas, escalamiento, fin, error
GET  /api/v1/chat/sesiones/{id}               → historial para reconstruir la UI
GET  /api/v1/chat/sesiones/{id}/eventos       → SSE: mensaje_asesor, escalamiento_resuelto
POST /api/v1/chat/sesiones/{id}/calificacion  → CSAT 1-5
```

**Reglas que el front debe respetar:**

| Regla | Dónde está en `frontend/` |
|---|---|
| El mensaje es POST: se lee con `fetch`, no con `EventSource` | `src/services/sse.ts` |
| `reemplazo` sustituye **todo** el texto del turno | `src/state/chatStore.ts` |
| Si el stream se corta, **no se reenvía**: se reconcilia con el historial | `src/hooks/useChat.ts` |
| Un stream en silencio más de 60 s se da por muerto (añadido: un proxy puede no propagar el corte) | `src/services/sse.ts` |
| Un 422 de formulario llega antes del stream y se pinta por campo | `src/features/artifacts/Formulario.tsx` |
| 429, 503 y 504 traen `Retry-After` | `src/services/http.ts` |
| Access token en memoria; el refresh rota y solo se usa uno a la vez | `src/services/http.ts` |
| Dinero y pesos llegan como **string decimal**: no sumar con `parseFloat` | Al construir las tarjetas |
| Tras reconectar `/eventos`, consultar el historial: lo publicado durante un corte no se reenvía | `src/services/chat.ts` |

**Permisos que afectan el flujo:**

| Rol | Puede | Efecto en la interfaz |
|---|---|---|
| Invitado | Chat, rastreo, cotización, mercancías | No se pide cuenta para lo principal |
| Cliente | + PQRS y detalle de sus guías | **PQRS exige iniciar sesión:** el backend lo dice en el chat; hay que llevar al login y volver |
| Asesor | Cola, tomar, responder y resolver | **Vista propia, necesaria para la demo** |
| Admin | Métricas, chat admin, RAG, ML | **Vista propia:** el pitch muestra allí las latencias |

**Vacíos del contrato que el front ya contempla:**
- No hay evento cuando el asesor toma el caso; se recomienda añadirlo para mostrar `conectado` antes del primer mensaje.
- `/eventos` publica en memoria y no reenvía: un mensaje enviado durante un corte solo se recupera con el historial.
- El historial devuelve `artifacts` como objetos sin tipar; se confía en que coinciden con la unión.

---

## 10. PWA

- **Manifest:** nombre "TransLogix · RUTI", nombre corto "RUTI", `display: standalone`, tema `#0C1928`.
- **Iconos:** pin de RUTI sobre fondo `#0C1928`, en 192, 512 y `maskable`.
- **Service worker:** cachea el shell y los recursos estáticos. **Nunca cachea respuestas del chat ni de tracking.**
- **Sin conexión:** la app abre, muestra el historial local y RUTI en `error`.
- **Historial local:** `sessionStorage`, sin guardar datos sensibles entre sesiones.
- **Instalación:** botón discreto tras la primera consulta resuelta.
- **Voz (opcional):** `POST /voz/transcribir` y `/voz/sintetizar` existen, pero requieren el clúster de voz y contexto seguro. Si se añade, las barras de `escuchando` pasan a ser reales. Se hace solo con todo lo demás listo.
- **Omnicanal:** el dosier pide una PWA "ligera y omnicanal". Esta PWA cubre web y móvil. Un adaptador de WhatsApp o PBX queda fuera del alcance y se explica en el pitch como evolución, salvo que el equipo decida otra cosa.

---

## 11. Arquitectura propuesta

**Stack recomendado:** Vite, React y TypeScript, igual que la propuesta. Para estilos, una sola estrategia: CSS Modules con variables CSS, aunque Tailwind también sirve si el equipo lo domina. Más `vite-plugin-pwa` y React Router. Es a confirmar: `AGENTS.md` exige fijarlo en `docs/collaboration.md`.

```text
frontend/
├── public/icons/            iconos de la PWA, a partir del pin de RUTI
├── src/
│   ├── app/App.tsx          rutas
│   ├── assets/ruti/ruti.svg SVG del kit
│   ├── components/
│   │   ├── layout/          AppShell, RutaRol
│   │   ├── ruti/            Ruti, RutiStatus, ruti.css
│   │   └── ui/              compartidos
│   ├── features/
│   │   ├── artifacts/       registro.tsx: un componente por tipo; Formulario, AvisoEscalamiento, Pendiente
│   │   ├── chat/            Conversacion
│   │   ├── asesor/          PanelAsesor
│   │   └── admin/           PanelAdmin
│   ├── hooks/               useChat, useAuth
│   ├── pages/               Landing, CentroServicios, Servicio, Login
│   ├── services/            api.d.ts (generado), http, sse, chat, auth
│   ├── state/               chatStore, rutiMachine
│   └── styles/              tokens.css, base.css
└── tests/                   sse, chatStore, rutiMachine
```

**Flujo de datos:**

```text
Pantallas y chat → useChat + chatStore → services → backend
                         │
                         ├→ registro de artifacts → componente de cada tipo
                         └→ rutiMachine (deriva el estado) → Ruti y RutiStatus
```

`rutiMachine` es una función pura: `(petición activa, respuesta, red, escritura) → { state, fase }`. Se prueba sin navegador. Es el punto que conecta datos reales con la mascota y lo que sustenta el criterio de Innovación.

---

## 12. Lo que se toma de Hex

| Se toma | Forma en este proyecto |
|---|---|
| Un foco por pantalla | Portada con RUTI, titular y una acción principal |
| Tecla física | Botón enviar |
| Texto que se materializa | Respuestas de RUTI |
| Tensión que crece en el personaje | Estados que reaccionan a datos reales |
| Panel con filas | Filas de las tarjetas de resultado |

| No se toma | Motivo |
|---|---|
| Personaje, textos y secuencia | Riesgo de "copia directa" en el criterio 3 |
| Explosiones y pantalla rota | Tapan información y afectan usabilidad |
| Más de 90 archivos de audio | Va contra una PWA ligera |
| Fondo negro neutro | La portada es azul marino y la aplicación es clara |

---

## 13. Plan de construcción

**Si falta tiempo, se sacrifican animaciones decorativas antes que rastreo, cotización, chat, errores, responsive o traspaso.**

| Fase | Entregable | Criterio | Estado |
|---|---|---|---|
| **1. Base** | Proyecto, tipos del contrato, rutas, SSE, sesión, errores, PWA | 1, 2 | **Hecha**, probada con el backend real y un modelo simulado |
| **2. RUTI base** | SVG inline, `rutiMachine`, 6 estados, movimiento reducido | 3 | **Hecha** |
| **3. Portada y servicios** | Estructura, navegación y demostración de RUTI (`features/portada/show.ts`) | 2, 3 | **Hecha**; falta probar la voz con el clúster |
| **4. Prueba con el LLM real** | Correr los flujos en la máquina principal: textos, confianza, RAG y latencias reales | 1 | **Siguiente paso** |
| **5. Rastreo** | `linea_tiempo_envio` y `mapa_ubicacion` | 1, 2 | Pendiente |
| **6. Traspaso y asesor** | Tarjeta global y `/asesor`: cola, tomar, responder, resolver | 1, 3 | Pendiente, P0 |
| **7. Cotización** | Pasos, `resultado_cotizacion`, `/trayectos/destinos` | 1, 2 | Pendiente, P0 |
| **8. Normativa y acciones** | `veredicto_mercancia`, `guia_embalaje`, `citas`, `respuestas_rapidas`, `confirmacion`, `ficha_cobertura` | 1, 3 | Pendiente, P0 |
| **9. PQRS** | `formulario_pqrs`, `estado_plazo`, checklist con carga, `ticket_pqrs`, ida y vuelta del login | 1, 2 | Pendiente, P1 |
| **10. Admin** | `/admin`: `tarjetas_kpi`, latencias, `tabla_datos`, `cola_escalamientos` | 3, 5 | Pendiente, P1 |
| **11. Experiencia** | Gestos, FLIP, materialización, Inter autoalojada, pulido con `impeccable` | 2, 3 | Pendiente, P1 |
| **12. Demo** | Guion, respaldo, ensayo | 5, 6 | Pendiente |
| **Opcional** | `grafico`, `tarjeta_prediccion`, `metricas_modelo`, voz, demo guiada | 3 | P2 |

`Pendiente.tsx` muestra lo que aún no tiene componente; no debe aparecer en la demo.

**Flujo de trabajo:** el `AGENTS.md` vigente ya no usa Issues ni reparto entre agentes: define commits directos en `main` para el backend y dice que el front lo hace otro grupo. Falta acordar cómo se integra `frontend/`. Sus reglas de seguridad y de Git (sin force-push, staging explícito) se respetan igual.

**Para probar con el backend real:** `make up`, `make migrate`, `make seed` y `make dev` en la raíz, con `.env` y el clúster LLM activos; luego `npm run dev` en `frontend/`.

---

## 14. Guion de demo

`docs/negocio.md` §8 fija un **pitch de 5 minutos**, con 1:30 de demo. El front se ajusta a él:

| # | Acción | RUTI | Mensaje al jurado |
|---|---|---|---|
| 1 | Portada y entrada al chat | Saluda | Una experiencia, un copiloto |
| 2 | `TLX-984021-CO` | `pensando → resuelto` | Línea de tiempo y ubicación al instante |
| 3 | "Quiero cotizar" | Formulario → $190.975 | Idéntico al cálculo manual |
| 4 | "¿Puedo enviar un perro?" | Prohibido, con cita | El código decide; el modelo redacta |
| 5 | "Esto es una estafa" | `escalamiento` | Transferencia con contexto |
| 6 | El asesor responde desde `/asesor` | `conectado` | Una persona que ya sabe todo |
| 7 | Panel `/admin` | — | Latencias medidas en pantalla |

El total de $190.975 corresponde a paquetería; con cadena de frío es $207.468,75. Con D-12, `TLX-984021-CO` ya no escala por valor declarado. Para la demo se necesitan **dos ventanas o dispositivos** (cliente y asesor), y un video de respaldo por si falla la red. Las cifras del dosier se presentan como problema del caso, no como resultados medidos de la solución.

---

## 15. Comprobación final

**Responsive**
- [ ] Sin desbordes a 360, 390, 768, 1024 y 1440 px.
- [ ] Portada y aplicación se sienten como un solo producto.
- [ ] Campo visible con el teclado móvil abierto (Android y iOS real).
- [ ] RUTI no tapa contenido en ningún tamaño.

**Integración**
- [ ] Cada petición muestra: enviando, respuesta y error.
- [ ] Probado con backend apagado, red lenta 3G y respuesta de más de 20 s.
- [ ] Reintentar no duplica mensajes.
- [ ] Cada una de las 5 guías muestra datos correctos.
- [ ] Una guía inexistente y una cotización sin cobertura dan mensajes claros.
- [ ] Sin llamadas duplicadas y sin spinners infinitos.
- [ ] El traspaso funciona desde chat, rastreo, cotización y PQRS.

**RUTI**
- [ ] Los 6 estados corresponden a datos reales.
- [ ] Prioridad de estados correcta si hay varias señales.
- [ ] El pin sigue a la cabeza y la mano sigue al brazo.
- [ ] `conectado` solo aparece tras la confirmación del backend.
- [ ] Movimiento reducido probado.

**Accesibilidad**
- [ ] Flujo completo solo con teclado.
- [ ] Probado con lector de pantalla (NVDA u Orca).
- [ ] Lighthouse: accesibilidad ≥ 95.
- [ ] Los indicadores de RUTI se distinguen sobre fondo claro.

**PWA y rendimiento**
- [ ] Instalable en móvil real.
- [ ] Abre sin conexión.
- [ ] Lighthouse: rendimiento ≥ 90 en móvil, LCP < 2.5 s, CLS < 0.1.
- [ ] Sin caídas visibles con CPU limitada a 4x.

**Competencia**
- [ ] README con comandos, URLs, variables públicas y limitaciones conocidas.
- [ ] Compilación, lint y pruebas acordadas en verde.
- [ ] Ninguna calificación se da por hecha antes de probar el front integrado.
- [ ] Los datos simulados están etiquetados como tales.
- [ ] Dos ensayos completos sin fallos.

---

## 16. Pendientes

**Resuelto por el backend:** contrato del chat, `CRIT-003` solo en PQRS (D-12), seguro mínimo por ruta del CSV (D-01), adjuntos de PQRS, texto natural del rastreo (`estado_texto`), asesor real con cola, plazo por pérdida 5 + 10 días (D-08) y tiempo del pitch.

| # | Asunto | Impacto | Responsable |
|---|---|---|---|
| 1 | **Probar con el LLM y los embeddings reales.** La API, la base de datos, los formularios, el asesor y los errores ya se probaron de verdad, pero con un modelo falso | Faltan redacción real, RAG real, `CRIT-001` y latencias | Equipo, en la máquina principal |
| 2 | **Exposición de la API (D-18).** Escucha en loopback. Si el front o la demo corren en otro equipo o en un móvil, hay que decidir LAN o túnel. El micrófono y la instalación de la PWA exigen HTTPS fuera de `localhost` | Bloquea la demo en un móvil real | Dueño del backend |
| 3 | **Flujo de Git para `frontend/`.** `AGENTS.md` habla solo de backend | Definir antes del primer commit | Equipo |
| 4 | **`mercancia_peligrosa` en cotización.** Validar con el backend real si cotizar ese servicio escala por `CRIT-005` | Evitar sorpresas en la demo | Front |
| 5 | **Fila 6 de la rúbrica cortada** en el PDF | Falta su contenido | Equipo |
| 6 | **Evento "asesor tomó el caso"** no existe | Mejora opcional del traspaso | Backend |
| 7 | **Muñecas y gestos de mano** sin probar | Validar en la fase 11 | Front |
| 8 | **Inter** aún no está en el bundle: se ve la fuente del sistema | Fase 11 | Front |
| 9 | **Vulnerabilidades de npm:** 12 (2 bajas, 10 moderadas), todas en herramientas de desarrollo. `npm audit --omit=dev` reporta 0: no llegan al usuario | Revisar al actualizar dependencias | Front |
| 11 | **Formularios largos:** al llegar, la vista queda al final y el inicio del formulario queda fuera de pantalla | Resolver en la fase 7 | Front |
| 10 | **Origen de imágenes del moodboard** | No usar sin licencia | Front |

