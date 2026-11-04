import { Link } from "react-router-dom";
import { BarrasH, GraficoLinea, RotuloSimulado } from "../../components/graficos/Graficos";
import { Icono } from "../../components/ui/Icono";
import type { PropsArtifact } from "./registro";

const COP = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });
const NUM = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 });
const FECHA = new Intl.DateTimeFormat("es-CO", { dateStyle: "medium", timeZone: "America/Bogota" });

function valorKpi(valor: string, formato: string, unidad?: string | null) {
  const n = Number(valor);
  if (formato === "moneda") return COP.format(n);
  if (formato === "porcentaje") return `${NUM.format(n)} %`;
  if (formato === "duracion_ms") return n >= 1000 ? `${NUM.format(n / 1000)} s` : `${NUM.format(n)} ms`;
  return `${NUM.format(n)}${unidad ? ` ${unidad}` : ""}`;
}

const TENDENCIA = { sube: "↑ Sube", baja: "↓ Baja", estable: "→ Estable" } as const;

export function TarjetasKpi({ artifact: a }: PropsArtifact<"tarjetas_kpi">) {
  return (
    <ul className="kpis">
      {a.tarjetas.map((t) => (
        <li key={t.id} className="kpi">
          <span className="kpi__etiqueta">{t.etiqueta}</span>
          <strong className="kpi__valor">{valorKpi(String(t.valor), t.formato ?? "numero", t.unidad)}</strong>
          {t.tendencia && <span className="kpi__nota">{TENDENCIA[t.tendencia]}</span>}
        </li>
      ))}
    </ul>
  );
}

export function GraficoArtifact({ artifact: a }: PropsArtifact<"grafico">) {
  const unidad = a.eje_y.unidad ?? undefined;
  return (
    <div className="bloque">
      {a.datos_simulados && <RotuloSimulado />}
      {a.tipo_grafico === "barras" && a.series.length === 1 ? (
        <BarrasH filas={a.series[0].puntos.map((p) => ({ etiqueta: p.x, valor: Number(p.y) }))} unidad={unidad} />
      ) : (
        <GraficoLinea
          etiquetaX={a.eje_x.etiqueta}
          unidad={unidad}
          series={a.series.map((s) => ({
            nombre: s.nombre,
            punteada: s.estilo === "punteada",
            puntos: s.puntos.map((p) => ({
              x: p.x,
              y: Number(p.y),
              inf: p.y_inf == null ? undefined : Number(p.y_inf),
              sup: p.y_sup == null ? undefined : Number(p.y_sup),
            })),
          }))}
        />
      )}
    </div>
  );
}

function celda(valor: unknown, tipo?: string) {
  if (valor === null || valor === undefined || valor === "") return "—";
  if (tipo === "moneda") return COP.format(Number(valor));
  if (tipo === "numero") return NUM.format(Number(valor));
  if (tipo === "fecha") return FECHA.format(new Date(String(valor)));
  if (tipo === "estado") return <span className="etiqueta">{String(valor)}</span>;
  return String(valor);
}

export function TablaDatos({ artifact: a }: PropsArtifact<"tabla_datos">) {
  if (!a.filas?.length) return <p className="nota">No hay registros.</p>;
  return (
    <div className="tabla-caja">
      <table className="tabla">
        <thead>
          <tr>
            {a.columnas.map((c) => (
              <th key={c.clave} scope="col">
                {c.etiqueta}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {a.filas.map((f, i) => (
            <tr key={i}>
              {a.columnas.map((c) => (
                <td key={c.clave}>{celda(f[c.clave], c.tipo)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {a.paginacion && a.paginacion.total > a.filas.length && (
        <p className="nota">
          Mostrando {a.filas.length} de {a.paginacion.total}.
        </p>
      )}
    </div>
  );
}

const NIVEL = {
  bajo: { clase: "exito", texto: "Riesgo bajo" },
  medio: { clase: "advertencia", texto: "Riesgo medio" },
  alto: { clase: "error", texto: "Riesgo alto" },
} as const;

export function TarjetaPrediccion({ artifact: a }: PropsArtifact<"tarjeta_prediccion">) {
  const n = NIVEL[a.nivel];
  return (
    <div className="bloque">
      <RotuloSimulado />
      <p className={`insignia insignia--${n.clase}`}>
        <Icono nombre="alerta" tamano={18} />
        {n.texto}: {NUM.format(Number(a.probabilidad) * 100)} %
      </p>
      <p className="nota">
        {a.guia && <>{a.guia} · </>}Modelo {a.modelo} v{a.version_modelo}
      </p>
      {a.factores && a.factores.length > 0 && (
        <ul className="lista-icono">
          {a.factores.map((f) => (
            <li key={f.nombre}>
              <Icono nombre="flecha" tamano={16} />
              <span>
                {f.descripcion ?? f.nombre}: {Number(f.efecto) >= 0 ? "+" : ""}
                {NUM.format(Number(f.efecto) * 100)} puntos
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function MetricasModelo({ artifact: a }: PropsArtifact<"metricas_modelo">) {
  const lista = (m?: Record<string, string>) =>
    Object.entries(m ?? {})
      .map(([k, v]) => `${k}: ${NUM.format(Number(v))}`)
      .join(" · ") || "—";
  return (
    <div className="bloque">
      <RotuloSimulado />
      <div className="tabla-caja">
        <table className="tabla">
          <thead>
            <tr>
              <th scope="col">Modelo</th>
              <th scope="col">Estado</th>
              <th scope="col">Métricas</th>
              <th scope="col">Línea base</th>
              <th scope="col">Muestras</th>
            </tr>
          </thead>
          <tbody>
            {a.modelos.map((m) => (
              <tr key={`${m.nombre}${m.version}`}>
                <td>
                  {m.nombre} v{m.version}
                </td>
                <td>
                  <span className="etiqueta">{m.estado}</span>
                </td>
                <td>{lista(m.metricas as Record<string, string>)}</td>
                <td>{lista(m.linea_base as Record<string, string> | undefined)}</td>
                <td>{NUM.format(m.n_train)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ColaEscalamientos({ artifact: a }: PropsArtifact<"cola_escalamientos">) {
  if (!a.items?.length) return <p className="nota">No hay casos en la cola.</p>;
  return (
    <ul className="lista-simple">
      {a.items.map((i) => (
        <li key={i.escalamiento_id}>
          <span className="etiqueta">
            {i.criterio} · {i.prioridad}
          </span>
          <span>{i.resumen}</span>
          <Link to={`/asesor?sesion=${i.sesion_id}`}>Abrir en la consola</Link>
        </li>
      ))}
    </ul>
  );
}
