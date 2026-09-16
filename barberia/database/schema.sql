-- ============================================================
-- BARBERSHOP OS 3.0 — ESQUEMA RELACIONAL SQLITE3
-- ============================================================
PRAGMA foreign_keys = ON;

-- ---------- BARBEROS ----------
CREATE TABLE IF NOT EXISTS barberos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT NOT NULL,
    especialidad    TEXT,                       -- ej. "Fade + Barba"
    porcentaje_comision REAL NOT NULL DEFAULT 40.0,  -- % que se lleva el barbero
    foto_url        TEXT,
    activo          INTEGER NOT NULL DEFAULT 1,  -- 1=disponible hoy, 0=no
    color_agenda    TEXT DEFAULT '#d4af37',
    creado_en       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- CLIENTES ----------
CREATE TABLE IF NOT EXISTS clientes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT NOT NULL,
    telefono        TEXT UNIQUE NOT NULL,        -- clave para WhatsApp webhook
    email           TEXT,
    tipo_rostro     TEXT,                        -- ovalado, redondo, cuadrado, etc (IA recomendador)
    puntos_lealtad  INTEGER NOT NULL DEFAULT 0,
    notas           TEXT,
    creado_en       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- SERVICIOS (catálogo) ----------
CREATE TABLE IF NOT EXISTS servicios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT NOT NULL,               -- "Corte Fade", "Barba Ritual"
    duracion_min    INTEGER NOT NULL DEFAULT 30,
    precio          REAL NOT NULL,
    puntos_otorga   INTEGER NOT NULL DEFAULT 10,
    activo          INTEGER NOT NULL DEFAULT 1
);

-- ---------- INVENTARIO ----------
CREATE TABLE IF NOT EXISTS inventario (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT NOT NULL,               -- "Cera Mate", "Aceite Barba"
    sku             TEXT UNIQUE,
    stock_actual    INTEGER NOT NULL DEFAULT 0,
    stock_minimo    INTEGER NOT NULL DEFAULT 3,
    precio_venta    REAL NOT NULL,
    costo_unitario  REAL NOT NULL DEFAULT 0,
    unidad_consumo_por_servicio REAL DEFAULT 0    -- cuánto se consume al aplicar un servicio (ej. 0.1 = 10% del frasco)
);

-- ---------- CITAS / SALA DE ESPERA ----------
CREATE TABLE IF NOT EXISTS citas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id      INTEGER NOT NULL REFERENCES clientes(id),
    barbero_id      INTEGER NOT NULL REFERENCES barberos(id),
    servicio_id     INTEGER NOT NULL REFERENCES servicios(id),
    fecha_hora      TEXT NOT NULL,                -- ISO datetime
    estado          TEXT NOT NULL DEFAULT 'pendiente',
                    -- pendiente | confirmada | en_espera | en_proceso | completada | cancelada | no_show
    posicion_cola   INTEGER,                      -- orden en sala de espera (tiempo real)
    tiempo_estimado_min INTEGER,
    pago_anticipo   REAL DEFAULT 0,
    metodo_pago_anticipo TEXT,                    -- 'mercado_pago' | 'spei' | null
    qr_referencia   TEXT,                         -- id de la referencia de pago/QR
    recordatorio_enviado INTEGER NOT NULL DEFAULT 0,
    creado_en       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- VENTAS (POS) ----------
CREATE TABLE IF NOT EXISTS ventas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id      INTEGER REFERENCES clientes(id),
    barbero_id      INTEGER NOT NULL REFERENCES barberos(id),
    cita_id         INTEGER REFERENCES citas(id),
    subtotal        REAL NOT NULL DEFAULT 0,
    descuento       REAL NOT NULL DEFAULT 0,
    total           REAL NOT NULL DEFAULT 0,
    comision_barbero REAL NOT NULL DEFAULT 0,
    metodo_pago     TEXT NOT NULL DEFAULT 'efectivo', -- efectivo | tarjeta | mercado_pago | spei
    puntos_otorgados INTEGER NOT NULL DEFAULT 0,
    creado_en       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------- VENTA_ITEMS (detalle: servicios y/o productos) ----------
CREATE TABLE IF NOT EXISTS venta_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id        INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
    tipo            TEXT NOT NULL,               -- 'servicio' | 'producto'
    referencia_id   INTEGER NOT NULL,            -- servicios.id o inventario.id
    nombre          TEXT NOT NULL,               -- snapshot del nombre al momento de vender
    cantidad        REAL NOT NULL DEFAULT 1,
    precio_unitario REAL NOT NULL,
    total_linea     REAL NOT NULL
);

-- ---------- ÍNDICES ----------
CREATE INDEX IF NOT EXISTS idx_citas_estado ON citas(estado);
CREATE INDEX IF NOT EXISTS idx_citas_fecha ON citas(fecha_hora);
CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(creado_en);
CREATE INDEX IF NOT EXISTS idx_clientes_telefono ON clientes(telefono);

-- ---------- SEED DATA MÍNIMA ----------
INSERT OR IGNORE INTO barberos (id, nombre, especialidad, porcentaje_comision, color_agenda) VALUES
 (1, 'Damián Reyes', 'Fade & Diseño', 45, '#d4af37'),
 (2, 'Kenji Ortiz',  'Barba & Navaja', 40, '#00e5ff'),
 (3, 'Bruno Salcedo','Clásico & Pompadour', 42, '#ff2e63');

INSERT OR IGNORE INTO servicios (id, nombre, duracion_min, precio, puntos_otorga) VALUES
 (1, 'Corte Clásico', 30, 250, 10),
 (2, 'Fade Premium', 45, 350, 15),
 (3, 'Barba Ritual (toalla caliente)', 25, 220, 10),
 (4, 'Corte + Barba Completo', 60, 480, 25),
 (5, 'Diseño / Línea de Cejas', 15, 100, 5);

INSERT OR IGNORE INTO inventario (id, nombre, sku, stock_actual, stock_minimo, precio_venta, costo_unitario, unidad_consumo_por_servicio) VALUES
 (1, 'Cera Mate Premium', 'CER-001', 12, 3, 280, 120, 0.08),
 (2, 'Aceite para Barba', 'ACE-002', 8, 3, 220, 90, 0.10),
 (3, 'Loción Post-Afeitado', 'LOC-003', 5, 2, 180, 70, 0.05),
 (4, 'Navajas Desechables (caja)', 'NAV-004', 20, 5, 0, 15, 1);
