import { describe, expect, it } from "vitest";
import type { Artifact, EventoChat } from "../src/services/chat";
import { chatReducer, estadoInicial, type EstadoChat, type TurnoAgente } from "../src/state/chatStore";

const aplicar = (e: EstadoChat, ...eventos: EventoChat[]) =>
  eventos.reduce((s, evento) => chatReducer(s, { tipo: "evento", evento }), e);
const meta: EventoChat = { evento: "meta", data: { turno_id: "t1", sesion_id: "s", intencion: "rastrear" } };
const fin: EventoChat = { evento: "fin", data: { turno_id: "t1", confianza: 0.9, latencias_ms: { total: 1 } } };
const turno = (e: EstadoChat) => e.entradas.at(-1) as TurnoAgente;

describe("chatReducer", () => {
  it("concatena deltas y el reemplazo sustituye todo el texto del turno", () => {
    const e = aplicar(
      estadoInicial,
      meta,
      { evento: "delta", data: { texto: "Sí puedes " } },
      { evento: "delta", data: { texto: "enviarlo" } },
      { evento: "reemplazo", data: { texto: "Está prohibido.", motivo: "polaridad_contradice_veredicto" } },
    );
    expect(turno(e).texto).toBe("Está prohibido.");
    expect(turno(e).corregido).toBe(true);
    expect(turno(e).intencion).toBe("rastrear");
  });

  it("el artifact se conserva en el turno abierto y `fin` lo cierra", () => {
    const artifact = { id: "a", tipo: "citas", version: 1, acciones: [], citas: [] } as unknown as Artifact;
    const inicio = chatReducer(estadoInicial, { tipo: "enviar", texto: "hola" });
    const e = aplicar(inicio, meta, { evento: "artifact", data: { artifact } }, fin);
    expect(turno(e).artifacts).toHaveLength(1);
    expect(turno(e).completo).toBe(true);
    expect(turno(e).latencias).toEqual({ total: 1 });
    expect(e.enCurso).toBe(false);
  });

  it("solo pasa a conectado con un mensaje real del asesor", () => {
    const escalado = aplicar(estadoInicial, {
      evento: "escalamiento",
      data: { escalamiento_id: "x", criterio: "CRIT-002", prioridad: "alta", mensaje: "m", espera_estimada_s: 45 },
    });
    expect(escalado.escalamiento?.fase).toBe("transfiriendo");
    const conectado = chatReducer(escalado, {
      tipo: "asesor",
      evento: { evento: "mensaje_asesor", data: { texto: "Hola", asesor: "Ana", creado_en: "" } },
    });
    expect(conectado.escalamiento?.fase).toBe("conectado");
  });

  it("el historial no muestra como mensaje el registro técnico de un formulario", () => {
    const base = { id: 1, turno_id: "t", artifacts: [], intencion: null, confianza: null, creado_en: "" };
    const e = chatReducer(estadoInicial, {
      tipo: "historial",
      historial: {
        id: "s",
        estado: "activa",
        canal: "web",
        creado_en: "",
        mensajes: [
          { ...base, rol: "usuario", contenido: "Quiero rastrear" },
          { ...base, rol: "usuario", contenido: "[formulario_guia] guia=TLX-551904-CO" },
        ],
      } as never,
    });
    expect(e.entradas).toEqual([{ rol: "usuario", texto: "Quiero rastrear" }]);
  });
});

describe("mensajes durante un escalamiento", () => {
  it("marca como acuse la confirmación de que el mensaje llegó al asesor", () => {
    const e = chatReducer(estadoInicial, { tipo: "evento", evento: { evento: "meta", data: { turno_id: "t", sesion_id: "s", intencion: "asesor_humano" } } });
    expect(e.entradas[0]).toMatchObject({ rol: "agente", acuse: true });
    const normal = chatReducer(estadoInicial, { tipo: "evento", evento: { evento: "meta", data: { turno_id: "t", sesion_id: "s", intencion: "rastrear" } } });
    expect(normal.entradas[0]).toMatchObject({ acuse: false });
  });
});
