import { useState } from "react";
import { Link } from "react-router-dom";
import { useDatos } from "../../hooks/useDatos";
import { verEnvios } from "../../services/admin";
import { COP, Estado, Filtro, NUM, Paginador, Seccion, fecha } from "./comun";

const ESTADOS = ["EN_TRANSITO", "EN_REPARTO", "EN_BODEGA_ORIGEN", "EN_BODEGA_DESTINO", "RECOGIDO_EN_ORIGEN", "SOLICITUD_GENERADA", "RETENIDO_NOVEDAD", "ENTREGADO"];

export function Envios() {
  const [estado, setEstado] = useState("");
  const [origen, setOrigen] = useState("");
  const [pagina, setPagina] = useState(1);
  const { datos, error, cargando, recargar } = useDatos(() => verEnvios(estado, origen, pagina), [estado, origen, pagina]);
  return (
    <div className="panel__cuerpo">
      <Seccion
        titulo="Envíos"
        descripcion="Los datos personales se muestran enmascarados."
        acciones={
          <div className="filtros">
            <Filtro
              etiqueta="Estado"
              valor={estado}
              opciones={[["", "Todos"], ...ESTADOS.map((e) => [e, e] as const)]}
              alCambiar={(v) => {
                setEstado(v);
                setPagina(1);
              }}
            />
            <Filtro
              etiqueta="Procedencia"
              valor={origen}
              opciones={[
                ["", "Todas"],
                ["dataset", "Dataset"],
                ["simulado", "Simulado"],
              ]}
              alCambiar={(v) => {
                setOrigen(v);
                setPagina(1);
              }}
            />
          </div>
        }
      >
        <Estado error={error} cargando={cargando} hayDatos={!!datos} alReintentar={recargar} />
        {datos && (
          <>
            <div className="tabla-caja">
              <table className="tabla">
                <thead>
                  <tr>
                    <th scope="col">Guía</th>
                    <th scope="col">Estado</th>
                    <th scope="col">Trayecto</th>
                    <th scope="col">Destinatario</th>
                    <th scope="col">Peso</th>
                    <th scope="col">Valor declarado</th>
                    <th scope="col">Entrega estimada</th>
                    <th scope="col">Predicción</th>
                  </tr>
                </thead>
                <tbody>
                  {datos.items.map((e) => (
                    <tr key={e.numero_guia}>
                      <td className="dato-mono">{e.numero_guia}</td>
                      <td>
                        <span className="etiqueta">{e.estado_actual}</span>
                        {e.origen_dato === "simulado" && " · simulado"}
                      </td>
                      <td>{e.trayecto_codigo ?? "—"}</td>
                      <td>{e.destinatario ?? "—"}</td>
                      <td>{NUM.format(Number(e.peso_facturable_kg))} kg</td>
                      <td>{COP.format(Number(e.valor_declarado))}</td>
                      <td>{fecha(e.fecha_estimada_entrega)}</td>
                      <td>
                        <Link to={`/admin/predicciones?guia=${e.numero_guia}`}>Ver riesgo</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Paginador pagina={datos.pagina} tamano={datos.tamano} total={datos.total} alCambiar={setPagina} />
          </>
        )}
      </Seccion>
    </div>
  );
}
