import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { Icono } from "../ui/Icono";

const ENLACES = [
  { a: "/servicios", texto: "Inicio" },
  { a: "/consultar", texto: "Consultar envío" },
  { a: "/cotizar", texto: "Cotizar" },
  { a: "/ayuda", texto: "Ayuda" },
  { a: "/pqrs", texto: "PQRS" },
];

export function AppShell() {
  const { usuario, logout } = useAuth();
  const { pathname } = useLocation();
  return (
    <div className="app" data-tema="claro">
      <a href="#contenido" className="saltar">
        Saltar al contenido
      </a>
      <header className="cabecera">
        <Link to="/" className="marca">
          <Icono nombre="caja" tamano={22} />
          TransLogix
        </Link>
        <nav aria-label="Principal">
          <ul>
            {ENLACES.map((e) => (
              <li key={e.a}>
                <NavLink to={e.a}>{e.texto}</NavLink>
              </li>
            ))}
            {usuario?.rol === "asesor" || usuario?.rol === "admin" ? (
              <li>
                <NavLink to="/asesor">Asesor</NavLink>
              </li>
            ) : null}
            {usuario?.rol === "admin" ? (
              <li>
                <NavLink to="/admin">Admin</NavLink>
              </li>
            ) : null}
          </ul>
        </nav>
        {usuario ? (
          <button type="button" className="boton boton--enlace" onClick={() => void logout()}>
            Salir
          </button>
        ) : (
          <Link className="boton boton--secundario" to="/login" state={{ desde: pathname }}>
            Iniciar sesión
          </Link>
        )}
      </header>
      <main id="contenido" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
