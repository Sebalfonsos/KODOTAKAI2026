import { describe, expect, it } from "vitest";
import { ErrorSilencio, extraerEventos, leerStream } from "../src/services/sse";

describe("extraerEventos", () => {
  it("lee eventos completos e ignora keep-alive", () => {
    const { eventos, resto } = extraerEventos(': ping\n\nevent: delta\ndata: {"texto":"Hola"}\n\n');
    expect(eventos).toEqual([{ evento: "delta", data: { texto: "Hola" } }]);
    expect(resto).toBe("");
  });

  it("conserva un evento cortado a la mitad hasta que llegue completo", () => {
    const parte = extraerEventos('event: delta\ndata: {"tex');
    expect(parte.eventos).toEqual([]);
    const fin = extraerEventos(`${parte.resto}to":"ok"}\n\n`);
    expect(fin.eventos[0].data).toEqual({ texto: "ok" });
  });

  it("acepta finales de línea CRLF", () => {
    const { eventos } = extraerEventos('event: fin\r\ndata: {"confianza":0.9}\r\n\r\n');
    expect(eventos[0].evento).toBe("fin");
  });
});

describe("leerStream", () => {
  const bytes = (t: string) => new TextEncoder().encode(t);

  it("une una tilde partida entre dos fragmentos", async () => {
    const todo = bytes('event: delta\ndata: {"texto":"Medellín"}\n\n');
    const corte = todo.indexOf(0xc3) + 1;
    const cuerpo = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(todo.slice(0, corte));
        c.enqueue(todo.slice(corte));
        c.close();
      },
    });
    const recibidos: unknown[] = [];
    await leerStream(cuerpo, (e) => recibidos.push(e.data));
    expect(recibidos).toEqual([{ texto: "Medellín" }]);
  });

  it("falla si el stream se queda en silencio", async () => {
    const mudo = new ReadableStream<Uint8Array>({ start() {} });
    await expect(leerStream(mudo, () => undefined, 20)).rejects.toBeInstanceOf(ErrorSilencio);
  });
});
