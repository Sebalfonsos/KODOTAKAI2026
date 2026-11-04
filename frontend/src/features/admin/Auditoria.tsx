import { useState } from "react";
import { useDatos } from "../../hooks/useDatos";
import { verAuditoria } from "../../services/admin";
import { Estado, Filtro, Paginador, Seccion, fechaHora } from "./comun";

const ENTIDADES = [
  ["", "Todas"],
  ["escalamiento", "Escalamientos"],
  ["sesion", "Sesiones"],
  ["usuario", "Usuarios"],
  ["pqrs", "PQRS"],
  ["documento", "Documentos"],
] as const;

export function Auditoria() {
  const [entidad, setEntidad] = useState("");
  const [pagina, setPagina] = useState(1);
  const { datos, error, cargando, recargar } = useDatos(() => verAuditoria(entidad, pagina), [entidad, pagina]);
  return (
    <div className="panel__cuerpo">
      <Seccion
        titulo="Auditoría"
        descripcion="Lo que hicieron asesores y administradores."
        acciones={
          <Filtro
            etiqueta="Entidad"
            valor={entidad}
            opciones={ENTIDADES}
            alCambiar={(v) => {
              setEntidad(v);
              setPagina(1);
            }}
          />
        }
      >
        <Estado error={error} cargando={cargando} hayDatos={!!datos} alReintentar={recargar} />
        {datos && !datos.items.length && <p className="nota">Sin registros.</p>}
        {datos && datos.items.length > 0 && (
          <>
            <div className="tabla-caja">
              <table className="tabla">
                <thead>
                  <tr>
                    <th scope="col">Fecha</th>
                    <th scope="col">Acción</th>
                    <th scope="col">Entidad</th>
                    <th scope="col">Detalle</th>
                  </tr>
                </thead>
                <tbody>
                  {datos.items.map((a) => (
                    <tr key={a.id}>
                      <td>{fechaHora(a.ocurrido_en)}</td>
                      <td className="dato-mono">{a.accion}</td>
                      <td>
                        {a.entidad}
                        {a.entidad_id && <small className="tabla__sub">{a.entidad_id}</small>}
                      </td>
                      <td className="tabla__largo">
                        {Object.entries(a.detalle)
                          .map(([k, v]) => `${k}: ${String(v)}`)
                          .join(" · ") || "—"}
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
