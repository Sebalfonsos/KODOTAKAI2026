import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { Ruti, RutiStatus } from "../components/ruti/Ruti";
import { Icono, type NombreIcono } from "../components/ui/Icono";
import type { VistaShow } from "../features/portada/show";
import { SERVICIOS } from "./CentroServicios";

type ModuloShow = typeof import("../features/portada/show");

const cargarShow = () => import("../features/portada/show");

const REPOSO: VistaShow = {
  fase: "reposo",
  estado: "reposo",
  escalamiento: null,
  linea: "¡Hola! Soy RUTI, tu copiloto logístico.",
  final: false,
  hablando: false,
  panel: false,
  celebrando: false,
  casos: [],
  filas: [],
};

const TECLA: Record<VistaShow["fase"], { texto: string; icono: NombreIcono }> = {
  reposo: { texto: "Ponme a prueba", icono: "chispa" },
  activo: { texto: "Saltar", icono: "flecha" },
  calma: { texto: "Ver otra vez", icono: "chispa" },
  resumen: { texto: "Cerrar resumen", icono: "x" },
};

const TONOS = ["#18c7c2", "#ffbd59", "#8fb8ff", "#c4b5fd", "#7ee2b8", "#f9a8a8", "#fde68a", "#8ff3ee"];

const CHISPAS = Array.from({ length: 12 }, (_, i) => {
  const angulo = (i / 12) * Math.PI * 2;
  const alcance = i % 2 ? 1 : 0.72;
  return {
    icono: (["caja", "camion", "check"] as const)[i % 3],
    estilo: { "--c": Math.cos(angulo) * alcance, "--s": Math.sin(angulo) * alcance, "--giro": `${i % 2 ? 14 : -14}deg` } as CSSProperties,
  };
});

const CLAVE_SONIDO = "translogix.portada.sonido";

function leerSonido() {
  try {
    return localStorage.getItem(CLAVE_SONIDO) === "1";
  } catch {
    return false;
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
  const [vista, setVista] = useState(REPOSO);
  const [sonido, setSonido] = useState(leerSonido);
  const [vozSonando, setVozSonando] = useState(false);
  const sonidoActual = useRef(sonido);
  const modulo = useRef<ModuloShow | null>(null);
  const control = useRef<AbortController | null>(null);
  const corrida = useRef<{ callar(): void } | null>(null);
  const hero = useRef<HTMLDivElement>(null);
  const show = useRef<HTMLElement>(null);
  const vibra = useRef<HTMLDivElement>(null);

  const pendientes = vista.casos.filter((c) => !c.resuelto).length;
  const llegados = vista.casos.length;

  function saltar() {
    control.current?.abort();
    if (modulo.current) setVista(modulo.current.vistaEn(Infinity));
  }

  async function pulsarTecla() {
    if (vista.fase === "activo") return saltar();
    if (vista.fase === "resumen") return setVista(REPOSO);
    try {
      const m = (modulo.current ??= await cargarShow());
      if (movimientoReducido()) return setVista(m.VISTA_RESUMEN);
      control.current?.abort();
      const c = new AbortController();
      control.current = c;
      setVista(m.vistaEn(0));
      corrida.current = m.correrShow({
        al: setVista,
        signal: c.signal,
        sonido: () => sonidoActual.current,
        alHablar: setVozSonando,
      });
      show.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    } catch {
      setVista({ ...REPOSO, linea: "No pude iniciar la demostración. Inténtalo de nuevo." });
    }
  }

  function alternarSonido() {
    const activo = !sonido;
    setSonido(activo);
    sonidoActual.current = activo;
    guardarSonido(activo);
    if (!activo) corrida.current?.callar();
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

  // ponytail: al ocultar la pestaña el show salta al final en vez de pausar su reloj; basta para una demo de 17 s.
  useEffect(() => {
    if (vista.fase !== "activo") return;
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
    };
  }, [vista.fase]);

  // La sacudida crece con cada mensaje: la tensión se ve en RUTI, no solo alrededor.
  useEffect(() => {
    if (vista.fase !== "activo" || llegados === 0) return;
    const a = 1 + llegados * 0.7;
    vibra.current?.animate(
      [
        { transform: "none" },
        { transform: `translateX(${-a}px) rotate(${-a / 3}deg)` },
        { transform: `translateX(${a}px) rotate(${a / 3}deg)` },
        { transform: "none" },
      ],
      { duration: 240, easing: "ease-out" },
    );
  }, [llegados, vista.fase]);

  useEffect(() => {
    if (!vista.celebrando) return;
    vibra.current?.animate(
      [{ transform: "none" }, { transform: "translateY(-18px) scale(1.04)" }, { transform: "none" }],
      { duration: 420, easing: "cubic-bezier(.22, 1.35, .36, 1)" },
    );
  }, [vista.celebrando]);

  const tecla = TECLA[vista.fase];
  const demostracion = vista.fase === "activo" || vista.fase === "resumen";

  return (
    <div className="portada" data-tema="oscuro">
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
            <div
              className="escena"
              data-fase={vista.fase}
              data-panel={vista.panel || undefined}
              data-celebra={vista.celebrando || undefined}
              style={{ "--tension": pendientes / 8 } as CSSProperties}
            >
              <div className="escena__cabeza">
                <div className="escena__vibra" ref={vibra}>
                  <Ruti
                    vista={{ estado: vista.estado, fase: vista.escalamiento }}
                    encuadre="cabeza"
                    hablando={vista.hablando || vozSonando}
                    className="ruti--saludo"
                  />
                </div>
              </div>

              {/* ponytail: la "física" son 8 posiciones fijas con rotación y resorte; sin colisiones reales. */}
              <ul className="escena__casos" aria-hidden="true">
                {vista.casos.map((c) => (
                  <li
                    key={c.id}
                    className="caso"
                    data-slot={c.id}
                    data-resuelto={c.resuelto || undefined}
                    data-viejo={c.id < llegados - 4 || undefined}
                    style={{ "--fila": c.fila, "--tono": TONOS[c.id] } as CSSProperties}
                  >
                    <span className="caso__quien">
                      <span className="caso__avatar">{c.iniciales}</span>
                      {c.quien}
                    </span>
                    {c.texto}
                  </li>
                ))}
              </ul>

              {vista.celebrando && (
                <div className="escena__chispas" aria-hidden="true">
                  {CHISPAS.map((c, i) => (
                    <span key={i} className="chispa" style={c.estilo}>
                      <Icono nombre={c.icono} tamano={22} />
                    </span>
                  ))}
                </div>
              )}

              <div className="panel-ruti" data-visible={vista.panel || undefined}>
                <p className="panel-ruti__titulo">
                  <Icono nombre="ruta" tamano={18} />
                  Panel de RUTI
                </p>
                <ol>
                  {vista.filas.map((f) => (
                    <li key={f.clave} data-lista={f.lista || undefined}>
                      <span className="panel-ruti__clave">{f.clave}</span>
                      <span className="panel-ruti__valor">
                        {f.valor.split(" ").map((palabra, i) => (
                          <span key={i} style={{ "--n": i } as CSSProperties}>
                            {palabra}{" "}
                          </span>
                        ))}
                      </span>
                      <Icono nombre="check" tamano={16} className="panel-ruti__check" />
                    </li>
                  ))}
                </ol>
              </div>
            </div>

            <div className="portada__subtitulo" data-final={vista.final || undefined}>
              <RutiStatus mensaje={vista.linea} />
            </div>

            <div className="portada__mando">
              <button type="button" className="tecla" data-fase={vista.fase} onClick={() => void pulsarTecla()}>
                <Icono nombre={tecla.icono} />
                {tecla.texto}
              </button>
              <p className="portada__etiqueta">
                {demostracion && "Demostración con datos de ejemplo"}
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
    </div>
  );
}
