import { NavLink, Outlet } from "react-router-dom";
import { Icono, type NombreIcono } from "../../components/ui/Icono";

const SECCIONES: { a: string; texto: string; icono: NombreIcono; fin?: boolean }[] = [
  { a: "/admin", texto: "Resumen", icono: "chispa", fin: true },
  { a: "/admin/predicciones", texto: "Predicciones IA", icono: "ruta" },
  { a: "/admin/chat", texto: "Preguntar", icono: "chat" },
  { a: "/admin/usuarios", texto: "Usuarios", icono: "asesor" },
  { a: "/admin/conversaciones", texto: "Conversaciones", icono: "documento" },
  { a: "/admin/envios", texto: "Envíos", icono: "camion" },
  { a: "/admin/pqrs", texto: "PQRS", icono: "alerta" },
  { a: "/admin/conocimiento", texto: "Conocimiento", icono: "lupa" },
  { a: "/admin/auditoria", texto: "Auditoría", icono: "escudo" },
];

export function PanelAdmin() {
  return (
    <div className="panel">
      <h1 className="panel__titulo">Panel administrativo</h1>
      <nav className="panel__nav" aria-label="Secciones de administración">
        <ul>
          {SECCIONES.map((s) => (
            <li key={s.a}>
              <NavLink to={s.a} end={s.fin}>
                <Icono nombre={s.icono} tamano={18} />
                {s.texto}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <Outlet />
    </div>
  );
}
