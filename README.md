# Detector de gastos deducibles — MVP

## Cómo ejecutar
```bash
cd backend
cp ../.env.example ../.env
../.venv/Scripts/python app.py
# abre http://localhost:5003
```

## Cómo correr los tests
```bash
.venv/Scripts/python -m pytest tests/ -v
```

OCR de tickets (opcional): requiere tener **Tesseract OCR** instalado en el sistema y apuntar `TESSERACT_CMD` en `.env` a su ruta. Sin esto, el flujo principal (subida de CSV) funciona igualmente.

Ver `NORMATIVA.md` (criterios fiscales) y `RESUMEN.md` (decisiones y pasos a producción).
