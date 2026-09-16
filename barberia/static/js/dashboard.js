/* ============================================================
   DASHBOARD — Analítica con Chart.js
   ============================================================ */
const Dashboard = (() => {
  let charts = {};
  const GOLD = "#d4af37", CYAN = "#37e6e0", MAGENTA = "#ff3d7f", DIM = "#9b96a8";

  function baseOptions(extra = {}) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: DIM, font: { family: "Manrope" } } } },
      scales: {
        x: { ticks: { color: DIM }, grid: { color: "rgba(255,255,255,0.05)" } },
        y: { ticks: { color: DIM }, grid: { color: "rgba(255,255,255,0.05)" } },
      },
      ...extra,
    };
  }

  function destroyIfExists(key) {
    if (charts[key]) charts[key].destroy();
  }

  async function cargar() {
    const res = await fetch("/api/analytics/resumen");
    const data = await res.json();

    document.getElementById("kpi-ingresos-hoy").textContent = `$${(data.ingresos_hoy || 0).toFixed(2)}`;
    document.getElementById("kpi-servicio-top").textContent = data.servicios_top[0]?.nombre || "—";
    document.getElementById("kpi-stock-bajo").textContent = data.inventario_bajo.length;

    // citas activas (fallback vía sala de espera)
    fetch("/api/sala-espera").then((r) => r.json()).then((cola) => {
      document.getElementById("kpi-citas-activas").textContent = cola.length;
    });

    renderIngresos(data.ingresos_7dias);
    renderHorasPico(data.horas_pico);
    renderServicios(data.servicios_top);
    renderBarberos(data.rendimiento_barberos);
  }

  function renderIngresos(rows) {
    destroyIfExists("ingresos");
    const ctx = document.getElementById("chart-ingresos");
    charts.ingresos = new Chart(ctx, {
      type: "line",
      data: {
        labels: rows.map((r) => r.dia),
        datasets: [{
          label: "Ingresos ($)",
          data: rows.map((r) => r.total),
          borderColor: GOLD,
          backgroundColor: "rgba(212,175,55,0.15)",
          fill: true,
          tension: 0.35,
          pointRadius: 3,
        }],
      },
      options: baseOptions(),
    });
  }

  function renderHorasPico(rows) {
    destroyIfExists("horas");
    const ctx = document.getElementById("chart-horaspico");
    charts.horas = new Chart(ctx, {
      type: "bar",
      data: {
        labels: rows.map((r) => `${r.hora}h`),
        datasets: [{ label: "Ventas", data: rows.map((r) => r.n), backgroundColor: CYAN, borderRadius: 6 }],
      },
      options: baseOptions({ plugins: { legend: { display: false } } }),
    });
  }

  function renderServicios(rows) {
    destroyIfExists("servicios");
    const ctx = document.getElementById("chart-servicios");
    charts.servicios = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: rows.map((r) => r.nombre),
        datasets: [{
          data: rows.map((r) => r.veces),
          backgroundColor: [GOLD, CYAN, MAGENTA, "#8b7bd8", "#4ade80", "#f59e0b"],
          borderWidth: 0,
        }],
      },
      options: baseOptions({ scales: {} }),
    });
  }

  function renderBarberos(rows) {
    destroyIfExists("barberos");
    const ctx = document.getElementById("chart-barberos");
    charts.barberos = new Chart(ctx, {
      type: "bar",
      data: {
        labels: rows.map((r) => r.nombre),
        datasets: [
          { label: "Ingresos", data: rows.map((r) => r.ingresos), backgroundColor: GOLD, borderRadius: 6 },
          { label: "Comisiones", data: rows.map((r) => r.comisiones), backgroundColor: MAGENTA, borderRadius: 6 },
        ],
      },
      options: baseOptions({ indexAxis: "y" }),
    });
  }

  return { cargar };
})();
