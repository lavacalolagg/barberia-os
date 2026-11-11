/* ============================================================
   VISOR 3D — Three.js
   Modelo procedural (sillón de barbería estilizado) rotable con
   drag / touch. Reemplazable por un GLTFLoader con modelo real.
   ============================================================ */
(function initViewer3D() {
  const container = document.getElementById("viewer3d-container");
  if (!container || typeof THREE === "undefined") return;

  let renderer, scene, camera, group;
  let isDragging = false, prevX = 0, prevY = 0;
  let rotY = 0.4, rotX = -0.2;

  function build() {
    const w = container.clientWidth, h = container.clientHeight || 340;

    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 100);
    camera.position.set(0, 1.2, 5);

    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    // Luces cyber-luxury: dorado cálido + cian frío
    scene.add(new THREE.AmbientLight(0x554433, 0.6));
    const goldLight = new THREE.PointLight(0xd4af37, 2.2, 12);
    goldLight.position.set(3, 3, 3);
    scene.add(goldLight);
    const cyanLight = new THREE.PointLight(0x37e6e0, 1.6, 12);
    cyanLight.position.set(-3, 1, -2);
    scene.add(cyanLight);

    group = new THREE.Group();

    // Base del sillón (cilindro)
    const base = new THREE.Mesh(
      new THREE.CylinderGeometry(0.9, 1.1, 0.3, 32),
      new THREE.MeshStandardMaterial({ color: 0x141018, metalness: 0.6, roughness: 0.3 })
    );
    base.position.y = -1.1;
    group.add(base);

    // Columna
    const column = new THREE.Mesh(
      new THREE.CylinderGeometry(0.18, 0.22, 1.2, 24),
      new THREE.MeshStandardMaterial({ color: 0xd4af37, metalness: 0.85, roughness: 0.2 })
    );
    column.position.y = -0.4;
    group.add(column);

    // Asiento
    const seat = new THREE.Mesh(
      new THREE.CylinderGeometry(0.85, 0.85, 0.25, 32),
      new THREE.MeshStandardMaterial({ color: 0x1c1622, metalness: 0.3, roughness: 0.5 })
    );
    seat.position.y = 0.35;
    group.add(seat);

    // Respaldo
    const backGeo = new THREE.SphereGeometry(0.9, 24, 24, 0, Math.PI * 2, 0, Math.PI / 1.8);
    const back = new THREE.Mesh(backGeo, new THREE.MeshStandardMaterial({ color: 0x1c1622, metalness: 0.3, roughness: 0.5 }));
    back.position.set(0, 0.9, -0.55);
    back.rotation.x = Math.PI;
    group.add(back);

    // Anillo decorativo neón flotante
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(1.5, 0.02, 16, 100),
      new THREE.MeshBasicMaterial({ color: 0x37e6e0 })
    );
    ring.rotation.x = Math.PI / 2;
    ring.position.y = -1.25;
    group.add(ring);

    scene.add(group);
    animate();
  }

  function animate() {
    requestAnimationFrame(animate);
    if (!isDragging) rotY += 0.003; // rotación idle sutil
    group.rotation.y = rotY;
    group.rotation.x = rotX;
    renderer.render(scene, camera);
  }

  function onDown(x, y) { isDragging = true; prevX = x; prevY = y; }
  function onMove(x, y) {
    if (!isDragging) return;
    rotY += (x - prevX) * 0.008;
    rotX = Math.max(-0.6, Math.min(0.6, rotX + (y - prevY) * 0.006));
    prevX = x; prevY = y;
  }
  function onUp() { isDragging = false; }

  container.addEventListener("mousedown", (e) => onDown(e.clientX, e.clientY));
  window.addEventListener("mousemove", (e) => onMove(e.clientX, e.clientY));
  window.addEventListener("mouseup", onUp);
  container.addEventListener("touchstart", (e) => onDown(e.touches[0].clientX, e.touches[0].clientY), { passive: true });
  container.addEventListener("touchmove", (e) => onMove(e.touches[0].clientX, e.touches[0].clientY), { passive: true });
  container.addEventListener("touchend", onUp);

  container.addEventListener("wheel", (e) => {
    e.preventDefault();
    camera.position.z = Math.max(2.5, Math.min(8, camera.position.z + e.deltaY * 0.01));
  }, { passive: false });

  window.addEventListener("resize", () => {
    if (!renderer) return;
    const w = container.clientWidth, h = container.clientHeight || 340;
    camera.aspect = w / h; camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  });

  // Solo construir cuando la sección "agenda" (donde vive el visor) es visible
  const observer = new MutationObserver(() => {
    if (container.offsetParent !== null && !renderer) build();
  });
  observer.observe(document.getElementById("view-agenda"), { attributes: true, attributeFilter: ["class"] });
  if (container.offsetParent !== null) build();
})();
