# NOIR & GOLD — Barbershop OS 3.0

Sistema operativo completo para barbería de alta gama: agenda, sala de espera
en tiempo real, punto de venta (POS), analítica y recomendador de estilo.

## Stack
- **Backend:** Python + Flask + Flask-SocketIO (WebSockets)
- **DB:** SQLite3 (archivo único, cero configuración)
- **Frontend:** HTML5 + CSS3 (Glassmorphism) + Vanilla JS — sin frameworks pesados
- **Visuales:** Three.js (visor 3D), Chart.js (dashboard), Web Audio API + Vibration API (micro-interacciones)
- **PWA:** manifest.json + service-worker.js (instalable, con caché offline)

## Instalación

```bash
cd barberia
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py
```

La base de datos SQLite se crea automáticamente en `database/barberia.db`
la primera vez que se ejecuta `app.py` (semillas de 3 barberos, 5 servicios
y 4 productos de inventario ya incluidas).

### Acceso de staff (POS / Dashboard / Inventario)

El área de reservaciones es pública (cualquier cliente puede agendar), pero
cobrar en el POS, ver la analítica, mover la sala de espera y administrar
el inventario requiere iniciar sesión en `/login` con **usuario y
contraseña reales** (no una sola clave compartida).

La primera vez que arranca, el sistema crea automáticamente una cuenta
administradora con las credenciales de las variables de entorno
`ADMIN_USER` / `ADMIN_PASSWORD` (por defecto en desarrollo:
usuario `admin`, contraseña `barberia123`). **Cambia esas variables en
producción.** Desde el panel de Inventario, un usuario con rol `admin`
puede crear más cuentas de staff (rol `staff`, sin acceso a gestión de
usuarios) o de administrador.

Abre `http://localhost:5000` en el navegador. Para probar la PWA en un
celular real, sirve la app por HTTPS (ej. con `ngrok` o un dominio con
certificado) — los service workers requieren contexto seguro.

## Estructura del proyecto

```
barberia/
├── app.py                     # Backend Flask + SocketIO + todas las rutas API
├── requirements.txt
├── database/
│   └── schema.sql              # Esquema relacional + datos semilla
├── templates/
│   └── index.html              # SPA shell (todas las vistas viven aquí)
└── static/
    ├── manifest.json           # PWA manifest
    ├── css/style.css           # Design system Cyber-Luxury
    └── js/
        ├── service-worker.js   # Caché offline
        ├── audio.js            # Sonidos + haptics + glow reactivo al cursor
        ├── realtime.js         # Cliente WebSocket (sala de espera en vivo)
        ├── viewer3d.js         # Visor 3D con Three.js
        ├── faceshape.js        # Recomendador de corte por forma de rostro
        ├── pos.js               # Punto de venta
        ├── dashboard.js         # Gráficos con Chart.js
        └── app.js                # Navegación SPA + formulario de citas
```

## Endpoints principales

| Método | Ruta                          | Descripción |
|--------|-------------------------------|-------------|
| GET    | `/api/clientes?q=`            | Buscar/listar clientes |
| POST   | `/api/clientes`                | Crear cliente |
| GET    | `/api/barberos` `/api/servicios` `/api/inventario` | Catálogos |
| GET    | `/api/citas?fecha=YYYY-MM-DD`  | Listar citas |
| POST   | `/api/citas`                    | Crear cita (genera QR si hay anticipo) |
| PATCH  | `/api/citas/<id>/estado`        | Cambiar estado (dispara evento WebSocket) |
| GET    | `/api/sala-espera`              | Snapshot HTTP de la cola actual |
| POST   | `/api/pagos/qr`                 | Generar QR de pago simulado (MP/SPEI) |
| POST   | `/api/pos/venta`                | Registrar venta: stock, comisión, puntos |
| GET    | `/api/analytics/resumen`        | Datos agregados para el dashboard |
| GET/POST | `/webhook/whatsapp`           | Verificación + procesamiento de mensajes |
| POST   | `/api/recordatorios/ejecutar`   | Dispara recordatorios de citas próximas (requiere sesión staff) |
| GET/POST | `/login` / `GET /logout`       | Inicio/cierre de sesión (usuario + contraseña) |
| GET    | `/api/whoami`                   | El frontend consulta esto para saber si el visitante es staff/admin |
| GET    | `/healthz`                      | Health check para monitoreo (Render, UptimeRobot) |
| POST   | `/api/inventario`                | Alta de producto nuevo (requiere sesión staff) |
| PUT    | `/api/inventario/<id>`           | Edición de atributos — nombre, descripción, precio, categoría, imagen. **Nunca toca stock.** |
| POST   | `/api/inventario/<id>/entrada`   | Entrada (+): compra/recepción — captura cantidad, proveedor, no. factura, fecha |
| POST   | `/api/inventario/<id>/salida`    | Salida (-): merma/daño/extravío/caducidad/muestra — motivo **obligatorio** |
| POST   | `/api/inventario/<id>/ajuste`    | Ajuste auditado (=): corrige a una cantidad exacta conocida, con motivo |
| GET    | `/api/inventario/movimientos`    | Kardex — bitácora de todos los movimientos (filtrable por `?producto_id=`) |
| GET/POST | `/api/usuarios`                | Listar / crear cuentas de staff (solo rol `admin`) |
| PATCH  | `/api/usuarios/<id>/estado`      | Activar/desactivar una cuenta (solo rol `admin`) |

🔒 Requieren sesión de staff (401 si no hay login): `POST /api/pos/venta`,
`GET /api/analytics/resumen`, `PATCH /api/citas/<id>/estado`,
`POST /api/recordatorios/ejecutar`, todo `/api/inventario/*` que no sea
el `GET /api/inventario` público, y todo `/api/usuarios/*`.
🔒🔒 Requieren además rol `admin` (403 si eres staff normal):
`GET/POST /api/usuarios`, `PATCH /api/usuarios/<id>/estado`.
El resto de la API es pública porque la alimenta la página de
reservaciones que usan los clientes.

Evento WebSocket: `sala_espera_update` — se emite cada vez que cambia una cita.

## Notas de producción (siguiente iteración)
- **Autenticación:** ya implementada como contraseña única de staff
  (`ADMIN_PASSWORD`). El siguiente paso natural es una tabla `usuarios`
  con cuentas individuales por barbero y roles (dueño vs barbero), para
  saber quién cobró qué sin tener que seleccionarlo manualmente en el POS.
- **Pagos reales:** sustituir `generar_qr_base64` y `/api/pagos/qr` por el SDK
  oficial de Mercado Pago (Checkout Pro / QR dinámico) y validación de webhooks
  de confirmación de pago antes de marcar la cita como `confirmada`.
- **WhatsApp real:** reemplazar `enviar_whatsapp_simulado` por la API oficial
  de WhatsApp Cloud (Meta) o Twilio, y programar `enviar_recordatorios_pendientes`
  con un scheduler (APScheduler / cron) en lugar de disparo manual.
- **Autenticación:** agregar login para dueño/barberos antes de exponer
  `/api/pos/venta` y el dashboard fuera de una red controlada.
- **Modelo 3D real:** el visor usa geometría procedural; para un modelo real,
  cargar `.glb` con `THREE.GLTFLoader` en `viewer3d.js`.
- **Recomendador de rostro:** la heurística de Canvas es una demo funcional,
  no reconocimiento facial real; para producción, integrar un modelo ligero
  (ej. TensorFlow.js con un modelo de landmarks faciales).
- **Concurrencia:** para producción usar `eventlet`/`gunicorn` con workers,
  y mover SQLite a modo WAL o migrar a PostgreSQL si el volumen crece.
