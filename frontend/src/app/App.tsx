import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { RutaRol } from "../components/layout/RutaRol";
import { PanelAdmin } from "../features/admin/PanelAdmin";
import { PanelAsesor } from "../features/asesor/PanelAsesor";
import { AuthProvider } from "../hooks/useAuth";
import { CentroServicios } from "../pages/CentroServicios";
import { Landing } from "../pages/Landing";
import { Login } from "../pages/Login";
import { Servicio } from "../pages/Servicio";

/** Mensajes iniciales: son los mismos de `respuestas_rapidas` del backend. */
export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route element={<AppShell />}>
            <Route path="/servicios" element={<CentroServicios />} />
            <Route path="/consultar" element={<Servicio inicio="Quiero rastrear" titulo="Consultar envío" />} />
            <Route path="/cotizar" element={<Servicio inicio="Quiero cotizar" titulo="Cotizar flete" />} />
            <Route path="/pqrs" element={<Servicio inicio="Quiero radicar un reclamo" titulo="Gestionar reclamación" />} />
            <Route path="/ayuda" element={<Servicio titulo="Conversar con RUTI" />} />
            <Route path="/login" element={<Login />} />
            <Route element={<RutaRol roles={["asesor", "admin"]} />}>
              <Route path="/asesor" element={<PanelAsesor />} />
            </Route>
            <Route element={<RutaRol roles={["admin"]} />}>
              <Route path="/admin" element={<PanelAdmin />} />
            </Route>
            <Route path="*" element={<p role="alert">No encontramos esa página.</p>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
