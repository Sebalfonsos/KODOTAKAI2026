import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { Ruti, RutiStatus } from "../components/ruti/Ruti";
import { Icono, type NombreIcono } from "../components/ui/Icono";
import { Avalancha, EscenaCaos, PanelRuti } from "../features/portada/Caos";
import type { Escenario } from "../features/portada/vidrio";
import { VISTA_REPOSO, type VistaShow } from "../features/portada/vista";
import { SERVICIOS } from "./CentroServicios";

// El motor (sintetizador, vidrio y guion) se carga aparte para no pesar en la primera pintura.
const cargarShow = () => Promise.all([import("../features/portada/show"), import("../features/portada/vidrio")]);
type ModuloShow = Awaited<ReturnType<typeof cargarShow>>;

const TECLA: Record<VistaShow["fase"], { texto: string; icono: NombreIcono }> = {
  reposo: { texto: "Ponme a prueba", icono: "chispa" },
  activo: { texto: "Agárrate…", icono: "alerta" },
  calma: { texto: "Otra vez, otra vez", icono: "chispa" },
  resumen: { texto: "Cerrar resumen", icono: "x" },
};

const CHISPAS = Array.from({ length: 12 }, (_, i) => {
  const angulo = (i / 12) * Math.PI * 2;
  const alcance = i % 2 ? 1 : 0.72;
  return {
    icono: (["caja", "camion", "check"] as const)[i % 3],
    estilo: { "--c": Math.cos(angulo) * alcance, "--s": Math.sin(angulo) * alcance, "--giro": `${i % 2 ? 14 : -14}deg` } as CSSProperties,
  };
});

const CLAVE_SONIDO = "translogix.portada.sonido";

/** El show suena desde que alguien lo pide con la tecla, que avisa antes. Si lo silencian, se recuerda. */
function leerSonido() {
  try {
    return localStorage.getItem(CLAVE_SONIDO) !== "0";
  } catch {
    return true;
  }
}

function guardarSonido(activo: boolean) {
  try {
    localStorage.setItem(CLAVE_SONIDO, activo ? "1" : "0");
  } catch {
    // Sin almacenamiento, la preferencia dura lo que dure la página.
  }
}

const movimientoReducido = () =>
  matchMedia("(prefers-reduced-motion: reduce)").matches || document.documentElement.dataset.movimiento === "reducido";

export function Landing() {
  const [vista, setVista] = useState(VISTA_REPOSO);
  const [sonido, setSonido] = useState(leerSonido);
  const [escenario, setEscenario] = useState<Escenario | null>(null);
  const sonidoActual = useRef(sonido);
  const modulo = useRef<ModuloShow | null>(null);
  const control = useRef<AbortController | null>(null);
  const corrida = useRef<{ silenciar(s: boolean): void } | null>(null);
  const raiz = useRef<HTMLDivElement>(null);
  const hero = useRef<HTMLDivElement>(null);
  const show = useRef<HTMLElement>(null);
  const cabeza = useRef<HTMLDivElement>(null);
  const vibra = useRef<HTMLDivElement>(null);
  const tecla = useRef<HTMLButtonElement>(null);
  const salida = useRef<HTMLButtonElement>(null);

  function saltar() {
    control.current?.abort();
    if (modulo.current) setVista(modulo.current[0].vistaEn(Infinity));
  }

  async function pulsarTecla() {
    if (vista.fase === "activo") return saltar();
    if (vista.fase === "resumen") return setVista(VISTA_REPOSO);
    try {
      const m = (modulo.current ??= await cargarShow());
      const [motor, vidrio] = m;
      if (movimientoReducido()) return setVista(motor.VISTA_RESUMEN);
      control.current?.abort();
      const c = new AbortController();
      control.current = c;

      // Lleva a RUTI al centro de la pantalla si hace falta, y ubica las tarjetas donde va a quedar.
      const rectShow = show.current?.getBoundingClientRect();
      const fuera = rectShow && (rectShow.top < 0 || rectShow.bottom > innerHeight);
      const desplazo = fuera ? rectShow.top + rectShow.height / 2 - innerHeight / 2 : 0;
      if (desplazo) scrollBy({ top: desplazo, behavior: "smooth" });
      const r = cabeza.current?.getBoundingClientRect();
      const rect = { left: r?.left ?? innerWidth / 2, top: (r?.top ?? innerHeight / 2) - desplazo, width: r?.width ?? 0, height: r?.height ?? 0 };
      setEscenario(vidrio.distribuir(innerWidth, innerHeight, rect, motor.TOTAL_CASOS));

      setVista(motor.vistaEn(0));
      corrida.current = motor.correrShow({
        al: setVista,
        signal: c.signal,
        raiz: () => raiz.current,
        impacto: { x: innerWidth / 2, y: innerHeight * 0.52 },
        sonido: () => sonidoActual.current,
      });
    } catch {
      setVista({ ...VISTA_REPOSO, linea: "No pude iniciar la demostración. Inténtalo de nuevo." });
    }
  }

  function alternarSonido() {
    const activo = !sonido;
    setSonido(activo);
    sonidoActual.current = activo;
    guardarSonido(activo);
    corrida.current?.silenciar(!activo);
  }

  // Precarga cuando el navegador esté libre. Safari no tiene requestIdleCallback.
  useEffect(() => {
    const precargar = () => void cargarShow().then((m) => (modulo.current = m)).catch(() => undefined);
    if ("requestIdleCallback" in window) {
      const id = requestIdleCallback(precargar);
      return () => cancelIdleCallback(id);
    }
    const id = setTimeout(precargar, 1500);
    return () => clearTimeout(id);
  }, []);

  useEffect(() => () => control.current?.abort(), []);

  // Pausa el movimiento si la pestaña se oculta o el hero sale de pantalla (ESTRUCTURA_FRONT.md §5.7).
  useEffect(() => {
    const nodo = hero.current;
    if (!nodo) return;
    let visible = true;
    const aplicar = () => nodo.toggleAttribute("data-pausado", document.hidden || !visible);
    const observador = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
      aplicar();
    });
    observador.observe(nodo);
    document.addEventListener("visibilitychange", aplicar);
    return () => {
      observador.disconnect();
      document.removeEventListener("visibilitychange", aplicar);
    };
  }, []);

  // La salida siempre está a mano. ponytail: al ocultar la pestaña el show salta al final en vez de pausar su reloj.
  useEffect(() => {
    if (vista.fase !== "activo") return;
    salida.current?.focus({ preventScroll: true });
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key === "Escape") saltar();
    };
    const alOcultar = () => {
      if (document.hidden) saltar();
    };
    document.addEventListener("keydown", alTeclear);
    document.addEventListener("visibilitychange", alOcultar);
    return () => {
      document.removeEventListener("keydown", alTeclear);
      document.removeEventListener("visibilitychange", alOcultar);
      tecla.current?.focus({ preventScroll: true });
    };
  }, [vista.fase]);

  // Sacudida por cada mensaje: crece con la cantidad. La tensión se ve en RUTI, no solo alrededor.
  const llegados = vista.casos.length;
  useEffect(() => {
    if (vista.fase !== "activo" || llegados === 0) return;
    const a = 1 + Math.min(llegados, 20) * 0.4;
    vibra.current?.animate(
      [
        { transform: "none" },
        { transform: `translateX(${-a}px) rotate(${-a / 2}deg)` },
        { transform: `translateX(${a}px) rotate(${a / 2}deg)` },
        { transform: "none" },
      ],
      { duration: 200, easing: "ease-out" },
    );
  }, [llegados, vista.fase]);

  // El cabezazo contra el vidrio de cada "¡UNO! ¡POR! ¡UNO!".
  useEffect(() => {
    if (vista.golpes === 0) return;
    vibra.current?.animate(
      [{ transform: "none" }, { transform: "scale(1.55) translateY(4%)", offset: 0.25 }, { transform: "none" }],
      { duration: 340, easing: "cubic-bezier(.2, 1.3, .4, 1)" },
    );
  }, [vista.golpes]);

  useEffect(() => {
    if (!vista.celebrando) return;
    vibra.current?.animate(
      [{ transform: "none" }, { transform: "translateY(-18px) scale(1.06)" }, { transform: "none" }],
      { duration: 420, easing: "cubic-bezier(.22, 1.35, .36, 1)" },
    );
  }, [vista.celebrando]);

  const datosTecla = vista.final && vista.fase === "activo" ? { texto: "Todo en su sitio", icono: "check" as const } : TECLA[vista.fase];

  return (
    <>
      <div
        ref={raiz}
        className="portada"
        data-tema="oscuro"
        data-temblor={vista.temblor || undefined}
        data-furia={vista.furia || undefined}
        data-congelado={vista.congelado || undefined}
        data-roto={vista.roto || undefined}
      >
        <div className="portada__hero" ref={hero}>
          {/* Línea de ruta ambiental: decorativa, detrás del contenido. La tercera se dibuja en la celebración. */}
          <svg className="portada__ruta" viewBox="0 0 1440 400" preserveAspectRatio="none" aria-hidden="true" focusable="false">
            <path d="M-20 330C240 250 420 380 700 300S1180 120 1460 180" />
            <path d="M-20 360C300 300 520 400 820 330S1220 200 1460 240" />
            {vista.celebrando && <path className="portada__ruta-viva" pathLength={1} d="M-20 330C240 250 420 380 700 300S1180 120 1460 180" />}
          </svg>
          <header className="portada__cabecera">
            <Link to="/" className="marca">
              <Icono nombre="caja" tamano={26} />
              TransLogix
            </Link>
            <nav aria-label="Principal" className="portada__nav">
              <Link to="/servicios">Servicios</Link>
              <Link to="/ayuda">Ayuda</Link>
              <button
                type="button"
                className="portada__sonido"
                aria-pressed={sonido}
                aria-label="Sonido de la demostración"
                title={sonido ? "Silenciar la demostración" : "Activar el sonido de la demostración"}
                onClick={alternarSonido}
              >
                <Icono nombre={sonido ? "altavoz" : "silencio"} />
              </button>
              <Link to="/login" className="boton boton--contorno boton--chico">
                <Icono nombre="asesor" tamano={18} />
                Iniciar sesión
              </Link>
            </nav>
          </header>
          <main className="portada__cuerpo">
            <div className="portada__texto">
              <p className="portada__antetitulo">TransLogix Colombia · Asistente logístico</p>
              <h1>
                Tu logística, más simple e <em>inteligente.</em>
              </h1>
              <p>Consulta tus envíos, cotiza y resuelve dudas con la ayuda de RUTI.</p>
              <div className="portada__acciones">
                <Link to="/ayuda" className="boton boton--acento boton--fisico boton--grande" data-pulso={vista.fase === "calma" || undefined}>
                  <Icono nombre="chat" />
                  Conversar con RUTI
                  <Icono nombre="flecha" />
                </Link>
                <Link to="/servicios" className="boton boton--contorno boton--grande">
                  Explorar servicios
                </Link>
              </div>
            </div>

            <section className="portada__show" aria-label="Demostración de RUTI" ref={show}>
              <div className="escena" data-fase={vista.fase}>
                <div className="escena__cabeza" ref={cabeza}>
                  <div className="escena__vibra" ref={vibra}>
                    <Ruti vista={{ estado: vista.estado, fase: vista.escalamiento }} encuadre="cabeza" hablando={vista.hablando} className="ruti--saludo" />
                  </div>
                </div>
                {vista.celebrando && (
                  <div className="escena__chispas" aria-hidden="true">
                    {CHISPAS.map((c, i) => (
                      <span key={i} className="chispa" style={c.estilo}>
                        <Icono nombre={c.icono} tamano={22} />
                      </span>
                    ))}
                  </div>
                )}
                {vista.fase === "resumen" && <PanelRuti filas={vista.filas} />}
              </div>

              <p className="portada__subtitulo" data-final={vista.final || undefined} aria-hidden="true">
                {vista.fase !== "activo" || vista.final ? vista.linea : ""}
              </p>

              <div className="portada__mando">
                <button ref={tecla} type="button" className="tecla" data-fase={vista.fase} disabled={vista.fase === "activo"} onClick={() => void pulsarTecla()}>
                  <Icono nombre={datosTecla.icono} />
                  {datosTecla.texto}
                </button>
                <p className="portada__etiqueta">
                  {vista.fase === "reposo" && "Con sonido fuerte, destellos y movimiento brusco."}
                  {vista.fase === "resumen" && "Demostración con datos de ejemplo"}
                  {vista.fase === "calma" && (
                    <span className="portada__insignia">
                      <Icono nombre="check" tamano={16} />
                      Lista para conversar
                    </span>
                  )}
                </p>
              </div>
            </section>
          </main>
        </div>

        <section className="portada__servicios" aria-labelledby="titulo-servicios">
          <h2 id="titulo-servicios">Empieza por lo que necesitas.</h2>
          <ul className="paradas">
            {SERVICIOS.map((s) => (
              <li key={s.a}>
                <Link to={s.a} className="parada">
                  <span className="parada__icono">
                    <Icono nombre={s.icono} tamano={24} />
                  </span>
                  <strong>{s.titulo}</strong>
                  <span>{s.texto}</span>
                  <span className="parada__cta">
                    {s.cta} <Icono nombre="flecha" tamano={16} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>

        <Avalancha vista={vista} escenario={escenario} />
      </div>

      <EscenaCaos vista={vista} hablando={vista.hablando} salida={salida} alSaltar={saltar} />

      {/* Fuera de lo que se rompe: el estado se sigue anunciando aunque la página esté hecha pedazos. */}
      <div className="sr-only">
        <RutiStatus mensaje={vista.linea} />
      </div>
    </>
  );
}
