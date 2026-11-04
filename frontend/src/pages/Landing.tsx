import { Link } from "react-router-dom";
import { Ruti, RutiStatus } from "../components/ruti/Ruti";
import { Icono } from "../components/ui/Icono";
import { SERVICIOS } from "./CentroServicios";

const SALUDO = { estado: "reposo", fase: null } as const;

export function Landing() {
  return (
    <div className="portada" data-tema="oscuro">
      {/* Línea de ruta ambiental: decorativa, detrás del contenido. */}
      <svg className="portada__ruta" viewBox="0 0 1440 400" preserveAspectRatio="none" aria-hidden="true" focusable="false">
        <path d="M-20 330C240 250 420 380 700 300S1180 120 1460 180" />
        <path d="M-20 360C300 300 520 400 820 330S1220 200 1460 240" />
      </svg>
      <header className="portada__cabecera">
        <Link to="/" className="marca">
          <Icono nombre="caja" tamano={26} />
          TransLogix
        </Link>
        <nav aria-label="Principal" className="portada__nav">
          <Link to="/servicios">Servicios</Link>
          <Link to="/ayuda">Ayuda</Link>
          <Link to="/login" className="boton boton--contorno boton--chico">
            <Icono nombre="asesor" tamano={18} />
            Iniciar sesión
          </Link>
        </nav>
      </header>
      <main className="portada__cuerpo">
        <div className="portada__texto">
          <p className="portada__antetitulo">TransLogix Colombia · Asistente logístico</p>
          <h1>
            Tu logística, más simple e <em>inteligente.</em>
          </h1>
          <p>Consulta tus envíos, cotiza fletes, resuelve dudas y gestiona reclamaciones con la ayuda de RUTI.</p>
          <div className="portada__acciones">
            <Link to="/ayuda" className="boton boton--acento boton--fisico boton--grande">
              <Icono nombre="chat" />
              Conversar con RUTI
              <Icono nombre="flecha" />
            </Link>
            <Link to="/servicios" className="boton boton--contorno boton--grande">
              Explorar servicios
            </Link>
          </div>
          <ul className="portada__atajos" aria-label="Accesos directos">
            {SERVICIOS.map((s) => (
              <li key={s.a}>
                <Link to={s.a}>
                  <Icono nombre={s.icono} tamano={18} />
                  {s.titulo}
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div className="portada__ruti">
          <div className="portada__escena" aria-hidden="true">
            <span className="flotante flotante--1">
              <Icono nombre="caja" tamano={28} />
            </span>
            <span className="flotante flotante--2">
              <Icono nombre="camion" tamano={28} />
            </span>
            <span className="flotante flotante--3">
              <Icono nombre="chat" tamano={28} />
            </span>
            <span className="portada__halo" />
          </div>
          <Ruti vista={SALUDO} className="ruti--saludo" />
          <RutiStatus mensaje="¡Hola! Soy RUTI, tu copiloto logístico." />
        </div>
      </main>
    </div>
  );
}
