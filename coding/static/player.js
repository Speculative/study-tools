// ---------------------------------------------------------------------------
// player.js — shared Vidstack helpers, speed overlay, hotkeys, utilities
// ---------------------------------------------------------------------------
// All exports are pure functions or setup functions (no side effects on import).
// Types come from the `vidstack` npm package via vidstack-cdn.d.ts path mapping.

/** @typedef {import("https://cdn.vidstack.io/player").Player} Player */

/**
 * @typedef {object} MediaHotkeyOptions
 * @property {HTMLElement | (() => HTMLElement | null | undefined)} [overlayContainer]
 *   Element (or getter) for speed overlay display.
 * @property {(t: number) => void} [seekTo]
 *   Custom seek function. Defaults to setting `player.currentTime`.
 * @property {() => boolean} [guard]
 *   If provided, hotkeys are ignored when this returns false.
 * @property {(e: KeyboardEvent, player: Player) => void} [extraKeys]
 *   Handler for additional page-specific keys.
 */

import {
  VidstackPlayer,
  VidstackPlayerLayout,
} from "https://cdn.vidstack.io/player";

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

/**
 * Escape a string for safe insertion into HTML.
 * @param {string} s
 * @returns {string}
 */
export function escHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/**
 * Format a number of seconds as HH:MM:SS.
 * @param {number} s
 * @returns {string}
 */
export function secondsToTs(s) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return h > 0 ? `${String(h).padStart(2, "0")}:${mm}` : mm;
}

// ---------------------------------------------------------------------------
// Player creation
// ---------------------------------------------------------------------------

/**
 * Create a Vidstack player instance.
 * @param {string} target  CSS selector for the target element.
 * @param {string} title   Player title.
 * @param {string} src     Video source URL.
 * @param {Record<string, any>} [opts]  Extra options forwarded to VidstackPlayer.create.
 * @returns {Promise<Player>}
 */
export async function createPlayer(target, title, src, opts = {}) {
  return /** @type {Promise<Player>} */ (VidstackPlayer.create({
    target,
    title,
    src,
    layout: new VidstackPlayerLayout({}),
    ...opts,
  }));
}

// ---------------------------------------------------------------------------
// Speed overlay
// ---------------------------------------------------------------------------

const SPEEDS = [1, 2, 4];
/** @type {WeakMap<HTMLElement, ReturnType<typeof setTimeout>>} */
const _overlayTimers = new WeakMap();

/**
 * Show a brief speed indicator overlay inside `container`.
 * @param {HTMLElement} container
 * @param {number} speed
 */
export function showSpeedOverlay(container, speed) {
  let el = /** @type {HTMLElement | null} */ (container.querySelector(".speed-overlay"));
  if (!el) {
    el = document.createElement("div");
    el.className = "speed-overlay absolute inset-0 flex items-center justify-center pointer-events-none z-10";
    container.classList.add("relative");
    container.appendChild(el);
  }
  el.innerHTML = `<span class="text-5xl font-bold text-white bg-black/45 rounded-xl py-2 px-6 tracking-wide transition-opacity duration-150">${speed}x</span>`;
  el.style.opacity = "1";

  const prev = _overlayTimers.get(container);
  if (prev) clearTimeout(prev);
  _overlayTimers.set(container, setTimeout(() => {
    /** @type {HTMLElement} */ (el).style.transition = "opacity 0.3s";
    /** @type {HTMLElement} */ (el).style.opacity = "0";
  }, 700));
}

// ---------------------------------------------------------------------------
// Speed cycling
// ---------------------------------------------------------------------------

/**
 * Cycle the playback speed up or down and optionally show an overlay.
 * @param {Player} player
 * @param {number} direction  Positive = faster, negative = slower.
 * @param {HTMLElement} [overlayContainer]
 * @returns {number} The new speed.
 */
export function cycleSpeed(player, direction, overlayContainer) {
  const cur = player.playbackRate ?? 1;
  const idx = SPEEDS.indexOf(cur);
  const next = direction > 0
    ? SPEEDS[Math.min(SPEEDS.length - 1, idx + 1)]
    : SPEEDS[Math.max(0, idx - 1)];
  player.playbackRate = next;
  if (overlayContainer) showSpeedOverlay(overlayContainer, next);
  return next;
}

// ---------------------------------------------------------------------------
// Media hotkeys setup
// ---------------------------------------------------------------------------

/**
 * Attach keyboard shortcuts for media playback.
 *
 * Handles Space (play/pause), Arrow Left/Right (seek ±5s, ±30s with Ctrl),
 * and Ctrl+Arrow Up/Down (speed cycling).
 *
 * @param {(() => Player | null | undefined)} getPlayer
 *   Function returning the current player instance (may be null).
 * @param {MediaHotkeyOptions} [opts]
 */
export function attachMediaHotkeys(getPlayer, opts = {}) {
  document.addEventListener("keydown", (e) => {
    const tag = document.activeElement?.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA") return;

    if (opts.guard && !opts.guard()) return;

    const player = getPlayer();
    if (!player) return;

    const overlayEl = typeof opts.overlayContainer === "function"
      ? opts.overlayContainer()
      : opts.overlayContainer;

    const doSeek = opts.seekTo || ((/** @type {number} */ t) => { player.currentTime = t; });

    if (e.ctrlKey && e.code === "ArrowUp") {
      e.preventDefault();
      cycleSpeed(player, 1, overlayEl ?? undefined);
    } else if (e.ctrlKey && e.code === "ArrowDown") {
      e.preventDefault();
      cycleSpeed(player, -1, overlayEl ?? undefined);
    } else if (e.code === "Space") {
      e.preventDefault();
      player.paused ? player.play() : player.pause();
    } else if (e.code === "ArrowLeft") {
      e.preventDefault();
      doSeek(Math.max(0, player.currentTime - (e.ctrlKey ? 30 : 5)));
    } else if (e.code === "ArrowRight") {
      e.preventDefault();
      doSeek(player.currentTime + (e.ctrlKey ? 30 : 5));
    } else if (opts.extraKeys) {
      opts.extraKeys(e, player);
    }
  });
}
