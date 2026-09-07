import os
import sys
import io
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_NOTREAL_FAKE_KEY_FOR_UNIT_TESTS_ONLY"

import app as backend_app  # noqa: E402


@pytest.fixture()
def client():
    backend_app.app.config["TESTING"] = True
    backend_app.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    with backend_app.app.app_context():
        backend_app.db.drop_all()
        backend_app.db.create_all()
    with backend_app.app.test_client() as c:
        yield c


CSV_EJEMPLO = """fecha,concepto,importe
01/01/2026,PAGO SEGURIDAD SOCIAL AUTONOMOS,-294.00
02/01/2026,MERCADONA COMPRA SEMANAL,-45.30
03/01/2026,REPSOL GASOLINERA,-60.00
04/01/2026,INGRESO CLIENTE FACTURA 1,1000.00
05/01/2026,NETFLIX SUSCRIPCION,-15.99
06/01/2026,GOOGLE WORKSPACE SUSCRIPCION,-12.00
"""


def test_clasificar_gasto_reta():
    r = backend_app.clasificar_gasto("PAGO SEGURIDAD SOCIAL AUTONOMOS")
    assert r["deducible"] is True
    assert r["porcentaje_estimado"] == 100


def test_clasificar_gasto_personal_no_deducible():
    r = backend_app.clasificar_gasto("MERCADONA COMPRA SEMANAL")
    assert r["deducible"] is False


def test_clasificar_gasto_vehiculo_parcial():
    r = backend_app.clasificar_gasto("REPSOL GASOLINERA")
    assert r["deducible"] == "parcial"
    assert r["porcentaje_estimado"] == 50


def test_clasificar_gasto_desconocido_requiere_revision():
    r = backend_app.clasificar_gasto("XYZ TRANSACCION RARISIMA 123")
    assert r["deducible"] == "revisar"


def test_subir_csv_procesa_solo_gastos_no_ingresos(client):
    data = {"file": (io.BytesIO(CSV_EJEMPLO.encode("utf-8")), "movimientos.csv")}
    r = client.post("/api/movimientos/csv", data=data, content_type="multipart/form-data")
    assert r.status_code == 201
    body = r.get_json()
    # 5 gastos (importe negativo), el ingreso de 1000 se descarta
    assert body["movimientos_procesados"] == 5


def test_subir_csv_rechaza_archivo_no_csv(client):
    data = {"file": (io.BytesIO(b"hola"), "archivo.txt")}
    r = client.post("/api/movimientos/csv", data=data, content_type="multipart/form-data")
    assert r.status_code == 400


def test_subir_csv_sin_archivo(client):
    r = client.post("/api/movimientos/csv", data={}, content_type="multipart/form-data")
    assert r.status_code == 400


def test_resumen_calcula_totales(client):
    data = {"file": (io.BytesIO(CSV_EJEMPLO.encode("utf-8")), "movimientos.csv")}
    client.post("/api/movimientos/csv", data=data, content_type="multipart/form-data")
    r = client.get("/api/movimientos/resumen")
    assert r.status_code == 200
    body = r.get_json()
    assert body["total_movimientos"] == 5
    assert body["total_deducible_estimado"] > 0


def test_exportar_csv(client):
    data = {"file": (io.BytesIO(CSV_EJEMPLO.encode("utf-8")), "movimientos.csv")}
    client.post("/api/movimientos/csv", data=data, content_type="multipart/form-data")
    r = client.get("/api/movimientos/exportar.csv")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert "descripcion" in r.get_data(as_text=True)


def test_ocr_endpoint_sin_dependencias_o_binario_responde_error_controlado(client):
    data = {"file": (io.BytesIO(b"fake-image-bytes"), "ticket.png")}
    r = client.post("/api/ticket/ocr", data=data, content_type="multipart/form-data")
    # Sin Tesseract instalado en el sistema de CI, debe fallar de forma controlada (no 500 crudo)
    assert r.status_code in (200, 501, 502)
    assert r.is_json


def test_suscribir_stripe_test_mode(client):
    r = client.post("/api/suscribir")
    assert r.status_code in (200, 400)
    assert r.is_json
