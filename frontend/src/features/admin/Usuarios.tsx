import { useState, type FormEvent } from "react";
import { useAuth } from "../../hooks/useAuth";
import { useDatos } from "../../hooks/useDatos";
import { crearUsuario, editarUsuario, verUsuarios, type Rol, type UsuarioCambio } from "../../services/admin";
import { mensajeError } from "../../services/http";
import { Estado, Filtro, Paginador, Seccion, fechaHora } from "./comun";

const ROLES = [
  ["cliente", "Cliente"],
  ["asesor", "Asesor"],
  ["admin", "Administrador"],
] as const;

export function Usuarios() {
  const { usuario } = useAuth();
  const [rol, setRol] = useState("");
  const [pagina, setPagina] = useState(1);
  const { datos, error, cargando, recargar } = useDatos(() => verUsuarios(rol, pagina), [rol, pagina]);
  const [fallo, setFallo] = useState<string | null>(null);
  const [creando, setCreando] = useState(false);

  const alCrear = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    const d = new FormData(form);
    setCreando(true);
    setFallo(null);
    try {
      await crearUsuario({ email: String(d.get("email")), nombre: String(d.get("nombre")), password: String(d.get("password")), rol: d.get("rol") as Rol });
      form.reset();
      await recargar();
    } catch (err) {
      setFallo(mensajeError(err));
    } finally {
      setCreando(false);
    }
  };
  const cambiar = async (id: string, c: UsuarioCambio) => {
    setFallo(null);
    try {
      await editarUsuario(id, c);
      await recargar();
    } catch (err) {
      setFallo(mensajeError(err));
    }
  };

  return (
    <div className="panel__cuerpo">
      <Seccion titulo="Crear usuario" descripcion="Así se dan de alta los asesores. La contraseña debe tener 12 caracteres o más, con letras y números.">
        <form className="filtros" onSubmit={(e) => void alCrear(e)}>
          <label className="filtro filtro--ancho">
            <span>Nombre</span>
            <input name="nombre" minLength={2} maxLength={120} required />
          </label>
          <label className="filtro filtro--ancho">
            <span>Correo</span>
            <input name="email" type="email" autoComplete="off" required />
          </label>
          <label className="filtro filtro--ancho">
            <span>Contraseña</span>
            <input name="password" type="password" minLength={12} maxLength={128} autoComplete="new-password" required />
          </label>
          <label className="filtro">
            <span>Rol</span>
            <select name="rol" defaultValue="asesor">
              {ROLES.map(([v, t]) => (
                <option key={v} value={v}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <button className="boton boton--primario" disabled={creando}>
            {creando ? "Creando…" : "Crear"}
          </button>
        </form>
      </Seccion>
      {fallo && (
        <p className="alerta alerta--critica" role="alert">
          {fallo}
        </p>
      )}
      <Seccion
        titulo="Usuarios"
        acciones={
          <Filtro
            etiqueta="Rol"
            valor={rol}
            opciones={[["", "Todos"], ...ROLES]}
            alCambiar={(v) => {
              setRol(v);
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
                    <th scope="col">Nombre</th>
                    <th scope="col">Correo</th>
                    <th scope="col">Rol</th>
                    <th scope="col">Estado</th>
                    <th scope="col">Último ingreso</th>
                    <th scope="col">Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {datos.items.map((u) => {
                    const yo = u.id === usuario?.id;
                    return (
                      <tr key={u.id}>
                        <td>
                          {u.nombre}
                          {yo && " (tú)"}
                        </td>
                        <td>{u.email}</td>
                        <td>
                          <select aria-label={`Rol de ${u.nombre}`} value={u.rol} disabled={yo} onChange={(e) => void cambiar(u.id, { rol: e.target.value as Rol })}>
                            {ROLES.map(([v, t]) => (
                              <option key={v} value={v}>
                                {t}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <span className={`etiqueta ${u.activo ? "etiqueta--exito" : ""}`}>{u.activo ? "Activo" : "Inactivo"}</span>
                        </td>
                        <td>{fechaHora(u.ultimo_login)}</td>
                        <td>
                          <button type="button" className="boton boton--secundario boton--chico" disabled={yo} onClick={() => void cambiar(u.id, { activo: !u.activo })}>
                            {u.activo ? "Desactivar" : "Activar"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
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
