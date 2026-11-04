import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
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
            <Route path="/consultar" element={<Servicio inicio="Quiero rastrear" titulo="Consultar envío" icono="caja" descripcion="Escribe tu guía y te muestro en qué va tu envío." pasos={{ nombres: ["Datos", "Consultando", "Resultado"], resultado: "linea_tiempo_envio" }} />} />
            <Route path="/cotizar" element={<Servicio inicio="Quiero cotizar" titulo="Cotizar flete" icono="calculadora" descripcion="Completa los datos y te doy el valor con su desglose." pasos={{ nombres: ["Datos del envío", "Calculando", "Cotización"], resultado: "resultado_cotizacion" }} />} />
            <Route path="/pqrs" element={<Servicio inicio="Quiero radicar un reclamo" titulo="Gestionar reclamación" icono="alerta" descripcion="Te guío para radicar tu caso con los documentos correctos." pasos={{ nombres: ["Tu caso", "Validando", "Radicado"], resultado: "ticket_pqrs" }} requiereSesion />} />
            <Route path="/ayuda" element={<Servicio titulo="Conversar con RUTI" icono="chat" descripcion="Mercancías, embalaje, cobertura, tiempos y más." />} />
            <Route path="/login" element={<Login />} />
            <Route element={<RutaRol roles={["asesor", "admin"]} />}>
              <Route path="/asesor" element={<PanelAsesor />} />
            </Route>
            <Route element={<RutaRol roles={["admin"]} />}>
              <Route path="/admin" element={<PanelAdmin />} />
            </Route>
            <Route
              path="*"
              element={
                <div className="seccion-pendiente" role="alert">
                  <h1>No encontramos esa página.</h1>
                  <p>
                    <Link to="/servicios">Volver a los servicios</Link>
                  </p>
                </div>
              }
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
