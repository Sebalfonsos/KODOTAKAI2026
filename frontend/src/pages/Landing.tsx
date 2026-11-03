import { Link } from "react-router-dom";
import { Ruti, RutiStatus } from "../components/ruti/Ruti";

const SALUDO = { estado: "reposo", fase: null } as const;

export function Landing() {
  return (
    <div className="portada" data-tema="oscuro">
      <header className="portada__cabecera">
        <span className="marca">TransLogix</span>
        <Link to="/login" className="boton boton--contorno">
          Iniciar sesión
        </Link>
      </header>
      <main className="portada__cuerpo">
        <div className="portada__texto">
          <h1>
            Tu logística, más simple e <em>inteligente.</em>
          </h1>
          <p>Consulta tus envíos, cotiza y resuelve dudas con la ayuda de RUTI.</p>
          <div className="portada__acciones">
            <Link to="/ayuda" className="boton boton--acento boton--fisico">
              Conversar con RUTI
            </Link>
            <Link to="/servicios" className="boton boton--contorno">
              Explorar servicios
            </Link>
          </div>
        </div>
        <div className="portada__ruti">
          <Ruti vista={SALUDO} />
          <RutiStatus mensaje="¡Hola! Soy RUTI, tu copiloto logístico." />
        </div>
      </main>
    </div>
  );
}
