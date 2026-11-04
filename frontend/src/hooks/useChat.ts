import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import {
  crearSesion,
  enviarMensaje,
  escucharAsesor,
  verHistorial,
  type MensajeEntrada,
} from "../services/chat";
import { ErrorApi, ErrorRed } from "../services/http";
import { chatReducer, estadoInicial } from "../state/chatStore";

/** Una sesión por servicio: cotizar, rastrear o PQRS no heredan la conversación de otro. */
const claveSesion = (servicio: string) => `translogix.sesion.${servicio}`;

function recordarSesion(servicio: string, id: string | null) {
  try {
    if (id) sessionStorage.setItem(claveSesion(servicio), id);
    else sessionStorage.removeItem(claveSesion(servicio));
  } catch {
    // La conversación sigue funcionando; solo no se recupera al recargar.
  }
}

function sesionGuardada(servicio: string): string | null {
  try {
    return sessionStorage.getItem(claveSesion(servicio));
  } catch {
    return null;
  }
}

export function useChat(servicio: string) {
  const [estado, despachar] = useReducer(chatReducer, estadoInicial);
  const sesionRef = useRef<string | null>(null);
  const pendiente = useRef<{ cuerpo: MensajeEntrada; ruta?: string } | null>(null);
  // La sesión guardada se recupera primero: un envío simultáneo quedaría pisado por el historial.
  const [listo, setListo] = useState(() => sesionGuardada(servicio) === null);
  const escalado = estado.escalamiento !== null && estado.escalamiento.fase !== "resuelto";

  const reconciliar = useCallback(async () => {
    if (!sesionRef.current) return null;
    const historial = await verHistorial(sesionRef.current);
    despachar({ tipo: "historial", historial });
    return historial;
  }, []);

  useEffect(() => {
    const guardada = sesionGuardada(servicio);
    if (!guardada) return;
    sesionRef.current = guardada;
    reconciliar()
      .catch(() => {
        // Sesión vencida o ajena: se empieza una nueva con el siguiente mensaje.
        sesionRef.current = null;
        recordarSesion(servicio, null);
      })
      .finally(() => setListo(true));
  }, [reconciliar, servicio]);

  useEffect(() => {
    if (!escalado || !sesionRef.current) return;
    return escucharAsesor(
      sesionRef.current,
      (evento) => despachar({ tipo: "asesor", evento }),
      () => void reconciliar().catch(() => undefined),
    );
  }, [escalado, reconciliar]);

  const enviar = useCallback(
    async (cuerpo: MensajeEntrada, ruta?: string, reintento = false): Promise<void> => {
      if (!reintento) despachar({ tipo: "enviar", texto: cuerpo.tipo === "texto" ? cuerpo.texto : null });
      pendiente.current = { cuerpo, ruta };
      let terminado = false;
      try {
        if (!sesionRef.current) {
          const sesion = await crearSesion();
          sesionRef.current = sesion.id;
          recordarSesion(servicio, sesion.id);
          despachar({ tipo: "sesion", id: sesion.id });
        }
        await enviarMensaje(ruta ?? `/api/v1/chat/sesiones/${sesionRef.current}/mensajes`, cuerpo, (evento) => {
          if (evento.evento === "fin" || evento.evento === "error") terminado = true;
          despachar({ tipo: "evento", evento });
        });
        if (!terminado) throw new ErrorRed("La respuesta se interrumpió.");
        pendiente.current = null;
      } catch (e) {
        if (e instanceof ErrorApi) {
          const codigo = e.problema.codigo;
          // Conversación cerrada por inactividad o ajena tras cambiar de cuenta: el texto sigue en una nueva.
          if (codigo === "SESION_CERRADA" || codigo === "SESION_NO_ENCONTRADA") {
            sesionRef.current = null;
            recordarSesion(servicio, null);
            if (cuerpo.tipo === "texto" && !reintento) return enviar(cuerpo, undefined, true);
            despachar({
              tipo: "fallo",
              titulo: "Esa conversación ya terminó.",
              detalle: "Escribe tu mensaje para iniciar una nueva.",
              reintentable: false,
            });
            return;
          }
          // Un 422 de formulario lo pinta el formulario, junto a cada campo.
          if (e.status === 422 && e.problema.errores?.length && cuerpo.tipo === "artifact_submit") {
            despachar({ tipo: "fallo", titulo: "Revisa los datos marcados.", reintentable: false });
            throw e;
          }
          despachar({
            tipo: "fallo",
            titulo: e.problema.title,
            detalle: e.reintentarEnS ? `Intenta de nuevo en ${e.reintentarEnS} s.` : (e.problema.detail ?? undefined),
            reintentable: e.status === 429 || e.status >= 500,
          });
          return;
        }
        // Corte de red: reenviar duplicaría el turno si el servidor ya lo recibió. Primero se consulta el historial.
        const llego = await reconciliar()
          .then((h) => {
            const u = h?.mensajes.filter((m) => m.rol === "usuario").at(-1);
            return cuerpo.tipo === "texto" && u?.contenido === cuerpo.texto;
          })
          .catch(() => false);
        despachar({
          tipo: "fallo",
          titulo: "No pude completar la consulta. ¿Reintentamos?",
          detalle: llego ? "Tu mensaje sí llegó; recuperé lo que el servidor alcanzó a responder." : undefined,
          reintentable: !llego,
        });
      }
    },
    [reconciliar, servicio],
  );

  const reintentar = useCallback(() => {
    if (!pendiente.current) return;
    // La burbuja del usuario ya está en pantalla: solo se reactiva el turno.
    despachar({ tipo: "enviar", texto: null });
    void enviar(pendiente.current.cuerpo, pendiente.current.ruta, true);
  }, [enviar]);

  const nueva = useCallback(() => {
    sesionRef.current = null;
    recordarSesion(servicio, null);
    despachar({ tipo: "reiniciar" });
  }, [servicio]);

  return { estado, listo, enviar, reintentar, nueva };
}
