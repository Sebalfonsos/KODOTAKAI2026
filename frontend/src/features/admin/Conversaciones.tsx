import { useState } from "react";
import { Link } from "react-router-dom";
import { useDatos } from "../../hooks/useDatos";
import { verConversacion, verConversaciones } from "../../services/admin";
import { MensajesSesion } from "../asesor/MensajesSesion";
import { Estado, Filtro, Paginador, Seccion, fechaHora } from "./comun";

const ESTADOS = [
  ["", "Todas"],
  ["activa", "Activas"],
  ["escalada", "Escaladas"],
  ["cerrada", "Cerradas"],
] as const;

function Detalle({ id, cerrar }: { id: string; cerrar: () => void }) {
  const { datos, error, cargando, recargar } = useDatos(() => verConversacion(id), [id]);
  return (
    <Seccion
      titulo="Conversación"
      descripcion={datos ? `${datos.usuario?.nombre ?? "Invitado"} · ${datos.canal} · ${datos.estado}` : undefined}
      acciones={
        <button type="button" className="boton boton--secundario boton--chico" onClick={cerrar}>
          Cerrar
        </button>
      }
    >
      <Estado error={error} cargando={cargando} hayDatos={!!datos} alReintentar={recargar} />
      {datos?.escalamiento && (
        <p className="nota">
          {datos.escalamiento.criterio_id}: {datos.escalamiento.criterio_categoria} · {datos.escalamiento.estado}.{" "}
          {datos.estado === "escalada" && <Link to={`/asesor?sesion=${datos.id}`}>Abrir en la consola del asesor</Link>}
        </p>
      )}
      {datos && <MensajesSesion mensajes={datos.mensajes} />}
    </Seccion>
  );
}

export function Conversaciones() {
  const [estado, setEstado] = useState("");
  const [pagina, setPagina] = useState(1);
  const [abierta, setAbierta] = useState<string | null>(null);
  const { datos, error, cargando, recargar } = useDatos(() => verConversaciones(estado, pagina), [estado, pagina]);
  return (
    <div className="panel__cuerpo">
      {abierta && <Detalle id={abierta} cerrar={() => setAbierta(null)} />}
      <Seccion
        titulo="Conversaciones"
        descripcion="Las más recientes primero."
        acciones={
          <Filtro
            etiqueta="Estado"
            valor={estado}
            opciones={ESTADOS}
            alCambiar={(v) => {
              setEstado(v);
              setPagina(1);
            }}
          />
        }
      >
        <Estado error={error} cargando={cargando} hayDatos={!!datos} alReintentar={recargar} />
        {datos && (
          <>
            <div className="tabla-caja">
              <table className="tabla">
                <thead>
                  <tr>
                    <th scope="col">Última actividad</th>
                    <th scope="col">Canal</th>
                    <th scope="col">Estado</th>
                    <th scope="col">Mensajes</th>
                    <th scope="col">Último mensaje</th>
                    <th scope="col">Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {datos.items.map((c) => (
                    <tr key={c.id}>
                      <td>{fechaHora(c.ultima_actividad)}</td>
                      <td>{c.canal}</td>
                      <td>
                        <span className="etiqueta">{c.estado}</span>
                        {c.escalada && " · escalada"}
                      </td>
                      <td>{c.mensajes}</td>
                      <td className="tabla__largo">{c.ultimo_mensaje ?? "—"}</td>
                      <td>
                        <button type="button" className="boton boton--secundario boton--chico" onClick={() => setAbierta(c.id)}>
                          Ver
                        </button>
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
