/* ============================================================
   POS — Punto de venta en una sola pantalla
   ============================================================ */
const POS = (() => {
  let servicios = [];
  let productos = [];
  let barberos = [];
  let carrito = []; // {tipo, referencia_id, nombre, precio, cantidad}

  async function cargarCatalogos() {
    [servicios, productos, barberos] = await Promise.all([
      fetch("/api/servicios").then((r) => r.json()),
      fetch("/api/inventario").then((r) => r.json()),
      fetch("/api/barberos").then((r) => r.json()),
    ]);
    pintarServicios();
    pintarProductos();
    pintarBarberos();
  }

  async function cargarClientes() {
    const clientes = await fetch("/api/clientes").then((r) => r.json());
    const sel = document.getElementById("pos-cliente");
    clientes.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = `${c.nombre} · ${c.puntos_lealtad} pts`;
      sel.appendChild(opt);
    });
  }

  function pintarServicios() {
    const el = document.getElementById("pos-servicios");
    el.innerHTML = servicios
      .map((s) => `
        <div class="item-pick" data-tipo="servicio" data-id="${s.id}" data-nombre="${s.nombre}" data-precio="${s.precio}">
          <span>${s.nombre}</span>
          <strong>$${s.precio.toFixed(2)}</strong>
        </div>`)
      .join("");
  }

  function pintarProductos() {
    const el = document.getElementById("pos-productos");
    el.innerHTML = productos
      .map((p) => `
        <div class="item-pick" data-tipo="producto" data-id="${p.id}" data-nombre="${p.nombre}" data-precio="${p.precio_venta}">
          <span>${p.nombre} <span class="text-faint">(${p.stock_actual} disp.)</span></span>
          <strong>$${p.precio_venta.toFixed(2)}</strong>
        </div>`)
      .join("");
  }

  function pintarBarberos() {
    const sel = document.getElementById("pos-barbero");
    sel.innerHTML = barberos.map((b) => `<option value="${b.id}">${b.nombre} (${b.porcentaje_comision}% com.)</option>`).join("");
  }

  function agregarAlCarrito(el) {
    const { tipo, id, nombre, precio } = el.dataset;
    const existente = carrito.find((c) => c.tipo === tipo && c.referencia_id == id);
    if (existente) existente.cantidad += 1;
    else carrito.push({ tipo, referencia_id: Number(id), nombre, precio: Number(precio), cantidad: 1 });
    renderCarrito();
    SFX.play("click");
  }

  function renderCarrito() {
    const el = document.getElementById("cart-lines");
    if (!carrito.length) {
      el.innerHTML = `<p class="text-faint">Selecciona servicios o productos para armar el ticket.</p>`;
    } else {
      el.innerHTML = carrito
        .map((c, i) => `
          <div class="cart-line">
            <span>${c.cantidad}× ${c.nombre}</span>
            <span class="flex gap-sm center">
              $${(c.precio * c.cantidad).toFixed(2)}
              <button class="btn btn-sm btn-ghost" onclick="POS.quitar(${i})">✕</button>
            </span>
          </div>`)
        .join("");
    }
    const total = carrito.reduce((s, c) => s + c.precio * c.cantidad, 0);
    document.getElementById("pos-total").textContent = `$${total.toFixed(2)}`;

    const barberoSel = document.getElementById("pos-barbero");
    const barbero = barberos.find((b) => b.id == barberoSel.value);
    if (barbero) {
      const comision = total * (barbero.porcentaje_comision / 100);
      document.getElementById("pos-comision").textContent =
        `Comisión de ${barbero.nombre}: $${comision.toFixed(2)} (${barbero.porcentaje_comision}%)`;
    }
  }

  function quitar(i) {
    carrito.splice(i, 1);
    renderCarrito();
  }

  async function cobrar() {
    if (!carrito.length) {
      FaceShape.toast("Agrega al menos un servicio o producto.", "error");
      return;
    }
    const body = {
      cliente_id: document.getElementById("pos-cliente").value || null,
      barbero_id: Number(document.getElementById("pos-barbero").value),
      items: carrito.map((c) => ({ tipo: c.tipo, referencia_id: c.referencia_id, cantidad: c.cantidad })),
      metodo_pago: document.getElementById("pos-metodo").value,
    };
    const btn = document.getElementById("btn-cobrar");
    btn.disabled = true;
    btn.textContent = "Procesando…";

    try {
      const res = await fetch("/api/pos/venta", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.status === 401) {
        window.location.href = "/login?next=/";
        return;
      }
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Error al cobrar");

      SFX.play("cash");
      FaceShape.toast(
        `Venta registrada · Comisión $${data.comision_barbero.toFixed(2)} · +${data.puntos_otorgados} pts`,
        "cash"
      );
      carrito = [];
      renderCarrito();
      cargarCatalogos(); // refresca stock
    } catch (err) {
      SFX.play("error");
      FaceShape.toast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Cobrar";
    }
  }

  function init() {
    cargarCatalogos();
    cargarClientes();
    document.addEventListener("click", (e) => {
      const pick = e.target.closest(".item-pick");
      if (pick) agregarAlCarrito(pick);
    });
    document.getElementById("pos-barbero")?.addEventListener("change", renderCarrito);
    document.getElementById("btn-cobrar")?.addEventListener("click", cobrar);
  }

  document.addEventListener("DOMContentLoaded", init);
  return { quitar };
})();
