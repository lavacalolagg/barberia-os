/* ============================================================
   INVENTORY — Panel administrativo auditado
   Entradas (+) · Salidas justificadas (-) · Ajustes auditados (=)
   Edición de atributos (sin tocar stock) · Kardex · Usuarios (admin)
   ============================================================ */
const Inventory = (() => {
  let productos = [];
  let isStaff = false;
  let isAdmin = false;
  let cargado = false;

  function toast(msg, sfx) {
    if (window.FaceShape) FaceShape.toast(msg, sfx);
  }

  async function verificarAcceso() {
    const data = await fetch("/api/whoami").then((r) => r.json());
    isStaff = !!data.staff;
    isAdmin = data.rol === "admin";
    document.getElementById("inv-locked").style.display = isStaff ? "none" : "block";
    document.getElementById("inv-content").style.display = isStaff ? "block" : "none";
    document.getElementById("inv-usuarios-panel").style.display = isAdmin ? "block" : "none";
    return isStaff;
  }

  async function cargar() {
    const ok = await verificarAcceso();
    if (!ok) return;

    productos = await fetch("/api/inventario").then((r) => r.json());
    ["entrada-producto", "salida-producto", "ajuste-producto"].forEach(llenarSelectProductos);
    renderTabla();
    cargarKardex();
    if (isAdmin) cargarUsuarios();

    const hoy = new Date().toISOString().slice(0, 10);
    const fEntrada = document.getElementById("entrada-fecha");
    if (fEntrada && !fEntrada.value) fEntrada.value = hoy;

    cargado = true;
  }

  function llenarSelectProductos(id) {
    const sel = document.getElementById(id);
    if (!sel) return;
    sel.innerHTML = productos
      .map((p) => `<option value="${p.id}">${p.nombre} (stock: ${p.stock_actual})</option>`)
      .join("");
  }

  function renderTabla() {
    const el = document.getElementById("inv-tabla");
    if (!el) return;
    if (!productos.length) {
      el.innerHTML = `<p class="text-faint">No hay productos todavía. Crea el primero con "+ Nuevo producto".</p>`;
      return;
    }
    el.innerHTML = `
      <div style="overflow-x:auto;">
      <table style="width:100%; border-collapse:collapse; font-size:13.5px;">
        <thead>
          <tr style="text-align:left; color:var(--text-faint); border-bottom:1px solid var(--border-glass);">
            <th style="padding:10px 8px;">Producto</th>
            <th style="padding:10px 8px;">Categoría</th>
            <th style="padding:10px 8px;">Stock</th>
            <th style="padding:10px 8px;">Precio</th>
            <th style="padding:10px 8px;"></th>
          </tr>
        </thead>
        <tbody>
          ${productos.map((p) => `
            <tr style="border-bottom:1px solid var(--border-glass);">
              <td style="padding:10px 8px;"><strong>${p.nombre}</strong><div class="text-faint" style="font-size:11.5px;">${p.sku || ""}</div></td>
              <td style="padding:10px 8px;">${p.categoria || "—"}</td>
              <td style="padding:10px 8px;">
                ${p.stock_actual}
                ${p.stock_actual <= p.stock_minimo ? '<span class="tag tag-magenta" style="margin-left:6px;">Bajo</span>' : ""}
              </td>
              <td style="padding:10px 8px;">$${Number(p.precio_venta).toFixed(2)}</td>
              <td style="padding:10px 8px;"><button class="btn btn-sm" data-editar-producto="${p.id}">Editar</button></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
      </div>
    `;
  }

  async function cargarKardex(productoId) {
    const url = productoId ? `/api/inventario/movimientos?producto_id=${productoId}` : "/api/inventario/movimientos";
    const res = await fetch(url);
    if (res.status === 401) return;
    const movs = await res.json();
    const el = document.getElementById("inv-kardex");
    if (!el) return;
    if (!movs.length) {
      el.innerHTML = `<p class="text-faint">Sin movimientos todavía.</p>`;
      return;
    }
    const tipoTag = {
      entrada: '<span class="tag tag-green">Entrada</span>',
      salida: '<span class="tag tag-magenta">Salida</span>',
      ajuste: '<span class="tag tag-cyan">Ajuste</span>',
      venta: '<span class="tag tag-gold">Venta</span>',
      consumo_servicio: '<span class="tag">Consumo servicio</span>',
    };
    el.innerHTML = `
      <div style="overflow-x:auto;">
      <table style="width:100%; border-collapse:collapse; font-size:13px;">
        <thead>
          <tr style="text-align:left; color:var(--text-faint); border-bottom:1px solid var(--border-glass);">
            <th style="padding:8px;">Fecha</th>
            <th style="padding:8px;">Producto</th>
            <th style="padding:8px;">Tipo</th>
            <th style="padding:8px;">Cantidad</th>
            <th style="padding:8px;">Stock resultante</th>
            <th style="padding:8px;">Motivo / Nota</th>
            <th style="padding:8px;">Usuario</th>
          </tr>
        </thead>
        <tbody>
          ${movs.map((m) => `
            <tr style="border-bottom:1px solid var(--border-glass);">
              <td style="padding:8px;">${m.fecha}</td>
              <td style="padding:8px;">${m.producto_nombre}</td>
              <td style="padding:8px;">${tipoTag[m.tipo] || m.tipo}</td>
              <td style="padding:8px; color:${m.cantidad >= 0 ? "var(--success)" : "var(--danger)"};">${m.cantidad > 0 ? "+" : ""}${m.cantidad}</td>
              <td style="padding:8px;">${m.stock_resultante}</td>
              <td style="padding:8px;">${[m.motivo, m.nota].filter(Boolean).join(" — ") || "—"}${m.proveedor ? `<div class="text-faint" style="font-size:11px;">Prov: ${m.proveedor}${m.numero_factura ? " · Fact: " + m.numero_factura : ""}</div>` : ""}</td>
              <td style="padding:8px;">${m.usuario_nombre || "—"}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
      </div>
    `;
  }

  async function registrarEntrada() {
    const body = {
      cantidad: Number(document.getElementById("entrada-cantidad").value),
      proveedor: document.getElementById("entrada-proveedor").value,
      numero_factura: document.getElementById("entrada-factura").value,
      fecha: document.getElementById("entrada-fecha").value,
    };
    const productoId = document.getElementById("entrada-producto").value;
    if (!body.cantidad || body.cantidad <= 0) { toast("La cantidad debe ser mayor a 0.", "error"); return; }

    const res = await fetch(`/api/inventario/${productoId}/entrada`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (await manejar401(res)) return;
    const data = await res.json();
    if (!res.ok) { toast(data.error, "error"); return; }
    toast(`Entrada registrada. Nuevo stock: ${data.stock_actual}`, "confirm");
    document.getElementById("entrada-cantidad").value = "";
    cargar();
  }

  async function registrarSalida() {
    const body = {
      cantidad: Number(document.getElementById("salida-cantidad").value),
      motivo: document.getElementById("salida-motivo").value,
      nota: document.getElementById("salida-nota").value,
    };
    const productoId = document.getElementById("salida-producto").value;
    if (!body.cantidad || body.cantidad <= 0) { toast("La cantidad debe ser mayor a 0.", "error"); return; }
    if (!body.motivo) { toast("El motivo es obligatorio para registrar una salida.", "error"); return; }

    const res = await fetch(`/api/inventario/${productoId}/salida`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (await manejar401(res)) return;
    const data = await res.json();
    if (!res.ok) { toast(data.error, "error"); return; }
    toast(`Salida registrada. Nuevo stock: ${data.stock_actual}`, "error");
    document.getElementById("salida-cantidad").value = "";
    document.getElementById("salida-nota").value = "";
    cargar();
  }

  async function registrarAjuste() {
    const body = {
      cantidad_nueva: Number(document.getElementById("ajuste-cantidad").value),
      motivo: document.getElementById("ajuste-motivo").value,
    };
    const productoId = document.getElementById("ajuste-producto").value;
    if (body.cantidad_nueva === "" || body.cantidad_nueva < 0 || Number.isNaN(body.cantidad_nueva)) {
      toast("Captura la cantidad real contada.", "error"); return;
    }
    if (!body.motivo.trim()) { toast("El motivo del ajuste es obligatorio.", "error"); return; }

    const res = await fetch(`/api/inventario/${productoId}/ajuste`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (await manejar401(res)) return;
    const data = await res.json();
    if (!res.ok) { toast(data.error, "error"); return; }
    toast(`Ajuste aplicado. Stock corregido a ${data.stock_actual}`, "confirm");
    document.getElementById("ajuste-motivo").value = "";
    cargar();
  }

  function abrirModalEditar(producto) {
    document.getElementById("edit-id").value = producto.id;
    document.getElementById("edit-nombre").value = producto.nombre || "";
    document.getElementById("edit-sku").value = producto.sku || "";
    document.getElementById("edit-categoria").value = producto.categoria || "";
    document.getElementById("edit-precio").value = producto.precio_venta ?? "";
    document.getElementById("edit-costo").value = producto.costo_unitario ?? "";
    document.getElementById("edit-minimo").value = producto.stock_minimo ?? "";
    document.getElementById("edit-consumo").value = producto.unidad_consumo_por_servicio ?? "";
    document.getElementById("edit-imagen").value = producto.imagen_url || "";
    document.getElementById("edit-descripcion").value = producto.descripcion || "";
    document.getElementById("modal-titulo").textContent = `Editar: ${producto.nombre}`;
    document.getElementById("modal-editar-producto").style.display = "block";
    document.getElementById("modal-editar-producto").scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function abrirModalNuevo() {
    ["edit-id", "edit-nombre", "edit-sku", "edit-categoria", "edit-precio", "edit-costo",
      "edit-minimo", "edit-consumo", "edit-imagen", "edit-descripcion"].forEach((id) => (document.getElementById(id).value = ""));
    document.getElementById("modal-titulo").textContent = "Nuevo producto";
    document.getElementById("modal-editar-producto").style.display = "block";
    document.getElementById("modal-editar-producto").scrollIntoView({ behavior: "smooth", block: "center" });
  }

  async function guardarProducto() {
    const id = document.getElementById("edit-id").value;
    const body = {
      nombre: document.getElementById("edit-nombre").value.trim(),
      sku: document.getElementById("edit-sku").value.trim(),
      categoria: document.getElementById("edit-categoria").value.trim(),
      precio_venta: Number(document.getElementById("edit-precio").value),
      costo_unitario: Number(document.getElementById("edit-costo").value || 0),
      stock_minimo: Number(document.getElementById("edit-minimo").value || 0),
      unidad_consumo_por_servicio: Number(document.getElementById("edit-consumo").value || 0),
      imagen_url: document.getElementById("edit-imagen").value.trim(),
      descripcion: document.getElementById("edit-descripcion").value.trim(),
    };
    if (!body.nombre || !body.precio_venta) { toast("Nombre y precio son obligatorios.", "error"); return; }

    const url = id ? `/api/inventario/${id}` : "/api/inventario";
    const method = id ? "PUT" : "POST";
    const res = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (await manejar401(res)) return;
    const data = await res.json();
    if (!res.ok) { toast(data.error, "error"); return; }
    toast(id ? "Producto actualizado." : "Producto creado.", "confirm");
    document.getElementById("modal-editar-producto").style.display = "none";
    cargar();
  }

  async function cargarUsuarios() {
    const res = await fetch("/api/usuarios");
    if (res.status === 403 || res.status === 401) return; // no es admin, no pasa nada
    const usuarios = await res.json();
    const el = document.getElementById("inv-usuarios-tabla");
    el.innerHTML = `
      <div style="overflow-x:auto;">
      <table style="width:100%; border-collapse:collapse; font-size:13.5px;">
        <thead><tr style="text-align:left; color:var(--text-faint);"><th style="padding:8px;">Usuario</th><th style="padding:8px;">Nombre</th><th style="padding:8px;">Rol</th><th style="padding:8px;">Estado</th><th></th></tr></thead>
        <tbody>
          ${usuarios.map((u) => `
            <tr style="border-bottom:1px solid var(--border-glass);">
              <td style="padding:8px;">${u.usuario}</td>
              <td style="padding:8px;">${u.nombre || "—"}</td>
              <td style="padding:8px;"><span class="tag ${u.rol === "admin" ? "tag-gold" : "tag-cyan"}">${u.rol}</span></td>
              <td style="padding:8px;">${u.activo ? '<span class="tag tag-green">Activo</span>' : '<span class="tag tag-magenta">Inactivo</span>'}</td>
              <td style="padding:8px;"><button class="btn btn-sm" data-toggle-usuario="${u.id}" data-activo="${u.activo}">${u.activo ? "Desactivar" : "Activar"}</button></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
      </div>
    `;
  }

  async function crearUsuario() {
    const body = {
      nombre: document.getElementById("nuevo-usuario-nombre").value.trim(),
      usuario: document.getElementById("nuevo-usuario-usuario").value.trim(),
      password: document.getElementById("nuevo-usuario-password").value,
      rol: document.getElementById("nuevo-usuario-rol").value,
    };
    if (!body.usuario || body.password.length < 6) { toast("Usuario y contraseña (mín. 6 caracteres) son obligatorios.", "error"); return; }
    const res = await fetch("/api/usuarios", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await res.json();
    if (!res.ok) { toast(data.error, "error"); return; }
    toast(`Usuario "${data.usuario}" creado.`, "confirm");
    ["nuevo-usuario-nombre", "nuevo-usuario-usuario", "nuevo-usuario-password"].forEach((id) => (document.getElementById(id).value = ""));
    cargarUsuarios();
  }

  async function manejar401(res) {
    if (res.status === 401) {
      window.location.href = "/login?next=/";
      return true;
    }
    return false;
  }

  function initEvents() {
    document.getElementById("btn-entrada")?.addEventListener("click", registrarEntrada);
    document.getElementById("btn-salida")?.addEventListener("click", registrarSalida);
    document.getElementById("btn-ajuste")?.addEventListener("click", registrarAjuste);
    document.getElementById("btn-nuevo-producto")?.addEventListener("click", abrirModalNuevo);
    document.getElementById("btn-guardar-producto")?.addEventListener("click", guardarProducto);
    document.getElementById("btn-cerrar-modal")?.addEventListener("click", () => {
      document.getElementById("modal-editar-producto").style.display = "none";
    });
    document.getElementById("btn-crear-usuario")?.addEventListener("click", crearUsuario);

    document.addEventListener("click", (e) => {
      const editBtn = e.target.closest("[data-editar-producto]");
      if (editBtn) {
        const producto = productos.find((p) => p.id == editBtn.dataset.editarProducto);
        if (producto) abrirModalEditar(producto);
      }
      const toggleBtn = e.target.closest("[data-toggle-usuario]");
      if (toggleBtn) {
        const activo = toggleBtn.dataset.activo === "1" ? false : true;
        fetch(`/api/usuarios/${toggleBtn.dataset.toggleUsuario}/estado`, {
          method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ activo }),
        }).then((r) => r.json()).then((data) => {
          if (data.error) toast(data.error, "error");
          else cargarUsuarios();
        });
      }
    });
  }

  document.addEventListener("DOMContentLoaded", initEvents);
  return { cargar };
})();
