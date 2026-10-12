"""Character Overview: the page, its public profile, and the landing preview."""
import json
import os
from html import escape
from typing import TYPE_CHECKING, Optional, Tuple

from app.pages.icons import _wiki_icon_url
from app.pages.player import PlayerView
from app.pages.shell import _shell

if TYPE_CHECKING:
    from app.models import GameAccount


_CHARACTER_OVERVIEW_CSS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "css", "character-overview.css"
)

try:
    _CHARACTER_OVERVIEW_CSS_VERSION = int(os.path.getmtime(_CHARACTER_OVERVIEW_CSS_PATH))
except OSError:
    _CHARACTER_OVERVIEW_CSS_VERSION = 0

# Snapshot for the landing Character Overview preview: real summary, progress,
# skills and collection-log pulls in one JSON file. The 3D model is a separate
# binary asset (app/static/img/landing-character-overview-demo-model.glb) the
# preview's extra_head points the viewer at directly.
_LANDING_CHARACTER_OVERVIEW_DEMO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "landing_character_overview_demo.json"
)

_landing_character_overview_demo_data = None


def _get_landing_character_overview_demo_data() -> Optional[dict]:
    global _landing_character_overview_demo_data
    if _landing_character_overview_demo_data is None:
        try:
            with open(_LANDING_CHARACTER_OVERVIEW_DEMO_PATH, "r") as f:
                _landing_character_overview_demo_data = json.load(f)
        except (OSError, ValueError):
            return None
    return _landing_character_overview_demo_data


_ICON_SUMMARY_COMBAT_LEVEL = _wiki_icon_url("Character_Summary_-_Combat_Level_icon.png")

_ICON_SUMMARY_TOTAL_LEVEL = _wiki_icon_url("Character_Summary_-_Total_Level.png")

_ICON_SUMMARY_TOTAL_XP = _wiki_icon_url("Character_Summary_-_Total_XP_icon.png")

_ICON_SUMMARY_QUESTS = _wiki_icon_url("Quest_List_tab_icon.png")

_ICON_SUMMARY_ACHIEVEMENTS = _wiki_icon_url("Achievement_Diaries_tab_icon.png")

_ICON_SUMMARY_COMBAT_TASKS = _wiki_icon_url("Character_Summary_-_Combat_Tasks_Completed_icon.png")

_ICON_SUMMARY_COLLECTIONS = _wiki_icon_url("Character_Summary_-_Collections_Logged_icon.png")

# Account-type tile: one icon per GameAccount.account_type code (app/models.py)
# plus the all-caps value label (e.g. "UGIM"). The icon is part of the value, so
# the script (ACCOUNT_TYPE_INFO, baked from this dict) swaps the <img>
# src/alt/title once account_type is fetched. MAIN's coin is the pre-fetch
# default.
_ACCOUNT_TYPE_INFO = {
    "MAIN": (_wiki_icon_url("Coins_10000.png"), "MAIN"),
    "IRONMAN": (_wiki_icon_url("Ironman_helm.png"), "IRONMAN"),
    "UIM": (_wiki_icon_url("Ultimate_ironman_helm.png"), "UIM"),
    "HCIM": (_wiki_icon_url("Hardcore_ironman_helm.png"), "HCIM"),
    "GIM": (_wiki_icon_url("Group_ironman_helm.png"), "GIM"),
    "HCGIM": (_wiki_icon_url("Hardcore_group_ironman_helm.png"), "HCGIM"),
    "UGIM": (_wiki_icon_url("Group_ironman_helm_(unranked).png"), "UGIM"),
}

_SUMMARY_STATS = (
    # (element key, icon, alt text), all from /api/character-overview/summary
    # (GameAccount.character_summary_* plus account_type, synced by
    # MyscapeClient#syncCharacterSummary in myscape-plugin). For accountType the
    # script swaps icon and alt (see _ACCOUNT_TYPE_INFO).
    ("accountType", _ACCOUNT_TYPE_INFO["MAIN"][0], "Account type"),
    ("combatLevel", _ICON_SUMMARY_COMBAT_LEVEL, "Combat level"),
    ("totalLevel", _ICON_SUMMARY_TOTAL_LEVEL, "Total level"),
    ("totalXp", _ICON_SUMMARY_TOTAL_XP, "Total experience"),
    ("quests", _ICON_SUMMARY_QUESTS, "Quests completed"),
    ("achievements", _ICON_SUMMARY_ACHIEVEMENTS, "Achievements completed"),
    ("combatTasks", _ICON_SUMMARY_COMBAT_TASKS, "Combat tasks completed"),
    ("collections", _ICON_SUMMARY_COLLECTIONS, "Collections logged"),
)

_SKILL_GRID_ORDER = (
    # Row-major order for the 3x8 skill card in render_character_overview,
    # matching the in-game Skills tab. Sailing (the 24th skill) takes the slot
    # of the omitted "Total level" footer. SKILL_NAMES (app/mindmaps.py) is a
    # set, so this tuple holds the order.
    "attack", "hitpoints", "mining",
    "strength", "agility", "smithing",
    "defence", "herblore", "fishing",
    "ranged", "thieving", "cooking",
    "prayer", "crafting", "firemaking",
    "magic", "fletching", "woodcutting",
    "runecraft", "slayer", "farming",
    "construction", "hunter", "sailing",
)

# Backgrounds the shuffle button picks from (app/static/img/model-viewer-bg/):
# decorative, same for every player. Index 0 is the first-visit default; order
# otherwise doesn't matter.
_MODEL_VIEWER_BACKGROUNDS = (
    "/static/img/model-viewer-bg/castle-courtyard.jpg",
    "/static/img/model-viewer-bg/garden-bridge.jpg",
    "/static/img/model-viewer-bg/scene-01.jpg",
    "/static/img/model-viewer-bg/scene-02.jpg",
    "/static/img/model-viewer-bg/scene-03.jpg",
    "/static/img/model-viewer-bg/scene-04.jpg",
    "/static/img/model-viewer-bg/scene-05.jpg",
    "/static/img/model-viewer-bg/scene-06.jpg",
    "/static/img/model-viewer-bg/scene-07.jpg",
    "/static/img/model-viewer-bg/scene-08.jpg",
    "/static/img/model-viewer-bg/scene-09.jpg",
    "/static/img/model-viewer-bg/scene-10.jpg",
    "/static/img/model-viewer-bg/scene-11.jpg",
    "/static/img/model-viewer-bg/scene-12.jpg",
    "/static/img/model-viewer-bg/scene-13.jpg",
    "/static/img/model-viewer-bg/scene-14.jpg",
    "/static/img/model-viewer-bg/scene-15.jpg",
    "/static/img/model-viewer-bg/scene-16.jpg",
    "/static/img/model-viewer-bg/scene-17.jpg",
    "/static/img/model-viewer-bg/scene-18.jpg",
    "/static/img/model-viewer-bg/scene-19.jpg",
    "/static/img/model-viewer-bg/scene-20.jpg",
    "/static/img/model-viewer-bg/scene-21.jpg",
    "/static/img/model-viewer-bg/scene-22.jpg",
    "/static/img/model-viewer-bg/scene-23.jpg",
    "/static/img/model-viewer-bg/scene-24.jpg",
    "/static/img/model-viewer-bg/scene-25.jpg",
    "/static/img/model-viewer-bg/scene-26.jpg",
    "/static/img/model-viewer-bg/scene-27.jpg",
    "/static/img/model-viewer-bg/scene-28.jpg",
    "/static/img/model-viewer-bg/scene-29.jpg",
    "/static/img/model-viewer-bg/scene-30.jpg",
    "/static/img/model-viewer-bg/scene-31.jpg",
    "/static/img/model-viewer-bg/scene-32.jpg",
    "/static/img/model-viewer-bg/scene-33.jpg",
    "/static/img/model-viewer-bg/scene-34.jpg",
    "/static/img/model-viewer-bg/scene-35.jpg",
    "/static/img/model-viewer-bg/scene-36.jpg",
    "/static/img/model-viewer-bg/scene-37.jpg",
    "/static/img/model-viewer-bg/scene-38.jpg",
    "/static/img/model-viewer-bg/scene-39.jpg",
    "/static/img/model-viewer-bg/scene-40.jpg",
    "/static/img/model-viewer-bg/scene-41.jpg",
    "/static/img/model-viewer-bg/scene-42.jpg",
    "/static/img/model-viewer-bg/scene-43.jpg",
    "/static/img/model-viewer-bg/scene-44.jpg",
    "/static/img/model-viewer-bg/scene-45.jpg",
    "/static/img/model-viewer-bg/scene-46.jpg",
    "/static/img/model-viewer-bg/scene-47.jpg",
    "/static/img/model-viewer-bg/scene-48.jpg",
    "/static/img/model-viewer-bg/scene-49.jpg",
    "/static/img/model-viewer-bg/scene-50.jpg",
    "/static/img/model-viewer-bg/scene-51.jpg",
    "/static/img/model-viewer-bg/scene-52.jpg",
    "/static/img/model-viewer-bg/scene-53.jpg",
    "/static/img/model-viewer-bg/scene-54.jpg",
    "/static/img/model-viewer-bg/scene-55.jpg",
    "/static/img/model-viewer-bg/scene-56.jpg",
    "/static/img/model-viewer-bg/scene-57.jpg",
    "/static/img/model-viewer-bg/scene-58.jpg",
    "/static/img/model-viewer-bg/scene-59.jpg",
    "/static/img/model-viewer-bg/scene-60.jpg",
    "/static/img/model-viewer-bg/scene-61.jpg",
    "/static/img/model-viewer-bg/scene-62.jpg",
    "/static/img/model-viewer-bg/scene-63.jpg",
    "/static/img/model-viewer-bg/scene-64.jpg",
    "/static/img/model-viewer-bg/scene-65.jpg",
    "/static/img/model-viewer-bg/scene-66.jpg",
    "/static/img/model-viewer-bg/scene-67.jpg",
    "/static/img/model-viewer-bg/scene-68.jpg",
    "/static/img/model-viewer-bg/scene-69.jpg",
    "/static/img/model-viewer-bg/scene-70.jpg",
    "/static/img/model-viewer-bg/scene-71.jpg",
    "/static/img/model-viewer-bg/scene-72.jpg",
    "/static/img/model-viewer-bg/scene-73.jpg",
    "/static/img/model-viewer-bg/scene-74.jpg",
    "/static/img/model-viewer-bg/scene-75.jpg",
)

_MODEL_VIEWER_HEAD = """
<script type="importmap">
{
  "imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.169.0/examples/jsm/"
  }
}
</script>
<script type="module">
  import * as THREE from "three";
  import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
  import { OrbitControls } from "three/addons/controls/OrbitControls.js";

  (function () {
    var wrap = document.getElementById("modelViewerCanvasWrap");
    var canvas = document.getElementById("modelViewerCanvas");
    var emptyEl = document.getElementById("modelViewerEmpty");
    if (!wrap || !canvas) return;

    var bgEl = document.getElementById("modelViewerBg");
    var bgShuffleBtn = document.getElementById("mvBgShuffleBtn");
    var playPauseBtn = document.getElementById("mvPlayPauseBtn");
    var playIcon = document.getElementById("mvPlayIcon");
    var pauseIcon = document.getElementById("mvPauseIcon");
    var resetBtn = document.getElementById("mvResetBtn");

    // Backdrop behind the alpha:true canvas, changed by the shuffle button; a
    // plain <div> since it never interacts with the three.js scene (see
    // .model-viewer-bg in character-overview.css).
    var MODEL_VIEWER_BACKGROUNDS = __MODEL_VIEWER_BACKGROUNDS_JSON__;
    // Persists the chosen background: localStorage for first paint, then the
    // account's saved pick (GameAccount.model_viewer_background_index, via
    // applyModelViewerBackgroundFromServer) so devices agree. A null key
    // (__MODEL_VIEWER_BG_STORAGE_KEY_JSON__) disables persistence; the landing
    // preview uses it to always start on index 0.
    var MODEL_VIEWER_BG_STORAGE_KEY = __MODEL_VIEWER_BG_STORAGE_KEY_JSON__;
    var bgIndex = 0;
    if (MODEL_VIEWER_BG_STORAGE_KEY) {
      try {
        var storedBgIndex = parseInt(localStorage.getItem(MODEL_VIEWER_BG_STORAGE_KEY), 10);
        if (!isNaN(storedBgIndex) && storedBgIndex >= 0 && storedBgIndex < MODEL_VIEWER_BACKGROUNDS.length) {
          bgIndex = storedBgIndex;
        }
      } catch (e) {
        // localStorage can throw (private browsing, disabled storage); the
        // index-0 default is fine then.
      }
    }

    function applyBackground() {
      if (bgEl && MODEL_VIEWER_BACKGROUNDS.length) {
        bgEl.style.backgroundImage = 'url("' + MODEL_VIEWER_BACKGROUNDS[bgIndex] + '")';
      }
    }
    applyBackground();

    function shuffleBackground() {
      if (MODEL_VIEWER_BACKGROUNDS.length < 2) return;
      var next = bgIndex;
      while (next === bgIndex) {
        next = Math.floor(Math.random() * MODEL_VIEWER_BACKGROUNDS.length);
      }
      bgIndex = next;
      applyBackground();
      if (MODEL_VIEWER_BG_STORAGE_KEY) {
        try {
          localStorage.setItem(MODEL_VIEWER_BG_STORAGE_KEY, String(bgIndex));
        } catch (e) {}
      }
      // Fire-and-forget sync to GameAccount.model_viewer_background_index so
      // public-profile visitors see the current pick (see
      // applyServerBackground). Requiring the real page's exact storage key
      // keeps this off the landing preview (null key) and public views (per-code
      // key).
      if (MODEL_VIEWER_BG_STORAGE_KEY === "myscape.modelViewerBgIndex") {
        fetch("/api/players/me/model-viewer-background", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ index: bgIndex }),
        }).catch(function () {
        });
      }
    }
    if (bgShuffleBtn) bgShuffleBtn.addEventListener("click", shuffleBackground);

    // Lets the wrapper script (outside this IIFE) push the owner's synced
    // background (from /api/public/<code>/summary) into the viewer. Only
    // render_public_character_overview's wrapper_script calls it, since public
    // visitors have no shuffle button or saved history.
    function applyModelViewerBackgroundFromServer(index) {
      if (typeof index !== "number" || isNaN(index) || index < 0 || index >= MODEL_VIEWER_BACKGROUNDS.length) {
        return;
      }
      bgIndex = index;
      applyBackground();
      // On the signed-in page, keep this browser's copy in step with the
      // account's so the next load doesn't flash a stale image first.
      if (MODEL_VIEWER_BG_STORAGE_KEY === "myscape.modelViewerBgIndex") {
        try {
          localStorage.setItem(MODEL_VIEWER_BG_STORAGE_KEY, String(index));
        } catch (e) {}
      }
    }
    window.myscapeApplyModelViewerBackground = applyModelViewerBackgroundFromServer;
    // This module script is deferred, but the wrapper's classic <script> runs
    // synchronously, so its fetch shim can call
    // window.myscapeApplyModelViewerBackground before it exists. The wrapper
    // also stashes the value in window.__myscapePendingModelViewerBg for this to
    // pick up, so whichever finishes second wins.
    if (typeof window.__myscapePendingModelViewerBg !== "undefined") {
      applyModelViewerBackgroundFromServer(window.__myscapePendingModelViewerBg);
    }

    // Syncs the play/pause button's SVGs and title/aria-label with a boolean;
    // shared by the play/pause and reset buttons (wired in initViewer).
    function setPlayPauseIcon(paused) {
      // `.hidden = x` is a no-op on inline <svg> in some browsers (it only
      // creates an expando), so set/remove the real attribute that the [hidden]
      // UA rule uses.
      function setHidden(el, isHidden) {
        if (!el) return;
        if (isHidden) el.setAttribute("hidden", "");
        else el.removeAttribute("hidden");
      }
      setHidden(playIcon, !paused);
      setHidden(pauseIcon, paused);
      if (playPauseBtn) {
        var label = paused ? "Play rotation" : "Pause rotation";
        playPauseBtn.setAttribute("data-tooltip", label);
        playPauseBtn.setAttribute("aria-label", label);
      }
    }

    function showEmpty(message) {
      wrap.style.display = "none";
      if (emptyEl) {
        if (message) emptyEl.textContent = message;
        emptyEl.style.display = "block";
      }
    }

    // GET /api/character-overview/model (app/main.py) serves the .glb uploaded
    // by MyscapeClient#syncCharacterModel; 404 until the plugin's "Export 3D
    // model" has been used. The landing preview substitutes a static URL via
    // __MODEL_VIEWER_MODEL_URL_JSON__ (see _character_overview_panel_markup), so
    // it needs no fetch shim.
    var MODEL_VIEWER_MODEL_URL = __MODEL_VIEWER_MODEL_URL_JSON__;
    fetch(MODEL_VIEWER_MODEL_URL)
      .then(function (r) {
        if (r.status === 404) {
          // No captured model: fall back to a shared static default model so the
          // viewer always shows something. The info popup explains how to
          // replace it.
          return fetch("/static/models/default-character.glb").then(function (r2) {
            return r2.ok ? r2.arrayBuffer() : Promise.reject();
          });
        }
        return r.ok ? r.arrayBuffer() : Promise.reject();
      })
      .then(function (buffer) {
        if (buffer) initViewer(buffer);
      })
      .catch(function (err) {
        // Log the real failure reason (network error, bad response) so a missing
        // model is diagnosable.
        if (window.console) console.error("[model-viewer] failed to fetch the model:", err);
        showEmpty("Could not load your 3D model right now.");
      });

    function initViewer(buffer) {
      var scene = new THREE.Scene();

      var camera = new THREE.PerspectiveCamera(35, wrap.clientWidth / wrap.clientHeight, 0.1, 1000);
      camera.position.set(0, 1.6, 3.2);

      var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(wrap.clientWidth, wrap.clientHeight);

      // A lost WebGL context (driver reset, too many contexts) would leave the
      // canvas blank with no sign. event.preventDefault() in the lost handler
      // lets the browser restore it; three.js re-uploads on the next render, so
      // restore only logs.
      var contextLost = false;
      canvas.addEventListener("webglcontextlost", function (event) {
        event.preventDefault();
        contextLost = true;
        if (window.console) console.warn("[model-viewer] WebGL context lost -- waiting to see if the browser restores it");
      });
      canvas.addEventListener("webglcontextrestored", function () {
        contextLost = false;
        if (window.console) console.warn("[model-viewer] WebGL context restored -- resuming rendering");
      });

      var controls = new OrbitControls(camera, renderer.domElement);
      controls.target.set(0, 1, 0);
      controls.enableDamping = true;
      // Panning is off: right-click would pan the camera off the character.
      controls.enablePan = false;
      // Zoom is off: the camera is framed once at a fixed distance.
      controls.enableZoom = false;
      // Dragging is off since autoRotate drives the camera (the canvas cursor
      // rule in character-overview.css drops the grab cursor too).
      controls.enableRotate = false;
      // Slow continuous spin instead of user orbit. autoRotate only turns the
      // azimuth, so DEFAULT_VERTICAL_TILT holds. It ignores enableRotate but
      // respects min/maxAzimuthAngle (left unset for a full revolution), and is
      // paced by elapsed time, independent of refresh rate.
      controls.autoRotate = true;
      var ROTATION_SECONDS_PER_REVOLUTION = 45;
      controls.autoRotateSpeed = 60 / ROTATION_SECONDS_PER_REVOLUTION;

      var loader = new GLTFLoader();
      loader.parse(
        buffer,
        "",
        function (gltf) {
          var model = gltf.scene;
          scene.add(model);

          // Per-face render-priority handling. OSRS paints faces in priority
          // order rather than depth-testing, so gear modeled flush against the
          // body (cape, necklace) can sit slightly inside what it layers on and
          // still draw on top. The export (ModelMeshBuilder/GlbWriter in
          // myscape-plugin) carries each primitive's priority as glTF extras,
          // which GLTFLoader copies onto geometry.userData.
          //
          // To emulate that, nudge each tagged primitive's view-space Z by a
          // fixed world-unit amount via a vertex-shader patch
          // (Material#onBeforeCompile), keeping the depth test on so unrelated
          // gaps stay ordered. renderOrder only breaks exact ties, depthTest =
          // false breaks self-occlusion, and polygonOffset uses non-linear
          // units. This is RuneProfile's technique
          // (packages/model-renderer/src/priority-offset.ts), with one
          // per-material uniform instead of a per-vertex attribute since the
          // exporter splits each (texture, priority, bias, translucent)
          // combination into its own primitive.
          //
          // Step and cap are RuneProfile's tuned constants: 3 game units per
          // priority step, capped at 6 steps. No 1/128 root scale here, so the
          // raw game-unit step is used. The missing-texture dimming below is
          // unrelated to priority.
          var PRIORITY_STEP_GAME_UNITS = 3.0;
          var PRIORITY_MAX_STEPS = 6;
          // Fixed, not user-adjustable: half of RuneProfile's tuned 1.0, for a
          // gentler nudge.
          var PRIORITY_NUDGE_MULTIPLIER = 0.5;

          function applyPriorityNudge(material, nudge) {
            material.onBeforeCompile = function (shader) {
              shader.uniforms.uPriorityNudge = { value: nudge };
              shader.vertexShader = shader.vertexShader
                .replace(
                  "#include <common>",
                  "#include <common>\\nuniform float uPriorityNudge;"
                )
                .replace(
                  "#include <project_vertex>",
                  [
                    "vec4 mvPosition = vec4( transformed, 1.0 );",
                    "#ifdef USE_BATCHING",
                    "	mvPosition = batchingMatrix * mvPosition;",
                    "#endif",
                    "#ifdef USE_INSTANCING",
                    "	mvPosition = instanceMatrix * mvPosition;",
                    "#endif",
                    "mvPosition = modelViewMatrix * mvPosition;",
                    // View space looks down -Z, so adding moves the vertex
                    // toward the camera.
                    "mvPosition.z += uPriorityNudge;",
                    "gl_Position = projectionMatrix * mvPosition;",
                  ].join("\\n")
                );
            };
            // Three keys its program cache on shader source, which
            // onBeforeCompile changes identically for every nudged material, so
            // a constant key shares one program.
            material.customProgramCacheKey = function () {
              return "osrs-priority-nudge";
            };
            material.needsUpdate = true;
          }

          model.traverse(function (node) {
            if (!node.isMesh || !node.geometry) return;
            if (node.material) {
              // GlbWriter always exports doubleSided: true, but the OSRS client
              // culls back faces, and thin cloth (a cape) is two coincident,
              // oppositely wound surfaces where culling picks the right one.
              // Double-sided z-fights them, so force FrontSide (as RuneProfile's
              // load-model.ts does), plus the depthWrite fix below.
              node.material.side = THREE.FrontSide;
              if (node.material.transparent) {
                node.material.depthWrite = false;
              }
            }
            if (!node.geometry.userData) return;
            var priority = node.geometry.userData.osrsPriority || 0;
            var bias = node.geometry.userData.osrsBias || 0;
            var missingTexture = !!node.geometry.userData.missingTexture;
            if ((priority !== 0 || bias !== 0 || missingTexture) && node.material) {
              node.material = node.material.clone();
              if (priority !== 0 || bias !== 0) {
                if (priority !== 0) {
                  var nudge = Math.min(priority, PRIORITY_MAX_STEPS) * PRIORITY_STEP_GAME_UNITS * PRIORITY_NUDGE_MULTIPLIER;
                  applyPriorityNudge(node.material, nudge);
                }
                if (window.console) {
                  console.log("[osrs-priority-debug]", {
                    name: node.name || "(unnamed)",
                    priority: priority,
                    bias: bias,
                  });
                }
              }
              if (missingTexture) {
                // The plugin couldn't capture this primitive's texture (see
                // GlbWriter/ModelExporter), leaving only COLOR_0 (lightness, no
                // hue): a bright near-white patch. Mute it to dim gray so it
                // reads as an unknown texture. Rarely triggers.
                node.material.color.setRGB(0.35, 0.35, 0.35);
                if (window.console) {
                  console.log("[osrs-missing-texture]", { name: node.name || "(unnamed)" });
                }
              }
            }
          });

          // Translucent draw order. Translucent primitives have depthWrite=false
          // and share one origin, so three.js draws them in creation order and
          // the last drawn lands on top even if behind (e.g. the Bow of
          // Faerdhinen's limbs behind translucent armor). As RuneProfile does,
          // fold every plain translucent primitive into one mesh and re-sort its
          // triangles back-to-front each draw; the priority nudge becomes a
          // per-vertex attribute and part of the sort key. Textured ones, and
          // any a merged mesh can't carry, are left as they were.
          (function mergeTranslucent() {
            var candidates = [];
            model.traverse(function (node) {
              if (!node.isMesh || !node.geometry || !node.material) return;
              var m = node.material;
              if (Array.isArray(m) || !m.transparent || m.map) return;
              var g = node.geometry;
              if (!g.attributes.position || !g.attributes.color) return;
              if (g.userData && g.userData.missingTexture) return;
              if (!node.parent || !node.matrix.equals(new THREE.Matrix4())) return;
              candidates.push(node);
            });
            if (candidates.length < 2) return;
            var parent = candidates[0].parent;
            candidates = candidates.filter(function (n) { return n.parent === parent; });
            if (candidates.length < 2) return;

            var positions = [];
            var colors = [];
            var nudges = [];
            var tris = [];
            var base = 0;
            candidates.forEach(function (node) {
              var g = node.geometry;
              var p = g.attributes.position;
              var c = g.attributes.color;
              var m = node.material;
              var priority = (g.userData && g.userData.osrsPriority) || 0;
              var nudge = Math.min(priority, PRIORITY_MAX_STEPS) * PRIORITY_STEP_GAME_UNITS * PRIORITY_NUDGE_MULTIPLIER;
              for (var i = 0; i < p.count; i++) {
                positions.push(p.getX(i), p.getY(i), p.getZ(i));
                colors.push(
                  c.getX(i) * m.color.r,
                  c.getY(i) * m.color.g,
                  c.getZ(i) * m.color.b,
                  (c.itemSize === 4 ? c.getW(i) : 1) * m.opacity
                );
                nudges.push(nudge);
              }
              var idx = g.index;
              var count = idx ? idx.count : p.count;
              for (var j = 0; j < count; j += 3) {
                tris.push(idx
                  ? [base + idx.getX(j), base + idx.getX(j + 1), base + idx.getX(j + 2)]
                  : [base + j, base + j + 1, base + j + 2]);
              }
              base += p.count;
            });
            if (!tris.length) return;

            var geometry = new THREE.BufferGeometry();
            geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
            geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 4));
            geometry.setAttribute("aPriorityNudge", new THREE.Float32BufferAttribute(nudges, 1));
            var indexArray = new Uint32Array(tris.length * 3);
            var indexAttr = new THREE.BufferAttribute(indexArray, 1);
            indexAttr.setUsage(THREE.DynamicDrawUsage);
            geometry.setIndex(indexAttr);

            var material = candidates[0].material.clone();
            material.color.setRGB(1, 1, 1);
            material.opacity = 1;
            material.side = THREE.FrontSide;
            material.transparent = true;
            material.depthWrite = false;
            material.vertexColors = true;
            material.onBeforeCompile = function (shader) {
              shader.vertexShader = shader.vertexShader
                .replace(
                  "#include <common>",
                  "#include <common>\\nattribute float aPriorityNudge;"
                )
                .replace(
                  "#include <project_vertex>",
                  [
                    "vec4 mvPosition = vec4( transformed, 1.0 );",
                    "mvPosition = modelViewMatrix * mvPosition;",
                    "mvPosition.z += aPriorityNudge;",
                    "gl_Position = projectionMatrix * mvPosition;",
                  ].join("\\n")
                );
            };
            material.customProgramCacheKey = function () {
              return "osrs-priority-nudge-attr";
            };
            material.needsUpdate = true;

            var triCount = tris.length;
            var centroids = new Float32Array(triCount * 3);
            var triNudge = new Float32Array(triCount);
            for (var t = 0; t < triCount; t++) {
              var a = tris[t][0], b = tris[t][1], d = tris[t][2];
              for (var k = 0; k < 3; k++) {
                centroids[t * 3 + k] = (positions[a * 3 + k] + positions[b * 3 + k] + positions[d * 3 + k]) / 3;
              }
              triNudge[t] = (nudges[a] + nudges[b] + nudges[d]) / 3;
            }
            var order = new Array(triCount);
            var depth = new Float32Array(triCount);
            var viewMatrix = new THREE.Matrix4();
            var lastView = new Float32Array(16);

            var merged = new THREE.Mesh(geometry, material);
            merged.name = "translucent_merged";
            merged.frustumCulled = false;
            merged.onBeforeRender = function (renderer, sceneArg, camera) {
              viewMatrix.multiplyMatrices(camera.matrixWorldInverse, merged.matrixWorld);
              var e = viewMatrix.elements;
              var same = true;
              for (var q = 0; q < 16; q++) {
                if (e[q] !== lastView[q]) { same = false; break; }
              }
              if (same) return;
              for (var q2 = 0; q2 < 16; q2++) lastView[q2] = e[q2];
              for (var i2 = 0; i2 < triCount; i2++) {
                order[i2] = i2;
                depth[i2] = e[2] * centroids[i2 * 3] + e[6] * centroids[i2 * 3 + 1] + e[10] * centroids[i2 * 3 + 2] + e[14] + triNudge[i2];
              }
              // View space looks down -Z: the most negative value is farthest,
              // drawn first.
              order.sort(function (x, y) { return depth[x] - depth[y]; });
              for (var i3 = 0; i3 < triCount; i3++) {
                var tri = tris[order[i3]];
                indexArray[i3 * 3] = tri[0];
                indexArray[i3 * 3 + 1] = tri[1];
                indexArray[i3 * 3 + 2] = tri[2];
              }
              indexAttr.needsUpdate = true;
            };

            candidates.forEach(function (node) {
              parent.remove(node);
              node.geometry.dispose();
              if (node.material && node.material.dispose) node.material.dispose();
            });
            parent.add(merged);
          })();

          // Frame the camera to the model's real bounding box with the standard
          // "fit object in view" distance, which works in any units. The export
          // origin isn't guaranteed to be the visual midpoint, so center/size
          // come from the geometry.
          var box = new THREE.Box3().setFromObject(model);
          var size = box.getSize(new THREE.Vector3());
          var center = box.getCenter(new THREE.Vector3());

          // Snug fit: zoom is disabled, so this is the only view. Each axis is
          // fit against its own extent (size.y vs the vertical FOV, size.x vs
          // the horizontal FOV via aspect); one largest-dimension value would
          // over-pad portrait viewports.
          var vFovHalfTan = Math.tan((Math.PI * camera.fov) / 360);
          var fitHeightDistance = Math.max(size.y, 1e-6) / (2 * vFovHalfTan);
          var fitWidthDistance = Math.max(size.x, 1e-6) / (2 * vFovHalfTan * camera.aspect);
          // 1.3 rather than a snug 1.15, leaving room for the button row
          // (.model-viewer-controls) inside the same frame.
          var CAMERA_DISTANCE_MULTIPLIER = 1.3;
          var distance = CAMERA_DISTANCE_MULTIPLIER * Math.max(fitHeightDistance, fitWidthDistance);

          // Orbit around and frame on the bounding box's geometric center.
          controls.target.copy(center);

          // Default view tilted 10 degrees down from level (polar angle below
          // 90) so more of the head top reads.
          var DEFAULT_VERTICAL_TILT = (10 * Math.PI) / 180;
          var defaultSpherical = new THREE.Spherical(distance, Math.PI / 2 - DEFAULT_VERTICAL_TILT, 0);
          camera.position.setFromSpherical(defaultSpherical).add(center);

          camera.near = distance / 100;
          camera.far = distance * 100;
          camera.updateProjectionMatrix();

          // Pan the image up via a 2D projection shift (applyVerticalFramePan,
          // near onResize), not by moving camera.position/controls.target, which
          // changes the viewing angle. setViewOffset leaves the 3D camera, and
          // what reset/pause freeze to, untouched while clearing space for
          // .model-viewer-controls.
          applyVerticalFramePan();

          // No orbit limits: nothing drags the camera, and unclamped azimuth
          // lets autoRotate complete a full revolution (DEFAULT_VERTICAL_TILT
          // holds since only azimuth changes).
          controls.update();

          // Snapshot of the framed view (post vertical shift) for the reset
          // button.
          var defaultCameraPosition = camera.position.clone();
          var defaultTarget = controls.target.clone();

          // enableDamping keeps autoRotate momentum alive briefly after it
          // switches off, which would read as a coast after pause or an offset
          // after reset. One extra update() with damping off consumes the whole
          // pending delta; damping is then restored.
          function killDampingMomentum() {
            var wasDamping = controls.enableDamping;
            controls.enableDamping = false;
            controls.update();
            controls.enableDamping = wasDamping;
          }

          if (playPauseBtn) {
            playPauseBtn.addEventListener("click", function () {
              controls.autoRotate = !controls.autoRotate;
              if (!controls.autoRotate) killDampingMomentum();
              setPlayPauseIcon(!controls.autoRotate);
            });
          }
          if (resetBtn) {
            resetBtn.addEventListener("click", function () {
              // Drain leftover autoRotate momentum against the current position
              // first, or update() would apply a stale delta on top of the reset
              // position.
              controls.autoRotate = false;
              killDampingMomentum();
              camera.position.copy(defaultCameraPosition);
              controls.target.copy(defaultTarget);
              // Reset also pauses; spinning away again immediately would defeat
              // the point.
              setPlayPauseIcon(true);
              controls.update();
            });
          }
        },
        undefined,
        function (err) {
          // As with the fetch-level catch above: GLTFLoader passes the real
          // parse error here; log it.
          if (window.console) console.error("[model-viewer] GLTFLoader failed to parse the model:", err);
          showEmpty("Could not display your 3D model right now.");
        }
      );

      // Fraction of canvas height to pan the image up via camera.setViewOffset
      // (a post-projection shift). Passing width/height as both full frame and
      // visible size, with only offsetY nonzero, avoids any scaling.
      var VERTICAL_FRAME_PAN_FRACTION = 0.03;
      function applyVerticalFramePan() {
        var w = wrap.clientWidth;
        var h = wrap.clientHeight;
        if (w <= 0 || h <= 0) return;
        camera.setViewOffset(w, h, 0, h * VERTICAL_FRAME_PAN_FRACTION, w, h);
      }

      function onResize() {
        var w = wrap.clientWidth;
        var h = wrap.clientHeight;
        if (w <= 0 || h <= 0) return;
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
        applyVerticalFramePan();
      }
      window.addEventListener("resize", onResize);

      // animateFailed latches the first time a frame throws (context loss is
      // handled via contextLost): log once and freeze on the last good frame
      // rather than throwing every frame.
      var animateFailed = false;
      (function animate() {
        requestAnimationFrame(animate);
        if (contextLost || animateFailed) return;
        try {
          controls.update();
          renderer.render(scene, camera);
        } catch (err) {
          animateFailed = true;
          if (window.console) console.error("[model-viewer] render loop failed:", err);
        }
      })();
    }
  })();
</script>
"""


def _character_overview_panel_markup(preview: bool = False, public_code: Optional[str] = None, public_character_name: Optional[str] = None) -> Tuple[str, str, str]:
    """Character Overview's real body/script, split out so the landing preview
    (render_landing_character_overview_preview) can reuse it verbatim.
    render_character_overview is this plus a _shell(...) call.
    
    preview=True (landing preview only) renders the same six sections; only
    two extra_head _MODEL_VIEWER_HEAD substitutions differ (background storage
    key and model-fetch URL), so the viewer opens on the default courtyard
    with the frozen demo model.
    
    public_code (render_public_character_overview only, never with preview)
    points those substitutions at another account's live model: GET
    /api/public/<code>/model and a per-code background key
    (myscape.modelViewerBgIndex.public.<code>). The owner-only settings card
    (public_profile_settings_btn) is omitted here and in preview.
    
    public_character_name (only with public_code) replaces the <h2> with the
    visited character's name; it is escape()'d like other player-controlled
    strings.
    
    Summary row (.co-summary-row): eight icon+stat pairs (_SUMMARY_STATS), alt
    text as hover tooltip (accountType excepted, see _ACCOUNT_TYPE_INFO).
    Values start as em dashes and are filled from
    /api/character-overview/summary. Combat level is rounded and total level
    has no thousands separator, unlike formatInt.
    
    Skills card (.skills-card in .co-left-col): 3x8 grid of .skill-cell in
    _SKILL_GRID_ORDER, each level a fixed 3ch wide. Shows VIRTUAL levels
    (levelForXp; xp table duplicated from Mindmaps), so maxed reads 126. Icons
    are app/static/skill-icons; data from GET /api/players/me/skills. Cells
    link to the wiki in a new tab; data-tooltip (.myscape-tooltip, _shell's
    shared_script) starts as the skill name and gains XP in setSkillTooltip.
    
    The collection log card (.clog-card) sits beside .co-left-col in
    .co-main-row; see character-overview.css.
    """
    stat_tiles = "\n      ".join(
        f"""<div class="co-stat">
        <img class="co-stat-icon" src="{escape(icon)}" alt="{escape(alt)}" data-tooltip="{escape(alt)}" {f'id="co-icon-{key}"' if key == "accountType" else ""} />
        <div class="co-stat-value" id="co-{key}">&mdash;</div>
      </div>"""
        for key, icon, alt in _SUMMARY_STATS
    )

    skill_cells = "\n      ".join(
        f"""<a class="skill-cell" id="skill-cell-{key}" data-tooltip="{key.capitalize()}" href="https://oldschool.runescape.wiki/w/{key.capitalize()}" target="_blank" rel="noopener">
        <img class="skill-cell-icon" src="/static/skill-icons/{key}.png" alt="{key.capitalize()}" />
        <span class="skill-cell-level" id="skill-{key}">&mdash;</span>
      </a>"""
        for key in _SKILL_GRID_ORDER
    )

    # Skills/Quests/Achievement Diaries/Combat Achievements (.co-quad-row)
    # render unconditionally, including in the landing preview, whose fetch shim
    # answers GET /api/character-overview/progress and /api/players/me/skills
    # (DEMO_PROGRESS / DEMO_SKILLS).
    quad_row_section = f"""
    <div class="co-quad-row" id="coQuadRow">
      <div class="skills-card" id="skillsCard">
        <div class="skills-grid">
          {skill_cells}
        </div>
      </div>

      <div class="quests-card" id="questsCard">
        <div class="quests-empty" id="questsEmpty">No quest data yet &mdash; open your quest list in-game with the myscape RuneLite plugin running, then refresh this page.</div>
        <div class="quests-list" id="questsList"></div>
      </div>

      <div class="diaries-card" id="diariesCard">
        <div class="diaries-list" id="diariesList"></div>
      </div>

      <div class="ca-card" id="caCard">
        <div class="ca-list" id="caList"></div>
      </div>
    </div>"""

    # The "i" tooltip and shuffle-background buttons are omitted for public_code
    # visitors (kept in preview as marketing): the plugin hint doesn't apply to
    # them and shuffling only changes their local pick. Omitting the markup is
    # safe because the script guards `if (bgShuffleBtn)`; the "i" button needs
    # no guard since its data-tooltip is read by the shared hover listener.
    mv_info_btn = "" if public_code else '<button class="model-viewer-btn" id="mvInfoBtn" type="button" data-tooltip="Set your character model in the myscape\nplugin sidebar on RuneLite." aria-label="Set your character model in the myscape\nplugin sidebar on RuneLite."><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="11"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg></button>'
    mv_shuffle_btn = "" if public_code else '<button class="model-viewer-btn" id="mvBgShuffleBtn" type="button" data-tooltip="Shuffle background" aria-label="Shuffle background"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 3 21 3 21 8"></polyline><line x1="4" y1="20" x2="21" y2="3"></line><polyline points="21 16 21 21 16 21"></polyline><line x1="15" y1="15" x2="21" y2="21"></line><line x1="4" y1="4" x2="9" y2="9"></line></svg></button>'

    # Owner's settings cog, absent in preview and public_code modes. The script
    # guards on `if (publicProfileSettingsBtn)`. Looks like the Storages
    # Viewer's .pm-settings-btn (see .co-settings-btn in character-overview.css)
    # and is a cog because it is opened rarely. The private/public card is
    # appended to this same wrap span below.
    public_profile_settings_btn = "" if (preview or public_code) else (
        ' <span class="co-settings-wrap">'
        '<button type="button" class="co-settings-btn" id="publicProfileSettingsBtn" aria-label="Public profile settings" data-tooltip="Public profile settings">'
        '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M8.65 6.20 L9.54 2.82 L14.46 2.82 L15.35 6.20 L18.72 5.28 L21.18 9.54 L18.70 12.00 L21.18 14.46 L18.72 18.72 L15.35 17.80 L14.46 21.18 L9.54 21.18 L8.65 17.80 L5.28 18.72 L2.82 14.46 L5.30 12.00 L2.82 9.54 L5.28 5.28 Z"></path>'
        '<circle cx="12" cy="12" r="3.1"></circle>'
        '</svg></button>'
    )

    # Public visitors see the character's name instead of "Character Overview".
    page_heading = escape(public_character_name) if public_character_name else "Character Overview"

    # Floats under the cog (position: absolute, see .public-profile-card in
    # character-overview.css) as a sibling of publicProfileSettingsBtn in
    # .co-settings-wrap. PRIVATE/PUBLIC segmented control (markup duplicated
    # from Mindmaps' .mm-segment-group), a readonly link field and two buttons.
    if not (preview or public_code):
        public_profile_settings_btn += (
            '<div class="public-profile-card" id="publicProfileCard" hidden>'
            '<div class="public-profile-seg-group">'
            '<button type="button" class="public-profile-seg-btn active" id="publicProfileSegPrivate" data-segment-value="private" data-tooltip="Makes your profile invisible to everyone\n(except those on your friends list)" data-tooltip-wide>Private</button>'
            '<button type="button" class="public-profile-seg-btn" id="publicProfileSegPublic" data-segment-value="public" data-tooltip="Makes your profile visible\nto anyone with your URL">Public</button>'
            '</div>'
            '<button type="button" class="public-profile-link-btn public-profile-link-display" id="publicProfileLinkBtn" disabled></button>'
            '<button class="public-profile-link-btn" id="publicProfileRegenerateBtn" type="button" data-tooltip="Generating a new link will render your old link\nobsolete. You can do this once every 24 hours.">Generate new link</button>'
            '</div>'
            '</span>'
        )

    body = f"""
    <h2 class="page-title">{page_heading}{public_profile_settings_btn}</h2>

    <div class="co-summary-row" id="coSummaryRow">
      {stat_tiles}
    </div>

    <div class="co-main-row">
      <div class="co-left-col">
        <div class="model-viewer-card" id="modelViewerCard">
          <div class="model-viewer-canvas-wrap" id="modelViewerCanvasWrap">
            <div class="model-viewer-bg" id="modelViewerBg"></div>
            <canvas id="modelViewerCanvas"></canvas>
            <div class="model-viewer-controls" id="modelViewerControls">
              {mv_info_btn}
              {mv_shuffle_btn}
              <button class="model-viewer-btn" id="mvPlayPauseBtn" type="button" data-tooltip="Pause rotation" aria-label="Pause rotation"><svg id="mvPlayIcon" width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none" hidden><polygon points="6 3 20 12 6 21 6 3"></polygon></svg><svg id="mvPauseIcon" width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg></button>
              <button class="model-viewer-btn" id="mvResetBtn" type="button" data-tooltip="Reset rotation" aria-label="Reset rotation"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg></button>
            </div>
          </div>
          <div class="model-viewer-empty" id="modelViewerEmpty">No 3D model captured yet &mdash; use the &ldquo;Export 3D model&rdquo; button in the myscape RuneLite plugin&rsquo;s sidebar, then refresh this page.</div>
        </div>
      </div>

      <div class="clog-card" id="clogCard">
        <div class="clog-empty" id="clogEmpty">No collection log data yet &mdash; open your collection log in-game with the myscape RuneLite plugin running, then refresh this page.</div>
        <div class="clog-body" id="clogBody">
          <div class="clog-toolbar">
            <div class="clog-tabs-wrap" id="clogTabsWrap">
              <div class="clog-tabs" id="clogTabs"></div>
              <span class="clog-tabs-arrow clog-tabs-arrow--left" aria-hidden="true"></span>
              <span class="clog-tabs-arrow clog-tabs-arrow--right" aria-hidden="true"></span>
            </div>
            <button class="clog-sync-btn" id="clogSyncBtn" type="button" data-tooltip="Refresh kill counts from official hiscores"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg></button>
          </div>
          <div class="clog-panes">
            <div class="clog-pages" id="clogPages"></div>
            <div class="clog-items-col" id="clogItemsCol">
              <div class="clog-items-header" id="clogItemsHeader"></div>
              <div class="clog-items" id="clogItems"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
    {quad_row_section}
    """

    script = """
    (function () {
      function formatInt(n) {
        return Math.round(n || 0).toLocaleString('en-US');
      }
      // Like formatInt but without thousands separators (combat/total level).
      function formatIntPlain(n) {
        return String(Math.round(n || 0));
      }
      function setStat(key, text) {
        var el = document.getElementById('co-' + key);
        if (el) el.textContent = text;
      }
      function setFraction(key, completed, total) {
        if (completed == null || total == null) return;
        setStat(key, formatInt(completed) + ' / ' + formatInt(total));
      }
      // (icon url, label) per GameAccount.account_type code, see
      // _ACCOUNT_TYPE_INFO in app/pages/. The accountType tile is the only one
      // whose icon is swapped; MAIN's coin icon is the pre-fetch default.
      var ACCOUNT_TYPE_INFO = __ACCOUNT_TYPE_INFO_JSON__;
      function setAccountType(code) {
        var info = code != null ? ACCOUNT_TYPE_INFO[code] : null;
        if (!info) return;
        var icon = document.getElementById('co-icon-accountType');
        if (icon) {
          icon.src = info[0];
          icon.alt = info[1];
          // data-tooltip is not swapped: it always reads the fixed "Account
          // type" label from the static markup (stat_tiles).
        }
        setStat('accountType', info[1]);
      }
      // OSRS xp-per-level curve for levels 1-126 (virtual levels past 99): xp(L)
      // = floor(1/4 * sum[l=1..L-1] of floor(l + 300*2^(l/7))), see
      // https://oldschool.runescape.wiki/w/Experience. Duplicated from
      // SKILL_XP_TABLE in Mindmaps' script. Index 0 is unused; SKILL_XP_TABLE[1]
      // is 0.
      var SKILL_XP_TABLE = (function () {
        var table = [0, 0];
        var cumulative = 0;
        for (var l = 1; l < 126; l++) {
          cumulative += Math.floor(l + 300 * Math.pow(2, l / 7));
          table[l + 1] = Math.floor(cumulative / 4);
        }
        return table;
      })();
      // Largest (virtual) level whose requirement is at or below xp, like
      // levelForXp in Mindmaps' script. Used instead of GameAccount.skills'
      // capped level so maxed skills read 126.
      function levelForXp(xp) {
        for (var l = 126; l >= 1; l--) {
          if (xp >= SKILL_XP_TABLE[l]) return l;
        }
        return 1;
      }
      function setSkillLevel(key, xp) {
        if (xp == null) return;
        var el = document.getElementById('skill-' + key);
        if (el) el.textContent = String(levelForXp(xp));
      }
      // Appends XP to the cell's data-tooltip (skill name from skill_cells in
      // app/pages/) with the usual middle-dot join.
      function setSkillTooltip(key, xp) {
        var el = document.getElementById('skill-cell-' + key);
        if (!el) return;
        var name = key.charAt(0).toUpperCase() + key.slice(1);
        el.setAttribute('data-tooltip', xp != null ? name + ' · ' + formatInt(xp) + ' xp' : name);
      }

      fetch('/api/character-overview/summary')
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data) return;
          // The shuffled background is saved on the account (the shuffle button
          // POSTs it) so all devices agree; localStorage only covers first
          // paint. The pending value covers this response arriving before the
          // viewer's module script runs (__myscapePendingModelViewerBg).
          if (typeof data.modelViewerBackgroundIndex === 'number') {
            window.__myscapePendingModelViewerBg = data.modelViewerBackgroundIndex;
            if (typeof window.myscapeApplyModelViewerBackground === 'function') {
              window.myscapeApplyModelViewerBackground(data.modelViewerBackgroundIndex);
            }
          }
          setAccountType(data.accountType);
          if (data.combatLevel != null) setStat('combatLevel', formatIntPlain(data.combatLevel));
          if (data.totalLevel != null) setStat('totalLevel', formatIntPlain(data.totalLevel));
          if (data.totalXp != null) setStat('totalXp', formatInt(data.totalXp) + ' xp');
          setFraction('quests', data.questsCompleted, data.questsTotal);
          setFraction('achievements', data.achievementsCompleted, data.achievementsTotal);
          setFraction('combatTasks', data.combatTasksCompleted, data.combatTasksTotal);
          setFraction('collections', data.collectionsCompleted, data.collectionsTotal);
        })
        .catch(function () { /* leave this row's em dashes showing */ });

      // Same GameAccount.skills snapshot the Mindmaps/Goal Tracking skill picker
      // reads (/api/players/me/skills in app/main.py).
      fetch('/api/players/me/skills')
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data || !data.skills) return;
          Object.keys(data.skills).forEach(function (key) {
            var entry = data.skills[key];
            if (!entry) return;
            setSkillLevel(key, entry.xp);
            setSkillTooltip(key, entry.xp);
          });
        })
        .catch(function () { /* leave this card's em dashes showing */ });

      // Collection Log (GET /api/players/me/collection-log)

      // Quests / Achievement Diaries / Combat Achievements: one GET
      // /api/character-overview/progress feeds all three .co-quad-row cards (see
      // its docstring in app/main.py).

      // Same convention as the Mindmaps goal editor's diary-area search
      // (render_mindmaps); duplicated since the page scripts are independent.
      var DIARY_AREA_LABELS = {
        ardougne: 'Ardougne', desert: 'Desert', falador: 'Falador',
        fremennik: 'Fremennik', kandarin: 'Kandarin', karamja: 'Karamja',
        kourend_kebos: 'Kourend & Kebos', lumbridge_draynor: 'Lumbridge & Draynor',
        morytania: 'Morytania', varrock: 'Varrock',
        western_provinces: 'Western Provinces', wilderness: 'Wilderness',
      };
      // Each area's "Main reward" icon per tier (easy/medium/hard/elite,
      // matching DIARY_TIER_ORDER); renderDiaries picks the highest completed
      // tier. URLs come from the Main Reward column of the wiki's
      // Achievement_Diary "List of diaries" table, which is the only place all
      // 48 icons are available.
      var DIARY_AREA_TIER_ICON = {
        ardougne: [
          'https://oldschool.runescape.wiki/images/Ardougne_cloak_1.png',
          'https://oldschool.runescape.wiki/images/Ardougne_cloak_2.png',
          'https://oldschool.runescape.wiki/images/Ardougne_cloak_3.png',
          'https://oldschool.runescape.wiki/images/Ardougne_cloak_4.png',
        ],
        desert: [
          'https://oldschool.runescape.wiki/images/Desert_amulet_1.png',
          'https://oldschool.runescape.wiki/images/Desert_amulet_2.png',
          'https://oldschool.runescape.wiki/images/Desert_amulet_3.png',
          'https://oldschool.runescape.wiki/images/Desert_amulet_4.png',
        ],
        falador: [
          'https://oldschool.runescape.wiki/images/Falador_shield_1.png',
          'https://oldschool.runescape.wiki/images/Falador_shield_2.png',
          'https://oldschool.runescape.wiki/images/Falador_shield_3.png',
          'https://oldschool.runescape.wiki/images/Falador_shield_4.png',
        ],
        fremennik: [
          'https://oldschool.runescape.wiki/images/Fremennik_sea_boots_1.png',
          'https://oldschool.runescape.wiki/images/Fremennik_sea_boots_2.png',
          'https://oldschool.runescape.wiki/images/Fremennik_sea_boots_3.png',
          'https://oldschool.runescape.wiki/images/Fremennik_sea_boots_4.png',
        ],
        kandarin: [
          'https://oldschool.runescape.wiki/images/Kandarin_headgear_1.png',
          'https://oldschool.runescape.wiki/images/Kandarin_headgear_2.png',
          'https://oldschool.runescape.wiki/images/Kandarin_headgear_3.png',
          'https://oldschool.runescape.wiki/images/Kandarin_headgear_4.png',
        ],
        karamja: [
          'https://oldschool.runescape.wiki/images/Karamja_gloves_1.png',
          'https://oldschool.runescape.wiki/images/Karamja_gloves_2.png',
          'https://oldschool.runescape.wiki/images/Karamja_gloves_3.png',
          'https://oldschool.runescape.wiki/images/Karamja_gloves_4.png',
        ],
        kourend_kebos: [
          "https://oldschool.runescape.wiki/images/Rada%27s_blessing_1.png",
          "https://oldschool.runescape.wiki/images/Rada%27s_blessing_2.png",
          "https://oldschool.runescape.wiki/images/Rada%27s_blessing_3.png",
          "https://oldschool.runescape.wiki/images/Rada%27s_blessing_4.png",
        ],
        lumbridge_draynor: [
          "https://oldschool.runescape.wiki/images/Explorer%27s_ring_1.png",
          "https://oldschool.runescape.wiki/images/Explorer%27s_ring_2.png",
          "https://oldschool.runescape.wiki/images/Explorer%27s_ring_3.png",
          "https://oldschool.runescape.wiki/images/Explorer%27s_ring_4.png",
        ],
        morytania: [
          'https://oldschool.runescape.wiki/images/Morytania_legs_1.png',
          'https://oldschool.runescape.wiki/images/Morytania_legs_2.png',
          'https://oldschool.runescape.wiki/images/Morytania_legs_3.png',
          'https://oldschool.runescape.wiki/images/Morytania_legs_4.png',
        ],
        varrock: [
          'https://oldschool.runescape.wiki/images/Varrock_armour_1.png',
          'https://oldschool.runescape.wiki/images/Varrock_armour_2.png',
          'https://oldschool.runescape.wiki/images/Varrock_armour_3.png',
          'https://oldschool.runescape.wiki/images/Varrock_armour_4.png',
        ],
        western_provinces: [
          'https://oldschool.runescape.wiki/images/Western_banner_1.png',
          'https://oldschool.runescape.wiki/images/Western_banner_2.png',
          'https://oldschool.runescape.wiki/images/Western_banner_3.png',
          'https://oldschool.runescape.wiki/images/Western_banner_4.png',
        ],
        wilderness: [
          'https://oldschool.runescape.wiki/images/Wilderness_sword_1.png',
          'https://oldschool.runescape.wiki/images/Wilderness_sword_2.png',
          'https://oldschool.runescape.wiki/images/Wilderness_sword_3.png',
          'https://oldschool.runescape.wiki/images/Wilderness_sword_4.png',
        ],
      };
      // Shown for an area with zero tiers completed; saved locally at
      // app/static/img/diary-not-started.png.
      var DIARY_AREA_NOT_STARTED_ICON = '/static/img/diary-not-started.png';
      // In-game area order (matches the journal's tabs), not the alphabetical
      // order DIARY_AREAS/get_diary_tier_totals iterate in.
      var DIARY_AREA_ORDER = [
        'ardougne', 'desert', 'falador', 'fremennik', 'kandarin', 'karamja',
        'kourend_kebos', 'lumbridge_draynor', 'morytania', 'varrock',
        'western_provinces', 'wilderness',
      ];
      var DIARY_TIER_ORDER = ['easy', 'medium', 'hard', 'elite'];
      var CA_TIER_ORDER = ['easy', 'medium', 'hard', 'elite', 'master', 'grandmaster'];
      function titleCase(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
      function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, function (c) {
          return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
      }

      function questWikiUrl(name) {
        return 'https://oldschool.runescape.wiki/w/' + encodeURIComponent(String(name).replace(/ /g, '_'));
      }
      function renderQuests(quests) {
        var listEl = document.getElementById('questsList');
        var emptyEl = document.getElementById('questsEmpty');
        if (!listEl || !quests) return;
        var groups = [['Free Quests', quests.free], ["Members' Quests", quests.members], ['Miniquests', quests.miniquests]];
        var html = '';
        groups.forEach(function (group) {
          var label = group[0];
          var items = group[1] || [];
          if (!items.length) return;
          html += '<div class="quests-group-title">' + escapeHtml(label) + '</div>';
          items.forEach(function (q) {
            html += '<a class="quest-row quest-row--' + q.state + '" href="' + questWikiUrl(q.name) + '" target="_blank" rel="noopener">' + escapeHtml(q.name) + '</a>';
          });
        });
        listEl.innerHTML = html;
        if (emptyEl) emptyEl.hidden = html.length > 0;
      }

      // Same convention as questWikiUrl: spaces become underscores before
      // encodeURIComponent (so "&" in "Kourend & Kebos" comes out %26).
      function diaryWikiUrl(area) {
        var label = DIARY_AREA_LABELS[area] || titleCase(area);
        return 'https://oldschool.runescape.wiki/w/' + encodeURIComponent(label.replace(/ /g, '_')) + '_Diary';
      }

      function renderDiaries(diaries) {
        var listEl = document.getElementById('diariesList');
        if (!listEl || !Array.isArray(diaries)) return;
        var byArea = {};
        diaries.forEach(function (d) { byArea[d.area] = d; });
        var html = '';
        DIARY_AREA_ORDER.forEach(function (area) {
          var d = byArea[area];
          if (!d) return;
          // Highest completed tier picks the reward icon (DIARY_TIER_ORDER is
          // easy->elite, so the last match wins). -1 means no tiers completed.
          var highestCompletedIndex = -1;
          DIARY_TIER_ORDER.forEach(function (tier, i) {
            if (d.tiers && d.tiers[tier] === 'completed') highestCompletedIndex = i;
          });
          var icon = highestCompletedIndex >= 0
            ? (DIARY_AREA_TIER_ICON[area] || [])[highestCompletedIndex]
            : DIARY_AREA_NOT_STARTED_ICON;
          var label = DIARY_AREA_LABELS[area] || titleCase(area);
          html += '<a class="diary-row" href="' + diaryWikiUrl(area) + '" target="_blank" rel="noopener">'
            + '<div class="diary-row-header">'
            + '<img class="diary-row-icon" src="' + icon + '" alt="" />'
            + '<span class="diary-row-label">' + escapeHtml(label) + '</span>'
            + '<span class="diary-row-count">' + d.completed + '/' + d.total + '</span>'
            + '</div>'
            + '<div class="diary-row-bar">'
            + DIARY_TIER_ORDER.map(function (tier) {
                var state = (d.tiers && d.tiers[tier]) || 'not_completed';
                return '<div class="diary-tier-seg' + (state === 'completed' ? ' diary-tier-seg--completed' : '') + '"></div>';
              }).join('')
            + '</div>'
            + '</a>';
        });
        listEl.innerHTML = html;
      }

      function renderCombatAchievements(items) {
        var listEl = document.getElementById('caList');
        if (!listEl || !Array.isArray(items)) return;
        var byTier = {};
        items.forEach(function (item) { byTier[item.tier] = item; });
        var html = '';
        CA_TIER_ORDER.forEach(function (tier) {
          var item = byTier[tier];
          if (!item) return;
          var completed = item.completed;
          var total = item.total;
          var pct = (completed != null && total) ? Math.min(100, (completed / total) * 100) : 0;
          html += '<a class="ca-tile" href="https://oldschool.runescape.wiki/w/Combat_Achievements/' + titleCase(tier) + '" target="_blank" rel="noopener">'
            + '<span class="ca-tile-label">' + titleCase(tier) + '</span>'
            + '<img class="ca-tile-icon" src="/static/img/combat-achievement-tiers/' + tier + '.png" alt="" />'
            + '<span class="ca-tile-count">' + (completed != null ? completed : '\u2014') + '/' + total + '</span>'
            + '<div class="ca-tile-bar"><div class="ca-tile-bar-fill" style="width: ' + pct + '%"></div></div>'
            + '</a>';
        });
        listEl.innerHTML = html;
      }

      fetch('/api/character-overview/progress')
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data) return;
          renderQuests(data.quests);
          renderDiaries(data.diaries);
          renderCombatAchievements(data.combatAchievements);
        })
        .catch(function () { /* leave each card's own empty/em-dash state showing */ });

      // Collection Log (GET /api/players/me/collection-log): tabs -> pages ->
      // items from the static schema (get_collection_log_tabs in
      // app/collectionlog.py) plus the obtained-item map
      // (GameAccount.collection_log_items, {item id string: quantity}, captured
      // by CollectionLogItemCapture in the Mootrius/myscape-plugin repo).
      // Rendered client-side.
      var clogCard = document.getElementById('clogCard');
      var clogEmpty = document.getElementById('clogEmpty');
      var clogBody = document.getElementById('clogBody');
      var clogTabsEl = document.getElementById('clogTabs');
      var clogPagesEl = document.getElementById('clogPages');
      var clogItemsEl = document.getElementById('clogItems');
      var clogItemsHeaderEl = document.getElementById('clogItemsHeader');
      var clogSyncBtn = document.getElementById('clogSyncBtn');

      var clogTabs = [];
      var clogObtained = {};
      // page name -> array of kill/completion counts
      // (collection_log_page_kill_counts in app/bosses.py; see
      // read_collection_log in app/main.py). Only boss/raid/clue pages have
      // entries; absent means no count shown. Several elements mean a combo page
      // (twin bosses, normal/hard-mode raids), see renderClogItemsHeader.
      var clogKillCounts = {};
      var clogActiveTab = 0;
      var clogActivePage = 0;

      // Same RuneLite item-icon CDN as item_icon_url in app/purchase_goals.py;
      // built from the bare numeric id since get_collection_log_tabs returns
      // bare ids.
      function clogIconUrl(itemId) {
        return 'https://static.runelite.net/cache/item/icon/' + itemId + '.png';
      }

      // Item ids repeat across pages (~205 do, e.g. clue rewards on several
      // tiers), so totals must dedupe by id rather than sum list lengths. Used
      // for the grand total and each tab's count.
      function clogUniqueIds(items) {
        var seen = {};
        var ids = [];
        items.forEach(function (item) {
          if (!seen[item.id]) { seen[item.id] = true; ids.push(item.id); }
        });
        return ids;
      }

      function clogObtainedCount(ids) {
        var count = 0;
        ids.forEach(function (id) { if (clogObtained[String(id)] != null) count++; });
        return count;
      }

      // Phone width: the tab strip scrolls sideways, and these classes drive the
      // edge fade and arrow (.clog-tabs-wrap in character-overview.css). Never
      // set on desktop.
      var clogTabsWrapEl = document.getElementById('clogTabsWrap');
      function updateClogTabsFade() {
        if (!clogTabsWrapEl) return;
        var max = clogTabsEl.scrollWidth - clogTabsEl.clientWidth;
        clogTabsWrapEl.classList.toggle('can-scroll-left', clogTabsEl.scrollLeft > 2);
        clogTabsWrapEl.classList.toggle('can-scroll-right', clogTabsEl.scrollLeft < max - 2);
      }
      clogTabsEl.addEventListener('scroll', updateClogTabsFade, { passive: true });
      window.addEventListener('resize', updateClogTabsFade);

      function renderClogTabs() {
        // Emptying the strip collapses it and would reset the scroll to the
        // first tab, so the scroll position is kept across the rebuild.
        var keepScrollLeft = clogTabsEl.scrollLeft;
        clogTabsEl.innerHTML = '';
        clogTabs.forEach(function (tab, tabIndex) {
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'clog-tab' + (tabIndex === clogActiveTab ? ' active' : '');
          btn.textContent = tab.name;
          btn.addEventListener('click', function () {
            clogActiveTab = tabIndex;
            clogActivePage = 0;
            renderClogTabs();
            renderClogPages();
            renderClogItems();
            renderClogItemsHeader();
            // Switching tabs resets to the first page and scrolls both panes to
            // the top. Replacing innerHTML doesn't do this since scrollTop lives
            // on clogPagesEl/clogItemsEl, which persist.
            clogPagesEl.scrollTop = 0;
            clogItemsEl.scrollTop = 0;
          });
          clogTabsEl.appendChild(btn);
        });
        clogTabsEl.scrollLeft = keepScrollLeft;
        updateClogTabsFade();
      }

      function renderClogPages() {
        clogPagesEl.innerHTML = '';
        var tab = clogTabs[clogActiveTab];
        if (!tab) return;
        tab.pages.forEach(function (page, pageIndex) {
          var obtainedCount = clogObtainedCount(clogUniqueIds(page.items));
          // Red/yellow/green by progress; a 0/0 page reads as complete.
          var progressState = obtainedCount === page.items.length ? 'complete'
            : obtainedCount === 0 ? 'zero'
            : 'started';
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'clog-page-btn ' + progressState
            + (pageIndex === clogActivePage ? ' active' : '');
          var label = document.createElement('span');
          label.textContent = page.name;
          var count = document.createElement('span');
          count.className = 'clog-page-count';
          count.textContent = formatInt(obtainedCount) + '/' + formatInt(page.items.length);
          btn.appendChild(label);
          btn.appendChild(count);
          btn.addEventListener('click', function () {
            clogActivePage = pageIndex;
            renderClogPages();
            renderClogItems();
            renderClogItemsHeader();
            // Reset the items grid to the top for the new page. .clog-pages
            // keeps its scroll position (unlike a tab switch) since the page
            // list stays the same.
            clogItemsEl.scrollTop = 0;
          });
          clogPagesEl.appendChild(btn);
        });
      }

      // Same wiki-URL shape as itemWikiUrl (gear slots); each render_* script is
      // independent, so it is a local copy.
      function clogItemWikiUrl(itemName) {
        return 'https://oldschool.runescape.wiki/w/' + encodeURIComponent(String(itemName).replace(/ /g, '_'));
      }
      function renderClogItems() {
        clogItemsEl.innerHTML = '';
        var tab = clogTabs[clogActiveTab];
        var page = tab && tab.pages[clogActivePage];
        if (!page) return;
        page.items.forEach(function (item) {
          var qty = clogObtained[String(item.id)];
          var tile = document.createElement('a');
          tile.className = 'clog-item' + (qty != null ? ' obtained' : '');
          tile.href = clogItemWikiUrl(item.name);
          tile.target = '_blank';
          tile.rel = 'noopener';
          // Site-styled tooltip (.myscape-tooltip in myscape.css, driven by
          // _shell's shared_script) with just the item name.
          tile.setAttribute('data-tooltip', item.name);
          var img = document.createElement('img');
          img.className = 'clog-item-icon';
          img.src = clogIconUrl(item.id);
          img.alt = '';
          img.loading = 'lazy';
          img.onerror = function () { img.style.display = 'none'; };
          tile.appendChild(img);
          if (qty != null && qty > 1) {
            var badge = document.createElement('div');
            badge.className = 'clog-item-qty';
            badge.textContent = formatInt(qty);
            tile.appendChild(badge);
          }
          clogItemsEl.appendChild(tile);
        });
      }

      // Active page's name + kill/completion count above the item grid. The
      // count is omitted when clogKillCounts has no entry. Pages with several
      // counts show them joined by a middot rather than summed (e.g. Callisto
      // and Artio). No personal-best time since nothing tracks one.
      function renderClogItemsHeader() {
        clogItemsHeaderEl.innerHTML = '';
        var tab = clogTabs[clogActiveTab];
        var page = tab && tab.pages[clogActivePage];
        if (!page) return;
        var name = document.createElement('span');
        name.className = 'clog-items-header-name';
        name.textContent = page.name;
        clogItemsHeaderEl.appendChild(name);
        var killCounts = clogKillCounts[page.name];
        if (killCounts != null && killCounts.length) {
          var kc = document.createElement('span');
          kc.className = 'clog-items-header-kc';
          kc.textContent = killCounts.map(formatInt).join(' \\u00b7 ');
          clogItemsHeaderEl.appendChild(kc);
        }
      }

      // Same empty-state swap as showEmpty in the model viewer's module script;
      // only called once there is nothing to show.
      function showClogEmpty() {
        clogBody.style.display = 'none';
        clogEmpty.style.display = 'block';
      }

      // Locks .clog-pages/.clog-items height to .model-viewer-card's rendered
      // height instead of a fixed px value in CSS. The .clog-tabs height depends
      // on the RuneScapePlain11 web font's line-height (font-display: optional
      // in myscape.css), which varies with network, environment and browser, so
      // it is computed from the real boxes.
      var modelViewerCard = document.getElementById('modelViewerCard');
      function syncClogHeight() {
        if (!modelViewerCard || !clogCard || !clogPagesEl || !clogItemsEl || !clogItemsHeaderEl) return;
        // Phone layout (700px breakpoint, as in character-overview.css): the log
        // stacks below the viewer, so drop inline heights and use the
        // stylesheet's.
        if (window.matchMedia('(max-width: 700px)').matches) {
          clogPagesEl.style.height = '';
          clogItemsEl.style.height = '';
          return;
        }
        var modelBoxHeight = modelViewerCard.getBoundingClientRect().height;
        if (!modelBoxHeight) return;
        var clogCS = getComputedStyle(clogCard);
        // Read .clog-toolbar, not .clog-tabs: the toolbar (wrapping .clog-tabs +
        // .clog-sync-btn) carries the row's margin-bottom, so using .clog-tabs
        // would under-subtract 8px.
        var toolbarEl = clogCard.querySelector('.clog-toolbar');
        var toolbarCS = toolbarEl ? getComputedStyle(toolbarEl) : null;
        var panesHeight = modelBoxHeight
          - parseFloat(clogCS.paddingTop)
          - parseFloat(clogCS.paddingBottom)
          - parseFloat(clogCS.borderTopWidth)
          - parseFloat(clogCS.borderBottomWidth)
          - (toolbarEl ? toolbarEl.getBoundingClientRect().height : 0)
          - (toolbarCS ? parseFloat(toolbarCS.marginBottom) : 0);
        if (panesHeight > 0) {
          // .clog-pages has no header, so it gets the whole budget;
          // .clog-items-header eats only into .clog-items' share (see
          // .clog-items-col in character-overview.css).
          clogPagesEl.style.height = panesHeight + 'px';
          var headerCS = getComputedStyle(clogItemsHeaderEl);
          var itemsHeight = panesHeight
            - clogItemsHeaderEl.getBoundingClientRect().height
            - parseFloat(headerCS.marginBottom);
          if (itemsHeight > 0) {
            clogItemsEl.style.height = itemsHeight + 'px';
          }
        }
      }
      if (modelViewerCard && window.ResizeObserver) {
        new ResizeObserver(syncClogHeight).observe(modelViewerCard);
      } else {
        window.addEventListener('resize', syncClogHeight);
      }
      syncClogHeight();
      // Re-run once the web font swaps in (see font-display: optional in
      // myscape.css); ResizeObserver on modelViewerCard won't catch it since the
      // card's height is width-driven.
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(syncClogHeight);
      }

      // Touch screens only show a tap tooltip for these: summary-row icons, the
      // model viewer info button, the Collection Log refresh button and item
      // tiles, Skills cells, and the PRIVATE/PUBLIC buttons in the
      // public-profile popup. Read by the shared tooltip script in _shell.
      window.myscapeTouchTooltipFilter = function (el) {
        return !!(el.closest && el.closest(
          '.co-summary-row, #mvInfoBtn, #clogSyncBtn, .clog-item, .skill-cell, ' +
          '#publicProfileSegPrivate, #publicProfileSegPublic'
        ));
      };

      // Tapping the summary-row icons or the viewer's info button a second time
      // dismisses their tooltip (same shared tooltip script).
      window.myscapeTouchTooltipToggle = function (el) {
        return !!(el.closest && el.closest('.co-summary-row, #mvInfoBtn'));
      };

      // Drawn scrollbars for the four scrolling lists (Collection Log pages +
      // items, Quests, Achievement Diaries), shown only at phone width; see
      // "Scrollbars on the scrolling lists" in character-overview.css. Always
      // built, CSS decides display. The thumb is sized from scrollTop and
      // draggable.
      (function () {
        function attach(list) {
          if (!list || !list.parentElement) return;
          var track = document.createElement('div');
          track.className = 'co-sb';
          track.setAttribute('aria-hidden', 'true');
          var thumb = document.createElement('div');
          thumb.className = 'co-sb-thumb';
          track.appendChild(thumb);
          list.parentElement.appendChild(track);

          var thumbH = 0;
          function update() {
            var ch = list.clientHeight;
            var sh = list.scrollHeight;
            var scrollable = ch > 0 && sh > ch + 1;
            track.classList.toggle('co-sb--on', scrollable);
            if (!scrollable) return;
            track.style.top = list.offsetTop + 'px';
            track.style.height = list.offsetHeight + 'px';
            track.style.left = (list.offsetLeft + list.offsetWidth - 16) + 'px';
            thumbH = Math.max(28, Math.round(ch * ch / sh));
            thumb.style.height = thumbH + 'px';
            var maxTop = list.offsetHeight - thumbH;
            var y = maxTop * list.scrollTop / (sh - ch);
            thumb.style.transform = 'translateY(' + Math.max(0, Math.min(maxTop, Math.round(y))) + 'px)';
          }
          list.addEventListener('scroll', update, { passive: true });
          window.addEventListener('resize', update);
          if (window.ResizeObserver) new ResizeObserver(update).observe(list);
          if (window.MutationObserver) new MutationObserver(update).observe(list, { childList: true });

          var dragStartY = 0;
          var dragStartScroll = 0;
          thumb.addEventListener('pointerdown', function (e) {
            dragStartY = e.clientY;
            dragStartScroll = list.scrollTop;
            thumb.classList.add('dragging');
            thumb.setPointerCapture(e.pointerId);
            e.preventDefault();
          });
          thumb.addEventListener('pointermove', function (e) {
            if (!thumb.classList.contains('dragging')) return;
            var travel = list.offsetHeight - thumbH;
            if (travel <= 0) return;
            list.scrollTop = dragStartScroll + (e.clientY - dragStartY) * (list.scrollHeight - list.clientHeight) / travel;
          });
          function endDrag() { thumb.classList.remove('dragging'); }
          thumb.addEventListener('pointerup', endDrag);
          thumb.addEventListener('pointercancel', endDrag);
          update();
        }
        ['clogPages', 'clogItems', 'questsList', 'diariesList'].forEach(function (id) {
          attach(document.getElementById(id));
        });
      })();

      // Named so the manual sync button can re-run it after a resync.
      function loadCollectionLog() {
        return fetch('/api/players/me/collection-log')
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (data) {
            if (!data || !data.syncedAt || !Array.isArray(data.tabs) || !data.tabs.length) {
              showClogEmpty();
              return;
            }
            clogTabs = data.tabs;
            clogObtained = data.obtainedItems || {};
            clogKillCounts = data.killCounts || {};
            renderClogTabs();
            renderClogPages();
            renderClogItems();
            renderClogItemsHeader();
            // Re-sync heights now that .clog-tabs and .clog-items-header have
            // content (both are 0px tall until now).
            syncClogHeight();
          })
          .catch(function () { showClogEmpty(); });
      }
      if (clogCard) {
        loadCollectionLog();
      }

      // Manual hiscores refresh for the counts renderClogItemsHeader shows. POST
      // /api/players/me/hiscores/sync is otherwise only triggered at link time
      // (sync_hiscores in app/hiscores.py), so later-added stats (e.g.
      // COLLECTION_LOG_CLUE_PAGE_TIERS in app/bosses.py) would stay empty. Only
      // clogKillCounts can change, so loadCollectionLog() is re-run.
      if (clogSyncBtn) {
        clogSyncBtn.addEventListener('click', function () {
          if (clogSyncBtn.disabled) return;
          clogSyncBtn.classList.remove('sync-failed');
          clogSyncBtn.disabled = true;
          clogSyncBtn.classList.add('syncing');
          fetch('/api/players/me/hiscores/sync', { method: 'POST' })
            .then(function (r) { return r.ok ? loadCollectionLog() : Promise.reject(); })
            .catch(function () {
              clogSyncBtn.classList.add('sync-failed');
              setTimeout(function () { clogSyncBtn.classList.remove('sync-failed'); }, 2500);
            })
            .then(function () {
              clogSyncBtn.disabled = false;
              clogSyncBtn.classList.remove('syncing');
            });
        });
      }

      // Public-profile settings card (#publicProfileCard). Absent in
      // preview/public_code mode (see publicProfileSettingsBtn in
      // render_character_overview); this guard makes that a no-op.
      var publicProfileSettingsBtn = document.getElementById('publicProfileSettingsBtn');
      if (publicProfileSettingsBtn) {
        var publicProfileCard = document.getElementById('publicProfileCard');
        var publicProfileSegBtns = [document.getElementById('publicProfileSegPrivate'), document.getElementById('publicProfileSegPublic')];
        var publicProfileLinkBtn = document.getElementById('publicProfileLinkBtn');
        var publicProfileRegenerateBtn = document.getElementById('publicProfileRegenerateBtn');

        // Collapsed by default; the cog toggles a floating popup under the
        // button (.co-settings-wrap). Mirrors the Storages Viewer's
        // pmSettingsBtn/pmSettingsMenu (setSettingsMenuOpen in app/pages/),
        // including the .active class and outside-click close. No refetch on
        // open since the initial GET already ran.
        function setPublicProfileOpen(open) {
          publicProfileCard.hidden = !open;
          publicProfileSettingsBtn.classList.toggle('active', open);
        }
        publicProfileSettingsBtn.addEventListener('click', function () {
          setPublicProfileOpen(publicProfileCard.hidden);
        });
        document.addEventListener('click', function (e) {
          var wrap = document.querySelector('.co-settings-wrap');
          if (wrap && !wrap.contains(e.target)) setPublicProfileOpen(false);
        });

        function applyPublicProfileState(data) {
          if (!data) return;
          var activeValue = data.isPublic ? 'public' : 'private';
          publicProfileSegBtns.forEach(function (btn) {
            btn.classList.toggle('active', btn.getAttribute('data-segment-value') === activeValue);
          });
          publicProfileLinkBtn.dataset.url = data.url || '';
          publicProfileLinkBtn.textContent = data.url || '';
          // A private page has no link to copy: the real disabled attribute (not
          // just styling) stops the click handler, matching
          // .public-profile-link-btn:disabled.
          publicProfileLinkBtn.disabled = !data.isPublic;
          // The data-tooltip attribute is removed while private, since "Click to
          // copy" would describe an action the disabled button can't do.
          if (data.isPublic) {
            publicProfileLinkBtn.setAttribute('data-tooltip', 'Click to copy');
          } else {
            publicProfileLinkBtn.removeAttribute('data-tooltip');
          }
        }

        fetch('/api/players/me/public-profile')
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(applyPublicProfileState)
          .catch(function () { /* leave the segmented control at its default (Private) */ });

        publicProfileSegBtns.forEach(function (btn) {
          btn.addEventListener('click', function () {
            if (btn.classList.contains('active')) return;
            var wantPublic = btn.getAttribute('data-segment-value') === 'public';
            publicProfileSegBtns.forEach(function (b) { b.disabled = true; });
            fetch('/api/players/me/public-profile', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ is_public: wantPublic }),
            })
              .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
              .then(applyPublicProfileState)
              .catch(function () {})
              .then(function () { publicProfileSegBtns.forEach(function (b) { b.disabled = false; }); });
          });
        });

        // The link display is the copy button, as in Loot Tracker's
        // lootShareLinkBtn (app/pages/) and the Account page's Shared Links
        // table. The URL is held in data-url since textContent swaps to "COPIED"
        // briefly.
        publicProfileLinkBtn.addEventListener('click', function () {
          var url = publicProfileLinkBtn.dataset.url;
          if (!url) return;
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(url);
          } else {
            var temp = document.createElement('textarea');
            temp.value = url;
            temp.style.position = 'fixed';
            temp.style.opacity = '0';
            document.body.appendChild(temp);
            temp.select();
            document.execCommand('copy');
            document.body.removeChild(temp);
          }
          publicProfileLinkBtn.textContent = 'COPIED';
          setTimeout(function () { publicProfileLinkBtn.textContent = url; }, 1200);
        });

        // Server-side limit is once per day (regenerate_public_profile_code in
        // app/main.py); a 429 flashes the button red like the collection log's
        // hiscores-sync failure.
        publicProfileRegenerateBtn.addEventListener('click', function () {
          publicProfileRegenerateBtn.disabled = true;
          fetch('/api/players/me/public-profile/regenerate-code', { method: 'POST' })
            .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
            .then(applyPublicProfileState)
            .catch(function () {
              publicProfileRegenerateBtn.classList.add('action-failed');
              setTimeout(function () { publicProfileRegenerateBtn.classList.remove('action-failed'); }, 2500);
            })
            .then(function () { publicProfileRegenerateBtn.disabled = false; });
        });
      }
    })();
    """.replace("__ACCOUNT_TYPE_INFO_JSON__", json.dumps(_ACCOUNT_TYPE_INFO))

    extra_head = (
        f'<link rel="stylesheet" href="/static/css/character-overview.css?v={_CHARACTER_OVERVIEW_CSS_VERSION}" />'
        + _MODEL_VIEWER_HEAD.replace(
            "__MODEL_VIEWER_BACKGROUNDS_JSON__", json.dumps(_MODEL_VIEWER_BACKGROUNDS)
        ).replace(
            "__MODEL_VIEWER_BG_STORAGE_KEY_JSON__",
            json.dumps(
                None if preview
                else f"myscape.modelViewerBgIndex.public.{public_code}" if public_code
                else "myscape.modelViewerBgIndex"
            ),
        ).replace(
            "__MODEL_VIEWER_MODEL_URL_JSON__",
            json.dumps(
                "/static/img/landing-character-overview-demo-model.glb" if preview
                else f"/api/public/{public_code}/model" if public_code
                else "/api/character-overview/model"
            ),
        )
    )
    return extra_head, body, script


def render_character_overview(player: PlayerView) -> str:
    """The real, authenticated Character Overview page:
    _character_overview_panel_markup's default output in the page shell. The
    landing preview (render_landing_character_overview_preview) and public
    view (render_public_character_overview) reuse the same body/script.
    """
    extra_head, body, script = _character_overview_panel_markup()
    return _shell(
        title="Character Overview — myscape",
        player=player,
        body=body,
        extra_head=extra_head,
        extra_script=script,
    )


def render_public_character_overview(game_account: "GameAccount", viewer: Optional[PlayerView]) -> str:
    """myscape.io/c/<code>: a visitor's view of someone else's public Character
    Overview. public_character_overview_page in app/main.py resolves the code
    and 404s if missing/private; viewer is whoever is signed in, used only for
    nav state.
    
    Reuses _character_overview_panel_markup(public_code=...) with a wrapper
    fetch shim that calls the code-scoped endpoints (GET
    /api/public/<code>/summary|progress|skills|collection-log in app/main.py)
    instead of the "me" endpoints. `fetch` is shadowed only inside this IIFE;
    window.fetch is untouched (see _MODEL_VIEWER_HEAD).
    
    accountType rides in the public summary response (low exposure).
    #clogSyncBtn gets the same hoverable-but-inert cloneNode+replaceWith
    treatment as the landing preview.
    """
    code = game_account.public_code
    display_name = game_account.runescape_name or "This player"
    extra_head, body, script = _character_overview_panel_markup(
        public_code=code, public_character_name=display_name
    )

    wrapper_script = f"""
    (function () {{
      var PUBLIC_CODE = {json.dumps(code)};

      // fetch shim: forwards to the real, public endpoints
      var fetch = function (url, options) {{
        var opts = options || {{}};
        var method = (opts.method || 'GET').toUpperCase();
        function fail() {{ return Promise.resolve({{ ok: false, json: function () {{ return Promise.resolve({{}}); }} }}); }}

        if (url === '/api/character-overview/summary' && method === 'GET') {{
          return window.fetch('/api/public/' + PUBLIC_CODE + '/summary').then(function (r) {{
            // Hands the owner's synced model-viewer background
            // (modelViewerBackgroundIndex in this response, see app/main.py) to
            // the 3D viewer, since a visitor has no shuffle history of their own
            // (see myscapeApplyModelViewerBackground in _MODEL_VIEWER_HEAD).
            // r.clone() because the reused script still reads this body and a
            // Response body can be consumed once.
            if (r.ok) {{
              r.clone().json().then(function (data) {{
                // Stashed on window whether or not the bridge function exists
                // yet: this fetch can resolve before the deferred module script
                // runs (see the handshake next to
                // window.myscapeApplyModelViewerBackground in
                // _MODEL_VIEWER_HEAD).
                window.__myscapePendingModelViewerBg = data.modelViewerBackgroundIndex;
                if (window.myscapeApplyModelViewerBackground) {{
                  window.myscapeApplyModelViewerBackground(data.modelViewerBackgroundIndex);
                }}
              }}).catch(function () {{}});
            }}
            return r;
          }});
        }}
        if (url === '/api/character-overview/progress' && method === 'GET') {{
          return window.fetch('/api/public/' + PUBLIC_CODE + '/progress');
        }}
        if (url === '/api/players/me/skills' && method === 'GET') {{
          return window.fetch('/api/public/' + PUBLIC_CODE + '/skills');
        }}
        if (url === '/api/players/me/collection-log' && method === 'GET') {{
          return window.fetch('/api/public/' + PUBLIC_CODE + '/collection-log');
        }}
        // #clogSyncBtn's click listener would fire this; unreachable in practice
        // (see the cloneNode+replaceWith strip below), answered with a graceful
        // failure anyway.
        if (url === '/api/players/me/hiscores/sync' && method === 'POST') {{
          return fail();
        }}
        // Anything else the reused script could call beyond the cases above.
        return fail();
      }};

      {script}

      var clogSyncBtn = document.getElementById('clogSyncBtn');
      if (clogSyncBtn) {{
        clogSyncBtn.replaceWith(clogSyncBtn.cloneNode(true));
      }}

      // friend-request button, next to the character's name. Uses the real
      // window.fetch on purpose (the local `fetch` answers only the Character
      // Overview endpoints).
      (function () {{
        var title = document.querySelector('h2.page-title');
        if (!title) return;
        var wrap = document.createElement('span');
        wrap.className = 'co-friend-wrap';
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'co-friend-btn';
        btn.id = 'friendRequestBtn';
        btn.hidden = true;
        wrap.appendChild(btn);
        title.appendChild(document.createTextNode(' '));
        title.appendChild(wrap);

        var ICON_ADD = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M19 8v6"></path><path d="M22 11h-6"></path></svg>';
        var ICON_DONE = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M16 11l2 2 4-4"></path></svg>';

        var state = 'none';
        var restoreTimer = null;
        function setState(next) {{
          state = next;
          btn.classList.remove('co-friend-btn--done');
          btn.disabled = false;
          if (next === 'self' || next === 'own') {{ btn.hidden = true; return; }}
          btn.hidden = false;
          var tip;
          if (next === 'friends') {{
            btn.innerHTML = ICON_DONE; tip = 'Friends';
            btn.classList.add('co-friend-btn--done'); btn.disabled = true;
          }} else if (next === 'pending_out') {{
            btn.innerHTML = ICON_DONE; tip = 'Friend request sent';
            btn.classList.add('co-friend-btn--done'); btn.disabled = true;
          }} else if (next === 'pending_in') {{
            btn.innerHTML = ICON_ADD; tip = 'Accept friend request';
          }} else if (next === 'anonymous') {{
            btn.innerHTML = ICON_ADD; tip = 'Log in to send a friend request';
          }} else {{
            btn.innerHTML = ICON_ADD; tip = 'Send friend request';
          }}
          btn.setAttribute('data-tooltip', tip);
          btn.setAttribute('aria-label', tip);
        }}

        window.fetch('/api/friends/status/' + encodeURIComponent(PUBLIC_CODE))
          .then(function (r) {{ return r.ok ? r.json() : null; }})
          .then(function (d) {{ if (d && d.state) setState(d.state); }})
          .catch(function () {{}});

        btn.addEventListener('click', function () {{
          if (state === 'anonymous') {{ window.location.href = '/login'; return; }}
          if (state !== 'none' && state !== 'pending_in') return;
          btn.disabled = true;
          window.fetch('/api/friends/requests', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ code: PUBLIC_CODE }}),
          }}).then(function (r) {{
            return r.json().catch(function () {{ return {{}}; }}).then(function (d) {{ return {{ ok: r.ok, data: d }}; }});
          }}).then(function (res) {{
            if (res.ok) {{
              if (window.myscapePollFriendNotifications) window.myscapePollFriendNotifications();
              setState(res.data.status === 'accepted' ? 'friends' : 'pending_out');
              return;
            }}
            var msg = (res.data && typeof res.data.detail === 'string') ? res.data.detail : 'Could not send that request.';
            btn.disabled = false;
            var previous = btn.getAttribute('data-tooltip');
            btn.setAttribute('data-tooltip', msg);
            clearTimeout(restoreTimer);
            restoreTimer = setTimeout(function () {{ btn.setAttribute('data-tooltip', previous); }}, 3500);
          }}).catch(function () {{ btn.disabled = false; }});
        }});
      }})();
    }})();
    """

    return _shell(
        title=f"{display_name} — myscape",
        player=viewer,
        body=body,
        extra_head=extra_head,
        extra_script=wrapper_script,
        meta_description=(
            f"{display_name}'s public myscape page — complete with their "
            "collection log data, skill levels, quest completions, "
            "achievement diary tiers, and combat task tiers."
        ),
    )


def render_landing_character_overview_preview() -> Optional[Tuple[str, str, str]]:
    """Landing page's interactive Character Overview preview: reuses
    _character_overview_panel_markup(preview=True) unmodified with a demo
    wrapper script. Backed by app/data/landing_character_overview_demo.json
    (real summary, progress and collection log snapshot; see
    _get_landing_character_overview_demo_data) plus a static .glb model.
    Returns (extra_head, body, script) for render_landing, or None if the
    snapshot is missing. First preview on the page, ahead of Loot Tracker.
    
    All six sections work like the real page; background shuffle works but
    never persists (see __MODEL_VIEWER_BG_STORAGE_KEY_JSON__). The container
    uses the usual fixed-height/clipped/feathered treatment
    (.landing-character-overview-preview in character-overview.css), so extra
    cards are reached by touch drag/keyboard. #clogSyncBtn stays visible and
    hoverable but inert (cloneNode+replaceWith strip, as for Loot Tracker's
    range button).
    
    1. A scoped `fetch` shim answers GET /api/character-overview/summary,
    /api/character-overview/progress, /api/players/me/skills and
    /api/players/me/collection-log from the snapshot, and fails the
    hiscores-sync POST gracefully. The 3D model bypasses the shim
    (__MODEL_VIEWER_MODEL_URL_JSON__ points at a static asset).
    2. No polling interval: each endpoint is fetched once on load.
    """
    demo = _get_landing_character_overview_demo_data()
    if demo is None:
        return None
    extra_head, body, script = _character_overview_panel_markup(preview=True)

    # Hero row: tagline wrap first, character second so the character lands on
    # the right; same flex/bottom-align as other previews (see
    # .loot-preview-hero in loot-tracker.css). The reused body's <h2> is hidden
    # via .landing-character-overview-preview .page-title.
    hero_markup = """
    <div class="co-preview-hero">
      <div class="co-preview-tagline-wrap">
        <p class="co-preview-tagline">
          <span class="co-preview-tagline-gold">CHARACTER OVERVIEWS</span> <span class="co-preview-tagline-white">that you can share with your friends.</span>
        </p>
      </div>
      <picture class="co-preview-char">
        <source srcset="/static/img/landing-character-overview-preview-char.webp" type="image/webp">
        <img src="/static/img/landing-character-overview-preview-char.png" alt="" />
      </picture>
    </div>
    """
    body = hero_markup + body

    summary_json = json.dumps(demo.get("summary") or {})
    progress_json = json.dumps(demo.get("progress") or {})
    skills_json = json.dumps(demo.get("skills") or {})
    collection_log_json = json.dumps(demo.get("collectionLog") or {})
    wrapper_script = f"""
    (function () {{
      // The captured snapshot (see _get_landing_character_overview_demo_data for
      // the sources). Static, since nothing in this preview mutates it.
      var DEMO_SUMMARY = {summary_json};
      var DEMO_PROGRESS = {progress_json};
      var DEMO_SKILLS = {skills_json};
      var DEMO_COLLECTION_LOG = {collection_log_json};

      // fetch shim
      var fetch = function (url, options) {{
        var opts = options || {{}};
        var method = (opts.method || 'GET').toUpperCase();
        function ok(data) {{ return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve(data); }} }}); }}
        function fail() {{ return Promise.resolve({{ ok: false, json: function () {{ return Promise.resolve({{}}); }} }}); }}

        if (url === '/api/character-overview/summary' && method === 'GET') {{
          return ok(DEMO_SUMMARY);
        }}
        if (url === '/api/character-overview/progress' && method === 'GET') {{
          return ok(DEMO_PROGRESS);
        }}
        if (url === '/api/players/me/skills' && method === 'GET') {{
          return ok(DEMO_SKILLS);
        }}
        if (url === '/api/players/me/collection-log' && method === 'GET') {{
          return ok(DEMO_COLLECTION_LOG);
        }}
        // Hiscores-sync POST from #clogSyncBtn's click listener; unreachable in
        // practice (see the cloneNode+replaceWith strip below), answered
        // gracefully anyway.
        if (url === '/api/players/me/hiscores/sync' && method === 'POST') {{
          return fail();
        }}
        // Fallback: a harmless failure for anything unexpected.
        return fail();
      }};

      {script}

      // Neutralizes the collection log's hiscores refresh button. Runs after the
      // reused script has wired its click listener, so the node is replaced
      // outright (cloneNode(true) copies markup but not listeners), as for Loot
      // Tracker's range button (render_landing_loot_preview). The button keeps
      // its hover styling and tooltip but does nothing on click.
      var clogSyncBtn = document.getElementById('clogSyncBtn');
      if (clogSyncBtn) {{
        clogSyncBtn.replaceWith(clogSyncBtn.cloneNode(true));
      }}

      // accountType ("MAIN", summary.accountType in
      // app/data/landing_character_overview_demo.json) flows through the summary
      // shim above like every other stat; no override needed.
    }})();
    """
    return extra_head, body, wrapper_script
