/* ============================================================
   APP.JS — Orquestador principal (navegación SPA, agenda, PWA)
   ============================================================ */
const App = (() => {
  let metodoPagoSeleccionado = "";

  // ---------------- NAVEGACIÓN SPA ----------------
  function initNav() {
    document.querySelectorAll("[data-view]").forEach((el) => {
      el.addEventListener("click", () => switchView(el.dataset.view));
    });
  }

  function switchView(view) {
    document.querySelectorAll(".view-section").forEach((s) => s.classList.remove("active"));
    document.getElementById(`view-${view}`)?.classList.add("active");
    document.querySelectorAll(".nav-icon").forEach((n) => n.classList.toggle("active", n.dataset.view === view));

    if (view === "dashboard") Dashboard.cargar();
    if (view === "pos") POS && renderPosLazy();
  }

  function renderPosLazy() { /* POS ya se autoinicializa en DOMContentLoaded */ }

  // ---------------- FORMULARIO DE AGENDA ----------------
  async function cargarCatalogosAgenda() {
    const [barberos, servicios] = await Promise.all([
      fetch("/api/barberos").then((r) => r.json()),
      fetch("/api/servicios").then((r) => r.json()),
    ]);
    document.getElementById("f-barbero").innerHTML = barberos
      .map((b) => `<option value="${b.id}">${b.nombre} — ${b.especialidad}</option>`).join("");
    document.getElementById("f-servicio").innerHTML = servicios
      .map((s) => `<option value="${s.id}">${s.nombre} · $${s.precio} · ${s.duracion_min} min</option>`).join("");
  }

  function initPagoButtons() {
    document.querySelectorAll("[data-pago]").forEach((btn) => {
      btn.addEventListener("click", () => {
        metodoPagoSeleccionado = btn.dataset.pago;
        document.querySelectorAll("[data-pago]").forEach((b) => b.classList.remove("btn-gold"));
        btn.classList.add("btn-gold");
      });
    });
  }

  async function crearOReutilizarCliente() {
    const nombre = document.getElementById("f-nombre").value.trim();
    const telefono = document.getElementById("f-telefono").value.trim();
    if (!nombre || !telefono) throw new Error("Nombre y teléfono son obligatorios");

    // buscamos si ya existe por teléfono
    const existentes = await fetch(`/api/clientes?q=${encodeURIComponent(telefono)}`).then((r) => r.json());
    const match = existentes.find((c) => c.telefono === telefono);
    if (match) return match.id;

    const res = await fetch("/api/clientes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nombre, telefono }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    return data.id;
  }

  async function agendar() {
    const btn = document.getElementById("btn-agendar");
    btn.disabled = true;
    const original = btn.textContent;
    btn.textContent = "Agendando…";

    try {
      const clienteId = await crearOReutilizarCliente();
      const barberoId = document.getElementById("f-barbero").value;
      const servicioId = document.getElementById("f-servicio").value;
      const fecha = document.getElementById("f-fecha").value;
      if (!fecha) throw new Error("Selecciona fecha y hora");

      const body = {
        cliente_id: clienteId,
        barbero_id: Number(barberoId),
        servicio_id: Number(servicioId),
        fecha_hora: fecha,
      };
      if (metodoPagoSeleccionado) {
        body.metodo_pago_anticipo = metodoPagoSeleccionado;
        body.pago_anticipo = 100; // anticipo fijo de ejemplo; ajustable a % del servicio
      }

      const res = await fetch("/api/citas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "No se pudo agendar");

      SFX.play("confirm");
      if (data.qr_data_url) {
        document.getElementById("qr-panel").style.display = "block";
        document.getElementById("qr-image").src = data.qr_data_url;
        document.getElementById("qr-ref").textContent = `Referencia: ${data.qr_referencia}`;
      } else {
        FaceShape.toast("Cita agendada correctamente.", "confirm");
      }
    } catch (err) {
      SFX.play("error");
      FaceShape.toast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  }

  // ---------------- PWA: SERVICE WORKER ----------------
  function registerServiceWorker() {
    if ("serviceWorker" in navigator) {
      window.addEventListener("load", () => {
        navigator.serviceWorker.register("/service-worker.js").catch((err) => console.warn("SW error:", err));
      });
    }
  }

  function init() {
    initNav();
    initPagoButtons();
    cargarCatalogosAgenda();
    document.getElementById("btn-agendar")?.addEventListener("click", agendar);
    registerServiceWorker();
  }

  document.addEventListener("DOMContentLoaded", init);
  return { switchView };
})();
