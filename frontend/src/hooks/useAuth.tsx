import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { login as apiLogin, logout as apiLogout, restaurarSesion, type Usuario } from "../services/auth";

interface Auth {
  usuario: Usuario | null;
  cargando: boolean;
  login: (email: string, password: string) => Promise<Usuario>;
  logout: () => Promise<void>;
}

const Contexto = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    restaurarSesion()
      .then(setUsuario)
      .catch(() => setUsuario(null))
      .finally(() => setCargando(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const u = await apiLogin(email, password);
    setUsuario(u);
    return u;
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setUsuario(null);
  }, []);

  const valor = useMemo(() => ({ usuario, cargando, login, logout }), [usuario, cargando, login, logout]);
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useAuth(): Auth {
  const c = useContext(Contexto);
  if (!c) throw new Error("useAuth requiere AuthProvider");
  return c;
}
