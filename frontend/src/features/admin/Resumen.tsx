import { useState } from "react";
import { BarrasH } from "../../components/graficos/Graficos";
import { useDatos } from "../../hooks/useDatos";
import { verMetricas, type Metricas } from "../../services/admin";
import { Estado, NUM, Seccion, hoyMas } from "./comun";

const barras = (c: Metricas["escalamientos_por_criterio"]) => c.map((x) => ({ etiqueta: x.clave, valor: x.total }));
const ms = (v?: number | null) => (v == null ? "Sin datos" : v >= 1000 ? `${NUM.format(v / 1000)} s` : `${NUM.format(v)} ms`);
const cifra = (v: number | null | undefined, sufijo = "") => (v == null ? "Sin datos" : `${NUM.format(v)}${sufijo}`);

export function Resumen() {
  const [desde, setDesde] = useState(() => hoyMas(-6));
  const [hasta, setHasta] = useState(() => hoyMas());
  const { datos: m, error, cargando, recargar } = useDatos(() => verMetricas(desde, hasta), [desde, hasta]);

  return (
    <div className="panel__cuerpo">
      <div className="filtros">
        <label className="filtro">
          <span>Desde</span>
          <input type="date" value={desde} max={hasta} onChange={(e) => setDesde(e.target.value)} />
        </label>
        <label className="filtro">
          <span>Hasta</span>
          <input type="date" value={hasta} min={desde} onChange={(e) => setHasta(e.target.value)} />
        </label>
      </div>
      <Estado error={error} cargando={cargando} hayDatos={!!m} alReintentar={recargar} />
      {m && (
        <>
          <ul className="kpis">
            <li className="kpi">
              <span className="kpi__etiqueta">Resuelto sin humano</span>
              <strong className="kpi__valor">{cifra(m.pct_resuelto_sin_humano, " %")}</strong>
              <span className="kpi__nota">
                {NUM.format(m.sesiones_escaladas)} de {NUM.format(m.sesiones)} sesiones escaladas
              </span>
            </li>
            <li className="kpi">
              <span className="kpi__etiqueta">Interacciones</span>
              <strong className="kpi__valor">{NUM.format(m.interacciones)}</strong>
              <span className="kpi__nota">Mensajes de usuarios</span>
            </li>
            <li className="kpi">
              <span className="kpi__etiqueta">Latencia p95</span>
              <strong className="kpi__valor">{ms(m.latencia_p95_ms)}</strong>
              <span className="kpi__nota">p50: {ms(m.latencia_p50_ms)}</span>
            </li>
            <li className="kpi">
              <span className="kpi__etiqueta">Confianza media</span>
              <strong className="kpi__valor">{m.confianza_media == null ? "Sin datos" : `${NUM.format(m.confianza_media * 100)} %`}</strong>
              <span className="kpi__nota">Promedio de las respuestas de la IA</span>
            </li>
            <li className="kpi">
              <span className="kpi__etiqueta">CSAT</span>
              <strong className="kpi__valor">{cifra(m.csat_promedio, " / 5")}</strong>
              <span className="kpi__nota">{NUM.format(m.calificaciones)} calificaciones</span>
            </li>
          </ul>
          <div className="panel__rejilla">
            <Seccion titulo="Escalamientos por criterio">
              <BarrasH filas={barras(m.escalamientos_por_criterio)} vacio="Ningún escalamiento en este periodo." />
            </Seccion>
            <Seccion titulo="Intenciones más frecuentes">
              <BarrasH filas={barras(m.intenciones_top)} />
            </Seccion>
            <Seccion titulo="Envíos por estado" descripcion="Foto actual de todos los envíos; no depende de las fechas.">
              <BarrasH filas={barras(m.envios_por_estado)} />
            </Seccion>
            <Seccion titulo="PQRS por estado" descripcion="Tickets creados en el periodo.">
              <BarrasH filas={barras(m.pqrs_por_estado)} vacio="Ninguna PQRS en este periodo." />
            </Seccion>
          </div>
        </>
      )}
    </div>
  );
}
