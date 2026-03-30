// ---------------------------------------------------------------------------
// codebook-store.js — centralised state for the codebook page
// ---------------------------------------------------------------------------
// Holds the single source of truth for notes, codes, and hidden status.
// All DOM updates flow from state mutations, never the other way around.

import { escHtml, secondsToTs } from "./player.js";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * @typedef {object} NoteData
 * @property {number}      id
 * @property {string}      pid
 * @property {string}      text
 * @property {number}      start
 * @property {number|null}  end
 * @property {string}      condition
 * @property {number|null}  sectionStart
 */

/**
 * @typedef {object} CodeData
 * @property {number}      id
 * @property {string}      name
 * @property {Set<number>} noteIds
 */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

/** @type {Map<number, NoteData>} */
const notes = new Map();

/** @type {Map<number, CodeData>} */
const codes = new Map();

/** @type {Set<number>} */
const hidden = new Set();

// ---------------------------------------------------------------------------
// Initialisation (called once from the page script)
// ---------------------------------------------------------------------------

/**
 * Populate the store from server-rendered data.
 *
 * @param {{id:number, name:string, noteIds:number[]}[]} codeDefs
 * @param {{id:number, pid:string, text:string, start:number, end:number|null, condition:string, sectionStart:number|null}[]} noteDefs
 * @param {number[]} hiddenIds
 */
export function init(codeDefs, noteDefs, hiddenIds) {
  notes.clear();
  codes.clear();
  hidden.clear();

  for (const n of noteDefs) {
    notes.set(n.id, { id: n.id, pid: n.pid, text: n.text, start: n.start, end: n.end, condition: n.condition, sectionStart: n.sectionStart ?? null });
  }
  for (const c of codeDefs) {
    codes.set(c.id, { id: c.id, name: c.name, noteIds: new Set(c.noteIds) });
  }
  for (const id of hiddenIds) {
    hidden.add(id);
  }
}

// ---------------------------------------------------------------------------
// Read helpers
// ---------------------------------------------------------------------------

/** @param {number} noteId  @returns {NoteData|undefined} */
export function getNote(noteId) { return notes.get(noteId); }

/** @param {number} codeId  @returns {CodeData|undefined} */
export function getCode(codeId) { return codes.get(codeId); }

/** @param {number} noteId  @returns {boolean} */
export function isHidden(noteId) { return hidden.has(noteId); }

/** @returns {ReadonlyMap<number, CodeData>} */
export function allCodes() { return codes; }

/**
 * Check whether a note is assigned to any code.
 * @param {number} noteId
 * @returns {boolean}
 */
export function isAssigned(noteId) {
  for (const code of codes.values()) {
    if (code.noteIds.has(noteId)) return true;
  }
  return false;
}

/**
 * Return the number of visible (non-hidden) notes in a code.
 * @param {number} codeId
 * @returns {number}
 */
export function codeNoteCount(codeId) {
  const code = codes.get(codeId);
  if (!code) return 0;
  return code.noteIds.size;
}

// ---------------------------------------------------------------------------
// Mutations — each returns a promise (API call) so the caller can await
// ---------------------------------------------------------------------------

/**
 * Assign a note to a code.
 * @param {number} codeId
 * @param {number} noteId
 * @returns {Promise<boolean>} true if the note was newly added
 */
export async function assignNote(codeId, noteId) {
  const code = codes.get(codeId);
  if (!code || code.noteIds.has(noteId)) return false;
  code.noteIds.add(noteId);
  await fetch(`/api/codes/${codeId}/notes/${noteId}`, { method: "POST" });
  return true;
}

/**
 * Remove a note from a code.
 * @param {number} codeId
 * @param {number} noteId
 * @returns {Promise<boolean>} true if the note was present and removed
 */
export async function unassignNote(codeId, noteId) {
  const code = codes.get(codeId);
  if (!code || !code.noteIds.has(noteId)) return false;
  code.noteIds.delete(noteId);
  await fetch(`/api/codes/${codeId}/notes/${noteId}`, { method: "DELETE" });
  return true;
}

/**
 * Mark a note as hidden.
 * @param {number} noteId
 * @returns {Promise<void>}
 */
export async function hideNoteInStore(noteId) {
  hidden.add(noteId);
  await fetch(`/api/notes/${noteId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hidden: true }),
  });
}

/**
 * Mark a note as visible again.
 * @param {number} noteId
 * @returns {Promise<void>}
 */
export async function unhideNoteInStore(noteId) {
  hidden.delete(noteId);
  await fetch(`/api/notes/${noteId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hidden: false }),
  });
}

/**
 * Update a note's text.
 * @param {number} noteId
 * @param {string} newText
 * @returns {Promise<boolean>}
 */
export async function updateNoteText(noteId, newText) {
  const note = notes.get(noteId);
  if (!note) return false;
  const res = await fetch(`/api/notes/${noteId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: newText }),
  });
  if (!res.ok) return false;
  note.text = newText;
  return true;
}

/**
 * Create a new code.
 * @param {string} name
 * @returns {Promise<CodeData|null>}
 */
export async function addCode(name) {
  const res = await fetch("/api/codes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) return null;
  const { id } = await res.json();
  /** @type {CodeData} */
  const code = { id, name, noteIds: new Set() };
  codes.set(id, code);
  return code;
}

/**
 * Rename a code.
 * @param {number} codeId
 * @param {string} newName
 * @returns {Promise<boolean>}
 */
export async function renameCode(codeId, newName) {
  const code = codes.get(codeId);
  if (!code) return false;
  await fetch(`/api/codes/${codeId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: newName }),
  });
  code.name = newName;
  return true;
}

/**
 * Delete a code. Its notes become uncategorized (if not in other codes).
 * @param {number} codeId
 * @returns {Promise<number[]>} noteIds that were in this code
 */
export async function deleteCodeInStore(codeId) {
  const code = codes.get(codeId);
  if (!code) return [];
  const noteIds = [...code.noteIds];
  codes.delete(codeId);
  await fetch(`/api/codes/${codeId}`, { method: "DELETE" });
  return noteIds;
}

// ---------------------------------------------------------------------------
// Chip builder
// ---------------------------------------------------------------------------

/**
 * Format the timestamp badge for a note.
 * @param {NoteData} note
 * @returns {string}
 */
function formatNoteTs(note) {
  const offset = note.sectionStart ?? 0;
  const s = secondsToTs(note.start - offset);
  return note.end != null ? `${s}–${secondsToTs(note.end - offset)}` : s;
}

/**
 * Build a note-chip DOM element.
 *
 * @param {NoteData} note
 * @param {"code"|"uncategorized"|"hidden"} context
 * @param {(btn: HTMLButtonElement) => void} onAction
 *   Click handler for the chip's action button (hide / unhide).
 * @returns {HTMLDivElement}
 */
export function buildChip(note, context, onAction) {
  const d = document.createElement("div");
  d.draggable = true;
  d.dataset.noteId = String(note.id);
  d.dataset.pid = note.pid;
  d.dataset.start = String(note.start);
  if (note.end != null) d.dataset.end = String(note.end);
  d.dataset.text = note.text;
  if (note.condition) d.dataset.condition = note.condition;

  if (context === "hidden") {
    d.className = "note-chip note-chip-hidden border border-gray-200 bg-gray-100 rounded px-2.5 py-1.5 text-sm cursor-grab select-none opacity-50";
    d.dataset.hidden = "1";
    d.innerHTML =
      `<span class="text-gray-400 text-xs mr-1">${escHtml(note.pid)}·${escHtml(formatNoteTs(note))}</span>` +
      `<span class="text-gray-500">${escHtml(note.text)}</span>`;
    const btn = document.createElement("button");
    btn.className = "ml-1 text-gray-400 hover:text-blue-500 text-xs";
    btn.title = "Unhide";
    btn.textContent = "↩";
    btn.onclick = (e) => { e.stopPropagation(); onAction(btn); };
    d.appendChild(btn);
  } else {
    const inCode = context === "code";
    d.className = inCode
      ? "note-chip border border-blue-200 bg-blue-50 rounded px-2.5 py-1.5 text-sm cursor-grab select-none"
      : "note-chip border border-gray-200 bg-gray-50 rounded px-2.5 py-1.5 text-sm cursor-grab select-none";
    const metaCls = inCode ? "text-blue-300 text-xs mr-1" : "text-gray-400 text-xs mr-1";
    const hideCls = inCode
      ? "hide-btn ml-1 px-0.5 text-blue-200 hover:text-blue-400 text-sm leading-none"
      : "hide-btn ml-1 px-0.5 text-gray-300 hover:text-gray-500 text-sm leading-none";
    d.innerHTML =
      `<span class="${metaCls}">${escHtml(note.pid)}·${escHtml(formatNoteTs(note))}</span>` +
      `<span class="text-gray-800">${escHtml(note.text)}</span>`;
    const btn = document.createElement("button");
    btn.className = hideCls;
    btn.title = "Hide";
    btn.textContent = "×";
    btn.onclick = (e) => { e.stopPropagation(); onAction(btn); };
    d.appendChild(btn);
  }

  return d;
}

/**
 * Re-style a chip in place when it moves between contexts.
 * @param {HTMLDivElement} chip
 * @param {"code"|"uncategorized"} context
 * @param {(btn: HTMLButtonElement) => void} onAction
 */
export function restyleChip(chip, context, onAction) {
  const inCode = context === "code";
  chip.className = inCode
    ? "note-chip border border-blue-200 bg-blue-50 rounded px-2.5 py-1.5 text-sm cursor-grab select-none"
    : "note-chip border border-gray-200 bg-gray-50 rounded px-2.5 py-1.5 text-sm cursor-grab select-none";
  const meta = chip.querySelector("span");
  if (meta) meta.className = inCode ? "text-blue-300 text-xs mr-1" : "text-gray-400 text-xs mr-1";
  // Replace action button
  chip.querySelector(".hide-btn")?.remove();
  const btn = document.createElement("button");
  btn.className = inCode
    ? "hide-btn ml-1 px-0.5 text-blue-200 hover:text-blue-400 text-sm leading-none"
    : "hide-btn ml-1 px-0.5 text-gray-300 hover:text-gray-500 text-sm leading-none";
  btn.title = "Hide";
  btn.textContent = "×";
  btn.onclick = (e) => { e.stopPropagation(); onAction(btn); };
  chip.appendChild(btn);
}
