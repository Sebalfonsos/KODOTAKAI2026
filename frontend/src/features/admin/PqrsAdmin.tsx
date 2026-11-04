import { useState } from "react";
import { useDatos } from "../../hooks/useDatos";
import { editarPqrs, verPqrs, verUsuarios, type Pqrs } from "../../services/admin";
import { mensajeError } from "../../services/http";
import { COP, Estado, Filtro, Paginador, Seccion, fecha } from "./comun";

type EstadoPqrs = Pqrs["estado"];
/** Solo para ofrecer los botones: quien valida la transición es el servidor (409 TRANSICION_INVALIDA). */
const SIGUIENTES: Record<EstadoPqrs, EstadoPqrs[]> = {
  incompleto: ["radicado"],
  radicado: ["en_revision"],
  en_revision: ["aprobado", "rechazado"],
  aprobado: ["cerrado"],
  rechazado: ["cerrado"],
  cerrado: [],
};
const NOMBRE: Record<EstadoPqrs, string> = {
  incompleto: "Incompleto",
  radicado: "Radicado",
  en_revision: "En revisión",
  aprobado: "Aprobado",
  rechazado: "Rechazado",
  cerrado: "Cerrado",
};
const ACCION: Record<EstadoPqrs, string> = {
  incompleto: "Marcar incompleto",
  radicado: "Radicar",
  en_revision: "Revisar",
  aprobado: "Aprobar",
  rechazado: "Rechazar",
  cerrado: "Cerrar",
};
const TIPOS = [
  ["", "Todos"],
  ["P", "Petición"],
  ["Q", "Queja"],
  ["R", "Reclamo"],
  ["S", "Sugerencia"],
] as const;

export function PqrsAdmin() {
  const [estado, setEstado] = useState("");
  const [tipo, setTipo] = useState("");
  const [pagina, setPagina] = useState(1);
  const [fallo, setFallo] = useState<string | null>(null);
  const { datos, error, cargando, recargar } = useDatos(() => verPqrs(estado, tipo, pagina), [estado, tipo, pagina]);
  const { datos: asesores } = useDatos(() => verUsuarios("asesor", 1), []);

  const cambiar = async (radicado: string, c: Parameters<typeof editarPqrs>[1]) => {
    setFallo(null);
    try {
      await editarPqrs(radicado, c);
      await recargar();
    } catch (e) {
      setFallo(mensajeError(e));
    }
  };

  return (
    <div className="panel__cuerpo">
      {fallo && (
        <p className="alerta alerta--critica" role="alert">
          {fallo}
        </p>
      )}
      <Seccion
        titulo="PQRS"
        descripcion="Primero las escaladas y las más próximas a vencer."
        acciones={
          <div className="filtros">
            <Filtro
              etiqueta="Estado"
              valor={estado}
              opciones={[["", "Todos"], ...(Object.keys(NOMBRE) as EstadoPqrs[]).map((e) => [e, NOMBRE[e]] as const)]}
              alCambiar={(v) => {
                setEstado(v);
                setPagina(1);
              }}
            />
            <Filtro
              etiqueta="Tipo"
              valor={tipo}
              opciones={TIPOS}
              alCambiar={(v) => {
                setTipo(v);
                setPagina(1);
              }}
            />
          </div>
        }
      >
        <Estado error={error} cargando={cargando} hayDatos={!!datos} alReintentar={recargar} />
        {datos && !datos.items.length && <p className="nota">No hay PQRS con estos filtros.</p>}
        {datos && datos.items.length > 0 && (
          <>
            <div className="tabla-caja">
              <table className="tabla">
                <thead>
                  <tr>
                    <th scope="col">Radicado</th>
                    <th scope="col">Tipo</th>
                    <th scope="col">Estado</th>
                    <th scope="col">Guía</th>
                    <th scope="col">Valor reclamado</th>
                    <th scope="col">Responder antes de</th>
                    <th scope="col">Asignada a</th>
                    <th scope="col">Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {datos.items.map((t) => (
                    <tr key={t.radicado}>
                      <td className="dato-mono">{t.radicado}</td>
                      <td>{t.tipo}</td>
                      <td>
                        <span className="etiqueta">{NOMBRE[t.estado]}</span>
                      </td>
                      <td className="dato-mono">{t.numero_guia ?? "—"}</td>
                      <td>{t.valor_reclamado ? COP.format(Number(t.valor_reclamado)) : "—"}</td>
                      <td>{fecha(t.fecha_limite_respuesta)}</td>
                      <td>
                        <select aria-label={`Asignar ${t.radicado}`} value={t.asignado_a ?? ""} onChange={(e) => e.target.value && void cambiar(t.radicado, { asignado_a: e.target.value })}>
                          <option value="">Sin asignar</option>
                          {asesores?.items.map((a) => (
                            <option key={a.id} value={a.id}>
                              {a.nombre}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="tabla__acciones">
                        {SIGUIENTES[t.estado].map((s) => (
                          <button key={s} type="button" className="boton boton--secundario boton--chico" onClick={() => void cambiar(t.radicado, { estado: s })}>
                            {ACCION[s]}
                          </button>
                        ))}
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
