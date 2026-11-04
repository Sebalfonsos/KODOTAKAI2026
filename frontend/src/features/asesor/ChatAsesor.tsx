import { useEffect, useState, type FormEvent } from "react";
import { Icono } from "../../components/ui/Icono";
import { useAuth } from "../../hooks/useAuth";
import { useDatos } from "../../hooks/useDatos";
import { escucharSesion, resolver, responder, tomar, verSesion } from "../../services/asesor";
import { mensajeError } from "../../services/http";
import { Estado, NUM } from "../admin/comun";
import { MensajesSesion } from "./MensajesSesion";

interface Props {
  sesionId: string;
  alCambiar: () => void;
  alVolver: () => void;
}

export function ChatAsesor({ sesionId, alCambiar, alVolver }: Props) {
  const { usuario } = useAuth();
  const { datos: sesion, error, cargando, recargar } = useDatos(() => verSesion(sesionId), [sesionId]);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [fallo, setFallo] = useState<string | null>(null);
  const [cerrando, setCerrando] = useState(false);
  const [nota, setNota] = useState("");

  const esc = sesion?.escalamiento;
  const abierto = !!esc && esc.estado !== "resuelto";
  useEffect(() => {
    if (!abierto) return;
    return escucharSesion(sesionId, () => void recargar());
  }, [abierto, sesionId, recargar]);

  const mio = esc?.estado === "tomado" && (esc.asesor_id === usuario?.id || usuario?.rol === "admin");

  const ejecutar = async (tarea: () => Promise<unknown>) => {
    setEnviando(true);
    setFallo(null);
    try {
      await tarea();
      await recargar();
      alCambiar();
      return true;
    } catch (e) {
      setFallo(mensajeError(e));
      await recargar();
      alCambiar();
      return false;
    } finally {
      setEnviando(false);
    }
  };

  const mandar = async (e?: FormEvent) => {
    e?.preventDefault();
    const limpio = texto.trim();
    if (!limpio || enviando) return;
    if (await ejecutar(() => responder(sesionId, limpio))) setTexto("");
  };
  const cerrarCaso = async (e: FormEvent) => {
    e.preventDefault();
    if (!esc) return;
    if (await ejecutar(() => resolver(esc.id, nota.trim()))) {
      setCerrando(false);
      setNota("");
    }
  };

  const payload = (esc?.payload ?? {}) as { sentimiento_detectado?: string; palabras_detectadas?: string[]; confidence_score_promedio?: number; intentos_previos?: number; nota_resolucion?: string | null };

  return (
    <div className="consola__sala">
      <section className="consola__chat" aria-label="Chat con el cliente">
        <header className="consola__cabeza">
          <button type="button" className="boton boton--icono consola__volver" aria-label="Volver a la cola" onClick={alVolver}>
            <Icono nombre="atras" />
          </button>
          <div className="consola__quien">
            <h2>{sesion?.usuario?.nombre ?? "Cliente invitado"}</h2>
            <p className="nota">{esc ? `${esc.criterio_categoria}${esc.numero_guia ? ` · ${esc.numero_guia}` : ""}` : "Sin escalamiento"}</p>
          </div>
          {mio && !cerrando && (
            <button type="button" className="boton boton--secundario boton--chico" onClick={() => setCerrando(true)}>
              Resolver caso
            </button>
          )}
        </header>
        <Estado error={error} cargando={cargando} hayDatos={!!sesion} alReintentar={recargar} />
        <div className="consola__hilo">{sesion && <MensajesSesion mensajes={sesion.mensajes} />}</div>
        {fallo && (
          <p className="alerta alerta--critica" role="alert">
            {fallo}
          </p>
        )}
        {esc?.estado === "pendiente" && (
          <div className="consola__pie">
            <p>Este caso aún no tiene asesor. Tómalo para responderle al cliente.</p>
            <button type="button" className="boton boton--primario" disabled={enviando} onClick={() => void ejecutar(() => tomar(esc.id))}>
              Tomar caso
            </button>
          </div>
        )}
        {esc?.estado === "tomado" && !mio && <p className="consola__pie">Otro asesor está atendiendo este caso.</p>}
        {esc?.estado === "resuelto" && (
          <p className="consola__pie">
            Caso resuelto{payload.nota_resolucion ? `: ${payload.nota_resolucion}` : "."} La conversación volvió a RUTI.
          </p>
        )}
        {mio && cerrando && (
          <form className="consola__cierre" onSubmit={(e) => void cerrarCaso(e)}>
            <label htmlFor="nota-cierre">Nota de cierre (opcional)</label>
            <textarea id="nota-cierre" rows={2} maxLength={1000} value={nota} onChange={(e) => setNota(e.target.value)} placeholder="Qué se resolvió" autoFocus />
            <div className="chips">
              <button className="boton boton--primario" disabled={enviando}>
                Confirmar y devolver a RUTI
              </button>
              <button type="button" className="boton boton--secundario" onClick={() => setCerrando(false)}>
                Seguir atendiendo
              </button>
            </div>
          </form>
        )}
        {mio && !cerrando && (
          <form className="compositor" onSubmit={(e) => void mandar(e)}>
            <label htmlFor="respuesta-asesor" className="sr-only">
              Respuesta al cliente
            </label>
            <textarea
              id="respuesta-asesor"
              rows={1}
              maxLength={2000}
              value={texto}
              placeholder="Escribe al cliente…"
              onChange={(e) => setTexto(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) void mandar(e);
              }}
            />
            <button className="boton boton--primario" disabled={enviando || !texto.trim()} aria-label="Enviar al cliente">
              <Icono nombre="flecha" />
            </button>
          </form>
        )}
      </section>

      <aside className="consola__contexto" aria-label="Contexto del caso">
        <h3>Resumen de la IA</h3>
        <p>{esc?.resumen_ia ?? "Sin resumen: el servicio de IA no lo generó."}</p>
        <h3>Por qué llegó</h3>
        {esc && (
          <dl className="consola__datos">
            <div>
              <dt>Criterio</dt>
              <dd>{esc.criterio_id}</dd>
            </div>
            {esc.numero_guia && (
              <div>
                <dt>Guía</dt>
                <dd className="dato-mono">{esc.numero_guia}</dd>
              </div>
            )}
            <div>
              <dt>Sentimiento</dt>
              <dd>{payload.sentimiento_detectado ?? "—"}</dd>
            </div>
            {payload.palabras_detectadas && payload.palabras_detectadas.length > 0 && (
              <div>
                <dt>Palabras detectadas</dt>
                <dd>{payload.palabras_detectadas.join(", ")}</dd>
              </div>
            )}
            {payload.confidence_score_promedio != null && (
              <div>
                <dt>Confianza de la IA</dt>
                <dd>{NUM.format(payload.confidence_score_promedio * 100)} %</dd>
              </div>
            )}
            <div>
              <dt>Escalamientos previos</dt>
              <dd>{payload.intentos_previos ?? 0}</dd>
            </div>
          </dl>
        )}
        <h3>Cliente</h3>
        <dl className="consola__datos">
          <div>
            <dt>Nombre</dt>
            <dd>{sesion?.usuario?.nombre ?? "Invitado"}</dd>
          </div>
          {sesion?.usuario && (
            <div>
              <dt>Correo</dt>
              <dd>{sesion.usuario.email}</dd>
            </div>
          )}
          {sesion?.cuenta && (
            <>
              <div>
                <dt>Cuenta</dt>
                <dd>
                  {sesion.cuenta.razon_social}
                  {sesion.cuenta.es_vip && <span className="etiqueta etiqueta--vip">VIP</span>}
                </dd>
              </div>
              <div>
                <dt>NIT</dt>
                <dd>{sesion.cuenta.nit_enmascarado}</dd>
              </div>
              <div>
                <dt>Envíos al mes</dt>
                <dd>{NUM.format(sesion.cuenta.envios_mensuales)}</dd>
              </div>
            </>
          )}
        </dl>
      </aside>
    </div>
  );
}
