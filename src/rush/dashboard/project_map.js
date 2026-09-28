/**
 * Phase 66 P66-02: animated project map renderer (plan sections 3.3-3.5).
 * Phase 69 P69-05: motion, responsive interaction, and recovery (plan
 * section 3.4/3.9, Phase 66 §0 rows 15/24) -- exact per-animation timings,
 * wheel zoom + background pan, keyboard shortcuts, roving tabindex, a
 * semantic (non-SVG) relationship list, hover/focus tooltip, real
 * `setFilters`/`fit` behavior, and a capture-live-transform-before-cancel
 * selection fix (row 24's corrected ordering).
 *
 * Native SVG for nodes/curved edges, semantic HTML for the docked inspector,
 * CSS for layout/theme, Web Animations API for coordinated transforms and
 * `requestAnimationFrame` only for pan/zoom interpolation -- no Canvas/WebGL,
 * no force-layout dependency, no framework, no build step. Loaded directly
 * as an ES module by `application.js` via `<script type="module">`.
 *
 * Exports: renderMap, selectNode, setFilters, showGroupMembers,
 * hideGroupMembers, fitMap, destroyMap, setReducedMotion, pulseEvidence.
 */

const SVG_NS = "http://www.w3.org/2000/svg";

const ZOOM_MIN = 0.4;
const ZOOM_MAX = 2.5;
const ZOOM_STEP = 0.1;
const TOOLTIP_DELAY_MS = 300;

const SECTORS = {
  file: [-150, -30],
  directory: [-150, -30],
  finding: [-30, 60],
  memory: [60, 150],
  agent: [150, 210],
};
const OVERVIEW_GROUP_RADIUS = 180;
const OVERVIEW_MEMBER_RADIUS = 340;
const NODE_RADII = {
  project: 28,
  group: 20,
  file: 10,
  directory: 10,
  finding: 9,
  memory: 12,
  agent: 12,
};
const KIND_ACCENT_VAR = {
  project: "--color-blue",
  directory: "--color-blue",
  file: "--color-blue",
  group: "--color-blue",
  finding: "--color-pink",
  memory: "--color-purple",
  agent: "--color-purple",
};

function sortKey(node) {
  return [node.path || "", node.id];
}

function compareSortKeys(a, b) {
  const [aPath, aId] = sortKey(a);
  const [bPath, bId] = sortKey(b);
  if (aPath !== bPath) return aPath < bPath ? -1 : 1;
  if (aId !== bId) return aId < bId ? -1 : 1;
  return 0;
}

function computeLayout(nodes) {
  const positions = new Map();
  const bySector = new Map();
  for (const node of nodes) {
    if (node.kind === "project") {
      positions.set(node.id, { x: 0, y: 0 });
      continue;
    }
    const sectorKind = SECTORS[node.kind] ? node.kind : "file";
    if (!bySector.has(sectorKind)) bySector.set(sectorKind, []);
    bySector.get(sectorKind).push(node);
  }
  for (const [sectorKind, members] of bySector) {
    const [start, end] = SECTORS[sectorKind];
    const width = end - start;
    const ordered = [...members].sort(compareSortKeys);
    const radius = ordered.some((n) => n.kind === "group")
      ? OVERVIEW_GROUP_RADIUS
      : OVERVIEW_MEMBER_RADIUS;
    ordered.forEach((node, index) => {
      const angleDeg = start + (index + 0.5) * width / ordered.length;
      const angleRad = (angleDeg * Math.PI) / 180;
      positions.set(node.id, {
        x: radius * Math.cos(angleRad),
        y: radius * Math.sin(angleRad),
      });
    });
  }
  return positions;
}

function curvedEdgePath(sourcePos, targetPos) {
  const dx = targetPos.x - sourcePos.x;
  const dy = targetPos.y - sourcePos.y;
  const c1x = sourcePos.x + dx * 0.45;
  const c1y = sourcePos.y + dy * 0.45;
  const c2x = sourcePos.x + dx * 0.55;
  const c2y = sourcePos.y + dy * 0.55;
  return `M ${sourcePos.x} ${sourcePos.y} C ${c1x} ${c1y} ${c2x} ${c2y} ${targetPos.x} ${targetPos.y}`;
}

/**
 * One renderer instance per mount; `renderMap` returns a handle exposing the
 * documented module-level operations so multiple maps could coexist in
 * principle, while the module-level `selectNode`/`setFilters`/`fitMap`/
 * `destroyMap` exports below always act on the most recently rendered
 * instance (the browser only ever mounts one map view at a time).
 */
function createRenderer(container, { theme, motion, reducedMotion: initialReducedMotion, onSelect }) {
  container.textContent = "";
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("role", "group");
  svg.setAttribute("aria-label", "Project map");
  svg.style.width = "100%";
  svg.style.height = "100%";

  const camera = document.createElementNS(SVG_NS, "g");
  camera.setAttribute("data-role", "camera");
  svg.appendChild(camera);
  container.appendChild(svg);

  const inspector = document.createElement("div");
  inspector.setAttribute("data-role", "group-inspector");
  inspector.hidden = true;
  container.appendChild(inspector);

  let currentMapData = null;
  let currentPositions = new Map();
  let selectedId = null;
  let generation = 0;
  let reducedMotion = !!initialReducedMotion;
  let cameraTranslate = { x: 0, y: 0 };
  let cameraScale = 1;
  let tooltipTimer = null;
  let tooltipEl = null;
  let panState = null;
  const activeAnimations = [];

  function cancelActiveAnimations() {
    while (activeAnimations.length) {
      const animation = activeAnimations.pop();
      try {
        animation.cancel();
      } catch (_err) {
      }
    }
  }

  function animate(target, keyframes, options) {
    if (reducedMotion) {
      const last = keyframes[keyframes.length - 1];
      Object.assign(target.style, last);
      return null;
    }
    const animation = target.animate(keyframes, options);
    activeAnimations.push(animation);
    return animation;
  }

  /** Row 24's corrected cancellation ordering (plan §3 clarification):
   * capture the live on-screen transform first, THEN cancel prior
   * animations, THEN start the new animation from the captured value --
   * cancelling first would remove the animated effect before its visible
   * intermediate position could be read back. Shared by every camera move
   * (selection focus, fit) so the fix lives in one place. */
  function moveCameraTo(x, y, scale, durationMs, easing) {
    const liveTransform = getComputedStyle(camera).transform;
    cancelActiveAnimations();
    cameraTranslate = { x, y };
    cameraScale = scale;
    const targetTransform = `translate(${x}px, ${y}px) scale(${scale})`;
    animate(camera, [{ transform: liveTransform }, { transform: targetTransform }], {
      duration: durationMs,
      easing,
      fill: "forwards",
    });
  }

  function clearTooltipTimer() {
    if (tooltipTimer) {
      window.clearTimeout(tooltipTimer);
      tooltipTimer = null;
    }
  }

  function hideTooltip() {
    if (tooltipEl) {
      tooltipEl.remove();
      tooltipEl = null;
    }
  }

  function showTooltip(node, anchorEl) {
    clearTooltipTimer();
    tooltipTimer = window.setTimeout(() => {
      hideTooltip();
      tooltipEl = document.createElement("div");
      tooltipEl.setAttribute("data-role", "map-tooltip");
      tooltipEl.setAttribute("role", "tooltip");
      tooltipEl.textContent = node.label || node.id;
      const rect = anchorEl.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      tooltipEl.style.left = `${rect.left - containerRect.left}px`;
      tooltipEl.style.top = `${rect.top - containerRect.top}px`;
      container.appendChild(tooltipEl);
    }, TOOLTIP_DELAY_MS);
  }

  function updateRovingTabindex() {
    const nodeEls = Array.from(camera.querySelectorAll("[data-node-id]"));
    if (nodeEls.length === 0) return;
    const activeEl =
      nodeEls.find((el) => el.getAttribute("data-node-id") === selectedId) || nodeEls[0];
    for (const el of nodeEls) {
      el.setAttribute("tabindex", el === activeEl ? "0" : "-1");
    }
  }

  function moveRovingFocus(direction) {
    const nodeEls = Array.from(camera.querySelectorAll("[data-node-id]"));
    if (nodeEls.length === 0) return;
    const currentIndex = Math.max(
      0,
      nodeEls.findIndex((el) => el.getAttribute("tabindex") === "0")
    );
    const nextIndex = (currentIndex + direction + nodeEls.length) % nodeEls.length;
    const nextEl = nodeEls[nextIndex];
    for (const el of nodeEls) el.setAttribute("tabindex", el === nextEl ? "0" : "-1");
    nextEl.focus();
  }

  function zoomBy(delta, pointer) {
    const focal = pointer || { x: 0, y: 0 };
    const nextScale = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, cameraScale + delta));
    const localX = (focal.x - cameraTranslate.x) / cameraScale;
    const localY = (focal.y - cameraTranslate.y) / cameraScale;
    const nextX = focal.x - localX * nextScale;
    const nextY = focal.y - localY * nextScale;
    cancelActiveAnimations();
    cameraTranslate = { x: nextX, y: nextY };
    cameraScale = nextScale;
    camera.style.transform = `translate(${nextX}px, ${nextY}px) scale(${nextScale})`;
  }

  function goBack() {
    hideGroupMembersInternal();
    selectedId = null;
    updateRovingTabindex();
  }

  function screenToLocal(clientX, clientY) {
    const rect = svg.getBoundingClientRect();
    return { x: clientX - rect.left - rect.width / 2, y: clientY - rect.top - rect.height / 2 };
  }

  function buildNodeElement(node, position) {
    const group = document.createElementNS(SVG_NS, "g");
    group.setAttribute("data-node-id", node.id);
    group.setAttribute("data-kind", node.kind);
    group.setAttribute("class", `rush-node-${node.kind}`);
    group.setAttribute("transform", `translate(${position.x} ${position.y})`);
    group.setAttribute("tabindex", "-1");
    group.setAttribute("role", "button");
    group.setAttribute("aria-label", node.label || node.id);

    const circle = document.createElementNS(SVG_NS, "circle");
    const radius = NODE_RADII[node.kind] || 10;
    circle.setAttribute("r", String(radius));
    const accentVar = KIND_ACCENT_VAR[node.kind] || "--color-blue";
    circle.style.stroke = `var(${accentVar})`;
    circle.style.strokeWidth = "1";
    circle.style.fill = "var(--color-surface-raised)";
    group.appendChild(circle);

    const label = document.createElementNS(SVG_NS, "text");
    label.textContent = node.label || node.id;
    label.setAttribute("x", String(radius + 4));
    label.setAttribute("y", "4");
    label.style.fill = "var(--color-text)";
    label.style.fontSize = "12px";
    group.appendChild(label);

    group.addEventListener("click", () => selectNodeInternal(node.id));
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter") selectNodeInternal(node.id);
    });
    group.addEventListener("mouseenter", () => showTooltip(node, group));
    group.addEventListener("focus", () => showTooltip(node, group));
    group.addEventListener("mousemove", () => showTooltip(node, group));
    group.addEventListener("mouseleave", () => {
      clearTooltipTimer();
      hideTooltip();
    });
    group.addEventListener("blur", () => {
      clearTooltipTimer();
      hideTooltip();
    });
    return group;
  }

  function selectNodeInternal(nodeId) {
    generation += 1;
    const thisGeneration = generation;
    selectedId = nodeId;

    const target = camera.querySelector(`[data-node-id="${CSS.escape(nodeId)}"]`);
    if (target) {
      const position = currentPositions.get(nodeId) || { x: 0, y: 0 };
      moveCameraTo(
        -position.x * cameraScale,
        -position.y * cameraScale,
        cameraScale,
        motion.camera_focus_ms,
        motion.easing
      );
    }
    updateRovingTabindex();

    if (typeof onSelect === "function") {
      const node =
        (currentMapData && currentMapData.nodes.find((n) => n.id === nodeId)) || null;
      onSelect(nodeId, {
        generation: thisGeneration,
        isCurrent: () => thisGeneration === generation,
        node,
      });
    }
  }

  /** Render (or extend, when `append` is set) a group node's fetched
   * membership page in the docked inspector (expand_group's real caller --
   * plan 3.5's browser pagination past the 200-node render bound). Each
   * newly staged row fades/translates in with a capped per-row stagger
   * (`detail_row_*` tokens); the inspector itself plays the angled-entry
   * transform (`inspector_initial_transform` -> identity) only the first
   * time it opens, not on every appended page. */
  function showGroupMembersInternal(groupId, members, options = {}) {
    const { total, hasMore, append, onLoadMore } = options;
    const wasHidden = inspector.hidden;
    inspector.hidden = false;
    inspector.setAttribute("data-group-id", groupId);

    let list = inspector.querySelector('[data-role="group-members"]');
    if (!append || !list) {
      inspector.textContent = "";
      list = document.createElement("ul");
      list.setAttribute("data-role", "group-members");
      inspector.appendChild(list);
    }
    let rowIndex = append ? list.children.length : 0;
    for (const member of members) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.setAttribute("data-role", "member-row");
      button.setAttribute("data-member-id", member.id);
      button.textContent = member.label || member.id;
      button.addEventListener("click", () => selectNodeInternal(member.id));
      button.addEventListener("keydown", (event) => {
        if (event.key === "Enter") selectNodeInternal(member.id);
      });
      item.appendChild(button);
      list.appendChild(item);
      if (!reducedMotion) {
        const delay = Math.min(
          rowIndex * motion.detail_row_stagger_ms,
          motion.detail_row_stagger_cap_ms
        );
        animate(
          item,
          [
            { opacity: 0, transform: `translateY(${motion.detail_row_translate_px}px)` },
            { opacity: 1, transform: "translateY(0px)" },
          ],
          { duration: motion.detail_row_fade_ms, delay, easing: motion.easing, fill: "forwards" }
        );
      }
      rowIndex += 1;
    }

    const existingButton = inspector.querySelector('[data-role="load-more"]');
    if (existingButton) existingButton.remove();
    if (hasMore) {
      const button = document.createElement("button");
      button.type = "button";
      button.setAttribute("data-role", "load-more");
      button.textContent = `Load more (${list.children.length}/${total})`;
      button.addEventListener("click", onLoadMore);
      inspector.appendChild(button);
    }

    if (wasHidden && !reducedMotion) {
      animate(
        inspector,
        [
          { opacity: 0, transform: motion.inspector_initial_transform },
          { opacity: 1, transform: "none" },
        ],
        { duration: motion.inspector_entry_ms, easing: motion.easing, fill: "forwards" }
      );
    }
  }

  function hideGroupMembersInternal() {
    inspector.hidden = true;
    inspector.textContent = "";
  }

  /** Accessible mirror of the SVG graph (row 15): the same node/edge records
   * and select action, exposed as a real DOM list for assistive tech that
   * can't navigate SVG well -- visually hidden via `.rush-sr-only`, never a
   * second source of truth (built straight from `mapData` on every real
   * render). */
  function buildRelationshipList(mapData) {
    let list = container.querySelector('[data-role="relationship-list"]');
    if (!list) {
      list = document.createElement("ul");
      list.setAttribute("data-role", "relationship-list");
      list.setAttribute("class", "rush-sr-only");
      list.setAttribute("aria-label", "Project map relationships (accessible list)");
      container.appendChild(list);
    }
    list.textContent = "";
    for (const node of mapData.nodes) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.setAttribute("data-role", "relationship-list-item");
      button.setAttribute("data-node-id", node.id);
      button.textContent = `${node.kind}: ${node.label || node.id}`;
      button.addEventListener("click", () => selectNodeInternal(node.id));
      item.appendChild(button);
      list.appendChild(item);
    }
    for (const edge of mapData.edges) {
      const item = document.createElement("li");
      item.setAttribute("data-role", "relationship-list-edge");
      item.textContent = `${edge.source} -> ${edge.target}`;
      list.appendChild(item);
    }
  }

  /** Row 15/24: incremental render. When `mapData.sequence` matches the last
   * rendered sequence, this is a no-op poll cycle -- camera, selection,
   * in-flight animations, and keyboard focus are left completely alone
   * (never call `cancelActiveAnimations()` here, unlike a genuine
   * project/view replacement which goes through `destroyMap`+`createRenderer`
   * instead). Otherwise, only nodes/edges actually added or removed touch
   * the DOM; survivors are left as-is. */
  function render(mapData) {
    if (
      currentMapData &&
      mapData &&
      typeof mapData.sequence !== "undefined" &&
      mapData.sequence === currentMapData.sequence
    ) {
      return;
    }
    currentMapData = mapData;
    currentPositions = computeLayout(mapData.nodes);

    const existingIds = new Set(
      Array.from(camera.children)
        .filter((el) => el.hasAttribute && el.hasAttribute("data-node-id"))
        .map((el) => el.getAttribute("data-node-id"))
    );
    const nextIds = new Set(mapData.nodes.map((n) => n.id));

    for (const child of Array.from(camera.children)) {
      const id = child.getAttribute("data-node-id");
      if (id && !nextIds.has(id)) camera.removeChild(child);
    }

    let edgeLayer = camera.querySelector('[data-role="edges"]');
    if (!edgeLayer) {
      edgeLayer = document.createElementNS(SVG_NS, "g");
      edgeLayer.setAttribute("data-role", "edges");
      camera.insertBefore(edgeLayer, camera.firstChild);
    }
    const existingEdgeIds = new Set(
      Array.from(edgeLayer.children).map((el) => el.getAttribute("data-edge-id"))
    );
    const nextEdgeIds = new Set(mapData.edges.map((e) => e.id));
    for (const child of Array.from(edgeLayer.children)) {
      const id = child.getAttribute("data-edge-id");
      if (id && !nextEdgeIds.has(id)) edgeLayer.removeChild(child);
    }
    let newEdgeIndex = 0;
    for (const edge of mapData.edges) {
      if (existingEdgeIds.has(edge.id)) continue;
      const sourcePos = currentPositions.get(edge.source);
      const targetPos = currentPositions.get(edge.target);
      if (!sourcePos || !targetPos) continue;
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", curvedEdgePath(sourcePos, targetPos));
      path.setAttribute("data-edge-id", edge.id);
      path.style.fill = "none";
      path.style.stroke = "var(--color-border)";
      path.style.strokeWidth = "1";
      edgeLayer.appendChild(path);
      if (!reducedMotion) {
        const length = path.getTotalLength ? path.getTotalLength() : 0;
        if (length > 0) {
          path.style.strokeDasharray = String(length);
          const delay = Math.min(
            newEdgeIndex * motion.relationship_stagger_ms,
            motion.relationship_stagger_cap_ms
          );
          animate(
            path,
            [{ strokeDashoffset: String(length) }, { strokeDashoffset: "0" }],
            {
              duration: motion.relationship_reveal_ms,
              delay,
              easing: motion.easing,
              fill: "forwards",
            }
          );
          newEdgeIndex += 1;
        }
      }
    }

    let newNodeIndex = 0;
    for (const node of mapData.nodes) {
      if (existingIds.has(node.id)) continue;
      const position = currentPositions.get(node.id) || { x: 0, y: 0 };
      const element = buildNodeElement(node, position);
      camera.appendChild(element);
      if (!reducedMotion) {
        const isProjectRoot = node.kind === "project";
        const duration = isProjectRoot ? motion.project_enter_ms : motion.relationship_reveal_ms;
        const delay = isProjectRoot
          ? 0
          : Math.min(newNodeIndex * motion.relationship_stagger_ms, motion.relationship_stagger_cap_ms);
        animate(element, [{ opacity: 0 }, { opacity: 1 }], {
          duration,
          delay,
          easing: motion.easing,
          fill: "forwards",
        });
        if (isProjectRoot) {
          const circle = element.querySelector("circle");
          if (circle) {
            const fullRadius = circle.getAttribute("r");
            animate(circle, [{ r: "0" }, { r: fullRadius }], {
              duration,
              easing: motion.easing,
              fill: "forwards",
            });
          }
        } else {
          newNodeIndex += 1;
        }
      }
    }

    buildRelationshipList(mapData);
    updateRovingTabindex();
  }

  /** Client-side quick filter over the already-rendered map (row 15): hides
   * non-matching nodes by kind (`nodeTypes`) and/or label substring
   * (`query`), and hides an edge whenever either endpoint is hidden --
   * never refetches, and never mutates `currentMapData`. */
  function setFiltersInternal(filters = {}) {
    const nodeTypes =
      filters.nodeTypes && filters.nodeTypes.length ? new Set(filters.nodeTypes) : null;
    const query = (filters.query || "").trim().toLowerCase();
    const hiddenIds = new Set();
    const nodeEls = camera.querySelectorAll("[data-node-id]");
    for (const el of nodeEls) {
      const kind = el.getAttribute("data-kind");
      const nodeId = el.getAttribute("data-node-id");
      const node = currentMapData && currentMapData.nodes.find((n) => n.id === nodeId);
      const label = ((node && (node.label || node.id)) || "").toLowerCase();
      const matchesType = !nodeTypes || nodeTypes.has(kind);
      const matchesQuery = !query || label.includes(query);
      const visible = matchesType && matchesQuery;
      el.style.display = visible ? "" : "none";
      if (!visible) hiddenIds.add(nodeId);
    }
    const edgeEls = camera.querySelectorAll("[data-edge-id]");
    for (const el of edgeEls) {
      const edgeId = el.getAttribute("data-edge-id");
      const edge = currentMapData && currentMapData.edges.find((e) => e.id === edgeId);
      const hidden = !edge || hiddenIds.has(edge.source) || hiddenIds.has(edge.target);
      el.style.display = hidden ? "none" : "";
    }
  }

  /** Fit restores the FULL content bounds (a real bounding-box computation
   * over every rendered node's position), not a bare translation reset --
   * distinct from the old behavior of always animating back to
   * `translate(0px, 0px)` regardless of what's actually on screen or the
   * current zoom level. */
  function fit() {
    const positions = Array.from(currentPositions.values());
    if (positions.length === 0) {
      moveCameraTo(0, 0, 1, motion.camera_focus_ms, motion.easing);
    } else {
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      for (const pos of positions) {
        minX = Math.min(minX, pos.x);
        maxX = Math.max(maxX, pos.x);
        minY = Math.min(minY, pos.y);
        maxY = Math.max(maxY, pos.y);
      }
      const boxWidth = Math.max(maxX - minX, 1);
      const boxHeight = Math.max(maxY - minY, 1);
      const viewWidth = svg.clientWidth || 800;
      const viewHeight = svg.clientHeight || 600;
      const padding = 0.85;
      const scale = Math.min(
        ZOOM_MAX,
        Math.max(
          ZOOM_MIN,
          Math.min((viewWidth / boxWidth) * padding, (viewHeight / boxHeight) * padding)
        )
      );
      const centerX = (minX + maxX) / 2;
      const centerY = (minY + maxY) / 2;
      moveCameraTo(-centerX * scale, -centerY * scale, scale, motion.camera_focus_ms, motion.easing);
    }
    selectedId = null;
    updateRovingTabindex();
  }

  /** Row 15: one-shot, non-repeating pulse on a real run/evidence update
   * event only -- never called from `render()`'s own add/remove diffing or
   * any idle/poll path, so it never plays on its own. */
  function pulseEvidenceInternal(nodeId) {
    if (reducedMotion) return;
    const target = camera.querySelector(`[data-node-id="${CSS.escape(nodeId)}"] circle`);
    if (!target) return;
    animate(
      target,
      [
        { filter: "drop-shadow(0 0 0px var(--color-warning))" },
        { filter: "drop-shadow(0 0 8px var(--color-warning))" },
        { filter: "drop-shadow(0 0 0px var(--color-warning))" },
      ],
      { duration: motion.evidence_pulse_ms, easing: motion.easing, iterations: 1 }
    );
  }

  function onWheel(event) {
    event.preventDefault();
    const pointer = screenToLocal(event.clientX, event.clientY);
    const direction = event.deltaY < 0 ? 1 : -1;
    zoomBy(direction * ZOOM_STEP, pointer);
  }

  function onMouseDown(event) {
    if (event.target !== svg && event.target !== camera) return;
    panState = { startX: event.clientX, startY: event.clientY, origin: { ...cameraTranslate } };
  }

  function onWindowMouseMove(event) {
    if (!panState) return;
    const dx = event.clientX - panState.startX;
    const dy = event.clientY - panState.startY;
    cameraTranslate = { x: panState.origin.x + dx, y: panState.origin.y + dy };
    camera.style.transform = `translate(${cameraTranslate.x}px, ${cameraTranslate.y}px) scale(${cameraScale})`;
  }

  function onWindowMouseUp() {
    panState = null;
  }

  container.addEventListener("keydown", (event) => {
    if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      zoomBy(ZOOM_STEP);
    } else if (event.key === "-") {
      event.preventDefault();
      zoomBy(-ZOOM_STEP);
    } else if (event.key === "0") {
      event.preventDefault();
      fit();
    } else if (event.key === "Escape") {
      event.preventDefault();
      clearTooltipTimer();
      hideTooltip();
      goBack();
    } else if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      moveRovingFocus(1);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      moveRovingFocus(-1);
    }
  });
  svg.addEventListener("wheel", onWheel, { passive: false });
  svg.addEventListener("mousedown", onMouseDown);
  window.addEventListener("mousemove", onWindowMouseMove);
  window.addEventListener("mouseup", onWindowMouseUp);

  function destroy() {
    cancelActiveAnimations();
    clearTooltipTimer();
    hideTooltip();
    window.removeEventListener("mousemove", onWindowMouseMove);
    window.removeEventListener("mouseup", onWindowMouseUp);
    container.textContent = "";
  }

  return {
    render,
    selectNode: selectNodeInternal,
    setFilters: setFiltersInternal,
    showGroupMembers: showGroupMembersInternal,
    hideGroupMembers: hideGroupMembersInternal,
    fit,
    destroy,
    setReducedMotion: (value) => {
      reducedMotion = !!value;
    },
    pulseEvidence: pulseEvidenceInternal,
    get selectedId() {
      return selectedId;
    },
    get mapData() {
      return currentMapData;
    },
  };
}

let activeRenderer = null;
let activeContainer = null;

export function renderMap(container, mapData, options = {}) {
  if (activeRenderer && activeContainer === container) {
    activeRenderer.render(mapData);
    return activeRenderer;
  }
  activeContainer = container;
  activeRenderer = createRenderer(container, options);
  activeRenderer.render(mapData);
  return activeRenderer;
}

export function selectNode(nodeId) {
  if (activeRenderer) activeRenderer.selectNode(nodeId);
}

export function setFilters(filters) {
  if (activeRenderer) activeRenderer.setFilters(filters);
}

export function showGroupMembers(groupId, members, options = {}) {
  if (activeRenderer) activeRenderer.showGroupMembers(groupId, members, options);
}

export function hideGroupMembers() {
  if (activeRenderer) activeRenderer.hideGroupMembers();
}

export function fitMap() {
  if (activeRenderer) activeRenderer.fit();
}

export function setReducedMotion(value) {
  if (activeRenderer) activeRenderer.setReducedMotion(value);
}

export function pulseEvidence(nodeId) {
  if (activeRenderer) activeRenderer.pulseEvidence(nodeId);
}

export function destroyMap() {
  if (activeRenderer) {
    activeRenderer.destroy();
    activeRenderer = null;
  }
  activeContainer = null;
}
