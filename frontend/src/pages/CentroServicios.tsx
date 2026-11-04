import { Link } from "react-router-dom";
import { Ruti } from "../components/ruti/Ruti";
import { Icono, type NombreIcono } from "../components/ui/Icono";

export const SERVICIOS: { a: string; titulo: string; texto: string; cta: string; icono: NombreIcono }[] = [
  { a: "/consultar", titulo: "Consultar envío", texto: "Rastrea tu guía y mira en qué va.", cta: "Rastrear", icono: "caja" },
  { a: "/cotizar", titulo: "Cotizar flete", texto: "Conoce el valor con su desglose.", cta: "Cotizar", icono: "calculadora" },
  { a: "/pqrs", titulo: "Gestionar reclamación", texto: "Radica tu caso con los documentos correctos.", cta: "Empezar", icono: "alerta" },
  { a: "/ayuda", titulo: "Resolver dudas", texto: "Mercancías, embalaje, cobertura y tiempos.", cta: "Preguntar", icono: "chat" },
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
              <span className="tarjeta-servicio__icono">
                <Icono nombre={s.icono} tamano={26} />
              </span>
              <strong>{s.titulo}</strong>
              <span>{s.texto}</span>
              <span className="tarjeta-servicio__cta">
                {s.cta} <Icono nombre="flecha" tamano={16} />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
