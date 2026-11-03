# TransLogix IA: caso de negocio y pitch

Material para los criterios 3 a 6 de la rúbrica de Mejor Proyecto (innovación, viabilidad de negocio, pitch y preguntas del jurado).

Regla de este documento: **las cifras del dosier se citan como hechos; todo lo demás es un supuesto explícito** (marcado `S-xx`) o una medición del propio sistema. Los supuestos se reemplazan por datos reales del cliente antes de cualquier cotización comercial.

## 1. El problema, con las cifras del dosier

TransLogix Colombia S.A.S.: 45.000 despachos al mes, OTIF del 92,4 %, 480 vehículos y cobertura en 32 departamentos.

| Hecho (dosier §3) | Valor |
|---|---|
| Interacciones diarias | **18.000** (WhatsApp 60 %, web 25 %, PBX 15 %) |
| Espera en hora pico | **14,5 min** |
| Consultas repetitivas | **78 %** |
| Abandono del chat | **22 %** |
| «¿Dónde está mi guía?» | **55 %** de las interacciones |
| Errores en cotizaciones manuales | **12 %** |
| Tiempo de un agente buscando una condición en manuales | **4,5 min** |
| PQRS radicadas incompletas | **40 %** |

Lectura: casi 8 de cada 10 conversaciones son repetitivas y más de la mitad es rastreo, pero hoy todas esperan a un humano. El costo no es solo nómina: son cotizaciones mal calculadas (margen perdido), reclamos que se radican incompletos y vencen plazos legales (Art. 1028 C. Co.), y clientes que abandonan.

## 2. Propuesta de valor

Un agente de atención que **resuelve sin humano lo repetitivo y deja al humano lo que importa**, con IA que corre dentro de la empresa.

| Dolor | Qué hace el sistema | Resultado verificable |
|---|---|---|
| Rastreo (55 %) | Detecta la guía y responde con línea de tiempo, mapa y ETA en lenguaje natural | % de rastreos resueltos sin humano (`/admin/metricas`) |
| Cotización (12 % de error) | Formulario guiado + cálculo determinista con las tarifas, mínimos y recargos de la matriz | 0 diferencias en el set de prueba T-COT |
| Información dispersa (4,5 min) | RAG sobre los manuales con cita de documento y sección | Recall@4 del set T-RAG y latencia medida |
| PQRS incompletas (40 %) | Valida el plazo en días hábiles con festivos, guía el checklist de documentos y radica | % de tickets con checklist completo |
| Casos sensibles | Escala por reglas del cliente (CRIT-001 a 005) con resumen IA para el asesor | Tiempo de toma del escalamiento |

Para la gerencia: panel administrativo conversacional («¿qué envíos están retenidos?») y predicciones de riesgo de retraso y de demanda por hub que se reentrenan solas.

## 3. Diferenciación

1. **IA 100 % local.** El LLM (LFM3-1.7B) y los embeddings corren en un equipo de la empresa. Ningún dato de conversación, cédula o factura sale a una API externa: cumplimiento por diseño de la Ley 1581 de 2012 y sin costo por token.
2. **Generative UI.** El chat no responde párrafos: responde componentes (formulario de cotización, línea de tiempo, veredicto de mercancía, checklist con carga de archivos). Menos ida y vuelta, menos errores de captura, y el mismo contrato sirve para web, app o WhatsApp.
3. **Cero alucinaciones por arquitectura, no por esperanza.** Las cifras y veredictos salen de código; el LLM solo redacta. Un verificador compara cada respuesta contra los hechos (cifras, polaridad permitido/prohibido, guías) y la reemplaza si contradice. Medido: sin estas capas, el modelo respondió «sí, podemos enviar un perro»; con ellas responde «prohibido» con la cita del manual.
4. **Escalamiento con reglas del negocio.** Los criterios del cliente (confianza, frustración, montos, cuentas VIP, carga crítica) se evalúan en código y llegan al asesor con un resumen.
5. **Predicción que aprende sola.** Modelos de riesgo de retraso y demanda con promoción champion/challenger: solo reemplazan al modelo en producción si mejoran la métrica en el mismo holdout. (En la demo, sobre datos simulados rotulados como tales.)
6. **Latencia baja en hardware modesto.** Sin razonamiento del modelo (de 3,8 s a 0,6 s medidos), enrutador determinista y artifact antes del texto: el usuario ve la respuesta útil en milisegundos.

## 4. Costo por interacción

### 4.1 Fórmulas

Sea `I` = interacciones por mes y `a` = fracción resuelta sin humano (se mide en `/admin/metricas`).

- **Costo humano por interacción:** `C_h = (salario_cargado_mensual × agentes) / interacciones_atendidas_mes`, o bien `C_h = costo_minuto_agente × TMO` (tiempo medio de operación).
- **Costo local por interacción:** `C_l = (amortización_hardware_mensual + energía_mensual + operación_mensual) / I`
  - `energía_mensual = potencia_media_kW × horas_activas × tarifa_kWh`
- **Costo nube por interacción (alternativa):** `C_n = tokens_entrada × precio_entrada + tokens_salida × precio_salida` (precios del proveedor elegido).
- **Ahorro mensual:** `A = I × a × (C_h − C_l)`, más el margen recuperado en cotizaciones: `I_cot × 12 % × pérdida_media_por_error × reducción_de_errores`.

### 4.2 Ejemplo con supuestos explícitos

Las filas `S-xx` **no son datos del mercado ni del cliente**: son valores ilustrativos para mostrar la sensibilidad del modelo. Se reemplazan con la nómina y la factura de energía reales.

| ID | Variable | Valor | Origen |
|---|---|---|---|
| — | Interacciones al mes `I` | 18.000 × 30 = **540.000** | Dosier |
| — | Canales de texto (WhatsApp + web) | 85 % → 459.000/mes | Dosier |
| S-01 | Fracción resuelta sin humano `a` | 0,60 (por debajo del 78 % repetitivo) | Supuesto; se mide en producción |
| S-02 | Costo humano por interacción `C_h` | `X` COP | Supuesto: dato de nómina del cliente |
| S-03 | Hardware dedicado (GPU de 6 GB clase consumidor) amortizado a 36 meses | `H / 36` COP/mes | Supuesto |
| S-04 | Potencia media del equipo en uso | 0,15 kW | Supuesto; medir con el equipo real |
| S-05 | Tarifa de energía | `T` COP/kWh | Supuesto: factura del cliente |
| — | Tiempo de LLM por turno | ~0,6 s sin razonamiento | **Medido** 2026-11-03 |
| — | Turnos concurrentes por equipo | 8 (slots de llama.cpp) | Configuración medida |

Capacidad de un equipo: con ~0,6 s de GPU por turno y 8 slots, el techo teórico es del orden de 8 / 0,6 ≈ 13 turnos por segundo. Aunque el rendimiento real sea varias veces menor (se mide con `tests/load.py`), 459.000 interacciones de texto al mes son ~0,18 por segundo en promedio: **un solo equipo cubre la carga media con amplio margen**; el pico se valida en la prueba de carga.

Consecuencia: `C_l` es casi fijo (hardware + energía) y se diluye con el volumen, mientras que `C_h` y `C_n` crecen linealmente. Con cualquier valor razonable de S-02, `A ≈ I × a × C_h`.

## 5. Modelo de monetización: SaaS por niveles

Cliente objetivo: operadores logísticos, transportadoras y empresas de paquetería en Colombia que atienden por WhatsApp y web. El producto se instala **on-premise** (un equipo con GPU en la sede del cliente) y se cobra como suscripción.

| Nivel | Para quién | Incluye | Precio (propuesta a validar) |
|---|---|---|---|
| **Básico** | Transportadora pequeña | Rastreo, cotización, mercancías, cobertura; 1 canal; hasta `N₁` interacciones/mes | Cuota fija mensual `P₁` |
| **Profesional** | Operador mediano | + PQRS con checklist y carga de documentos, escalamiento a asesores, panel de métricas; hasta `N₂` | `P₂` |
| **Empresarial** | Operador grande (perfil TransLogix) | + chat administrativo, predicciones autoentrenadas, cuentas corporativas/VIP, SLA y soporte; volumen ilimitado por equipo | `P₃` + implantación única |

Regla de precio: **precio por valor**, una fracción del ahorro medido `A` (p. ej. 20-30 % del ahorro del primer año), de modo que el cliente siempre gana. La implantación (carga de tarifas, manuales y reglas propias) se cobra una vez.

Ingresos adicionales: implantación, integración con su TMS/CRM real (hoy son mocks), nuevos módulos (voz para la PBX, que ya tiene punto de integración) y soporte.

## 6. Escalabilidad

- **Técnica:** API sin estado + PostgreSQL; más carga = más slots del LLM o un segundo equipo detrás del balanceador HAProxy que ya existe. Los embeddings van en CPU y no compiten por la GPU.
- **Comercial:** los datos de negocio (tarifas, cobertura, reglas de escalamiento, clases ONU) viven en la base de datos y se cargan desde archivos del cliente: llevar el producto a otra transportadora es configurar, no reprogramar.
- **De canal:** el contrato de artifacts es independiente del canal; WhatsApp, web y app consumen el mismo backend.

## 7. Riesgos y mitigación

| Riesgo | Mitigación |
|---|---|
| El LLM se equivoca | No decide nada: reglas en código, verificador, confianza < 0,75 → humano |
| Un solo equipo es punto único de falla | Si el LLM cae, la API responde 503 y escala a humano; segundo equipo en HAProxy para alta disponibilidad |
| Datos personales | Procesamiento local, enmascarado de cédula, teléfono y NIT, logs sin datos personales, control de propiedad por usuario |
| Inyección de prompts | El contenido del usuario es dato; el admin no tiene texto-a-SQL, solo consultas en lista blanca |
| Predicciones con datos simulados | Rotuladas como simuladas; con datos reales del TMS el mismo ciclo se reentrena solo |
| Licencias de modelos | Revisión de licencias antes del uso comercial (decisión del cliente) |

## 8. Guion de pitch (5 minutos)

| Tiempo | Bloque | Qué se dice / muestra |
|---|---|---|
| 0:00-0:40 | Gancho | «Cada día 18.000 personas le escriben a TransLogix. 55 % solo quiere saber dónde está su paquete, y esperan hasta 14,5 minutos. Uno de cada cinco se va.» |
| 0:40-1:20 | Problema | Tres cifras: 78 % repetitivo, 12 % de cotizaciones con error, 40 % de reclamos incompletos. Cada una cuesta margen, multas o clientes |
| 1:20-2:50 | Demo en vivo | (1) «TLX-984021-CO» → línea de tiempo y mapa al instante. (2) «Quiero cotizar» → formulario → $190.975, idéntico al cálculo manual. (3) «¿Puedo enviar un perro?» → prohibido, con cita del manual. (4) «Esto es una estafa» → transferencia al asesor con resumen |
| 2:50-3:30 | Por qué funciona | IA 100 % local (Ley 1581, sin costo por token); el modelo redacta, el código decide; verificador anti-alucinación; latencias medidas en pantalla (panel admin) |
| 3:30-4:10 | Negocio | Fórmula de ahorro `I × a × C_h`, SaaS en 3 niveles con precio por valor, implantación por configuración |
| 4:10-4:40 | Visión | Predicción de retrasos y demanda que se reentrena sola; voz para la PBX; cualquier transportadora del país |
| 4:40-5:00 | Cierre | «Lo repetitivo, en segundos y sin errores. Lo importante, con un humano que ya sabe todo el contexto.» |

Reparto sugerido: una persona narra, otra opera la demo. Ensayar con cronómetro; tener un video de respaldo de la demo por si falla la red.

## 9. Preguntas probables del jurado

| Pregunta | Respuesta |
|---|---|
| ¿Por qué un modelo tan pequeño (1,7B)? | Porque no le pedimos que sepa ni que calcule: clasifica, extrae y redacta sobre hechos que le damos. Así cabe en una GPU de 6 GB, responde en ~0,6 s y mantiene los datos dentro de la empresa |
| ¿Cómo garantizan que no alucina? | Tres capas: cifras y veredictos calculados en código; RAG con cita; verificador que reemplaza el texto si contradice los hechos. Si la confianza baja de 0,75, pasa a humano (CRIT-001) |
| ¿Qué pasa si el modelo se cae? | La API responde 503 con `Retry-After` y el chat escala a un asesor. Nunca queda una respuesta vacía |
| ¿Cómo miden la latencia? | Cada turno guarda latencias por etapa; el panel admin muestra p50/p95 y la prueba de carga mide 1, 4 y 8 conversaciones concurrentes |
| ¿Las predicciones son reales? | El ciclo (entrenar, vigilar deriva, reentrenar, promover solo si mejora) es real; los datos de la demo son simulados y así se rotulan. Con el histórico del TMS se alimenta el mismo ciclo |
| ¿Cumple la Ley 1581? | Procesamiento local, enmascarado de datos personales, logs sin datos sensibles, acceso por rol y por propietario |
| ¿Cuánto cuesta para el cliente? | Suscripción por niveles con precio ligado al ahorro medido; la fórmula y sus supuestos están a la vista y se recalculan con su nómina real |
| ¿Por qué no usar un servicio en la nube? | Costo por token que crece con el volumen, datos personales fuera de la empresa y dependencia de internet. Local: costo casi fijo y soberanía de datos |
| ¿Cómo se adapta a otra empresa? | Tarifas, cobertura, reglas y manuales se cargan desde sus archivos a la base de datos; no se toca el código |
| ¿Qué diferencia hay con un chatbot de menús? | Entiende lenguaje natural, pero responde con componentes interactivos y cálculos exactos; y el humano recibe el caso con contexto y resumen |
| ¿Cómo evitan que un usuario manipule al bot? | El texto del usuario se trata como dato, no como instrucción; el chat admin solo ejecuta consultas en lista blanca, sin SQL generado |
