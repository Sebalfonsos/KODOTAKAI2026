// Sintetizador del show: todo se genera con Web Audio, sin un solo archivo. Un compresor al final evita saturar.

/** Perilla general. 1 es el máximo pensado; se puede bajar sin tocar nada más. */
export const VOLUMEN = 0.8;

export type ModoVoz = "normal" | "grito" | "grave";

export interface Sonido {
  ding(n: number): void;
  grieta(): void;
  golpe(): void;
  alarma(): () => void;
  cinta(): void;
  bocina(duracion: number): void;
  choque(): void;
  reversa(duracion: number): void;
  acorde(): void;
  hablar(texto: string, modo: ModoVoz): void;
  silenciar(si: boolean): void;
  cerrar(): void;
}

const VOCALES = [730, 1090, 1400, 1850, 2300];

function curvaSaturacion(k: number) {
  const curva = new Float32Array(1024);
  for (let i = 0; i < curva.length; i++) {
    const x = (i * 2) / curva.length - 1;
    curva[i] = ((1 + k) * x) / (1 + k * Math.abs(x));
  }
  return curva;
}

export function crearSonido(ctx: BaseAudioContext, volumen = VOLUMEN): Sonido {
  const maestro = ctx.createGain();
  maestro.gain.value = volumen;
  const compresor = ctx.createDynamicsCompressor();
  compresor.threshold.value = -12;
  compresor.ratio.value = 14;
  compresor.attack.value = 0.002;
  compresor.release.value = 0.2;
  const salidaFinal = ctx.createGain();
  salidaFinal.gain.value = 0.85;
  maestro.connect(compresor).connect(salidaFinal).connect(ctx.destination);

  const saturador = ctx.createWaveShaper();
  saturador.curve = curvaSaturacion(18);
  saturador.connect(maestro);

  const ruido = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
  const datos = ruido.getChannelData(0);
  for (let i = 0; i < datos.length; i++) datos[i] = Math.random() * 2 - 1;

  const paneo = (destino: AudioNode, valor: number) => {
    const p = ctx.createStereoPanner();
    p.pan.value = valor;
    p.connect(destino);
    return p;
  };

  /** Oscilador con envolvente percusiva. Devuelve el oscilador por si hay que barrer su frecuencia. */
  function tono(tipo: OscillatorType, hz: number, t: number, dur: number, pico: number, destino: AudioNode = maestro) {
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = tipo;
    o.frequency.setValueAtTime(hz, t);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(pico, t + 0.004);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(destino);
    o.start(t);
    o.stop(t + dur + 0.02);
    return o;
  }

  function soplo(t: number, dur: number, pico: number, tipoFiltro: BiquadFilterType, hz: number, destino: AudioNode = maestro) {
    const s = ctx.createBufferSource();
    s.buffer = ruido;
    s.loop = true;
    const f = ctx.createBiquadFilter();
    f.type = tipoFiltro;
    f.frequency.setValueAtTime(hz, t);
    const g = ctx.createGain();
    g.gain.setValueAtTime(pico, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    s.connect(f).connect(g).connect(destino);
    s.start(t, Math.random());
    s.stop(t + dur + 0.02);
    return f;
  }

  const ping = (t: number, pico: number) => {
    tono("sine", 1800 + Math.random() * 7200, t, 0.04 + Math.random() * 0.2, pico, paneo(maestro, Math.random() * 1.8 - 0.9));
  };

  return {
    /** Notificación: cada una sube de tono y salta de un oído a otro. */
    ding(n) {
      const t = ctx.currentTime;
      const hz = 500 * 2 ** (Math.min(n, 30) / 16);
      const lado = paneo(maestro, Math.random() * 1.6 - 0.8);
      tono("sine", hz, t, 0.18, 0.5, lado);
      tono("triangle", hz * 1.5, t + 0.05, 0.14, 0.24, lado);
    },
    grieta() {
      const t = ctx.currentTime;
      for (let i = 0; i < 7; i++) soplo(t + Math.random() * 0.14, 0.03, 0.5, "highpass", 3500);
    },
    /** Puñetazo contra la pantalla. */
    golpe() {
      const t = ctx.currentTime;
      const o = tono("sine", 150, t, 0.42, 0.95, saturador);
      o.frequency.exponentialRampToValueAtTime(36, t + 0.3);
      soplo(t, 0.16, 0.6, "lowpass", 2400);
    },
    /** Sirena de dos tonos. Devuelve cómo apagarla: se apaga de un corte, para que duela el silencio. */
    alarma() {
      const t = ctx.currentTime;
      const g = ctx.createGain();
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.32, t + 2);
      const f = ctx.createBiquadFilter();
      f.type = "lowpass";
      f.frequency.value = 2200;
      const o = ctx.createOscillator();
      o.type = "sawtooth";
      for (let i = 0; i < 40; i++) o.frequency.setValueAtTime(i % 2 ? 930 : 620, t + i * 0.3);
      o.connect(f).connect(g).connect(maestro);
      o.start(t);
      o.stop(t + 12);
      return () => {
        const ahora = ctx.currentTime;
        g.gain.cancelScheduledValues(ahora);
        g.gain.setValueAtTime(0.0001, ahora);
      };
    },
    /** Se va la luz: todo se hunde como una cinta que se frena. */
    cinta() {
      const t = ctx.currentTime;
      const o = tono("sawtooth", 520, t, 0.55, 0.3, saturador);
      o.frequency.exponentialRampToValueAtTime(22, t + 0.52);
    },
    /** Bocina de camión que se viene encima: tres notas desafinadas que suben y se abren. */
    bocina(duracion) {
      const t = ctx.currentTime;
      const fin = t + duracion;
      const g = ctx.createGain();
      g.gain.setValueAtTime(0.008, t);
      g.gain.exponentialRampToValueAtTime(0.55, fin);
      g.gain.setValueAtTime(0.0001, fin + 0.02);
      const f = ctx.createBiquadFilter();
      f.type = "lowpass";
      f.frequency.setValueAtTime(260, t);
      f.frequency.exponentialRampToValueAtTime(4800, fin);
      f.connect(g).connect(saturador);
      for (const hz of [147, 185, 220, 222.5]) {
        const o = ctx.createOscillator();
        o.type = "sawtooth";
        o.frequency.setValueAtTime(hz, t);
        o.frequency.exponentialRampToValueAtTime(hz * 1.2, fin);
        o.connect(f);
        o.start(t);
        o.stop(fin + 0.03);
      }
    },
    /** El choque: subgrave, latigazo de ruido, lámina de metal y una lluvia de vidrio de casi tres segundos. */
    choque() {
      const t = ctx.currentTime;
      const sub = tono("sine", 95, t, 1.9, 1, saturador);
      sub.frequency.exponentialRampToValueAtTime(24, t + 1.5);
      const barrido = soplo(t, 1.5, 1, "lowpass", 11000);
      barrido.frequency.exponentialRampToValueAtTime(180, t + 1.2);
      soplo(t, 0.9, 0.7, "highpass", 4800);
      for (const [i, hz] of [211, 347, 521, 797, 1163, 1709, 2593].entries()) {
        tono("square", hz, t + i * 0.006, 1.1 - i * 0.08, 0.1, paneo(maestro, i % 2 ? 0.6 : -0.6));
      }
      for (const eco of [0.28, 0.55, 0.9]) {
        const o = tono("sine", 90, t + eco, 0.3, 0.55 - eco * 0.4, saturador);
        o.frequency.exponentialRampToValueAtTime(30, t + eco + 0.25);
        soplo(t + eco, 0.22, 0.3, "bandpass", 1600);
      }
      // Muchos pings al principio y cada vez menos, como vidrio que termina de caer.
      for (let i = 0; i < 110; i++) ping(t + 0.02 + 2.9 * Math.random() ** 2.4, 0.05 + Math.random() * 0.16);
    },
    /** El vidrio al revés: los pings se aceleran hacia el final y todo sube hasta el clic de la última pieza. */
    reversa(duracion) {
      const t = ctx.currentTime;
      const fin = t + duracion;
      const g = ctx.createGain();
      g.gain.setValueAtTime(0.002, t);
      g.gain.exponentialRampToValueAtTime(0.5, fin);
      g.gain.setValueAtTime(0.0001, fin + 0.01);
      const f = ctx.createBiquadFilter();
      f.type = "bandpass";
      f.Q.value = 1.2;
      f.frequency.setValueAtTime(300, t);
      f.frequency.exponentialRampToValueAtTime(7000, fin);
      const s = ctx.createBufferSource();
      s.buffer = ruido;
      s.loop = true;
      s.connect(f).connect(g).connect(maestro);
      s.start(t);
      s.stop(fin + 0.02);
      const sube = tono("triangle", 70, t, duracion + 0.02, 0.28);
      sube.frequency.exponentialRampToValueAtTime(1400, fin);
      for (let i = 0; i < 70; i++) ping(fin - duracion * Math.random() ** 2.4, 0.04 + Math.random() * 0.12);
    },
    /** Todo volvió a su sitio: acorde mayor con pecho y destellos. */
    acorde() {
      const t = ctx.currentTime;
      tono("sine", 65.4, t, 1.6, 0.7, saturador);
      [261.6, 329.6, 392, 523.2, 659.3, 784].forEach((hz, i) => {
        tono("triangle", hz, t + i * 0.07, 1.5, 0.2, paneo(maestro, (i - 2.5) / 3));
        tono("sawtooth", hz / 2, t + i * 0.07, 1.1, 0.04);
      });
      for (let i = 0; i < 18; i++) ping(t + 0.3 + Math.random() * 1.2, 0.05);
    },
    /** Voz inventada de robot: una sílaba por cada grupo de letras, con vocales que cambian al azar. */
    hablar(texto, modo) {
      const t = ctx.currentTime;
      const silabas = Math.min(Math.ceil(texto.replace(/[^\p{L}]/gu, "").length / 2.4), 26) || 1;
      const base = { normal: 215, grito: 340, grave: 58 }[modo];
      const paso = { normal: 0.082, grito: 0.075, grave: 0.17 }[modo];
      const pico = { normal: 1, grito: 1.4, grave: 1 }[modo];
      const destino = modo === "normal" ? maestro : saturador;
      for (let i = 0; i < silabas; i++) {
        const inicio = t + i * paso;
        const f = ctx.createBiquadFilter();
        f.type = "bandpass";
        f.Q.value = 5;
        f.frequency.value = VOCALES[Math.floor(Math.random() * VOCALES.length)] * (modo === "grave" ? 0.5 : 1);
        f.connect(destino);
        const contorno = 1 + Math.sin((i / silabas) * Math.PI) * 0.25 + (Math.random() - 0.5) * 0.28;
        const o = tono("square", base * contorno, inicio, paso * 1.15, pico, f);
        if (modo !== "normal") o.frequency.exponentialRampToValueAtTime(base * contorno * (modo === "grito" ? 1.5 : 0.75), inicio + paso);
      }
    },
    silenciar(si) {
      maestro.gain.setTargetAtTime(si ? 0 : volumen, ctx.currentTime, 0.015);
    },
    cerrar() {
      if (ctx instanceof AudioContext && ctx.state !== "closed") void ctx.close();
    },
  };
}
