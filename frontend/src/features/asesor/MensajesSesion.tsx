import { useEffect, useRef } from "react";
import type { MensajeSesion } from "../../services/asesor";

const HORA = new Intl.DateTimeFormat("es-CO", { hour: "numeric", minute: "2-digit", timeZone: "America/Bogota" });

/** "[formulario_guia] guia=…" es el registro técnico de un formulario enviado por el cliente. */
function formularioEnviado(contenido: string) {
  const m = /^\[([a-z_]+)\] (.*)$/s.exec(contenido);
  return m ? { tipo: m[1].replace(/_/g, " "), datos: m[2] } : null;
}

/** Historial visto por el personal: quién habló, con la IA aparte de la conversación entre personas. */
export function MensajesSesion({ mensajes }: { mensajes: MensajeSesion[] }) {
  const final = useRef<HTMLDivElement>(null);
  useEffect(() => {
    final.current?.scrollIntoView({ block: "end" });
  }, [mensajes.length]);

  return (
    <ol className="mensajes" role="log" aria-live="polite" aria-label="Mensajes de la conversación">
      {mensajes.map((m) => {
        const hora = <time dateTime={m.creado_en}>{HORA.format(new Date(m.creado_en))}</time>;
        if (m.rol === "asistente" || m.rol === "sistema") {
          const tarjetas = (m.artifacts as { tipo?: string }[]).map((a) => a.tipo?.replace(/_/g, " ")).filter(Boolean);
          return (
            <li key={m.id} className="mensaje mensaje--ia">
              <span className="mensaje__autor">RUTI {hora}</span>
              {m.contenido && <p>{m.contenido}</p>}
              {tarjetas.length > 0 && <p className="nota">Mostró: {tarjetas.join(", ")}</p>}
            </li>
          );
        }
        const formulario = m.rol === "usuario" ? formularioEnviado(m.contenido) : null;
        return (
          <li key={m.id} className={`mensaje mensaje--${m.rol}`}>
            <span className="mensaje__autor">
              {m.rol === "asesor" ? "Asesor" : "Cliente"} {hora}
            </span>
            {formulario ? (
              <p>
                <strong>Envió {formulario.tipo}:</strong> {formulario.datos}
              </p>
            ) : (
              <p>{m.contenido}</p>
            )}
          </li>
        );
      })}
      <div ref={final} />
    </ol>
  );
}
