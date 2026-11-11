/* ============================================================
   AUDIO-HÁPTICA — Web Audio API + Vibration API
   Sonidos sintetizados (sin archivos externos), sutiles y de lujo.
   ============================================================ */
const SFX = (() => {
  let ctx = null;

  function ensureCtx() {
    if (!ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) ctx = new AudioCtx();
    }
    if (ctx && ctx.state === "suspended") ctx.resume();
    return ctx;
  }

  function tone({ freq = 440, duration = 0.08, type = "sine", gain = 0.05, glideTo = null }) {
    const c = ensureCtx();
    if (!c) return;
    const osc = c.createOscillator();
    const amp = c.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, c.currentTime);
    if (glideTo) osc.frequency.exponentialRampToValueAtTime(glideTo, c.currentTime + duration);
    amp.gain.setValueAtTime(gain, c.currentTime);
    amp.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + duration);
    osc.connect(amp).connect(c.destination);
    osc.start();
    osc.stop(c.currentTime + duration + 0.02);
  }

  function vibrate(pattern) {
    if (navigator.vibrate) navigator.vibrate(pattern);
  }

  const presets = {
    click:   () => { tone({ freq: 720, duration: 0.05, type: "sine", gain: 0.04 }); vibrate(8); },
    hover:   () => { tone({ freq: 1200, duration: 0.02, type: "sine", gain: 0.015 }); },
    confirm: () => { tone({ freq: 520, duration: 0.16, type: "triangle", gain: 0.06, glideTo: 880 }); vibrate([10, 30, 18]); },
    cash:    () => { tone({ freq: 660, duration: 0.09, type: "square", gain: 0.03 });
                      setTimeout(() => tone({ freq: 990, duration: 0.12, type: "sine", gain: 0.05 }), 90);
                      vibrate([12, 20, 12]); },
    error:   () => { tone({ freq: 200, duration: 0.22, type: "sawtooth", gain: 0.05, glideTo: 90 }); vibrate([30, 40, 30]); },
    notify:  () => { tone({ freq: 880, duration: 0.1, type: "sine", gain: 0.045 }); vibrate(15); },
  };

  function play(name) {
    if (presets[name]) presets[name]();
  }

  // Delegación global: cualquier elemento con data-sfx reproduce su sonido al click
  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-sfx]");
    if (el) play(el.dataset.sfx || "click");
    else if (e.target.closest(".btn, .nav-icon")) play("click");
  });

  document.addEventListener(
    "mouseover",
    (e) => { if (e.target.closest(".nav-icon, .item-pick, .face-option")) play("hover"); },
    true
  );

  return { play, ensureCtx };
})();

// El primer gesto del usuario "despierta" el AudioContext (requisito de navegadores)
["click", "touchstart", "keydown"].forEach((evt) =>
  document.addEventListener(evt, () => SFX.ensureCtx(), { once: true })
);

/* ---------------- CURSOR / TOQUE REACTIVO (glow doradoo/neón) ---------------- */
(function reactiveGlow() {
  const root = document.documentElement;
  function updateGlow(x, y) {
    root.style.setProperty("--mx", `${(x / window.innerWidth) * 100}%`);
    root.style.setProperty("--my", `${(y / window.innerHeight) * 100}%`);
  }
  window.addEventListener("pointermove", (e) => updateGlow(e.clientX, e.clientY));
  window.addEventListener("touchmove", (e) => {
    if (e.touches[0]) updateGlow(e.touches[0].clientX, e.touches[0].clientY);
  }, { passive: true });

  // Glow local dentro de cada glass-panel (sigue al cursor dentro del panel)
  document.addEventListener("pointermove", (e) => {
    const panel = e.target.closest(".glass-panel");
    if (!panel) return;
    const rect = panel.getBoundingClientRect();
    panel.style.setProperty("--px", `${e.clientX - rect.left}px`);
    panel.style.setProperty("--py", `${e.clientY - rect.top}px`);
  });
})();
