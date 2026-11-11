/* ============================================================
   RECOMENDADOR DE CORTE — "IA" de estilo (heurística en cliente)
   Selección manual de forma de rostro + análisis simple de proporciones
   a partir de una foto subida (procesado 100% en el navegador, sin servidor).
   ============================================================ */
const FaceShape = (() => {
  const CATALOGO = {
    ovalado: {
      label: "Ovalado",
      desc: "El más versátil: casi cualquier corte funciona.",
      cortes: ["Fade Premium con textura arriba", "Pompadour clásico", "Buzz cut moderno"],
    },
    redondo: {
      label: "Redondo",
      desc: "Busca dar altura y ángulos para alargar visualmente el rostro.",
      cortes: ["Fade alto con volumen arriba", "Undercut con flequillo texturizado", "Corte militar con línea marcada"],
    },
    cuadrado: {
      label: "Cuadrado",
      desc: "Suaviza la mandíbula marcada con texturas y curvas suaves.",
      cortes: ["Crop texturizado", "Side part clásico", "Barba corta que redondee la mandíbula"],
    },
    alargado: {
      label: "Alargado",
      desc: "Evita volumen excesivo arriba; suma anchura visual a los lados.",
      cortes: ["Corte medio con flequillo recto", "Caesar cut", "Barba plena para acortar el rostro"],
    },
    corazon: {
      label: "Corazón",
      desc: "Frente ancha y mentón fino: equilibra con volumen bajo y barba.",
      cortes: ["Textured crop con flequillo lateral", "Corte con barba para dar peso al mentón"],
    },
    diamante: {
      label: "Diamante",
      desc: "Pómulos marcados: suaviza con flequillo y evita rapados extremos en sienes.",
      cortes: ["Corte con flequillo suave", "Fade bajo con textura media"],
    },
  };

  const iconPath = {
    ovalado: "M23 8 Q23 40 23 52 Q23 12 23 8 Z", // placeholder, se sobreescriben abajo con SVGs reales
  };

  function svgFor(shape) {
    // Iconos SVG simples y distintos por forma (silueta minimal)
    const shapes = {
      ovalado:  `<ellipse cx="23" cy="30" rx="16" ry="22"/>`,
      redondo:  `<circle cx="23" cy="30" r="19"/>`,
      cuadrado: `<rect x="6" y="10" width="34" height="40" rx="8"/>`,
      alargado: `<ellipse cx="23" cy="30" rx="13" ry="26"/>`,
      corazon:  `<path d="M23 8 C10 8 4 20 8 30 C12 42 23 52 23 52 C23 52 34 42 38 30 C42 20 36 8 23 8 Z"/>`,
      diamante: `<path d="M23 6 L38 30 L23 54 L8 30 Z"/>`,
    };
    return `<svg class="face-shape-icon" viewBox="0 0 46 60" fill="none" stroke="var(--neon-cyan)" stroke-width="2">${shapes[shape]}</svg>`;
  }

  function renderOptions() {
    const container = document.getElementById("face-options");
    if (!container) return;
    container.innerHTML = Object.entries(CATALOGO)
      .map(([key, v]) => `
        <div class="face-option" data-shape="${key}">
          ${svgFor(key)}
          <div><strong>${v.label}</strong></div>
        </div>
      `)
      .join("");

    container.addEventListener("click", (e) => {
      const opt = e.target.closest(".face-option");
      if (!opt) return;
      container.querySelectorAll(".face-option").forEach((el) => el.classList.remove("selected"));
      opt.classList.add("selected");
      showResult(opt.dataset.shape);
      SFX.play("confirm");
    });
  }

  function showResult(shape) {
    const data = CATALOGO[shape];
    const box = document.getElementById("face-result");
    box.style.display = "block";
    box.innerHTML = `
      <div class="flex between center" style="margin-bottom:12px;">
        <h3>Rostro ${data.label}</h3>
        <span class="tag tag-cyan">Recomendación IA</span>
      </div>
      <p>${data.desc}</p>
      <div class="grid grid-3 mt-lg">
        ${data.cortes.map((c) => `<div class="glass-panel pad-md">${c}</div>`).join("")}
      </div>
      <button class="btn btn-gold mt-lg" onclick="document.querySelector('[data-view=agenda]').click()">
        Agendar este estilo
      </button>
    `;
  }

  /* ---- Análisis heurístico simple de una foto subida (Canvas) ----
     No es reconocimiento facial real: mide el bounding box de los tonos
     de piel detectados para estimar una proporción ancho/alto aproximada
     y sugerir la forma más cercana. Sirve como demo/simulador en cliente. */
  function analizarImagen(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        const w = (canvas.width = 220);
        const h = (canvas.height = Math.round((img.height / img.width) * 220));
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, w, h);
        const { data } = ctx.getImageData(0, 0, w, h);

        let minX = w, maxX = 0, minY = h, maxY = 0, found = false;
        for (let y = 0; y < h; y += 2) {
          for (let x = 0; x < w; x += 2) {
            const i = (y * w + x) * 4;
            const r = data[i], g = data[i + 1], b = data[i + 2];
            if (isSkinTone(r, g, b)) {
              found = true;
              if (x < minX) minX = x; if (x > maxX) maxX = x;
              if (y < minY) minY = y; if (y > maxY) maxY = y;
            }
          }
        }

        if (!found) {
          toast("No pudimos detectar un rostro claro. Elige tu forma manualmente.", "error");
          return;
        }

        const ratio = (maxY - minY) / Math.max(1, maxX - minX);
        const forma = ratio > 1.45 ? "alargado" : ratio < 1.1 ? "redondo" : "ovalado";
        document.querySelector(`.face-option[data-shape="${forma}"]`)?.click();
        toast(`Análisis completado: rostro estimado ${CATALOGO[forma].label}`, "notify");
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  }

  function isSkinTone(r, g, b) {
    return r > 60 && g > 30 && b > 15 && r > g && r > b && Math.abs(r - g) > 12 && r - b > 15;
  }

  function toast(msg, sfx) {
    const stack = document.getElementById("toast-stack");
    if (!stack) return;
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    stack.appendChild(el);
    if (window.SFX) SFX.play(sfx || "notify");
    setTimeout(() => el.remove(), 3800);
  }

  function init() {
    renderOptions();
    const uploadInput = document.getElementById("face-upload");
    if (uploadInput) {
      uploadInput.addEventListener("change", (e) => {
        if (e.target.files[0]) analizarImagen(e.target.files[0]);
      });
    }
  }

  document.addEventListener("DOMContentLoaded", init);
  return { showResult, toast };
})();
