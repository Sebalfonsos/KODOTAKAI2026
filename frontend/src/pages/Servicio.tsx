import { Link, useLocation } from "react-router-dom";
import { Icono, type NombreIcono } from "../components/ui/Icono";
import { Conversacion, type Pasos } from "../features/chat/Conversacion";
import { useAuth } from "../hooks/useAuth";

interface Props {
  inicio?: string;
  titulo: string;
  pasos?: Pasos;
  /** El backend exige cuenta de cliente (p. ej. radicar PQRS): se avisa antes de empezar. */
  requiereSesion?: boolean;
  icono?: NombreIcono;
  descripcion?: string;
  conAgente?: boolean;
}

/** Cada servicio arranca un flujo del chat: el servidor emite el formulario y evalúa el escalamiento. */
export function Servicio({ inicio, titulo, pasos, requiereSesion, icono, descripcion, conAgente }: Props) {
  const { usuario } = useAuth();
  const { pathname } = useLocation();
  const aviso =
    requiereSesion && !usuario ? (
      <p className="alerta alerta--info aviso-sesion" role="note">
        <Icono nombre="asesor" tamano={18} />
        <span>
          Para radicar una reclamación necesitas tu cuenta de cliente.{" "}
          <Link to="/login" state={{ desde: pathname }}>
            Iniciar sesión
          </Link>
        </span>
      </p>
    ) : null;
  return <Conversacion key={inicio ?? "ayuda"} inicio={inicio} titulo={titulo} pasos={pasos} aviso={aviso} icono={icono} descripcion={descripcion} conAgente={conAgente} />;
}
