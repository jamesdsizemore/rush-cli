/**
 * Phase 66 P66-02: animated project map renderer (plan sections 3.3-3.5).
 *
 * Native SVG for nodes/curved edges, semantic HTML for the docked inspector,
 * CSS for layout/theme, Web Animations API for coordinated transforms and
 * `requestAnimationFrame` only for pan/zoom interpolation -- no Canvas/WebGL,
 * no force-layout dependency, no framework, no build step. Loaded directly
 * as an ES module by `application.js` via `<script type="module">`.
 *
 * Exports: renderMap, selectNode, setFilters, showGroupMembers,
 * hideGroupMembers, fitMap, destroyMap.
 */

const SVG_NS = "http://www.w3.org/2000/svg";

// Mirrors rush.dashboard.project_map's polar layout formulas exactly (spec
// 3.5) so the browser lays out nodes identically to the deterministic
// server-side `compute_layout` used for testing.
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
function createRenderer(container, { theme, motion, reducedMotion, onSelect }) {
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

  // Docked inspector (module doc line 4): lists a group node's paginated
  // membership fetched via expand_group -- the browser's page-past-the-
  // render-bound view (plan section 3.5's "server-paginated members").
  const inspector = document.createElement("div");
  inspector.setAttribute("data-role", "group-inspector");
  inspector.hidden = true;
  container.appendChild(inspector);

  let currentMapData = null;
  let currentPositions = new Map();
  let selectedId = null;
  let generation = 0;
  const activeAnimations = [];

  function cancelActiveAnimations() {
    while (activeAnimations.length) {
      const animation = activeAnimations.pop();
      try {
        animation.cancel();
      } catch (_err) {
        // Already finished/cancelled -- ignore.
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

  function buildNodeElement(node, position) {
    const group = document.createElementNS(SVG_NS, "g");
    group.setAttribute("data-node-id", node.id);
    group.setAttribute("data-kind", node.kind);
    group.setAttribute("class", `rush-node-${node.kind}`);
    group.setAttribute("transform", `translate(${position.x} ${position.y})`);
    group.setAttribute("tabindex", "0");
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
    return group;
  }

  function selectNodeInternal(nodeId) {
    generation += 1;
    const thisGeneration = generation;
    selectedId = nodeId;
    cancelActiveAnimations();

    const target = camera.querySelector(`[data-node-id="${CSS.escape(nodeId)}"]`);
    if (target) {
      const position = currentPositions.get(nodeId) || { x: 0, y: 0 };
      animate(
        camera,
        [
          { transform: camera.style.transform || "translate(0px, 0px)" },
          { transform: `translate(${-position.x}px, ${-position.y}px)` },
        ],
        { duration: motion.camera_focus_ms, easing: motion.easing, fill: "forwards" }
      );
    }

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
   * plan 3.5's browser pagination past the 200-node render bound). */
  function showGroupMembersInternal(groupId, members, options = {}) {
    const { total, hasMore, append, onLoadMore } = options;
    inspector.hidden = false;
    inspector.setAttribute("data-group-id", groupId);

    let list = inspector.querySelector('[data-role="group-members"]');
    if (!append || !list) {
      inspector.textContent = "";
      list = document.createElement("ul");
      list.setAttribute("data-role", "group-members");
      inspector.appendChild(list);
    }
    for (const member of members) {
      const item = document.createElement("li");
      item.setAttribute("data-member-id", member.id);
      item.textContent = member.label || member.id;
      list.appendChild(item);
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
  }

  function hideGroupMembersInternal() {
    inspector.hidden = true;
    inspector.textContent = "";
  }

  function render(mapData) {
    currentMapData = mapData;
    currentPositions = computeLayout(mapData.nodes);
    cancelActiveAnimations();

    const existingIds = new Set(
      Array.from(camera.children).map((el) => el.getAttribute("data-node-id"))
    );
    const nextIds = new Set(mapData.nodes.map((n) => n.id));

    // Remove nodes no longer present (filtered out / project switched).
    for (const child of Array.from(camera.children)) {
      const id = child.getAttribute("data-node-id");
      if (id && !nextIds.has(id)) camera.removeChild(child);
    }

    // Edges first (drawn under nodes), cleared and rebuilt each render --
    // edge count is bounded (<=400) so this stays cheap.
    let edgeLayer = camera.querySelector('[data-role="edges"]');
    if (!edgeLayer) {
      edgeLayer = document.createElementNS(SVG_NS, "g");
      edgeLayer.setAttribute("data-role", "edges");
      camera.insertBefore(edgeLayer, camera.firstChild);
    }
    edgeLayer.textContent = "";
    for (const edge of mapData.edges) {
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
          animate(
            path,
            [{ strokeDashoffset: String(length) }, { strokeDashoffset: "0" }],
            {
              duration: motion.relationship_reveal_ms,
              easing: motion.easing,
              fill: "forwards",
            }
          );
        }
      }
    }

    for (const node of mapData.nodes) {
      if (existingIds.has(node.id)) continue;
      const position = currentPositions.get(node.id) || { x: 0, y: 0 };
      const element = buildNodeElement(node, position);
      camera.appendChild(element);
      if (!reducedMotion) {
        animate(element, [{ opacity: 0 }, { opacity: 1 }], {
          duration: motion.relationship_reveal_ms,
          easing: motion.easing,
          fill: "forwards",
        });
      }
    }
  }

  function setFiltersInternal(_filters) {
    // Filtering is server-side (build_project_map's node_types/severity/
    // status/query params); the caller re-fetches and calls render() again
    // with the filtered map. This hook exists so application.js has one
    // stable entry point regardless of where filtering happens.
  }

  function fit() {
    cancelActiveAnimations();
    animate(camera, [{ transform: camera.style.transform || "" }, { transform: "translate(0px, 0px)" }], {
      duration: motion.camera_focus_ms,
      easing: motion.easing,
      fill: "forwards",
    });
    selectedId = null;
  }

  function destroy() {
    cancelActiveAnimations();
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
    get selectedId() {
      return selectedId;
    },
    get mapData() {
      return currentMapData;
    },
  };
}

let activeRenderer = null;

export function renderMap(container, mapData, options = {}) {
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

export function destroyMap() {
  if (activeRenderer) {
    activeRenderer.destroy();
    activeRenderer = null;
  }
}
