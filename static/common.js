"use strict";

// ---------- tiny helpers ----------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;   // textContent => file names can't inject HTML
  return node;
}

function showError(message) {
  const box = $("#js-alert");
  box.textContent = message;
  box.hidden = false;
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
function clearError() { $("#js-alert").hidden = true; }

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const formatSize = n => n < 1024 ? `${n} B`
  : n < 1048576 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`;

// ---------- talking to the server ----------
async function apiFetch(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error("Could not reach the server. Is the app still running?");
  }
  let data = {};
  try { data = await response.json(); } catch { /* not JSON */ }
  if (!response.ok) throw new Error(data.error || "Something went wrong. Please try again.");
  return data;
}

function uploadPdf(file, allowEncrypted = false) {
  const form = new FormData();
  form.append("file", file);
  if (allowEncrypted) form.append("allow_encrypted", "1");
  return apiFetch("/api/upload", { method: "POST", body: form });   // -> {doc, name, pages, size, encrypted}
}

function uploadImage(file) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch("/api/upload-image", { method: "POST", body: form });
}

function postJson(url, body) {
  return apiFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// Calls a tool; if the server starts a background job (OCR) it polls until finished.
// Resolves with the URL of the preview page.
async function runTool(url, body, onProgress) {
  const first = await postJson(url, body);
  if (!first.job) return first.url;
  for (;;) {
    await new Promise(resolve => setTimeout(resolve, 700));
    const job = await apiFetch(`/api/job/${first.job}`);
    if (job.error) throw new Error(job.error);
    if (onProgress) onProgress(job.progress, job.total);
    if (job.done) return job.url;
  }
}

// ---------- option forms (used by tool pages) ----------
function collectOptions(root) {
  const values = {};
  $$("[name]", root).forEach(input => {
    if (input.type === "radio") { if (input.checked) values[input.name] = input.value; }
    else if (input.type === "checkbox") values[input.name] = input.checked;
    else values[input.name] = input.value;
  });
  return values;
}

// Elements with data-show-when="name=a|b" are shown only while that field has one of those values.
function applyVisibility(root) {
  const values = collectOptions(root);
  $$("[data-show-when]", root).forEach(node => {
    const [name, allowed] = node.dataset.showWhen.split("=");
    node.hidden = !allowed.split("|").includes(String(values[name]));
  });
}

// ---------- drop zone (click, or drag files from your computer) ----------
const isPdf = file => file.type === "application/pdf" || /\.pdf$/i.test(file.name);
const isImage = file => /^image\//.test(file.type) || /\.(jpe?g|png|gif|bmp|tiff?|webp)$/i.test(file.name);
const hasFiles = e => Array.from(e.dataTransfer?.types || []).includes("Files");

function setupDropZone(zone, input, onFiles, multiple, test = isPdf, what = "PDF") {
  const accept = fileList => {
    const all = Array.from(fileList);
    const good = all.filter(test);
    if (good.length < all.length) showError(`Only ${what} files are supported here.`);
    else clearError();
    if (good.length) onFiles(multiple ? good : good.slice(0, 1));
  };
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("keydown", e => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
  });
  input.addEventListener("change", () => { accept(input.files); input.value = ""; });
  zone.addEventListener("dragover", e => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    zone.classList.add("over");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("over"));
  zone.addEventListener("drop", e => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    zone.classList.remove("over");
    accept(e.dataTransfer.files);
  });
}

// Don't let the browser open a file if it is dropped outside the drop zone.
["dragover", "drop"].forEach(type =>
  window.addEventListener(type, e => { if (hasFiles(e)) e.preventDefault(); }));

// ---------- drag & drop re-ordering ----------
// Cards inside `container` (elements with draggable="true") can be dragged into a new place.
function makeSortable(container, onChange) {
  let dragged = null;

  container.addEventListener("dragstart", e => {
    const item = e.target.closest ? e.target.closest(".card-item") : null;
    if (!item || !container.contains(item)) return;
    dragged = item;
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", "");          // Firefox needs some data
    requestAnimationFrame(() => item.classList.add("dragging"));
  });

  container.addEventListener("dragover", e => {
    if (!dragged) return;
    e.preventDefault();
    const target = e.target.closest(".card-item");
    if (!target || target === dragged) return;
    const box = target.getBoundingClientRect();
    const after = e.clientX - box.left > box.width / 2;   // right half => drop after it
    container.insertBefore(dragged, after ? target.nextSibling : target);
    if (onChange) onChange();
  });

  container.addEventListener("drop", e => { if (dragged) e.preventDefault(); });

  container.addEventListener("dragend", () => {
    if (dragged) dragged.classList.remove("dragging");
    dragged = null;
    if (onChange) onChange();
  });
}

// ---------- one page thumbnail card (used by Remove, Organize and Rotate) ----------
function pageCard(doc, n, { draggable = false, badge = false } = {}) {
  const card = el("div", "card-item page-card");
  card.dataset.page = n;
  card.draggable = draggable;

  const img = el("img");
  img.src = `/thumb/${doc}/${n}.jpg`;
  img.alt = `Page ${n}`;
  img.loading = "lazy";
  img.draggable = false;               // so the card is dragged, not the picture
  const thumb = el("div", "thumb");
  thumb.append(img);

  if (badge) card.append(el("span", "badge", n));
  card.append(thumb, el("div", "caption", `Page ${n}`));
  return card;
}

// ---------- keep-alive ping + links that open in the normal browser ----------
// The packaged app closes itself when the page has been gone for a few minutes.
function ping() { fetch("/api/ping", { method: "POST" }).catch(() => {}); }
ping();
setInterval(ping, 10000);

// <a data-external> opens in the user's default browser instead of inside the app window.
document.addEventListener("click", e => {
  const link = e.target.closest ? e.target.closest("a[data-external]") : null;
  if (!link) return;
  e.preventDefault();
  postJson("/api/open-external", { url: link.href }).catch(() => window.open(link.href, "_blank"));
});
