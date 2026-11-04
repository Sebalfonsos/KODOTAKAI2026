import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { GraficoLinea, RotuloSimulado } from "../../components/graficos/Graficos";
import { Icono } from "../../components/ui/Icono";
import { useDatos } from "../../hooks/useDatos";
import {
  avanzarSimulador,
  entrenar,
  verEntrenamientos,
  verEstadoMl,
  verModelos,
  verOrigenes,
  verPronostico,
  verRiesgo,
  type AvanceSimulacion,
  type EstadoMl,
  type Modelo,
  type ResultadoEntrenamiento,
  type Riesgo,
} from "../../services/admin";
import { mensajeError } from "../../services/http";
import { Estado, NUM, Paginador, Seccion, fecha, fechaHora } from "./comun";

/** Con dos decimales, 0,665 y 0,663 parecerían un empate. */
const METRICA = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 3 });

const NOMBRE_MODELO: Record<string, { titulo: string; que: string }> = {
  riesgo_retraso: { titulo: "Riesgo de retraso", que: "Probabilidad de que una guía supere su fecha estimada." },
  demanda: { titulo: "Demanda por hub", que: "Despachos diarios esperados por origen." },
};

/** [métrica, etiqueta, línea base, cómo leerla]. Una métrica ausente en el modelo no se muestra. */
const METRICAS: Record<string, [string, string, string | null, string][]> = {
  riesgo_retraso: [
    ["roc_auc", "ROC-AUC", "roc_auc_logistica", "Más alto es mejor"],
    ["brier", "Brier", "brier_tasa_base", "Más bajo es mejor"],
  ],
  demanda: [
    ["mae", "MAE (despachos)", "mae_naive", "Más bajo es mejor"],
    ["mase", "MASE", "mase_naive", "Más bajo es mejor"],
    ["cobertura_80", "Cobertura del intervalo 80 %", null, "Cerca de 0,80 es mejor"],
  ],
};

const MOTIVO: Record<string, string> = {
  inicial: "Inicial",
  nuevos_datos: "Datos nuevos",
  deriva: "Deriva",
  antiguedad: "Antigüedad",
  manual: "Manual",
};
const RESULTADO: Record<string, string> = { promovido: "Promovido", rechazado: "Rechazado", en_curso: "En curso", error: "Error" };
const GUIAS = ["TLX-984021-CO", "TLX-310482-CO", "TLX-118493-CO"];

function TarjetaModelo({ m }: { m: Modelo }) {
  const info = NOMBRE_MODELO[m.nombre];
  return (
    <article className="modelo">
      <header>
        <h3>{info.titulo}</h3>
        <span className="etiqueta etiqueta--exito">Activo · v{m.version}</span>
      </header>
      <p className="nota">{info.que}</p>
      <div className="tabla-caja">
        <table className="tabla tabla--compacta">
          <thead>
            <tr>
              <th scope="col">Métrica</th>
              <th scope="col">Modelo</th>
              <th scope="col">Línea base</th>
            </tr>
          </thead>
          <tbody>
            {METRICAS[m.nombre].map(([clave, etiqueta, base, lectura]) => (
              <tr key={clave}>
                <th scope="row">
                  {etiqueta}
                  <small>{lectura}</small>
                </th>
                <td>{m.metricas[clave] == null ? "—" : METRICA.format(m.metricas[clave]!)}</td>
                <td>{base && m.linea_base[base] != null ? METRICA.format(m.linea_base[base]!) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="nota">
        {m.algoritmo} · {NUM.format(m.n_train)} muestras · datos hasta {fecha(m.entrenado_hasta)}
      </p>
    </article>
  );
}

function Autoentrenamiento({ e }: { e: EstadoMl }) {
  const avance = Math.min(100, (e.n_nuevos / e.min_etiquetas_nuevas) * 100);
  const horas = e.horas_desde_ultimo;
  return (
    <div className="auto">
      <div>
        <h3>Se reentrena solo cuando</h3>
        <ul className="auto__reglas">
          <li>
            <div>
              <strong>Hay etiquetas nuevas</strong>
              <span>
                {NUM.format(e.n_nuevos)} de {NUM.format(e.min_etiquetas_nuevas)}
              </span>
            </div>
            <span className="progreso" role="progressbar" aria-valuenow={Math.round(avance)} aria-valuemin={0} aria-valuemax={100} aria-label="Etiquetas nuevas">
              <span style={{ width: `${avance}%` }} />
            </span>
          </li>
          <li>
            <div>
              <strong>El último modelo es antiguo</strong>
              <span>
                {horas == null ? "Sin entrenar" : `Hace ${NUM.format(horas)} h`} · límite {e.max_horas} h
              </span>
            </div>
          </li>
          <li>
            <div>
              <strong>El error en vivo se desvía</strong>
              <span>
                {e.error_vivo == null
                  ? `Faltan datos: ${NUM.format(e.n_vivo)} de 50 predicciones con desenlace`
                  : `Brier ${METRICA.format(e.error_vivo)} frente a ${METRICA.format(e.error_entrenamiento ?? 0)} al entrenar · margen ${METRICA.format(e.delta_deriva)}`}
              </span>
            </div>
          </li>
        </ul>
      </div>
      <div className="auto__config">
        <h3>Configuración vigente</h3>
        <dl className="datos">
          <div>
            <dt>Revisión</dt>
            <dd>Cada {e.revision_cada_min} min</dd>
          </div>
          <div>
            <dt>Mínimo para entrenar</dt>
            <dd>{NUM.format(e.min_etiquetados)} envíos entregados</dd>
          </div>
          <div>
            <dt>Disponibles</dt>
            <dd>{NUM.format(e.n_etiquetados)} envíos entregados</dd>
          </div>
        </dl>
        <p className="nota">
          Se cambia en el servidor con <code>ML_CHECK_MIN</code>, <code>ML_MIN_NUEVOS</code> y <code>ML_MAX_HORAS</code>. Solo se promueve un modelo si supera al actual con los mismos datos de prueba.
        </p>
      </div>
    </div>
  );
}

function PanelRiesgo() {
  const [parametros] = useSearchParams();
  const inicial = parametros.get("guia") ?? "";
  const [guia, setGuia] = useState(inicial);
  const [riesgo, setRiesgo] = useState<Riesgo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  const consultar = async (valor: string) => {
    setCargando(true);
    setError(null);
    try {
      setRiesgo(await verRiesgo(valor));
    } catch (e) {
      setRiesgo(null);
      setError(mensajeError(e));
    } finally {
      setCargando(false);
    }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- solo la guía que llega en el enlace de Envíos.
  useEffect(() => void (inicial && consultar(inicial)), []);

  const alEnviar = (e: FormEvent) => {
    e.preventDefault();
    void consultar(guia.trim().toUpperCase());
  };
  const n = riesgo?.nivel;
  const clase = n === "alto" ? "error" : n === "medio" ? "advertencia" : "exito";
  const maxImpacto = Math.max(0.01, ...(riesgo?.factores ?? []).map((f) => Math.abs(f.impacto)));

  return (
    <Seccion titulo="Riesgo de retraso de una guía" descripcion="Calcula la probabilidad y explica qué factores la empujan.">
      <form className="filtros" onSubmit={alEnviar}>
        <label className="filtro filtro--ancho">
          <span>Número de guía</span>
          <input value={guia} onChange={(e) => setGuia(e.target.value)} pattern="^[Tt][Ll][Xx]-\d{6}-[Cc][Oo]$" placeholder="TLX-984021-CO" required />
        </label>
        <button className="boton boton--primario" disabled={cargando}>
          {cargando ? "Calculando…" : "Calcular"}
        </button>
      </form>
      <div className="chips">
        {GUIAS.map((g) => (
          <button
            key={g}
            type="button"
            className="boton boton--secundario boton--chico"
            onClick={() => {
              setGuia(g);
              void consultar(g);
            }}
          >
            {g}
          </button>
        ))}
      </div>
      {error && (
        <p className="alerta alerta--critica" role="alert">
          {error}
        </p>
      )}
      {riesgo && (
        <div className="riesgo" aria-live="polite">
          <div className="riesgo__cifra">
            <strong>{NUM.format(riesgo.probabilidad * 100)} %</strong>
            <span className={`etiqueta etiqueta--${clase}`}>Riesgo {riesgo.nivel}</span>
            <span className="nota">
              {riesgo.guia} · {riesgo.estado_actual}
              {riesgo.retrasado_real != null && ` · Desenlace real: ${riesgo.retrasado_real ? "se retrasó" : "a tiempo"}`} · Modelo v{riesgo.version}
            </span>
          </div>
          <div>
            <h3>Qué lo explica</h3>
            <ul className="factores">
              {riesgo.factores.map((f) => (
                <li key={f.factor}>
                  <span>{f.factor}</span>
                  <span className="factores__barra" aria-hidden="true">
                    <span data-signo={f.impacto >= 0 ? "sube" : "baja"} style={{ width: `${(Math.abs(f.impacto) / maxImpacto) * 100}%` }} />
                  </span>
                  <strong>
                    {f.impacto >= 0 ? "+" : "−"}
                    {NUM.format(Math.abs(f.impacto) * 100)} pts
                  </strong>
                </li>
              ))}
            </ul>
            <p className="nota">Puntos de probabilidad frente a un envío típico.</p>
          </div>
        </div>
      )}
    </Seccion>
  );
}

function PanelPronostico() {
  const { datos: origenes } = useDatos(verOrigenes, []);
  const [origen, setOrigen] = useState("");
  const [dias, setDias] = useState(14);
  const elegido = origen || origenes?.[0]?.valor || "";
  const { datos: p, error, cargando, recargar } = useDatos(
    () => (elegido ? verPronostico(elegido, dias) : Promise.resolve(null)),
    [elegido, dias],
  );
  return (
    <Seccion titulo="Pronóstico de despachos" descripcion={p ? `${p.hub} · modelo v${p.version}` : "Despachos diarios esperados por origen."}>
      <div className="filtros">
        <label className="filtro filtro--ancho">
          <span>Origen</span>
          <select value={elegido} onChange={(e) => setOrigen(e.target.value)}>
            {origenes?.map((o) => (
              <option key={o.valor} value={o.valor}>
                {o.etiqueta}
              </option>
            ))}
          </select>
        </label>
        <label className="filtro">
          <span>Horizonte</span>
          <select value={dias} onChange={(e) => setDias(Number(e.target.value))}>
            {[7, 14, 30].map((d) => (
              <option key={d} value={d}>
                {d} días
              </option>
            ))}
          </select>
        </label>
      </div>
      <Estado error={error} cargando={cargando} hayDatos={!!p} alReintentar={recargar} />
      {p && !error && (
        <GraficoLinea
          etiquetaX="Fecha"
          unidad="despachos"
          series={[
            { nombre: "Observado", puntos: p.historico.map((h) => ({ x: h.fecha, y: h.valor })) },
            { nombre: "Pronóstico", punteada: true, puntos: p.pronostico.map((f) => ({ x: f.fecha, y: f.prediccion, inf: f.p10, sup: f.p90 })) },
          ]}
        />
      )}
    </Seccion>
  );
}

export function Predicciones() {
  const modelos = useDatos(verModelos, []);
  const estado = useDatos(verEstadoMl, []);
  const [pagina, setPagina] = useState(1);
  const corridas = useDatos(() => verEntrenamientos(pagina), [pagina]);
  const [entrenando, setEntrenando] = useState(false);
  const [resultado, setResultado] = useState<ResultadoEntrenamiento | null>(null);
  const [fallo, setFallo] = useState<string | null>(null);
  const [diasSim, setDiasSim] = useState(7);
  const [avanzando, setAvanzando] = useState(false);
  const [avance, setAvance] = useState<AvanceSimulacion | null>(null);

  const refrescar = () => {
    void modelos.recargar();
    void estado.recargar();
    void corridas.recargar();
  };
  const accion = async (marcar: (v: boolean) => void, tarea: () => Promise<void>) => {
    marcar(true);
    setFallo(null);
    try {
      await tarea();
      refrescar();
    } catch (e) {
      setFallo(mensajeError(e));
    } finally {
      marcar(false);
    }
  };
  const reentrenar = () => void accion(setEntrenando, async () => setResultado(await entrenar()));
  const simular = () => void accion(setAvanzando, async () => setAvance(await avanzarSimulador(diasSim)));
  const activos = modelos.datos?.activos ?? [];

  return (
    <div className="panel__cuerpo">
      <div className="alerta alerta--advertencia" role="note">
        <Icono nombre="alerta" tamano={18} />
        <span>
          <strong>Datos simulados.</strong> Estos modelos aprenden del simulador de TransLogix, no de la operación real: sus cifras sirven para demostrar el flujo, no para decidir.
        </span>
      </div>

      <Seccion
        titulo="Modelos en producción"
        descripcion="El modelo activo responde las predicciones y el chat administrativo."
        acciones={
          <button type="button" className="boton boton--primario" onClick={reentrenar} disabled={entrenando}>
            {entrenando ? "Entrenando…" : "Reentrenar ahora"}
          </button>
        }
      >
        <Estado error={modelos.error} cargando={modelos.cargando} hayDatos={!!modelos.datos} alReintentar={modelos.recargar} />
        {fallo && (
          <p className="alerta alerta--critica" role="alert">
            {fallo}
          </p>
        )}
        {resultado && (
          <ul className="lista-simple" aria-live="polite">
            {Object.entries(resultado.modelos).map(([nombre, r]) => (
              <li key={nombre}>
                <span className={`etiqueta ${r.promovido ? "etiqueta--exito" : ""}`}>{r.promovido ? "Promovido" : "Se mantiene el actual"}</span>
                <span>
                  <strong>{NOMBRE_MODELO[nombre]?.titulo ?? nombre}</strong>: {r.decision}
                </span>
              </li>
            ))}
            <li className="nota">Duración: {NUM.format(resultado.duracion_s)} s</li>
          </ul>
        )}
        {modelos.datos && !activos.length && <p className="nota">Aún no hay modelos activos. Entrena el primero con «Reentrenar ahora» o avanza el simulador.</p>}
        <div className="modelos">
          {activos.map((m) => (
            <TarjetaModelo key={m.id} m={m} />
          ))}
        </div>
      </Seccion>

      <div className="panel__rejilla">
        <PanelRiesgo />
        <PanelPronostico />
      </div>

      <Seccion titulo="Autoentrenamiento" descripcion="Reglas vigentes y lo que mide ahora mismo.">
        <Estado error={estado.error} cargando={estado.cargando} hayDatos={!!estado.datos} alReintentar={estado.recargar} />
        {estado.datos && <Autoentrenamiento e={estado.datos} />}
      </Seccion>

      <Seccion titulo="Simulador" descripcion="Crea envíos simulados y cierra los pendientes: es lo que aporta etiquetas nuevas para reentrenar.">
        <div className="filtros">
          <label className="filtro">
            <span>Días a avanzar</span>
            <input type="number" min={1} max={60} value={diasSim} onChange={(e) => setDiasSim(Number(e.target.value))} />
          </label>
          <button type="button" className="boton boton--secundario" onClick={simular} disabled={avanzando || diasSim < 1 || diasSim > 60}>
            {avanzando ? "Avanzando…" : "Avanzar simulador"}
          </button>
        </div>
        {avance && (
          <p className="nota" aria-live="polite">
            Del {fecha(avance.desde)} al {fecha(avance.hasta)}: {NUM.format(avance.envios_nuevos)} envíos nuevos, {NUM.format(avance.envios_cerrados)} entregados y {NUM.format(avance.eventos)} eventos.
          </p>
        )}
      </Seccion>

      <Seccion titulo="Historial de entrenamientos" descripcion="Cada corrida con su motivo y la decisión frente al modelo activo.">
        <Estado error={corridas.error} cargando={corridas.cargando} hayDatos={!!corridas.datos} alReintentar={corridas.recargar} />
        {corridas.datos && (
          <>
            <div className="tabla-caja">
              <table className="tabla">
                <thead>
                  <tr>
                    <th scope="col">Inicio</th>
                    <th scope="col">Modelo</th>
                    <th scope="col">Motivo</th>
                    <th scope="col">Resultado</th>
                    <th scope="col">Decisión</th>
                  </tr>
                </thead>
                <tbody>
                  {corridas.datos.items.map((c) => (
                    <tr key={c.id}>
                      <td>{fechaHora(c.iniciado_en)}</td>
                      <td>{NOMBRE_MODELO[c.nombre]?.titulo ?? c.nombre}</td>
                      <td>{MOTIVO[c.motivo] ?? c.motivo}</td>
                      <td>
                        <span className={`etiqueta ${c.resultado === "promovido" ? "etiqueta--exito" : c.resultado === "error" ? "etiqueta--error" : ""}`}>{RESULTADO[c.resultado] ?? c.resultado}</span>
                      </td>
                      <td>{String((c.detalle as { decision?: unknown }).decision ?? "—")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Paginador pagina={pagina} tamano={corridas.datos.paginacion.tamano} total={corridas.datos.paginacion.total} alCambiar={setPagina} />
          </>
        )}
      </Seccion>
      <RotuloSimulado />
    </div>
  );
}
