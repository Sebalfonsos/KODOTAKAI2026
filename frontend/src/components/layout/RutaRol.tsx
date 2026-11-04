import { Link, Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";

/** Oculta rutas por rol. La autorización real la aplica el servidor (401, 403 y 404). */
export function RutaRol({ roles }: { roles: string[] }) {
  const { usuario, cargando } = useAuth();
  const lugar = useLocation();
  if (cargando) return <p role="status">Cargando…</p>;
  if (!usuario) return <Navigate to="/login" replace state={{ desde: lugar.pathname }} />;
  if (!roles.includes(usuario.rol)) {
    return (
      <div className="seccion-pendiente" role="alert">
        <h1>Esta sección no es para tu cuenta.</h1>
        <p>
          Entraste como {usuario.nombre}.{" "}
          <Link to="/login" state={{ desde: lugar.pathname }}>
            Entrar con otra cuenta
          </Link>
        </p>
      </div>
    );
  }
  return <Outlet />;
}
