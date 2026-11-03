from app import openapi
from app.main import app

ESQUEMA = app.openapi()
METODOS = {"get", "post", "put", "patch", "delete"}


def _operaciones(prefijo="/api/v1"):
    for ruta, ops in ESQUEMA["paths"].items():
        if ruta.startswith(prefijo):
            for metodo, op in ops.items():
                if metodo in METODOS:
                    yield f"{metodo.upper()} {ruta}", op


def test_docs_openapi_json_al_dia():
    assert openapi.RUTA.read_text(encoding="utf-8") == openapi.generar(), "Ejecuta `make openapi`"
    assert openapi.main(["--check"]) == 0


def test_seguridad_bearer_documentada():
    esquemas = ESQUEMA["components"]["securitySchemes"]
    assert any(s["type"] == "http" and s["scheme"].lower() == "bearer" for s in esquemas.values())


def test_rutas_del_dosier_literales():
    assert {"/api/v1/tracking/{guia}", "/api/v1/cotizar", "/api/v1/pqrs/crear-ticket"} <= set(ESQUEMA["paths"])


def test_cada_ruta_v1_documenta_un_error_problem_json():
    sin_error = [
        op_id
        for op_id, op in _operaciones()
        if not any(
            c[0] in "45" and "application/problem+json" in r.get("content", {}) for c, r in op["responses"].items()
        )
    ]
    assert not sin_error, f"Rutas sin respuesta de error documentada: {sin_error}"


def test_los_422_documentados_usan_problema_no_httpvalidationerror():
    """El handler real responde problem+json; la doc no debe prometer el HTTPValidationError de FastAPI."""
    malos = [
        op_id
        for op_id, op in _operaciones()
        if "422" in op["responses"]
        and "HTTPValidationError" in str(op["responses"]["422"].get("content", {}).get("application/json", ""))
    ]
    assert not malos, malos


def test_operaciones_con_resumen_y_tag():
    for op_id, op in _operaciones():
        assert op.get("summary") and op.get("tags"), op_id
