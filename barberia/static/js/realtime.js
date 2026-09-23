/* ============================================================
   REALTIME — Sala de espera en vivo vía Socket.IO
   ============================================================ */
const Realtime = (() => {
  const socket = io({ transports: ["websocket", "polling"] });
  const queueList = document.getElementById("queue-list");
  const wsStatus = document.getElementById("ws-status");
  let isStaff = false;
  let ultimaCola = [];

  // Próximo estado lógico en el flujo de atención (para el botón de "avanzar")
  const SIGUIENTE_ESTADO = {
    confirmada: "en_espera",
    en_espera: "en_proceso",
    en_proceso: "completada",
  };
  const ACCION_LABEL = {
    confirmada: "Poner en espera",
    en_espera: "Llamar / Iniciar",
    en_proceso: "Marcar completada",
  };

  fetch("/api/whoami")
    .then((r) => r.json())
    .then((data) => {
      isStaff = !!data.staff;
      renderQueue(ultimaCola); // re-render por si ya había datos, ahora con controles
    })
    .catch(() => {});

  socket.on("connect", () => {
    if (wsStatus) wsStatus.textContent = "Conectado en vivo";
    socket.emit("solicitar_actualizacion");
  });

  socket.on("disconnect", () => {
    if (wsStatus) wsStatus.textContent = "Reconectando…";
  });

  socket.on("sala_espera_update", ({ cola }) => renderQueue(cola || []));

  function estadoLabel(estado) {
    return {
      confirmada: '<span class="tag tag-cyan">Confirmada</span>',
      en_espera: '<span class="tag tag-gold">En espera</span>',
      en_proceso: '<span class="tag tag-green">En proceso</span>',
    }[estado] || `<span class="tag">${estado}</span>`;
  }

  function renderQueue(cola) {
    ultimaCola = cola;
    if (!queueList) return;
    if (!cola.length) {
      queueList.innerHTML = `<div class="pad-lg text-dim">No hay clientes en la fila en este momento.</div>`;
      return;
    }
    queueList.innerHTML = cola
      .map((c, i) => `
        <div class="queue-row ${i === 0 && c.estado === "en_proceso" ? "now-serving" : ""}">
          <div class="queue-num">${i + 1}</div>
          <div>
            <strong>${c.cliente_nombre}</strong>
            <div class="text-faint" style="font-size:12.5px;">${c.servicio_nombre} · con ${c.barbero_nombre}</div>
          </div>
          <div class="text-dim" style="font-size:13px;">~${c.tiempo_estimado_min || c.duracion_min} min</div>
          <div class="flex gap-sm center">
            ${estadoLabel(c.estado)}
            ${isStaff && SIGUIENTE_ESTADO[c.estado] ? `
              <button class="btn btn-sm btn-gold" data-avanzar-cita="${c.id}" data-siguiente="${SIGUIENTE_ESTADO[c.estado]}">
                ${ACCION_LABEL[c.estado]}
              </button>` : ""}
          </div>
        </div>
      `)
      .join("");
  }

  // Delegación: clic en cualquier botón "avanzar" de la fila
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-avanzar-cita]");
    if (!btn) return;
    const citaId = btn.dataset.avanzarCita;
    const siguiente = btn.dataset.siguiente;
    btn.disabled = true;
    try {
      const res = await fetch(`/api/citas/${citaId}/estado`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ estado: siguiente }),
      });
      if (res.status === 401) {
        window.location.href = "/login?next=/";
        return;
      }
      if (!res.ok) throw new Error("No se pudo actualizar la cita");
      SFX.play("confirm");
    } catch (err) {
      SFX.play("error");
      btn.disabled = false;
    }
  });

  // Refresco periódico de respaldo (fallback si el socket se cae)
  setInterval(() => socket.connected && socket.emit("solicitar_actualizacion"), 20000);

  return { socket, renderQueue };
})();
