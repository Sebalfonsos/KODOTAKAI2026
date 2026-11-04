import { useState, type FormEvent } from "react";
import { useDatos } from "../../hooks/useDatos";
import { buscarRag, desactivarDocumento, subirDocumento, verDocumentos, type ResultadoRag } from "../../services/admin";
import { mensajeError } from "../../services/http";
import { Estado, NUM, Seccion, fecha } from "./comun";

const TIPOS = ["mercancia_peligrosa", "embalaje", "prohibido", "pqrs", "cobertura", "trayecto", "politica", "legal"];

export function Conocimiento() {
  const { datos, error, cargando, recargar } = useDatos(verDocumentos, []);
  const [fallo, setFallo] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [consulta, setConsulta] = useState("");
  const [resultados, setResultados] = useState<ResultadoRag[] | null>(null);
  const [buscando, setBuscando] = useState(false);

  const alSubir = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    setSubiendo(true);
    setFallo(null);
    setAviso(null);
    try {
      const r = await subirDocumento(new FormData(form));
      setAviso(r.omitido ? `${r.codigo}: el contenido no cambió, no se volvió a indexar.` : `${r.codigo}: ${r.chunks} fragmentos indexados.`);
      form.reset();
      await recargar();
    } catch (err) {
      setFallo(mensajeError(err));
    } finally {
      setSubiendo(false);
    }
  };
  const desactivar = async (id: number) => {
    setFallo(null);
    try {
      await desactivarDocumento(id);
      await recargar();
    } catch (err) {
      setFallo(mensajeError(err));
    }
  };
  const alBuscar = async (e: FormEvent) => {
    e.preventDefault();
    setBuscando(true);
    setFallo(null);
    try {
      setResultados(await buscarRag(consulta));
    } catch (err) {
      setResultados(null);
      setFallo(mensajeError(err));
    } finally {
      setBuscando(false);
    }
  };

  return (
    <div className="panel__cuerpo">
      {fallo && (
        <p className="alerta alerta--critica" role="alert">
          {fallo}
        </p>
      )}
      {aviso && (
        <p className="alerta alerta--info" role="status">
          {aviso}
        </p>
      )}
      <Seccion titulo="Documentos" descripcion="Lo que RUTI puede citar al responder.">
        <Estado error={error} cargando={cargando} hayDatos={!!datos} alReintentar={recargar} />
        {datos && !datos.length && <p className="nota">Aún no hay documentos indexados. Ejecuta la semilla con el corpus o sube uno.</p>}
        {datos && datos.length > 0 && (
          <div className="tabla-caja">
            <table className="tabla">
              <thead>
                <tr>
                  <th scope="col">Código</th>
                  <th scope="col">Título</th>
                  <th scope="col">Tipo</th>
                  <th scope="col">Fragmentos</th>
                  <th scope="col">Creado</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Acción</th>
                </tr>
              </thead>
              <tbody>
                {datos.map((d) => (
                  <tr key={d.id}>
                    <td className="dato-mono">{d.codigo}</td>
                    <td>{d.titulo}</td>
                    <td>{d.tipo}</td>
                    <td>{NUM.format(d.chunks)}</td>
                    <td>{fecha(d.creado_en)}</td>
                    <td>
                      <span className={`etiqueta ${d.activo ? "etiqueta--exito" : ""}`}>{d.activo ? "Activo" : "Inactivo"}</span>
                    </td>
                    <td>
                      {d.activo && (
                        <button type="button" className="boton boton--secundario boton--chico" onClick={() => void desactivar(d.id)}>
                          Desactivar
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Seccion>
      <div className="panel__rejilla">
        <Seccion titulo="Subir o actualizar" descripcion="Markdown o texto plano, hasta 2 MB. Un código existente se reemplaza.">
          <form className="formulario-simple" onSubmit={(e) => void alSubir(e)}>
            <label className="filtro">
              <span>Código</span>
              <input name="codigo" pattern="[A-Z0-9][A-Z0-9\-]{2,39}" placeholder="DOC-OPS-2026-05" required />
            </label>
            <label className="filtro">
              <span>Título</span>
              <input name="titulo" minLength={3} maxLength={200} required />
            </label>
            <label className="filtro">
              <span>Tipo</span>
              <select name="tipo">
                {TIPOS.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </label>
            <label className="filtro">
              <span>Archivo</span>
              <input name="archivo" type="file" accept=".md,.txt" required />
            </label>
            <button className="boton boton--primario" disabled={subiendo}>
              {subiendo ? "Indexando…" : "Subir"}
            </button>
          </form>
        </Seccion>
        <Seccion titulo="Probar la búsqueda" descripcion="Muestra los fragmentos tal como los ve el asistente.">
          <form className="filtros" onSubmit={(e) => void alBuscar(e)}>
            <label className="filtro filtro--ancho">
              <span>Consulta</span>
              <input value={consulta} onChange={(e) => setConsulta(e.target.value)} minLength={2} maxLength={500} placeholder="¿Llegan a Quibdó?" required />
            </label>
            <button className="boton boton--secundario" disabled={buscando}>
              {buscando ? "Buscando…" : "Buscar"}
            </button>
          </form>
          {resultados && !resultados.length && <p className="nota">Sin resultados.</p>}
          {resultados && (
            <ul className="lista-simple">
              {resultados.map((r) => (
                <li key={r.chunk_id}>
                  <strong>
                    {r.doc_codigo} · {r.seccion}
                  </strong>
                  <span>{r.contenido.slice(0, 280)}</span>
                  <span className="nota">Coseno {NUM.format(r.score_vector)}</span>
                </li>
              ))}
            </ul>
          )}
        </Seccion>
      </div>
    </div>
  );
}
