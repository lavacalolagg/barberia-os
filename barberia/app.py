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

from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import (
    Flask, request, jsonify, g, render_template, send_from_directory,
    session, redirect, url_for,
)
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
# AUTENTICACIÓN DE PERSONAL (usuarios reales, no contraseña compartida)
# ------------------------------------------------------------------
# Motivos de salida de inventario permitidos (lista cerrada + nota libre).
MOTIVOS_SALIDA_VALIDOS = {"Merma", "Rompimiento", "Uso interno", "Muestra", "Caducidad", "Extravío", "Otro"}


def login_required(f):
    """Protege endpoints que solo el staff logueado debe poder usar.
    Devuelve 401 JSON porque estos endpoints los consume JavaScript;
    el frontend decide qué hacer con el 401 (mandar a /login)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "No autorizado. Inicia sesión como staff."}), 401
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    """Protege endpoints que solo un usuario con rol 'admin' debe poder usar
    (ej. crear/desactivar cuentas de otros usuarios)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "No autorizado. Inicia sesión como staff."}), 401
        if session.get("rol") != "admin":
            return jsonify({"error": "Esta acción requiere rol de administrador."}), 403
        return f(*args, **kwargs)
    return wrapper

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
    """Se corre en cada arranque. Es seguro repetirla: el esquema usa
    CREATE TABLE IF NOT EXISTS / INSERT OR IGNORE, así que no duplica ni
    rompe nada si la base de datos ya existía."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    ensure_schema_upgrades()
    seed_admin_user()


def ensure_schema_upgrades():
    """Parches idempotentes para bases de datos creadas con una versión
    anterior del esquema (ej. antes de agregar columnas nuevas a inventario).
    Cada ALTER se ignora si la columna ya existe."""
    conn = sqlite3.connect(DB_PATH)
    for stmt in [
        "ALTER TABLE inventario ADD COLUMN descripcion TEXT",
        "ALTER TABLE inventario ADD COLUMN categoria TEXT",
        "ALTER TABLE inventario ADD COLUMN imagen_url TEXT",
        "ALTER TABLE inventario ADD COLUMN activo INTEGER NOT NULL DEFAULT 1",
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # la columna ya existe
    conn.commit()
    conn.close()


def seed_admin_user():
    """Crea la primera cuenta de administrador si la tabla usuarios está
    vacía, usando las credenciales de las variables de entorno ADMIN_USER
    y ADMIN_PASSWORD (con valores por defecto para desarrollo local)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    existe = conn.execute("SELECT COUNT(*) AS n FROM usuarios").fetchone()["n"]
    if existe == 0:
        usuario = os.environ.get("ADMIN_USER", "admin")
        password = os.environ.get("ADMIN_PASSWORD", "barberia123")
        conn.execute(
            "INSERT INTO usuarios (usuario, password_hash, nombre, rol) VALUES (?,?,?,?)",
            (usuario, generate_password_hash(password), "Administrador", "admin"),
        )
        conn.commit()
        app.logger.info(f"Usuario admin inicial creado: '{usuario}' (cambia la contraseña por defecto en producción).")
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


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        row = db.execute(
            "SELECT * FROM usuarios WHERE usuario=? AND activo=1", (usuario,)
        ).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            session["user_id"] = row["id"]
            session["usuario"] = row["usuario"]
            session["nombre"] = row["nombre"]
            session["rol"] = row["rol"]
            next_url = request.args.get("next") or "/"
            return redirect(next_url)
        error = "Usuario o contraseña incorrectos."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/api/whoami")
def whoami():
    """El frontend usa esto para saber si debe mostrar controles de staff
    (botones de la sala de espera, panel de inventario, gestión de usuarios)
    sin exponer esa lógica solo en el cliente."""
    return jsonify({
        "staff": bool(session.get("user_id")),
        "usuario": session.get("usuario"),
        "nombre": session.get("nombre"),
        "rol": session.get("rol"),
    })


@app.route("/healthz")
def healthz():
    """Endpoint simple de salud para monitoreo (Render, UptimeRobot, etc)."""
    return jsonify({"status": "ok", "ts": datetime.now().isoformat()})


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
    rows = db.execute("SELECT * FROM inventario WHERE activo=1 ORDER BY nombre ASC").fetchall()
    return jsonify(rows_to_list(rows))


# ------------------------------------------------------------------
# API: INVENTARIO — PANEL ADMINISTRATIVO AUDITADO
#
# Toda modificación de stock físico queda registrada en
# movimientos_inventario con quién, cuándo y por qué. Tres flujos:
#   1) Entrada (+): compra/recepción de proveedor.
#   2) Salida (-): merma, daño, extravío, caducidad, muestra — motivo obligatorio.
#   3) Ajuste (=): corrección auditada de una cantidad incorrecta (con motivo).
# La edición de atributos (nombre, descripción, precio, categoría, imagen)
# es una operación separada que NUNCA toca stock_actual directamente.
# ------------------------------------------------------------------
def registrar_movimiento(db, producto_id, tipo, cantidad, stock_resultante,
                          motivo=None, nota=None, proveedor=None, numero_factura=None, fecha=None):
    db.execute(
        """INSERT INTO movimientos_inventario
           (producto_id, tipo, cantidad, stock_resultante, motivo, nota,
            proveedor, numero_factura, fecha, usuario_id, usuario_nombre)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (producto_id, tipo, cantidad, stock_resultante, motivo, nota,
         proveedor, numero_factura, fecha or datetime.now().strftime("%Y-%m-%d"),
         session.get("user_id"), session.get("nombre") or session.get("usuario")),
    )


@app.route("/api/inventario", methods=["POST"])
@login_required
def crear_producto():
    """Alta de un producto nuevo en el catálogo. El stock inicial (si se
    manda) se registra también como un movimiento de tipo 'entrada' para
    que el kardex arranque completo desde el día uno."""
    data = request.get_json(force=True)
    nombre = (data.get("nombre") or "").strip()
    precio_venta = data.get("precio_venta")
    if not nombre or precio_venta is None:
        return jsonify({"error": "nombre y precio_venta son obligatorios"}), 400

    db = get_db()
    stock_inicial = float(data.get("stock_actual", 0) or 0)
    cur = db.execute(
        """INSERT INTO inventario
           (nombre, sku, descripcion, categoria, imagen_url, stock_actual, stock_minimo,
            precio_venta, costo_unitario, unidad_consumo_por_servicio)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (nombre, data.get("sku"), data.get("descripcion"), data.get("categoria"), data.get("imagen_url"),
         stock_inicial, data.get("stock_minimo", 3), precio_venta,
         data.get("costo_unitario", 0), data.get("unidad_consumo_por_servicio", 0)),
    )
    producto_id = cur.lastrowid
    if stock_inicial > 0:
        registrar_movimiento(db, producto_id, "entrada", stock_inicial, stock_inicial,
                              nota="Alta inicial de producto", proveedor=data.get("proveedor"))
    db.commit()
    producto = db.execute("SELECT * FROM inventario WHERE id=?", (producto_id,)).fetchone()
    return jsonify(row_to_dict(producto)), 201


@app.route("/api/inventario/<int:producto_id>", methods=["PUT"])
@login_required
def editar_producto(producto_id):
    """Edición / Modificación: SOLO atributos (nombre, descripción, precio,
    categoría, imagen, costo, mínimo, consumo por servicio). No toca
    stock_actual — para eso están /entrada, /salida y /ajuste, que sí
    quedan auditados en el kardex."""
    db = get_db()
    producto = db.execute("SELECT * FROM inventario WHERE id=?", (producto_id,)).fetchone()
    if not producto:
        return jsonify({"error": "Producto no encontrado"}), 404

    data = request.get_json(force=True)
    campos_editables = {
        "nombre": data.get("nombre", producto["nombre"]),
        "sku": data.get("sku", producto["sku"]),
        "descripcion": data.get("descripcion", producto["descripcion"]),
        "categoria": data.get("categoria", producto["categoria"]),
        "imagen_url": data.get("imagen_url", producto["imagen_url"]),
        "precio_venta": data.get("precio_venta", producto["precio_venta"]),
        "costo_unitario": data.get("costo_unitario", producto["costo_unitario"]),
        "stock_minimo": data.get("stock_minimo", producto["stock_minimo"]),
        "unidad_consumo_por_servicio": data.get("unidad_consumo_por_servicio", producto["unidad_consumo_por_servicio"]),
        "activo": data.get("activo", producto["activo"]),
    }
    db.execute(
        """UPDATE inventario SET nombre=?, sku=?, descripcion=?, categoria=?, imagen_url=?,
           precio_venta=?, costo_unitario=?, stock_minimo=?, unidad_consumo_por_servicio=?, activo=?
           WHERE id=?""",
        (*campos_editables.values(), producto_id),
    )
    db.commit()
    actualizado = db.execute("SELECT * FROM inventario WHERE id=?", (producto_id,)).fetchone()
    return jsonify(row_to_dict(actualizado))


@app.route("/api/inventario/<int:producto_id>/entrada", methods=["POST"])
@login_required
def entrada_inventario(producto_id):
    """Entradas (+): incremento de stock por compra o recepción de
    proveedor. Captura: cantidad, proveedor / no. de factura, fecha."""
    data = request.get_json(force=True)
    cantidad = data.get("cantidad")
    if not cantidad or float(cantidad) <= 0:
        return jsonify({"error": "cantidad debe ser mayor a 0"}), 400

    db = get_db()
    producto = db.execute("SELECT * FROM inventario WHERE id=?", (producto_id,)).fetchone()
    if not producto:
        return jsonify({"error": "Producto no encontrado"}), 404

    nuevo_stock = producto["stock_actual"] + float(cantidad)
    db.execute("UPDATE inventario SET stock_actual=? WHERE id=?", (nuevo_stock, producto_id))
    registrar_movimiento(
        db, producto_id, "entrada", float(cantidad), nuevo_stock,
        proveedor=data.get("proveedor"), numero_factura=data.get("numero_factura"),
        nota=data.get("nota"), fecha=data.get("fecha"),
    )
    db.commit()
    actualizado = db.execute("SELECT * FROM inventario WHERE id=?", (producto_id,)).fetchone()
    return jsonify(row_to_dict(actualizado)), 201


@app.route("/api/inventario/<int:producto_id>/salida", methods=["POST"])
@login_required
def salida_inventario(producto_id):
    """Bajas / Salidas justificadas (-): merma, producto dañado, extravío,
    caducidad o muestra. El motivo es de llenado OBLIGATORIO (lista cerrada)
    + nota de texto libre opcional."""
    data = request.get_json(force=True)
    cantidad = data.get("cantidad")
    motivo = (data.get("motivo") or "").strip()

    if not cantidad or float(cantidad) <= 0:
        return jsonify({"error": "cantidad debe ser mayor a 0"}), 400
    if motivo not in MOTIVOS_SALIDA_VALIDOS:
        return jsonify({"error": f"motivo obligatorio, debe ser uno de: {', '.join(sorted(MOTIVOS_SALIDA_VALIDOS))}"}), 400

    db = get_db()
    producto = db.execute("SELECT * FROM inventario WHERE id=?", (producto_id,)).fetchone()
    if not producto:
        return jsonify({"error": "Producto no encontrado"}), 404
    if producto["stock_actual"] < float(cantidad):
        return jsonify({"error": f"Stock insuficiente (disponible: {producto['stock_actual']})"}), 409

    nuevo_stock = producto["stock_actual"] - float(cantidad)
    db.execute("UPDATE inventario SET stock_actual=? WHERE id=?", (nuevo_stock, producto_id))
    registrar_movimiento(
        db, producto_id, "salida", -float(cantidad), nuevo_stock,
        motivo=motivo, nota=data.get("nota"), fecha=data.get("fecha"),
    )
    db.commit()
    actualizado = db.execute("SELECT * FROM inventario WHERE id=?", (producto_id,)).fetchone()
    return jsonify(row_to_dict(actualizado)), 201


@app.route("/api/inventario/<int:producto_id>/ajuste", methods=["POST"])
@login_required
def ajustar_inventario(producto_id):
    """Ajuste de Inventario auditado: corrige el stock a una cantidad
    exacta conocida (ej. tras un conteo físico), dejando registro del
    delta aplicado y el motivo — en vez de editar la cifra a ciegas."""
    data = request.get_json(force=True)
    if "cantidad_nueva" not in data:
        return jsonify({"error": "cantidad_nueva es obligatoria"}), 400
    motivo = (data.get("motivo") or "").strip()
    if not motivo:
        return jsonify({"error": "motivo es obligatorio para todo ajuste"}), 400

    db = get_db()
    producto = db.execute("SELECT * FROM inventario WHERE id=?", (producto_id,)).fetchone()
    if not producto:
        return jsonify({"error": "Producto no encontrado"}), 404

    cantidad_nueva = float(data["cantidad_nueva"])
    delta = cantidad_nueva - producto["stock_actual"]
    db.execute("UPDATE inventario SET stock_actual=? WHERE id=?", (cantidad_nueva, producto_id))
    registrar_movimiento(
        db, producto_id, "ajuste", delta, cantidad_nueva,
        motivo=motivo, nota=data.get("nota"), fecha=data.get("fecha"),
    )
    db.commit()
    actualizado = db.execute("SELECT * FROM inventario WHERE id=?", (producto_id,)).fetchone()
    return jsonify(row_to_dict(actualizado)), 201


@app.route("/api/inventario/movimientos", methods=["GET"])
@login_required
def listar_movimientos():
    """Kardex global (o filtrado por producto con ?producto_id=). Es la
    bitácora auditada: quién movió qué, cuándo, cuánto y por qué."""
    db = get_db()
    producto_id = request.args.get("producto_id")
    base = """
        SELECT m.*, i.nombre AS producto_nombre
        FROM movimientos_inventario m
        JOIN inventario i ON i.id = m.producto_id
    """
    if producto_id:
        rows = db.execute(base + " WHERE m.producto_id=? ORDER BY m.creado_en DESC LIMIT 200", (producto_id,)).fetchall()
    else:
        rows = db.execute(base + " ORDER BY m.creado_en DESC LIMIT 200").fetchall()
    return jsonify(rows_to_list(rows))


# ------------------------------------------------------------------
# API: USUARIOS (solo administradores)
# ------------------------------------------------------------------
@app.route("/api/usuarios", methods=["GET"])
@admin_required
def listar_usuarios():
    db = get_db()
    rows = db.execute("SELECT id, usuario, nombre, rol, activo, creado_en FROM usuarios ORDER BY creado_en").fetchall()
    return jsonify(rows_to_list(rows))


@app.route("/api/usuarios", methods=["POST"])
@admin_required
def crear_usuario():
    data = request.get_json(force=True)
    usuario = (data.get("usuario") or "").strip()
    password = data.get("password") or ""
    if not usuario or len(password) < 6:
        return jsonify({"error": "usuario es obligatorio y password debe tener al menos 6 caracteres"}), 400
    rol = data.get("rol") if data.get("rol") in ("admin", "staff") else "staff"

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO usuarios (usuario, password_hash, nombre, rol) VALUES (?,?,?,?)",
            (usuario, generate_password_hash(password), data.get("nombre"), rol),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Ese nombre de usuario ya existe"}), 409

    nuevo = db.execute("SELECT id, usuario, nombre, rol, activo, creado_en FROM usuarios WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(row_to_dict(nuevo)), 201


@app.route("/api/usuarios/<int:usuario_id>/estado", methods=["PATCH"])
@admin_required
def cambiar_estado_usuario(usuario_id):
    """Activa/desactiva una cuenta (mejor que borrarla: conserva el
    historial de quién hizo qué en movimientos_inventario)."""
    data = request.get_json(force=True)
    activo = 1 if data.get("activo") else 0
    if usuario_id == session.get("user_id") and not activo:
        return jsonify({"error": "No puedes desactivar tu propia cuenta."}), 400
    db = get_db()
    db.execute("UPDATE usuarios SET activo=? WHERE id=?", (activo, usuario_id))
    db.commit()
    return jsonify({"ok": True})


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
@login_required
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
@login_required
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
        if it["tipo"] == "producto":
            nuevo_stock_prod = None
            fila_prod = db.execute("SELECT stock_actual FROM inventario WHERE id=?", (it["referencia_id"],)).fetchone()
            if fila_prod:
                nuevo_stock_prod = fila_prod["stock_actual"] - it["cantidad"]
                db.execute("UPDATE inventario SET stock_actual = ? WHERE id=?", (nuevo_stock_prod, it["referencia_id"]))
                registrar_movimiento(db, it["referencia_id"], "venta", -it["cantidad"], nuevo_stock_prod,
                                      nota=f"Venta #{venta_id}")

    # - servicio: descuenta el consumo proporcional de insumos configurado
    #   en inventario.unidad_consumo_por_servicio (ej. cera, aceite, toallas).
    #   Se aplica una sola vez por cada unidad de servicio vendida, sumando
    #   todos los servicios del ticket, para no descontar de más si el
    #   ticket trae varios servicios y varios productos a la vez.
    total_servicios_vendidos = sum(i["cantidad"] for i in items_resueltos if i["tipo"] == "servicio")
    if total_servicios_vendidos > 0:
        insumos = db.execute(
            "SELECT id, stock_actual, unidad_consumo_por_servicio FROM inventario WHERE unidad_consumo_por_servicio > 0"
        ).fetchall()
        for insumo in insumos:
            consumo = insumo["unidad_consumo_por_servicio"] * total_servicios_vendidos
            nuevo_stock = max(0, insumo["stock_actual"] - consumo)
            db.execute("UPDATE inventario SET stock_actual=? WHERE id=?", (nuevo_stock, insumo["id"]))
            registrar_movimiento(db, insumo["id"], "consumo_servicio", -(insumo["stock_actual"] - nuevo_stock), nuevo_stock,
                                  nota=f"Consumo por {total_servicios_vendidos} servicio(s) en venta #{venta_id}")

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
@login_required
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
@login_required
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
# init_db() es idempotente (CREATE TABLE IF NOT EXISTS / INSERT OR IGNORE),
# así que se corre siempre: crea la base de datos si no existe, o la
# actualiza con columnas/tablas nuevas (usuarios, movimientos_inventario)
# si ya existía de una versión anterior del esquema.
init_db()

if __name__ == "__main__":
    # Modo desarrollo local: python app.py
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=True)

# Modo producción (Render/Railway): gunicorn arranca este mismo módulo
# usando la variable `app` de abajo con el worker eventlet, por eso la
# inicialización de la DB y el patch de eventlet están fuera del if.
