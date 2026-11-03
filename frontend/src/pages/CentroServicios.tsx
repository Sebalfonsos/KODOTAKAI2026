import { Link } from "react-router-dom";
import { Ruti } from "../components/ruti/Ruti";

const SERVICIOS = [
  { a: "/consultar", titulo: "Consultar envío", texto: "Rastrea tu guía y mira en qué va." },
  { a: "/cotizar", titulo: "Cotizar flete", texto: "Conoce el valor exacto con su desglose." },
  { a: "/pqrs", titulo: "Gestionar reclamación", texto: "Radica tu caso con los documentos correctos." },
  { a: "/ayuda", titulo: "Resolver dudas", texto: "Pregunta por mercancías, embalaje o cobertura." },
];

export function CentroServicios() {
  return (
    <div className="servicios">
      <div className="servicios__saludo">
        <Ruti vista={{ estado: "reposo", fase: null }} encuadre="cabeza" />
        <div>
          <h1>¡Hola! Soy RUTI. ¿Qué necesitas hoy?</h1>
          <p>Elige una opción y te acompaño en el proceso.</p>
        </div>
      </div>
      <ul className="servicios__lista">
        {SERVICIOS.map((s) => (
          <li key={s.a}>
            <Link to={s.a} className="tarjeta-servicio">
              <strong>{s.titulo}</strong>
              <span>{s.texto}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
