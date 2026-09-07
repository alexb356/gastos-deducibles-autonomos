"""
MVP: Detector de gastos deducibles para autónomos.

Flujo:
1. El usuario sube un CSV de movimientos bancarios (fecha, descripción, importe) o,
   opcionalmente, una imagen de un ticket (OCR con pytesseract si está disponible).
2. El clasificador de reglas (ver NORMATIVA.md) marca cada gasto como deducible/no
   deducible/parcial, con % estimado y la norma que lo justifica.
3. Resumen exportable (CSV) con el total deducible estimado.
4. Suscripción de pago vía Stripe en modo TEST.

Ver NORMATIVA.md para las fuentes y criterios fiscales exactos usados.
"""
import os
import io
import csv
import re
import uuid
from datetime import datetime, timezone

from flask import Flask, request, jsonify, render_template, Response
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-only-not-secure")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///gastos.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8MB: admite CSV/foto de ticket, mitiga DoS

db = SQLAlchemy(app)


@app.after_request
def _cabeceras_seguridad(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resp

# ---------------------------------------------------------------------------
# Motor de reglas de deducibilidad (ver NORMATIVA.md)
# ---------------------------------------------------------------------------

REGLAS = [
    # (patrón regex sobre descripción en minúsculas, deducible, porcentaje, norma)
    (r"seguridad social|reta|autonomos?.*cuota|cuota.*autonomo", True, 100,
     "Cuota de autónomos (RETA) 100% deducible en IRPF (rendimientos de actividades económicas)."),
    (r"alquiler.*(oficina|local|despacho)|renta.*local", True, 100,
     "Alquiler de local exclusivamente profesional: 100% deducible (Art. 30 LIRPF)."),
    (r"gestor|gestoria|asesor(ia)? fiscal|asesoria laboral", True, 100,
     "Servicios profesionales de gestoría/asesoría: 100% deducible."),
    (r"combustible|gasolina|diesel|gasoil|repsol|cepsa|shell(?! company)", "parcial", 50,
     "Combustible de vehículo: deducible 50% en IVA salvo afectación exclusiva probada (100% IRPF solo si actividad de transporte). Ver NORMATIVA.md."),
    (r"parking|aparcamiento|peaje|autopista|itv\b", "parcial", 50,
     "Gastos asociados al vehículo: deducible 50% salvo afectación exclusiva probada."),
    (r"taller|neumaticos|revision.*coche|seguro.*(coche|vehiculo|auto)", "parcial", 50,
     "Mantenimiento/seguro de vehículo: deducible 50% en IVA salvo afectación exclusiva probada; en IRPF solo si afectación 100%."),
    (r"restaurante|cafeteria|menu del dia|bar\b|hosteleria", "revisar", 0,
     "Manutención/dietas: deducible solo si es en municipio distinto al de residencia habitual, pagado por medios electrónicos, con justificante y límite 26,67€/día en España (48,08€ extranjero) — requiere revisión manual del contexto del viaje."),
    (r"movil|telefonia|vodafone|movistar|orange|yoigo|internet|fibra|router", "parcial", 50,
     "Teléfono/internet de uso mixto: deducible la parte proporcional de uso profesional (100% si línea exclusiva profesional)."),
    (r"software|saas|suscripcion.*(app|plataforma)|hosting|dominio|adobe|microsoft 365|google workspace", True, 100,
     "Software/herramientas digitales para la actividad: 100% deducible si vinculado a la actividad."),
    (r"formacion|curso|master|masterclass|udemy|coursera", True, 100,
     "Formación relacionada con la actividad profesional: 100% deducible."),
    (r"marketing|publicidad|ads\b|meta ads|google ads|facebook ads", True, 100,
     "Gastos de publicidad/marketing de la actividad: 100% deducible."),
    (r"nomina|salario.*empleado|seguridad social.*empleado", True, 100,
     "Sueldos y Seguridad Social de empleados: 100% deducible."),
    (r"material de oficina|papeleria|consumibles|tinta.*impresora", True, 100,
     "Material de oficina/consumibles: 100% deducible."),
    (r"luz\b|electricidad|agua\b|gas natural|suministro", "parcial", 30,
     "Suministros de vivienda con uso parcial para la actividad: fórmula legal = importe × (m² afectados/m² totales) × 30% (Art. 30 LIRPF). Requiere confirmar m² declarados."),
    (r"comida personal|supermercado|compra semanal|mercadona|carrefour|alcampo", False, 0,
     "Gasto de alimentación de carácter personal/familiar: no vinculado a la actividad económica, no deducible."),
    (r"netflix|spotify personal|hbo|disney\+|ropa|moda|gimnasio", False, 0,
     "Gasto de consumo personal sin vinculación demostrable con la actividad: no deducible."),
]


def clasificar_gasto(descripcion, importe=None):
    desc = (descripcion or "").lower()
    for patron, deducible, porcentaje, norma in REGLAS:
        if re.search(patron, desc):
            return {"deducible": deducible, "porcentaje_estimado": porcentaje, "norma": norma}
    return {
        "deducible": "revisar",
        "porcentaje_estimado": 0,
        "norma": "Gasto no reconocido automáticamente por el motor de reglas. Requiere clasificación manual: comprobar vinculación con la actividad, factura con NIF y registro contable (Art. 30 LIRPF / Art. 95 Ley IVA).",
    }


class Movimiento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.String(20))
    descripcion = db.Column(db.String(500), nullable=False)
    importe = db.Column(db.Float, nullable=False)
    deducible = db.Column(db.String(20))  # "True"/"False"/"parcial"/"revisar"
    porcentaje_estimado = db.Column(db.Float)
    norma = db.Column(db.Text)
    lote = db.Column(db.String(100))
    creado = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id, "fecha": self.fecha, "descripcion": self.descripcion,
            "importe": self.importe, "deducible": self.deducible,
            "porcentaje_estimado": self.porcentaje_estimado, "norma": self.norma,
            "lote": self.lote,
        }


@app.route("/")
def index():
    return render_template("index.html")


def _detectar_delimitador(muestra):
    """Detecta si el CSV usa coma o punto y coma como separador de columnas.
    Los extractos bancarios españoles suelen usar ';' precisamente porque el
    importe usa ',' como separador decimal (ej. "-45,30")."""
    try:
        dialecto = csv.Sniffer().sniff(muestra, delimiters=",;\t")
        return dialecto.delimiter
    except csv.Error:
        return ","


@app.route("/api/movimientos/csv", methods=["POST"])
def subir_csv():
    if "file" not in request.files:
        return jsonify({"error": "falta el archivo CSV (campo 'file')"}), 400
    f = request.files["file"]
    if not f.filename or not f.filename.lower().endswith(".csv"):
        return jsonify({"error": "el archivo debe tener extensión .csv"}), 400

    try:
        contenido = f.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return jsonify({"error": "no se pudo leer el CSV (codificación no soportada, usa UTF-8)"}), 400

    if not contenido.strip():
        return jsonify({"error": "el CSV está vacío"}), 400

    lote = datetime.now(timezone.utc).strftime("lote-%Y%m%d%H%M%S-") + uuid.uuid4().hex[:12]
    delimitador = _detectar_delimitador(contenido[:4096])
    reader = csv.DictReader(io.StringIO(contenido), delimiter=delimitador)
    campos = {c.lower().strip(): c for c in (reader.fieldnames or [])}
    col_fecha = next((campos[k] for k in campos if "fecha" in k), None)
    col_desc = next((campos[k] for k in campos if "concepto" in k or "descrip" in k), None)
    col_importe = next((campos[k] for k in campos if "importe" in k or "cantidad" in k or "monto" in k), None)

    if not col_desc or not col_importe:
        return jsonify({"error": "el CSV debe tener columnas de descripción/concepto e importe"}), 400

    creados = []
    for row in reader:
        desc = (row.get(col_desc) or "").strip()
        importe_valor = row.get(col_importe) or ""
        # Si el delimitador es ',' y el importe usa coma decimal (ej. "-45,30 €"),
        # DictReader puede haber partido el valor en columnas extra (row[None]).
        # Reconstruimos el importe original antes de normalizar.
        extra = row.get(None)
        if delimitador == "," and extra:
            importe_valor = ",".join([importe_valor] + [str(x) for x in extra if x is not None])
        importe_raw = importe_valor.replace(".", "").replace(",", ".").replace("€", "").strip() \
            if importe_valor.count(",") == 1 and re.search(r",\d{1,2}\D*$", importe_valor) \
            else importe_valor.replace(",", ".").replace("€", "").strip()
        try:
            importe = float(importe_raw)
        except ValueError:
            continue
        if not desc:
            continue
        if importe >= 0:
            continue  # solo analizamos gastos (importes negativos en un extracto bancario)
        clasificacion = clasificar_gasto(desc, importe)
        mov = Movimiento(
            fecha=(row.get(col_fecha) or "").strip() if col_fecha else "",
            descripcion=desc[:500],
            importe=abs(importe),
            deducible=str(clasificacion["deducible"]),
            porcentaje_estimado=clasificacion["porcentaje_estimado"],
            norma=clasificacion["norma"],
            lote=lote,
        )
        db.session.add(mov)
        creados.append(mov)
    db.session.commit()
    return jsonify({"lote": lote, "movimientos_procesados": len(creados),
                    "movimientos": [m.to_dict() for m in creados]}), 201


@app.route("/api/movimientos", methods=["GET"])
def listar_movimientos():
    lote = request.args.get("lote")
    if not lote:
        return jsonify({"error": "falta el parámetro 'lote' (no se listan movimientos de otros usuarios sin especificarlo)"}), 400
    q = Movimiento.query.filter_by(lote=lote)
    return jsonify([m.to_dict() for m in q.order_by(Movimiento.id.desc()).all()])


@app.route("/api/movimientos/resumen")
def resumen():
    lote = request.args.get("lote")
    if not lote:
        return jsonify({"error": "falta el parámetro 'lote' (no se agregan movimientos de otros usuarios sin especificarlo)"}), 400
    movimientos = Movimiento.query.filter_by(lote=lote).all()
    total_gastado = sum(m.importe for m in movimientos)
    total_deducible_estimado = 0.0
    for m in movimientos:
        if m.deducible == "True":
            total_deducible_estimado += m.importe
        elif m.deducible == "parcial":
            total_deducible_estimado += m.importe * (m.porcentaje_estimado or 0) / 100
    return jsonify({
        "total_movimientos": len(movimientos),
        "total_gastado": round(total_gastado, 2),
        "total_deducible_estimado": round(total_deducible_estimado, 2),
        "pendientes_revision": sum(1 for m in movimientos if m.deducible == "revisar"),
    })


def _sanitizar_celda_csv(valor):
    """Mitiga CSV/Formula Injection (CWE-1236): si el valor empieza por un
    carácter que Excel/Sheets interpretaría como inicio de fórmula, se le
    antepone un apóstrofo para forzar texto plano."""
    s = "" if valor is None else str(valor)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


@app.route("/api/movimientos/exportar.csv")
def exportar_csv():
    lote = request.args.get("lote")
    if not lote:
        return jsonify({"error": "falta el parámetro 'lote' (no se exportan movimientos de otros usuarios sin especificarlo)"}), 400
    movimientos = Movimiento.query.filter_by(lote=lote).order_by(Movimiento.id.asc()).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["fecha", "descripcion", "importe", "deducible", "porcentaje_estimado", "norma"])
    for m in movimientos:
        writer.writerow([
            _sanitizar_celda_csv(m.fecha), _sanitizar_celda_csv(m.descripcion),
            m.importe, _sanitizar_celda_csv(m.deducible), m.porcentaje_estimado,
            _sanitizar_celda_csv(m.norma),
        ])
    return Response(buf.getvalue(), mimetype="text/csv",
                     headers={"Content-Disposition": "attachment; filename=resumen_gastos_deducibles.csv"})


@app.route("/api/ticket/ocr", methods=["POST"])
def ocr_ticket():
    """OCR opcional de una foto de ticket. Requiere Tesseract instalado en el sistema."""
    if "file" not in request.files:
        return jsonify({"error": "falta la imagen (campo 'file')"}), 400
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return jsonify({"error": "Dependencias de OCR no instaladas (pytesseract/Pillow)"}), 501

    tesseract_cmd = os.environ.get("TESSERACT_CMD", "").strip()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    f = request.files["file"]
    try:
        img = Image.open(f.stream)
        img.verify()  # detecta imágenes truncadas/corruptas antes de decodificar
        f.stream.seek(0)
        img = Image.open(f.stream)
        # Mitiga "decompression bombs" (imágenes con dimensiones declaradas
        # absurdamente grandes que agotan memoria al decodificar). Pillow ya
        # avisa por defecto sobre Image.MAX_IMAGE_PIXELS; aquí lo forzamos
        # explícitamente con un límite razonable para una foto de ticket.
        ancho, alto = img.size
        if ancho * alto > 40_000_000:  # ~40 megapíxeles, muy por encima de una foto de móvil normal
            return jsonify({"error": "imagen demasiado grande para procesar"}), 413
        texto = pytesseract.image_to_string(img, lang="spa+eng")
    except Exception as exc:
        return jsonify({"error": f"No se pudo procesar la imagen. ¿Tesseract OCR está instalado? Detalle: {exc}"}), 502

    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    resultados = []
    for linea in lineas:
        m = re.search(r"(\d+[.,]\d{2})\s*€?\s*$", linea)
        if m:
            importe = float(m.group(1).replace(",", "."))
            descripcion = linea[:m.start()].strip() or linea
            resultados.append({"descripcion": descripcion, "importe": importe,
                                **clasificar_gasto(descripcion, importe)})
    return jsonify({"texto_extraido": texto, "lineas_detectadas": resultados})


@app.route("/api/suscribir", methods=["POST"])
def suscribir():
    import stripe
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe.api_key or not stripe.api_key.startswith("sk_test_"):
        return jsonify({"error": "Stripe no configurado en modo TEST"}), 400
    try:
        intent = stripe.PaymentIntent.create(amount=500, currency="eur",
                                              metadata={"producto": "detector-gastos-deducibles"})
    except stripe.error.StripeError as exc:
        return jsonify({"error": f"Stripe rechazó la petición: {exc.user_message or str(exc)}"}), 400
    return jsonify({"client_secret": intent.client_secret, "payment_intent_id": intent.id})


def crear_tablas():
    with app.app_context():
        db.create_all()


if __name__ == "__main__":
    crear_tablas()
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=5003)
