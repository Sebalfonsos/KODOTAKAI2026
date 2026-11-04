// Vidrio roto sin librerías. Cada fragmento es un clon real de la página recortado con `clip-path`: el texto, los
// botones y las tarjetas de verdad salen volando, nítidos, y solo se anima `transform` y `opacity`.

export interface Punto {
  x: number;
  y: number;
}

export type Poligono = Punto[];

export const azar = (semilla: number) => () => {
  semilla = (semilla + 0x6d2b79f5) | 0;
  let t = Math.imul(semilla ^ (semilla >>> 15), 1 | semilla);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

export const centro = (p: Poligono): Punto => ({
  x: p.reduce((s, q) => s + q.x, 0) / p.length,
  y: p.reduce((s, q) => s + q.y, 0) / p.length,
});

/**
 * Fractura radial: rayos que salen del impacto y anillos cada vez más separados, como un vidrio de verdad. Los
 * fragmentos comparten vértices, así que cubren toda la pantalla sin huecos. Se descartan los que quedan fuera.
 */
export function fracturar(w: number, h: number, impacto: Punto, rayos: number, anillos: number, semilla = 7): Poligono[] {
  const rnd = azar(semilla);
  const paso = (Math.PI * 2) / rayos;
  const angulos = Array.from({ length: rayos }, (_, i) => i * paso + (rnd() - 0.5) * paso * 0.7);
  const alcance = Math.hypot(Math.max(impacto.x, w - impacto.x), Math.max(impacto.y, h - impacto.y));
  const radio = (j: number) => (j === anillos - 1 ? alcance * 3 : alcance * ((j + 1) / anillos) ** 1.7 * (0.85 + rnd() * 0.3));
  const malla = Array.from({ length: anillos }, (_, j) =>
    angulos.map((a) => {
      const r = radio(j);
      return { x: impacto.x + Math.cos(a) * r, y: impacto.y + Math.sin(a) * r };
    }),
  );
  const piezas: Poligono[] = [];
  for (let i = 0; i < rayos; i++) {
    const s = (i + 1) % rayos;
    piezas.push([impacto, malla[0][i], malla[0][s]]);
    for (let j = 1; j < anillos; j++) piezas.push([malla[j - 1][i], malla[j][i], malla[j][s], malla[j - 1][s]]);
  }
  return piezas.filter((p) => {
    const xs = p.map((q) => q.x);
    const ys = p.map((q) => q.y);
    return Math.max(...xs) > 0 && Math.min(...xs) < w && Math.max(...ys) > 0 && Math.min(...ys) < h;
  });
}

export interface Vuelo {
  frames: Keyframe[];
  duracion: number;
  demora: number;
}

/** Tiro parabólico muestreado: hacia afuera y hacia la cámara, con gravedad y giro en 3D. */
export function trayectoria(p: Poligono, impacto: Punto, rnd: () => number): Vuelo {
  const c = centro(p);
  const dx = c.x - impacto.x;
  const dy = c.y - impacto.y;
  const d = Math.hypot(dx, dy) || 1;
  const fuerza = 640 + 1900 * Math.exp(-d / 520) * (0.6 + rnd() * 0.6);
  const vx = (dx / d) * fuerza;
  const vy = (dy / d) * fuerza - 240 * rnd();
  const vz = 200 + 800 * Math.exp(-d / 420) * rnd();
  const eje = [rnd() - 0.5, rnd() - 0.5, (rnd() - 0.5) * 0.5];
  const giro = (rnd() < 0.5 ? -1 : 1) * (160 + rnd() * 620);
  const duracion = 1.5 + rnd() * 0.9;
  const pasos = 12;
  const frames: Keyframe[] = Array.from({ length: pasos + 1 }, (_, i) => {
    const t = (i / pasos) * duracion;
    const z = Math.min(vz * t, 1100);
    return {
      transform: `translate3d(${(vx * t).toFixed(1)}px, ${(vy * t + 1250 * t * t).toFixed(1)}px, ${z.toFixed(1)}px) rotate3d(${eje.join(",")}, ${(giro * t).toFixed(1)}deg)`,
      opacity: i >= pasos - 1 ? (pasos - i) * 0.5 : 1,
    };
  });
  return { frames, duracion: duracion * 1000, demora: d / 3.6 };
}

/** Grieta en estrella para los golpes previos: brazos quebrados y unas uniones entre ellos. */
export function grieta(c: Punto, radio: number, rnd: () => number): string {
  const brazos = 7;
  const nudos: Punto[][] = [];
  let d = "";
  for (let b = 0; b < brazos; b++) {
    let a = (b / brazos) * Math.PI * 2 + rnd() * 0.5;
    const largo = radio * (0.45 + rnd() * 0.75);
    const brazo: Punto[] = [c];
    for (let i = 1; i <= 4; i++) {
      a += (rnd() - 0.5) * 0.55;
      const r = (largo * i) / 4;
      brazo.push({ x: c.x + Math.cos(a) * r, y: c.y + Math.sin(a) * r });
    }
    nudos.push(brazo);
    d += `M${brazo.map((q) => `${q.x.toFixed(0)} ${q.y.toFixed(0)}`).join("L")}`;
  }
  for (let b = 0; b < brazos; b++) {
    const u = nudos[b][2];
    const v = nudos[(b + 1) % brazos][2];
    d += `M${u.x.toFixed(0)} ${u.y.toFixed(0)}L${v.x.toFixed(0)} ${v.y.toFixed(0)}`;
  }
  return d;
}

export interface Ubicacion {
  x: number;
  y: number;
  r: number;
  e: number;
}

export interface Escenario {
  w: number;
  h: number;
  ubicaciones: Ubicacion[];
  grietas: string[];
}

/**
 * Reparte las tarjetas por toda la pantalla, las primeras alrededor de RUTI y sin taparle la cara.
 * ponytail: posiciones sorteadas con rechazo y sin colisiones reales; basta para un caos de 2 segundos.
 */
export function distribuir(w: number, h: number, cabeza: DOMRectReadOnly | { left: number; top: number; width: number; height: number }, total: number, semilla = 11): Escenario {
  const rnd = azar(semilla);
  const ancho = Math.min(240, w * 0.46);
  const alto = 110;
  const c = { x: cabeza.left + cabeza.width / 2, y: cabeza.top + cabeza.height / 2 };
  const libreX = cabeza.width * 0.42 + ancho / 2;
  const libreY = cabeza.height * 0.42 + alto / 2;
  const encima = (x: number, y: number) => Math.abs(x + ancho / 2 - c.x) < libreX && Math.abs(y + alto / 2 - c.y) < libreY;
  const limitar = (v: number, max: number) => Math.min(Math.max(8, v), Math.max(8, max));
  const ubicaciones = Array.from({ length: total }, (_, i) => {
    let x = 0;
    let y = 0;
    for (let intento = 0; intento < 8; intento++) {
      // Si alrededor de RUTI no hay espacio (móvil), la tarjeta se va a otro lado antes que taparle la cara.
      if (i < 8 && intento < 3) {
        const a = (i / 8) * Math.PI * 2 + rnd() * 0.5;
        x = c.x + Math.cos(a) * (cabeza.width * 0.75 + ancho * 0.5) - ancho / 2;
        y = c.y + Math.sin(a) * (cabeza.height * 0.75 + alto * 0.6) - alto / 2;
      } else {
        x = rnd() * (w - ancho);
        y = rnd() * (h - alto);
      }
      x = limitar(x, w - ancho - 8);
      y = limitar(y, h - alto - 8);
      if (!encima(x, y)) break;
    }
    return { x, y, r: (rnd() - 0.5) * (i < 8 ? 8 : 26), e: i < 8 ? 1 : 1 + (i / total) * 0.32 };
  });
  const radio = Math.min(w, h) * 0.34;
  const puntos: Punto[] = [
    { x: c.x + cabeza.width * 0.1, y: c.y + cabeza.height * 0.45 },
    { x: w * 0.2, y: h * 0.3 },
    { x: w * 0.78, y: h * 0.74 },
    { x: w * 0.46, y: h * 0.16 },
    { x: w * 0.1, y: h * 0.82 },
    { x: w * 0.9, y: h * 0.22 },
  ];
  return { w, h, ubicaciones, grietas: puntos.map((p) => grieta(p, radio, rnd)) };
}

export interface Fractura {
  romper(): void;
  recomponer(): void;
  quitar(): void;
}

const SVG = "http://www.w3.org/2000/svg";

/** Clona la página y deja los fragmentos listos. Se llama antes del golpe para que romper sea instantáneo. */
export function prepararFractura(raiz: HTMLElement, impacto: Punto): Fractura {
  const w = innerWidth;
  const h = innerHeight;
  const movil = w < 768;
  const yInicial = scrollY;
  const rnd = azar(23);
  const poligonos = fracturar(w, h, impacto, movil ? 8 : 11, 3);

  const capa = document.createElement("div");
  capa.className = "fractura";
  capa.setAttribute("aria-hidden", "true");
  capa.inert = true;
  capa.style.visibility = "hidden";

  const piezas = poligonos.map((p) => {
    const pieza = document.createElement("div");
    pieza.className = "fractura__pieza";
    const puntos = p.map((q) => `${q.x.toFixed(1)}px ${q.y.toFixed(1)}px`).join(",");
    pieza.style.clipPath = `polygon(${puntos})`;
    const c = centro(p);
    pieza.style.transformOrigin = `${c.x.toFixed(0)}px ${c.y.toFixed(0)}px`;
    // Los de cerca del impacto vuelan hacia la cámara: tienen que pasar por encima de los que aún no se mueven.
    pieza.style.zIndex = String(10000 - Math.round(Math.hypot(c.x - impacto.x, c.y - impacto.y)));

    const clon = raiz.cloneNode(true) as HTMLElement;
    clon.querySelectorAll("[role=status]").forEach((n) => n.remove());
    clon.style.cssText += `position:absolute;left:0;top:${-yInicial}px;width:${raiz.offsetWidth}px;`;

    // Reflejo y filo: es lo que hace que un recorte se lea como vidrio.
    const brillo = document.createElement("div");
    brillo.className = "fractura__brillo";
    brillo.style.setProperty("--angulo", `${Math.round(rnd() * 360)}deg`);
    brillo.style.setProperty("--fuerza", (0.08 + rnd() * 0.16).toFixed(2));
    const filo = document.createElementNS(SVG, "svg");
    filo.classList.add("fractura__filo");
    const borde = document.createElementNS(SVG, "polygon");
    borde.setAttribute("points", p.map((q) => `${q.x.toFixed(1)},${q.y.toFixed(1)}`).join(" "));
    filo.append(borde);

    pieza.append(clon, brillo, filo);
    capa.append(pieza);
    return { pieza, clon, vuelo: trayectoria(p, impacto, rnd), animacion: null as Animation | null };
  });

  // Astillas: polvo de vidrio que sale disparado del punto de impacto.
  const astillas = Array.from({ length: movil ? 18 : 42 }, () => {
    const a = document.createElement("span");
    a.className = "fractura__astilla";
    a.style.left = `${impacto.x}px`;
    a.style.top = `${impacto.y}px`;
    const t = 4 + rnd() * 16;
    a.style.width = `${t}px`;
    a.style.height = `${t * (0.6 + rnd())}px`;
    capa.append(a);
    return a;
  });

  document.body.append(capa);

  return {
    romper() {
      capa.style.visibility = "visible";
      for (const p of piezas) {
        p.animacion = p.pieza.animate(p.vuelo.frames, { duration: p.vuelo.duracion, delay: p.vuelo.demora, fill: "both", easing: "linear" });
      }
      for (const a of astillas) {
        const angulo = rnd() * Math.PI * 2;
        const v = 300 + rnd() * 1100;
        const t = 0.9 + rnd() * 0.9;
        const x = Math.cos(angulo) * v * t;
        const y = Math.sin(angulo) * v * t + 900 * t * t;
        a.animate(
          [
            { transform: "translate(0, 0) rotate(0deg)", opacity: 1 },
            { transform: `translate(${x.toFixed(0)}px, ${y.toFixed(0)}px) rotate(${(rnd() * 1400).toFixed(0)}deg)`, opacity: 0 },
          ],
          { duration: t * 1000, easing: "cubic-bezier(.1,.6,.5,1)", fill: "both" },
        );
      }
    },
    recomponer() {
      astillas.forEach((a) => a.remove());
      // RUTI barre también el desorden: lo que regresa es la página limpia, sin tarjetas ni grietas.
      for (const { clon } of piezas) {
        clon.querySelectorAll(".avalancha, .grietas").forEach((n) => n.remove());
        for (const attr of ["data-furia", "data-temblor", "data-congelado", "data-apagon"]) clon.removeAttribute(attr);
        clon.querySelector("svg[data-state]")?.setAttribute("data-state", "reposo");
      }
      const lejos = Math.max(...piezas.map((p) => p.vuelo.demora), 1);
      for (const p of piezas) {
        p.animacion?.cancel();
        p.animacion = p.pieza.animate(p.vuelo.frames, {
          duration: 1000,
          delay: (1 - p.vuelo.demora / lejos) * 220,
          direction: "reverse",
          fill: "both",
          easing: "cubic-bezier(.65,0,.3,1)",
        });
      }
    },
    quitar() {
      capa.remove();
      scrollTo({ top: yInicial, behavior: "instant" });
    },
  };
}
