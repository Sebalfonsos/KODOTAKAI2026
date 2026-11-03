import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";

/** Oculta rutas por rol. La autorización real la aplica el servidor (401, 403 y 404). */
export function RutaRol({ roles }: { roles: string[] }) {
  const { usuario, cargando } = useAuth();
  const lugar = useLocation();
  if (cargando) return <p role="status">Cargando…</p>;
  if (!usuario) return <Navigate to="/login" replace state={{ desde: lugar.pathname }} />;
  if (!roles.includes(usuario.rol)) return <p role="alert">No tienes permiso para ver esta sección.</p>;
  return <Outlet />;
}
