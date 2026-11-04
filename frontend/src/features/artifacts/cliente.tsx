import { useState, type ChangeEvent, type FormEvent } from "react";
import { Icono, type NombreIcono } from "../../components/ui/Icono";
import type { Accion, Cita } from "../../services/chat";
import { ErrorApi, json, peticion } from "../../services/http";
import type { PropsArtifact } from "./registro";

// Artifacts del cliente (docs/frontend.md §6.1). Solo muestran lo que envía el servidor: no recalculan nada.

const COP = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });
const ZONA = "America/Bogota";
const FECHA_HORA = new Intl.DateTimeFormat("es-CO", { dateStyle: "medium", timeStyle: "short", timeZone: ZONA });
const FECHA = new Intl.DateTimeFormat("es-CO", { dateStyle: "long", timeZone: ZONA });

const dinero = (v: string | number) => COP.format(Number(v));
/** Fechas sin hora (`AAAA-MM-DD`) se leen como día local; con hora, en la zona de Colombia. */
const fecha = (iso: string) => (iso.length === 10 ? FECHA.format(new Date(`${iso}T12:00:00`)) : FECHA_HORA.format(new Date(iso)));
const kg = (v: string) => `${Number(v).toLocaleString("es-CO", { maximumFractionDigits: 2 })} kg`;

export function Fuentes({ fuentes }: { fuentes: Cita[] }) {
  if (!fuentes.length) return null;
  return (
    <details className="fuentes">
      <summary>Fuentes ({fuentes.length})</summary>
      <ul>
        {fuentes.map((c) => (
          <li key={`${c.doc_codigo}-${c.seccion}`}>
            {c.documento}: {c.seccion}
          </li>
        ))}
      </ul>
    </details>
  );
}

function Lista({ titulo, items, icono }: { titulo: string; items: string[]; icono: NombreIcono }) {
  if (!items.length) return null;
  return (
    <div className="bloque">
      <h3>{titulo}</h3>
      <ul className="lista-icono">
        {items.map((t) => (
          <li key={t}>
            <Icono nombre={icono} tamano={18} />
            <span>{t}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ——— Rastreo ———

/** Hitos visibles. Agrupa los códigos de `app/domain/estados.py`; un código desconocido no pinta hitos. */
const HITOS: { nombre: string; icono: NombreIcono; codigos: string[] }[] = [
  { nombre: "Recibido", icono: "documento", codigos: ["SOLICITUD_GENERADA", "RECOGIDO_EN_ORIGEN"] },
  { nombre: "En bodega", icono: "bodega", codigos: ["EN_BODEGA_ORIGEN", "RELECTURA_HUB_FONTIBON"] },
  { nombre: "En tránsito", icono: "camion", codigos: ["EN_TRANSITO", "EN_BODEGA_DESTINO"] },
  { nombre: "En reparto", icono: "pin", codigos: ["EN_REPARTO"] },
  { nombre: "Entregado", icono: "check", codigos: ["ENTREGADO"] },
];
const hitoDe = (codigo: string) => HITOS.findIndex((h) => h.codigos.includes(codigo));
const DIA_CORTO = new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "short", timeZone: ZONA });

function Hitos({ actual, eventos }: { actual: string; eventos: { estado: string; ts: string }[] }) {
  // Con una novedad (RETENIDO_NOVEDAD) el hito es el del último evento normal.
  const normal = [...eventos].reverse().find((e) => hitoDe(e.estado) >= 0);
  const indice = hitoDe(actual) >= 0 ? hitoDe(actual) : normal ? hitoDe(normal.estado) : -1;
  if (indice < 0) return null;
  const detenido = hitoDe(actual) < 0;
  return (
    <ol className="hitos-h" aria-label="Etapas del envío" data-detenido={detenido || undefined}>
      {HITOS.map((h, i) => {
        const primero = eventos.find((e) => h.codigos.includes(e.estado));
        const estado = i < indice || (i === indice && i === HITOS.length - 1) ? "hecho" : i === indice ? "actual" : undefined;
        return (
          <li key={h.nombre} data-estado={estado} aria-current={i === indice ? "step" : undefined}>
            <span className="hitos-h__icono">
              <Icono nombre={i === indice && detenido ? "alerta" : h.icono} tamano={18} />
            </span>
            <span className="hitos-h__nombre">{h.nombre}</span>
            <span className="hitos-h__fecha">{primero ? DIA_CORTO.format(new Date(primero.ts)) : "—"}</span>
          </li>
        );
      })}
    </ol>
  );
}

export function LineaTiempoEnvio({ artifact: a }: PropsArtifact<"linea_tiempo_envio">) {
  const eventos = [...a.eventos].sort((x, y) => x.ts.localeCompare(y.ts));
  return (
    <div className="rastreo">
      <div className="rastreo__cabeza">
        <span className="rastreo__icono" data-novedad={hitoDe(a.estado_actual) < 0 || undefined}>
          <Icono nombre={a.estado_actual === "ENTREGADO" ? "check" : hitoDe(a.estado_actual) < 0 ? "alerta" : "camion"} tamano={26} />
        </span>
        <div>
          <p className="rastreo__estado">{a.estado_texto}</p>
          <p className="dato-mono">Guía {a.guia}</p>
        </div>
      </div>
      <dl className="datos">
        <div>
          <dt>
            <Icono nombre="ruta" tamano={14} /> Ruta
          </dt>
          <dd>
            {a.origen} → {a.destino}
          </dd>
        </div>
        {a.servicio && (
          <div>
            <dt>
              <Icono nombre="camion" tamano={14} /> Servicio
            </dt>
            <dd>{a.servicio}</dd>
          </div>
        )}
        {a.eta && (
          <div>
            <dt>
              <Icono nombre="reloj" tamano={14} /> Llegada estimada
            </dt>
            <dd>{fecha(a.eta)}</dd>
          </div>
        )}
      </dl>
      <Hitos actual={a.estado_actual} eventos={eventos} />
      <div className="progreso" role="progressbar" aria-valuenow={a.progreso_pct} aria-valuemin={0} aria-valuemax={100} aria-label="Avance del envío">
        <span style={{ width: `${a.progreso_pct}%` }} />
      </div>
      {a.alerta && (
        <p className={`alerta alerta--${a.alerta.nivel}`} role="note">
          <Icono nombre="alerta" tamano={18} />
          <span>
            <strong>{a.alerta.nivel === "critica" ? "Atención: " : a.alerta.nivel === "advertencia" ? "Aviso: " : "Información: "}</strong>
            {a.alerta.mensaje}
          </span>
        </p>
      )}
      <details className="historial">
        <summary>
          <Icono nombre="reloj" tamano={16} />
          Ver historial completo ({eventos.length})
        </summary>
      <ol className="hitos">
        {eventos.map((e, i) => (
          <li key={`${e.ts}-${i}`} aria-current={i === eventos.length - 1 ? "step" : undefined}>
            <time dateTime={e.ts}>{fecha(e.ts)}</time>
            <strong>{e.estado_texto}</strong>
            {e.ubicacion && <span>{e.ubicacion}</span>}
            {e.descripcion && <span className="hitos__detalle">{e.descripcion}</span>}
          </li>
        ))}
      </ol>
      </details>
    </div>
  );
}

/** ponytail: iframe de OpenStreetMap en vez de Leaflet; si hace falta interacción (rutas, varios pines), Leaflet. */
export function MapaUbicacion({ artifact: a }: PropsArtifact<"mapa_ubicacion">) {
  const d = 0.08;
  const bbox = [a.longitud - d, a.latitud - d / 2, a.longitud + d, a.latitud + d / 2].join(",");
  const src = `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${a.latitud},${a.longitud}`;
  return (
    <div className="mapa">
      <iframe title={`Mapa de la última ubicación de la guía ${a.guia}`} src={src} loading="lazy" referrerPolicy="no-referrer" />
      <p className="mapa__texto">
        <Icono nombre="pin" tamano={18} />
        <span>
          {a.referencia ?? `${a.latitud.toFixed(4)}, ${a.longitud.toFixed(4)}`}
          {a.actualizado && <small> · Actualizado {fecha(a.actualizado)}</small>}
        </span>
      </p>
    </div>
  );
}

// ——— Cotización ———

export function ResultadoCotizacion({ artifact: a }: PropsArtifact<"resultado_cotizacion">) {
  return (
    <div className="cotizacion">
      <div className="cotizacion__total">
        <span>Total a pagar</span>
        <strong>{dinero(a.total)}</strong>
        <div className="cotizacion__ruta">
          <span>
            <Icono nombre="pin" tamano={16} /> {a.origen}
          </span>
          <span className="cotizacion__linea" aria-hidden="true" />
          <span>
            <Icono nombre="bandera" tamano={16} /> {a.destino}
          </span>
        </div>
        <div className="cotizacion__chips">
          <span>
            <Icono nombre="camion" tamano={16} /> {a.servicio}
          </span>
          <span>
            <Icono nombre="reloj" tamano={16} /> ~{a.tiempo_estimado_horas} h
          </span>
          <span>
            <Icono nombre="pesa" tamano={16} /> {kg(a.peso_facturable_kg)} facturables
          </span>
        </div>
      </div>
      <table className="desglose">
        <caption className="sr-only">Desglose de la cotización</caption>
        <tbody>
          <tr>
            <th scope="row">Peso real</th>
            <td>{kg(a.peso_real_kg)}</td>
          </tr>
          <tr>
            <th scope="row">Peso volumétrico</th>
            <td>{kg(a.peso_volumetrico_kg)}</td>
          </tr>
          <tr>
            <th scope="row">
              Peso facturable <small>({a.base_facturacion === "volumetrico" ? "volumétrico" : "real"})</small>
            </th>
            <td>{kg(a.peso_facturable_kg)}</td>
          </tr>
          <tr>
            <th scope="row">Tarifa por kg</th>
            <td>{dinero(a.tarifa_kg)}</td>
          </tr>
          <tr>
            <th scope="row">Flete base{a.flete_minimo_aplicado && <small> (mínimo aplicado)</small>}</th>
            <td>{dinero(a.flete_base)}</td>
          </tr>
          <tr>
            <th scope="row">Seguro</th>
            <td>{dinero(a.seguro)}</td>
          </tr>
          {a.recargos.map((r) => (
            <tr key={r.concepto}>
              <th scope="row">{r.concepto}</th>
              <td>{dinero(r.valor)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Total</th>
            <td>{dinero(a.total)}</td>
          </tr>
        </tfoot>
      </table>
      {a.advertencias.map((t) => (
        <p key={t} className="alerta alerta--advertencia" role="note">
          <Icono nombre="alerta" tamano={18} />
          <span>{t}</span>
        </p>
      ))}
      {a.observaciones && <p className="nota">{a.observaciones}</p>}
      <p className="nota dato-mono">Cotización {a.cotizacion_id}</p>
    </div>
  );
}

// ——— Mercancías y cobertura ———

const VEREDICTO = {
  permitido: { texto: "Permitido", icono: "check", clase: "exito" },
  restringido: { texto: "Restringido: con condiciones", icono: "alerta", clase: "advertencia" },
  solo_ftl: { texto: "Solo en camión dedicado (FTL)", icono: "camion", clase: "info" },
  prohibido: { texto: "Prohibido", icono: "x", clase: "error" },
} as const;

export function VeredictoMercancia({ artifact: a }: PropsArtifact<"veredicto_mercancia">) {
  const v = VEREDICTO[a.veredicto];
  return (
    <div className="veredicto">
      <p className={`insignia insignia--${v.clase}`}>
        <Icono nombre={v.icono} tamano={22} />
        {v.texto}
      </p>
      <p>
        <strong>{a.producto}</strong>
        {a.clase_onu && <> · Clase ONU {a.clase_onu}</>}
      </p>
      <p>{a.motivo}</p>
      <Lista titulo="Condiciones" items={a.condiciones} icono="check" />
      <Lista titulo="Documentos requeridos" items={a.documentos} icono="documento" />
      <Lista titulo="Embalaje" items={a.embalaje} icono="caja" />
      <Fuentes fuentes={a.fuentes} />
    </div>
  );
}

const ESTADO_PLAN = {
  permitido: { clase: "exito", icono: "check", texto: "Se puede enviar" },
  restringido: { clase: "advertencia", icono: "alerta", texto: "Se puede enviar con restricciones" },
  solo_ftl: { clase: "advertencia", icono: "camion", texto: "Solo en carga completa" },
  sin_registro: { clase: "info", icono: "lupa", texto: "Sin clasificar en el catálogo" },
  sin_producto: { clase: "info", icono: "caja", texto: "Falta saber qué envías" },
} as const;

export function PlanEnvio({ artifact: a }: PropsArtifact<"plan_envio">) {
  const e = ESTADO_PLAN[a.estado];
  return (
    <div className="veredicto">
      <p className={`insignia insignia--${e.clase}`}>
        <Icono nombre={e.icono} tamano={20} />
        {e.texto}
      </p>
      <p>{a.resumen}</p>
      <ol className="plan">
        {a.pasos.map((p) => (
          <li key={p.titulo}>
            <strong>{p.titulo}</strong>
            <span>{p.detalle}</span>
            {p.items.length > 0 && (
              <ul>
                {p.items.map((i) => (
                  <li key={i}>{i}</li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
      <Fuentes fuentes={a.fuentes} />
    </div>
  );
}

export function GuiaEmbalaje({ artifact: a }: PropsArtifact<"guia_embalaje">) {
  return (
    <div className="bloque">
      <p className="insignia insignia--info">
        <Icono nombre="caja" tamano={20} />
        Categoría {a.categoria}: {a.nombre_categoria}
      </p>
      {a.requisito && (
        <p className="alerta alerta--advertencia" role="note">
          <Icono nombre="alerta" tamano={18} />
          <span>{a.requisito}</span>
        </p>
      )}
      <ol className="pasos">
        {a.pasos.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ol>
      <Fuentes fuentes={a.fuentes} />
    </div>
  );
}

function Chip({ si, texto }: { si: boolean; texto: string }) {
  return (
    <span className={`chip chip--${si ? "si" : "no"}`}>
      <Icono nombre={si ? "check" : "x"} tamano={16} />
      {texto}: {si ? "sí" : "no"}
    </span>
  );
}

export function FichaCobertura({ artifact: a }: PropsArtifact<"ficha_cobertura">) {
  return (
    <div className="bloque">
      <p className="rastreo__estado">
        {a.municipio}, {a.departamento}
      </p>
      <div className="chips">
        <Chip si={a.same_day} texto="Entrega el mismo día" />
        <Chip si={a.refrigerado} texto="Refrigerado" />
      </div>
      <dl className="datos">
        <div>
          <dt>Cobertura</dt>
          <dd>{a.tipo_cobertura}</dd>
        </div>
        <div>
          <dt>Tiempo estándar</dt>
          <dd>{a.tiempo_estandar_horas} h</dd>
        </div>
        <div>
          <dt>Hub</dt>
          <dd>{a.hub}</dd>
        </div>
        {a.frecuencia_despacho && (
          <div>
            <dt>Frecuencia</dt>
            <dd>{a.frecuencia_despacho}</dd>
          </div>
        )}
        <div>
          <dt>Peso máximo</dt>
          <dd>{kg(a.peso_maximo_kg)}</dd>
        </div>
        <div>
          <dt>Volumen máximo</dt>
          <dd>{Number(a.volumen_maximo_m3).toLocaleString("es-CO")} m³</dd>
        </div>
      </dl>
      {a.restricciones && (
        <p className="alerta alerta--advertencia" role="note">
          <Icono nombre="alerta" tamano={18} />
          <span>{a.restricciones}</span>
        </p>
      )}
    </div>
  );
}

// ——— PQRS ———

export function EstadoPlazo({ artifact: a }: PropsArtifact<"estado_plazo">) {
  return (
    <div className="bloque">
      <p className={`insignia insignia--${a.vigente ? "exito" : "error"}`}>
        <Icono nombre={a.vigente ? "reloj" : "x"} tamano={20} />
        {a.vigente ? "Plazo vigente" : "Plazo vencido"}
      </p>
      <p>{a.mensaje}</p>
      <dl className="datos">
        {a.fecha_limite && (
          <div>
            <dt>Fecha límite</dt>
            <dd>{fecha(a.fecha_limite)}</dd>
          </div>
        )}
        <div>
          <dt>Días hábiles restantes</dt>
          <dd>
            {a.dias_habiles_restantes} de {a.dias_habiles_plazo}
          </dd>
        </div>
      </dl>
      {a.fundamento && <p className="nota">{a.fundamento}</p>}
    </div>
  );
}

export function ChecklistDocumentos({ artifact: a, contexto }: PropsArtifact<"checklist_documentos">) {
  const [hechos, setHechos] = useState<Record<string, boolean>>(() => Object.fromEntries(a.items.map((i) => [i.id, i.completado])));
  const [subiendo, setSubiendo] = useState<string | null>(null);
  const [errores, setErrores] = useState<Record<string, string>>({});
  const submit = a.acciones.find((x: Accion) => x.tipo === "submit");
  const listos = a.items.every((i) => !i.requerido || hechos[i.id]);

  const subir = async (id: string, max: number | null | undefined, e: ChangeEvent<HTMLInputElement>) => {
    const archivo = e.target.files?.[0];
    if (!archivo || !a.endpoint_carga) return;
    if (max && archivo.size > max) {
      setErrores((p) => ({ ...p, [id]: `El archivo supera ${Math.round(max / 1048576)} MB.` }));
      return;
    }
    const cuerpo = new FormData();
    cuerpo.set("archivo", archivo);
    cuerpo.set("tipo_documento", id);
    setSubiendo(id);
    setErrores((p) => ({ ...p, [id]: "" }));
    try {
      await peticion(a.endpoint_carga, { method: "POST", body: cuerpo });
      setHechos((p) => ({ ...p, [id]: true }));
    } catch (err) {
      setErrores((p) => ({ ...p, [id]: err instanceof ErrorApi ? (err.problema.detail ?? err.problema.title) : "No se pudo subir. Revisa tu conexión." }));
    } finally {
      setSubiendo(null);
    }
  };

  const radicar = (e: FormEvent) => {
    e.preventDefault();
    void contexto.enviar({ tipo: "artifact_submit", artifact_id: a.id, valores: {} }, submit?.endpoint ?? undefined);
  };

  return (
    <form className="checklist" onSubmit={radicar}>
      {a.radicado && <p className="nota dato-mono">Radicado {a.radicado}</p>}
      <ul>
        {a.items.map((i) => (
          <li key={i.id} data-hecho={hechos[i.id] || undefined}>
            <span className="checklist__marca">
              <Icono nombre={hechos[i.id] ? "check" : "documento"} tamano={18} />
            </span>
            <div>
              <strong>
                {i.etiqueta}
                {!i.requerido && <small> (opcional)</small>}
              </strong>
              {i.descripcion && <span className="nota">{i.descripcion}</span>}
              {hechos[i.id] ? (
                <span className="nota">Listo</span>
              ) : a.endpoint_carga ? (
                <label className="boton boton--secundario boton--chico">
                  <Icono nombre="subir" tamano={16} />
                  {subiendo === i.id ? "Subiendo…" : "Adjuntar"}
                  <input type="file" className="sr-only" accept={i.accept ?? undefined} disabled={subiendo !== null} onChange={(e) => void subir(i.id, i.max_bytes, e)} />
                </label>
              ) : null}
              {errores[i.id] && (
                <span className="campo__error" role="alert">
                  {errores[i.id]}
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>
      {submit && (
        <button className="boton boton--primario" disabled={!listos || contexto.bloqueado}>
          {submit.etiqueta}
        </button>
      )}
      {submit && !listos && <p className="nota">Adjunta los documentos requeridos para continuar.</p>}
    </form>
  );
}

export function TicketPqrs({ artifact: a }: PropsArtifact<"ticket_pqrs">) {
  const [copiado, setCopiado] = useState(false);
  const copiar = () =>
    void navigator.clipboard?.writeText(a.radicado).then(
      () => setCopiado(true),
      () => setCopiado(false),
    );
  return (
    <div className="ticket">
      <p className="insignia insignia--exito">
        <Icono nombre="check" tamano={20} />
        Radicado con éxito
      </p>
      <div className="ticket__radicado">
        <span className="dato-mono">{a.radicado}</span>
        <button type="button" className="boton boton--secundario boton--chico" onClick={copiar}>
          <Icono nombre="copiar" tamano={16} />
          {copiado ? "Copiado" : "Copiar"}
        </button>
      </div>
      <dl className="datos">
        <div>
          <dt>Estado</dt>
          <dd>{a.estado}</dd>
        </div>
        <div>
          <dt>Radicación</dt>
          <dd>{fecha(a.fecha_radicacion)}</dd>
        </div>
        <div>
          <dt>Respuesta a más tardar</dt>
          <dd>{fecha(a.fecha_limite_respuesta)}</dd>
        </div>
        {a.guia && (
          <div>
            <dt>Guía</dt>
            <dd className="dato-mono">{a.guia}</dd>
          </div>
        )}
        {a.escalado_a && (
          <div>
            <dt>Escalado a</dt>
            <dd>{a.escalado_a}</dd>
          </div>
        )}
      </dl>
      {a.liquidacion_estimada && (
        <div className="bloque">
          <h3>Liquidación estimada</h3>
          <table className="desglose">
            <tbody>
              <tr>
                <th scope="row">Base</th>
                <td>{dinero(a.liquidacion_estimada.base)}</td>
              </tr>
              <tr>
                <th scope="row">Deducible</th>
                <td>
                  {Number(a.liquidacion_estimada.deducible) > 0 && "−"}
                  {dinero(a.liquidacion_estimada.deducible)}
                </td>
              </tr>
              <tr>
                <th scope="row">Flete devuelto</th>
                <td>{dinero(a.liquidacion_estimada.flete_devuelto)}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">Total</th>
                <td>{dinero(a.liquidacion_estimada.total)}</td>
              </tr>
            </tfoot>
          </table>
          <p className="nota">{a.liquidacion_estimada.nota}</p>
        </div>
      )}
    </div>
  );
}

// ——— Conversación ———

export function CitasArtifact({ artifact: a }: PropsArtifact<"citas">) {
  return <Fuentes fuentes={a.citas} />;
}

/** Chips y sí/no: sus botones los pinta `AccionesArtifact`. */
export function SoloAcciones() {
  return null;
}

export function Confirmacion({ artifact: a }: PropsArtifact<"confirmacion">) {
  return <p>{a.mensaje}</p>;
}

export function EncuestaSatisfaccion({ artifact: a }: PropsArtifact<"encuesta_satisfaccion">) {
  const accion = a.acciones.find((x: Accion) => x.endpoint);
  const [puntaje, setPuntaje] = useState<number | null>(null);
  const [comentario, setComentario] = useState("");
  const [estado, setEstado] = useState<"idle" | "enviando" | "ok" | "error">("idle");
  const escala = Array.from({ length: a.escala_max - a.escala_min + 1 }, (_, i) => a.escala_min + i);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (puntaje === null || !accion?.endpoint) return;
    setEstado("enviando");
    try {
      await json(accion.endpoint, { ...(accion.payload ?? {}), puntaje, comentario: comentario.trim() || undefined });
      setEstado("ok");
    } catch {
      setEstado("error");
    }
  };

  if (estado === "ok") {
    return (
      <p className="insignia insignia--exito" role="status">
        <Icono nombre="check" tamano={20} />
        ¡Gracias por tu calificación!
      </p>
    );
  }
  return (
    <form className="encuesta" onSubmit={enviar}>
      <fieldset>
        <legend>{a.pregunta}</legend>
        <div className="estrellas">
          {escala.map((n) => (
            <label key={n} data-activa={puntaje !== null && n <= puntaje ? "" : undefined}>
              <input type="radio" name={`${a.id}-puntaje`} className="sr-only" value={n} checked={puntaje === n} onChange={() => setPuntaje(n)} />
              <Icono nombre="estrella" tamano={28} />
              <span className="sr-only">
                {n} de {a.escala_max}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      {a.permite_comentario && (
        <div className="campo">
          <label htmlFor={`${a.id}-comentario`}>Comentario (opcional)</label>
          <textarea id={`${a.id}-comentario`} rows={2} maxLength={1000} value={comentario} onChange={(e) => setComentario(e.target.value)} />
        </div>
      )}
      {estado === "error" && (
        <p className="campo__error" role="alert">
          No pudimos guardar tu calificación. Intenta de nuevo.
        </p>
      )}
      <button className="boton boton--primario" disabled={puntaje === null || estado === "enviando"}>
        {accion?.etiqueta ?? "Enviar"}
      </button>
    </form>
  );
}
