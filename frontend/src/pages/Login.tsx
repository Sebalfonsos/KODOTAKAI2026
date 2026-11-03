import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { ErrorApi } from "../services/http";

export function Login() {
  const { login } = useAuth();
  const navegar = useNavigate();
  const lugar = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const alEnviar = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const datos = new FormData(e.currentTarget);
    setEnviando(true);
    setError(null);
    try {
      const u = await login(String(datos.get("email")), String(datos.get("password")));
      const destino = (lugar.state as { desde?: string } | null)?.desde;
      navegar(destino ?? (u.rol === "admin" ? "/admin" : u.rol === "asesor" ? "/asesor" : "/servicios"), {
        replace: true,
      });
    } catch (err) {
      setError(err instanceof ErrorApi ? (err.problema.detail ?? err.problema.title) : "No pudimos conectarnos.");
    } finally {
      setEnviando(false);
    }
  };

  return (
    <form className="login" onSubmit={alEnviar}>
      <h1>Iniciar sesión</h1>
      <p>Necesitas una cuenta para radicar reclamos y ver el detalle de tus envíos.</p>
      <label htmlFor="email">Correo</label>
      <input id="email" name="email" type="email" autoComplete="username" required />
      <label htmlFor="password">Contraseña</label>
      <input id="password" name="password" type="password" autoComplete="current-password" required />
      {error && (
        <p className="campo__error" role="alert">
          {error}
        </p>
      )}
      <button className="boton boton--primario" disabled={enviando}>
        Entrar
      </button>
    </form>
  );
}
