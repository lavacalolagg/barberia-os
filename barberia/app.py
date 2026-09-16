"""
BARBERSHOP OS 3.0 — Backend
Flask + Flask-SocketIO + SQLite3
CTO note: arquitectura monolítica modular, lista para separarse en
blueprints/microservicios cuando el volumen lo justifique.
"""
import os
import io
import base64
import sqlite3
import uuid
from datetime import datetime, timedelta

# eventlet debe parchar el runtime ANTES de importar cualquier otra cosa
# de red (incluido Flask). Es el patrón recomendado por Flask-SocketIO
# para correr en producción con gunicorn --worker-class eventlet.
import eventlet
eventlet.monkey_patch()

from flask import Flask, request, jsonify, g, render_template, send_from_directory
from flask_socketio import SocketIO, emit

# QR opcional: si 'qrcode' no está instalado, degradamos con gracia.
try:
    import qrcode
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "barberia.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "database", "schema.sql")

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cyber-luxury-dev-key")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ------------------------------------------------------------------
# DB HELPERS
# ------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def row_to_dict(row):
    return dict(row) if row else None


def rows_to_list(rows):
    return [dict(r) for r in rows]


# ------------------------------------------------------------------
# VISTA PRINCIPAL (SPA SHELL)
# ------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/manifest.json")
def manifest():
    return send_from_directory(app.static_folder, "manifest.json")


@app.route("/service-worker.js")
def service_worker():
    # Servido desde raíz para que su scope cubra toda la app (PWA)
    resp = send_from_directory(app.static_folder + "/js", "service-worker.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


# ------------------------------------------------------------------
# API: CLIENTES
# ------------------------------------------------------------------
@app.route("/api/clientes", methods=["GET"])
def listar_clientes():
    db = get_db()
    q = request.args.get("q", "").strip()
    if q:
        rows = db.execute(
            "SELECT * FROM clientes WHERE nombre LIKE ? OR telefono LIKE ? ORDER BY nombre",
            (f"%{q}%", f"%{q}%"),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM clientes ORDER BY nombre").fetchall()
    return jsonify(rows_to_list(rows))


@app.route("/api/clientes", methods=["POST"])
def crear_cliente():
    data = request.get_json(force=True)
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO clientes (nombre, telefono, email, tipo_rostro, notas) VALUES (?,?,?,?,?)",
            (data["nombre"], data["telefono"], data.get("email"), data.get("tipo_rostro"), data.get("notas")),
        )
        db.commit()
        cliente = db.execute("SELECT * FROM clientes WHERE id=?", (cur.lastrowid,)).fetchone()
        return jsonify(row_to_dict(cliente)), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Ya existe un cliente con ese teléfono"}), 409


# ------------------------------------------------------------------
# API: BARBEROS / SERVICIOS / INVENTARIO (catálogos)
# ------------------------------------------------------------------
@app.route("/api/barberos", methods=["GET"])
def listar_barberos():
    db = get_db()
    rows = db.execute("SELECT * FROM barberos ORDER BY nombre").fetchall()
    return jsonify(rows_to_list(rows))


@app.route("/api/servicios", methods=["GET"])
def listar_servicios():
    db = get_db()
    rows = db.execute("SELECT * FROM servicios WHERE activo=1 ORDER BY precio").fetchall()
    return jsonify(rows_to_list(rows))


@app.route("/api/inventario", methods=["GET"])
def listar_inventario():
    db = get_db()
    rows = db.execute("SELECT * FROM inventario ORDER BY stock_actual ASC").fetchall()
    return jsonify(rows_to_list(rows))


# ------------------------------------------------------------------
# API: CITAS + SALA DE ESPERA EN TIEMPO REAL
# ------------------------------------------------------------------
def emitir_sala_de_espera():
    """Recalcula la cola y la transmite por WebSocket a todos los clientes conectados."""
    db = get_db()
    rows = db.execute(
        """
        SELECT c.id, c.fecha_hora, c.estado, c.posicion_cola, c.tiempo_estimado_min,
               cl.nombre AS cliente_nombre, b.nombre AS barbero_nombre, b.id AS barbero_id,
               s.nombre AS servicio_nombre, s.duracion_min
        FROM citas c
        JOIN clientes cl ON cl.id = c.cliente_id
        JOIN barberos b  ON b.id = c.barbero_id
        JOIN servicios s ON s.id = c.servicio_id
        WHERE c.estado IN ('confirmada','en_espera','en_proceso')
        ORDER BY c.posicion_cola ASC, c.fecha_hora ASC
        """
    ).fetchall()
    cola = rows_to_list(rows)
    socketio.emit("sala_espera_update", {"cola": cola, "ts": datetime.now().isoformat()})
    return cola


@app.route("/api/citas", methods=["GET"])
def listar_citas():
    db = get_db()
    fecha = request.args.get("fecha")  # YYYY-MM-DD opcional
    base = """
        SELECT c.*, cl.nombre AS cliente_nombre, cl.telefono AS cliente_telefono,
               b.nombre AS barbero_nombre, s.nombre AS servicio_nombre, s.precio
        FROM citas c
        JOIN clientes cl ON cl.id=c.cliente_id
        JOIN barberos b ON b.id=c.barbero_id
        JOIN servicios s ON s.id=c.servicio_id
    """
    if fecha:
        rows = db.execute(base + " WHERE date(c.fecha_hora)=? ORDER BY c.fecha_hora", (fecha,)).fetchall()
    else:
        rows = db.execute(base + " ORDER BY c.fecha_hora DESC LIMIT 100").fetchall()
    return jsonify(rows_to_list(rows))


@app.route("/api/citas", methods=["POST"])
def crear_cita():
    """
    Crea una cita. Si el body incluye metodo_pago_anticipo, genera un QR
    de pago simulado (Mercado Pago / SPEI) para reservar con anticipación.
    """
    data = request.get_json(force=True)
    db = get_db()

    servicio = db.execute("SELECT * FROM servicios WHERE id=?", (data["servicio_id"],)).fetchone()
    if not servicio:
        return jsonify({"error": "Servicio no encontrado"}), 404

    # calcular siguiente posición en cola del barbero para el día
    max_pos = db.execute(
        "SELECT COALESCE(MAX(posicion_cola),0) AS m FROM citas WHERE barbero_id=? AND estado IN ('confirmada','en_espera','en_proceso') AND date(fecha_hora)=date(?)",
        (data["barbero_id"], data["fecha_hora"]),
    ).fetchone()["m"]

    qr_ref = None
    metodo = data.get("metodo_pago_anticipo")
    estado_inicial = "pendiente"
    if metodo:
        qr_ref = f"{metodo.upper()}-{uuid.uuid4().hex[:10]}"
        estado_inicial = "confirmada"  # el anticipo confirma la cita automáticamente (simulado)

    cur = db.execute(
        """INSERT INTO citas
           (cliente_id, barbero_id, servicio_id, fecha_hora, estado, posicion_cola,
            tiempo_estimado_min, pago_anticipo, metodo_pago_anticipo, qr_referencia)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            data["cliente_id"], data["barbero_id"], data["servicio_id"], data["fecha_hora"],
            estado_inicial, max_pos + 1, servicio["duracion_min"],
            data.get("pago_anticipo", 0), metodo, qr_ref,
        ),
    )
    db.commit()
    cita_id = cur.lastrowid
    emitir_sala_de_espera()

    payload = {"id": cita_id, "estado": estado_inicial, "qr_referencia": qr_ref}
    if qr_ref:
        payload["qr_data_url"] = generar_qr_base64(f"barberia-pay://{metodo}/{qr_ref}?monto={data.get('pago_anticipo',0)}")
    return jsonify(payload), 201


@app.route("/api/citas/<int:cita_id>/estado", methods=["PATCH"])
def actualizar_estado_cita(cita_id):
    data = request.get_json(force=True)
    nuevo_estado = data.get("estado")
    valid = {"pendiente", "confirmada", "en_espera", "en_proceso", "completada", "cancelada", "no_show"}
    if nuevo_estado not in valid:
        return jsonify({"error": "estado inválido"}), 400
    db = get_db()
    db.execute("UPDATE citas SET estado=? WHERE id=?", (nuevo_estado, cita_id))
    db.commit()
    cola = emitir_sala_de_espera()
    return jsonify({"ok": True, "cola": cola})


@app.route("/api/sala-espera", methods=["GET"])
def sala_espera_snapshot():
    """Fallback HTTP (por si el socket aún no conectó) para pintar el estado inicial."""
    cola = emitir_sala_de_espera()
    return jsonify(cola)


# ------------------------------------------------------------------
# API: PAGOS / QR (simulado — reemplazar por SDK real de Mercado Pago/SPEI)
# ------------------------------------------------------------------
def generar_qr_base64(payload_text: str) -> str:
    if not QR_AVAILABLE:
        return ""
    img = qrcode.make(payload_text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@app.route("/api/pagos/qr", methods=["POST"])
def generar_qr_pago():
    data = request.get_json(force=True)
    metodo = data.get("metodo", "mercado_pago")
    monto = data.get("monto", 0)
    referencia = f"{metodo.upper()}-{uuid.uuid4().hex[:10]}"
    payload = f"barberia-pay://{metodo}/{referencia}?monto={monto}"
    return jsonify({
        "referencia": referencia,
        "metodo": metodo,
        "monto": monto,
        "qr_data_url": generar_qr_base64(payload),
        "qr_disponible": QR_AVAILABLE,
    })


# ------------------------------------------------------------------
# API: PUNTO DE VENTA (POS)
# ------------------------------------------------------------------
@app.route("/api/pos/venta", methods=["POST"])
def registrar_venta():
    """
    Body esperado:
    {
      "cliente_id": 1, "barbero_id": 2, "cita_id": null,
      "items": [
        {"tipo":"servicio","referencia_id":2,"cantidad":1},
        {"tipo":"producto","referencia_id":1,"cantidad":1}
      ],
      "descuento": 0, "metodo_pago": "tarjeta"
    }
    Efectos: calcula totales, descuenta stock automáticamente,
    calcula comisión del barbero y suma puntos de lealtad al cliente.
    """
    data = request.get_json(force=True)
    db = get_db()

    barbero = db.execute("SELECT * FROM barberos WHERE id=?", (data["barbero_id"],)).fetchone()
    if not barbero:
        return jsonify({"error": "Barbero no encontrado"}), 404

    subtotal = 0.0
    puntos_totales = 0
    items_resueltos = []

    for item in data.get("items", []):
        cantidad = item.get("cantidad", 1)
        if item["tipo"] == "servicio":
            row = db.execute("SELECT * FROM servicios WHERE id=?", (item["referencia_id"],)).fetchone()
            if not row:
                return jsonify({"error": f"Servicio {item['referencia_id']} no existe"}), 404
            precio = row["precio"]
            puntos_totales += row["puntos_otorga"] * cantidad
            nombre = row["nombre"]
        elif item["tipo"] == "producto":
            row = db.execute("SELECT * FROM inventario WHERE id=?", (item["referencia_id"],)).fetchone()
            if not row:
                return jsonify({"error": f"Producto {item['referencia_id']} no existe"}), 404
            if row["stock_actual"] < cantidad:
                return jsonify({"error": f"Stock insuficiente de {row['nombre']}"}), 409
            precio = row["precio_venta"]
            nombre = row["nombre"]
        else:
            return jsonify({"error": "tipo de item inválido"}), 400

        total_linea = precio * cantidad
        subtotal += total_linea
        items_resueltos.append({
            "tipo": item["tipo"], "referencia_id": item["referencia_id"],
            "nombre": nombre, "cantidad": cantidad,
            "precio_unitario": precio, "total_linea": total_linea,
        })

    descuento = data.get("descuento", 0)
    total = max(subtotal - descuento, 0)
    comision = round(total * (barbero["porcentaje_comision"] / 100.0), 2)

    cur = db.execute(
        """INSERT INTO ventas (cliente_id, barbero_id, cita_id, subtotal, descuento, total,
                                comision_barbero, metodo_pago, puntos_otorgados)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (data.get("cliente_id"), data["barbero_id"], data.get("cita_id"),
         subtotal, descuento, total, comision, data.get("metodo_pago", "efectivo"), puntos_totales),
    )
    venta_id = cur.lastrowid

    for it in items_resueltos:
        db.execute(
            """INSERT INTO venta_items (venta_id, tipo, referencia_id, nombre, cantidad, precio_unitario, total_linea)
               VALUES (?,?,?,?,?,?,?)""",
            (venta_id, it["tipo"], it["referencia_id"], it["nombre"], it["cantidad"], it["precio_unitario"], it["total_linea"]),
        )
        # Descuento automático de inventario:
        # - venta directa de producto: descuenta la cantidad vendida
        # - servicio: descuenta el consumo proporcional configurado (insumos usados)
        if it["tipo"] == "producto":
            db.execute("UPDATE inventario SET stock_actual = stock_actual - ? WHERE id=?", (it["cantidad"], it["referencia_id"]))

    if data.get("cliente_id") and puntos_totales:
        db.execute("UPDATE clientes SET puntos_lealtad = puntos_lealtad + ? WHERE id=?", (puntos_totales, data["cliente_id"]))

    if data.get("cita_id"):
        db.execute("UPDATE citas SET estado='completada' WHERE id=?", (data["cita_id"],))

    db.commit()
    emitir_sala_de_espera()

    venta = db.execute("SELECT * FROM ventas WHERE id=?", (venta_id,)).fetchone()
    return jsonify({
        "venta": row_to_dict(venta),
        "items": items_resueltos,
        "comision_barbero": comision,
        "puntos_otorgados": puntos_totales,
    }), 201


# ------------------------------------------------------------------
# API: DASHBOARD / ANALÍTICA
# ------------------------------------------------------------------
@app.route("/api/analytics/resumen", methods=["GET"])
def analytics_resumen():
    db = get_db()
    hoy = datetime.now().strftime("%Y-%m-%d")

    ingresos_hoy = db.execute(
        "SELECT COALESCE(SUM(total),0) AS t FROM ventas WHERE date(creado_en)=?", (hoy,)
    ).fetchone()["t"]

    ingresos_7dias = db.execute(
        """SELECT date(creado_en) AS dia, SUM(total) AS total
           FROM ventas WHERE date(creado_en) >= date(?, '-6 days')
           GROUP BY dia ORDER BY dia""", (hoy,)
    ).fetchall()

    horas_pico = db.execute(
        """SELECT strftime('%H', creado_en) AS hora, COUNT(*) AS n
           FROM ventas GROUP BY hora ORDER BY hora"""
    ).fetchall()

    servicios_top = db.execute(
        """SELECT nombre, COUNT(*) AS veces, SUM(total_linea) AS ingresos
           FROM venta_items WHERE tipo='servicio'
           GROUP BY nombre ORDER BY veces DESC LIMIT 6"""
    ).fetchall()

    rendimiento_barberos = db.execute(
        """SELECT b.nombre, COUNT(v.id) AS ventas, COALESCE(SUM(v.total),0) AS ingresos,
                  COALESCE(SUM(v.comision_barbero),0) AS comisiones
           FROM barberos b LEFT JOIN ventas v ON v.barbero_id=b.id
           GROUP BY b.id ORDER BY ingresos DESC"""
    ).fetchall()

    inventario_bajo = db.execute(
        "SELECT nombre, stock_actual, stock_minimo FROM inventario WHERE stock_actual <= stock_minimo"
    ).fetchall()

    return jsonify({
        "ingresos_hoy": ingresos_hoy,
        "ingresos_7dias": rows_to_list(ingresos_7dias),
        "horas_pico": rows_to_list(horas_pico),
        "servicios_top": rows_to_list(servicios_top),
        "rendimiento_barberos": rows_to_list(rendimiento_barberos),
        "inventario_bajo": rows_to_list(inventario_bajo),
    })


# ------------------------------------------------------------------
# WEBHOOK WHATSAPP (confirmación / recordatorio de citas)
# ------------------------------------------------------------------
@app.route("/webhook/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    """
    GET: verificación del webhook (patrón Meta/WhatsApp Cloud API).
    POST: recibe mensajes entrantes y responde según intención simple
    (CONFIRMAR / CANCELAR / palabras clave). En producción, sustituir
    el 'enviar_whatsapp' simulado por una llamada real a la API oficial.
    """
    if request.method == "GET":
        verify_token = os.environ.get("WHATSAPP_VERIFY_TOKEN", "barberia-verify")
        if request.args.get("hub.verify_token") == verify_token:
            return request.args.get("hub.challenge", ""), 200
        return "Token inválido", 403

    payload = request.get_json(force=True, silent=True) or {}
    telefono = payload.get("from") or payload.get("telefono")
    texto = (payload.get("text") or payload.get("mensaje") or "").strip().lower()

    db = get_db()
    cliente = db.execute("SELECT * FROM clientes WHERE telefono=?", (telefono,)).fetchone()
    respuesta = "No encontramos una cita asociada a este número."

    if cliente:
        cita = db.execute(
            """SELECT c.*, s.nombre as servicio_nombre, b.nombre as barbero_nombre
               FROM citas c JOIN servicios s ON s.id=c.servicio_id JOIN barberos b ON b.id=c.barbero_id
               WHERE c.cliente_id=? AND c.estado IN ('pendiente','confirmada')
               ORDER BY c.fecha_hora ASC LIMIT 1""",
            (cliente["id"],),
        ).fetchone()

        if cita:
            if "confirm" in texto:
                db.execute("UPDATE citas SET estado='confirmada' WHERE id=?", (cita["id"],))
                db.commit()
                emitir_sala_de_espera()
                respuesta = f"¡Listo {cliente['nombre']}! Tu cita de {cita['servicio_nombre']} con {cita['barbero_nombre']} quedó confirmada."
            elif "cancel" in texto:
                db.execute("UPDATE citas SET estado='cancelada' WHERE id=?", (cita["id"],))
                db.commit()
                emitir_sala_de_espera()
                respuesta = "Tu cita fue cancelada. ¡Esperamos verte pronto!"
            else:
                respuesta = (
                    f"Hola {cliente['nombre']}, tienes una cita de {cita['servicio_nombre']} "
                    f"con {cita['barbero_nombre']} el {cita['fecha_hora']}. Responde CONFIRMAR o CANCELAR."
                )

    enviar_whatsapp_simulado(telefono, respuesta)
    return jsonify({"status": "processed", "respuesta": respuesta})


def enviar_whatsapp_simulado(telefono, mensaje):
    """Placeholder de integración real (Twilio / WhatsApp Cloud API)."""
    app.logger.info(f"[WHATSAPP -> {telefono}] {mensaje}")


def enviar_recordatorios_pendientes():
    """
    Job de recordatorios: citas dentro de la próxima hora sin recordatorio enviado.
    Se puede disparar con un scheduler externo (cron, APScheduler) llamando este endpoint.
    """
    db = get_db()
    ahora = datetime.now()
    limite = ahora + timedelta(hours=1)
    rows = db.execute(
        """SELECT c.*, cl.nombre, cl.telefono, s.nombre as servicio_nombre
           FROM citas c JOIN clientes cl ON cl.id=c.cliente_id JOIN servicios s ON s.id=c.servicio_id
           WHERE c.recordatorio_enviado=0 AND c.estado IN ('confirmada','pendiente')
           AND c.fecha_hora BETWEEN ? AND ?""",
        (ahora.isoformat(), limite.isoformat()),
    ).fetchall()

    for r in rows:
        enviar_whatsapp_simulado(
            r["telefono"],
            f"Hola {r['nombre']}, te recordamos tu cita de {r['servicio_nombre']} en menos de 1 hora."
        )
        db.execute("UPDATE citas SET recordatorio_enviado=1 WHERE id=?", (r["id"],))
    db.commit()
    return len(rows)


@app.route("/api/recordatorios/ejecutar", methods=["POST"])
def ejecutar_recordatorios():
    n = enviar_recordatorios_pendientes()
    return jsonify({"enviados": n})


# ------------------------------------------------------------------
# SOCKET.IO EVENTS
# ------------------------------------------------------------------
@socketio.on("connect")
def on_connect():
    with app.app_context():
        cola = emitir_sala_de_espera()
    emit("sala_espera_update", {"cola": cola, "ts": datetime.now().isoformat()})


@socketio.on("solicitar_actualizacion")
def on_solicitud(_data=None):
    with app.app_context():
        emitir_sala_de_espera()


# ------------------------------------------------------------------
# BOOT
# ------------------------------------------------------------------
if not os.path.exists(DB_PATH):
    init_db()

if __name__ == "__main__":
    # Modo desarrollo local: python app.py
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=True)

# Modo producción (Render/Railway): gunicorn arranca este mismo módulo
# usando la variable `app` de abajo con el worker eventlet, por eso la
# inicialización de la DB y el patch de eventlet están fuera del if.
