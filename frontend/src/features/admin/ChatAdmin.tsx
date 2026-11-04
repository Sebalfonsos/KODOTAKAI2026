import { useReducer, useRef, useState, type FormEvent } from "react";
import { Icono } from "../../components/ui/Icono";
import { preguntarAdmin } from "../../services/admin";
import { ErrorApi, mensajeError } from "../../services/http";
import { chatReducer, estadoInicial } from "../../state/chatStore";
import { Hilo } from "../chat/Hilo";

const PREGUNTAS = [
  "¿Cómo vamos? Dame los KPI",
  "¿Cuál es el estado de los modelos?",
  "Riesgo de TLX-984021-CO",
  "Pronóstico de demanda de Bogotá",
  "¿Qué envíos están retenidos?",
  "Muestra la cola de escalamientos",
  "Resumen de PQRS",
  "Rendimiento de la IA",
];

/** Las consultas son herramientas fijas del servidor (sin texto-a-SQL): el modelo solo clasifica y resume. */
export function ChatAdmin() {
  const [estado, despachar] = useReducer(chatReducer, estadoInicial);
  const [texto, setTexto] = useState("");
  const sesion = useRef<string | null>(null);

  const preguntar = async (pregunta: string) => {
    const limpio = pregunta.trim();
    if (limpio.length < 2 || estado.enCurso) return;
    setTexto("");
    despachar({ tipo: "enviar", texto: limpio });
    try {
      await preguntarAdmin(limpio, sesion.current, (evento) => {
        if (evento.evento === "meta") sesion.current = evento.data.sesion_id;
        despachar({ tipo: "evento", evento });
      });
    } catch (e) {
      despachar({ tipo: "fallo", titulo: "No pude responder.", detalle: mensajeError(e), reintentable: false });
      if (e instanceof ErrorApi && e.status === 404) sesion.current = null;
    }
  };
  const alEnviar = (e: FormEvent) => {
    e.preventDefault();
    void preguntar(texto);
  };

  return (
    <div className="chat-admin">
      <Hilo
        estado={estado}
        contexto={{ enviar: async () => undefined, bloqueado: true }}
        vacio={
          <div className="agente__vacio">
            <p>
              <strong>Pregunta por la operación en lenguaje natural.</strong>
              <br />
              Las cifras salen de la base de datos y de los modelos; la IA no las inventa.
            </p>
            <ul className="chips">
              {PREGUNTAS.map((p) => (
                <li key={p}>
                  <button type="button" className="boton boton--secundario boton--chico" onClick={() => void preguntar(p)}>
                    {p}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        }
      />
      {estado.fallo && (
        <div className="banda banda--error" role="alert">
          <span>
            <strong>{estado.fallo.titulo}</strong> {estado.fallo.detalle}
          </span>
        </div>
      )}
      <form className="compositor" onSubmit={alEnviar}>
        <label htmlFor="pregunta-admin" className="sr-only">
          Tu pregunta
        </label>
        <textarea
          id="pregunta-admin"
          rows={1}
          maxLength={1000}
          value={texto}
          placeholder="Escribe tu pregunta…"
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) alEnviar(e);
          }}
        />
        <button className="boton boton--primario" disabled={estado.enCurso || texto.trim().length < 2} aria-label="Enviar">
          <Icono nombre="flecha" />
        </button>
      </form>
    </div>
  );
}
