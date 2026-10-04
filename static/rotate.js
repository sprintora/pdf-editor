"use strict";

const workspace = $("#workspace");
const grid = $("#pages");
const goButton = $("#go");
const counter = $("#counter");
const fileInfo = $("#file-info");
const goLabel = goButton.textContent;
let doc = null;

setupDropZone($("#dropzone"), $("#file-input"), files => load(files[0]), false);

async function load(file) {
  doc = null;
  grid.replaceChildren();
  workspace.hidden = false;
  fileInfo.textContent = `Uploading ${file.name}…`;
  refresh();
  try {
    const d = await uploadPdf(file);
    doc = d.doc;
    fileInfo.textContent = `${d.name} — ${plural(d.pages, "page")}`;
    for (let n = 1; n <= d.pages; n++) grid.append(rotatableCard(n));
    refresh();
  } catch (err) {
    workspace.hidden = true;
    showError(err.message);
  }
}

function rotatableCard(n) {
  const card = pageCard(doc, n);
  card.dataset.rot = "0";
  const img = card.querySelector("img");
  img.addEventListener("load", () => applyRotation(card));
  const buttons = el("div", "rot-buttons");
  [["↺", -90, "Rotate left"], ["↻", 90, "Rotate right"]].forEach(([label, delta, title]) => {
    const b = el("button", "rot-btn", label);
    b.type = "button"; b.title = title; b.dataset.delta = delta;
    buttons.append(b);
  });
  card.append(buttons);
  return card;
}

function applyRotation(card) {
  const degrees = Number(card.dataset.rot);
  const img = card.querySelector("img");
  const box = card.querySelector(".thumb");
  let scale = 1;
  if (degrees % 180 !== 0 && img.offsetWidth && img.offsetHeight) {
    // a quarter turn swaps width and height, so shrink the page to keep it inside the box
    scale = Math.min(1, box.clientWidth / img.offsetHeight, box.clientHeight / img.offsetWidth);
  }
  img.style.transform = `rotate(${degrees}deg) scale(${scale})`;
}

function rotateCard(card, delta) {
  card.dataset.rot = String((Number(card.dataset.rot) + delta + 360) % 360);
  card.classList.toggle("rotated", card.dataset.rot !== "0");
  applyRotation(card);
}

grid.addEventListener("click", e => {
  const button = e.target.closest(".rot-btn");
  if (!button) return;
  rotateCard(button.closest(".page-card"), Number(button.dataset.delta));
  refresh();
});
$("#all-left").addEventListener("click", () => { [...grid.children].forEach(c => rotateCard(c, -90)); refresh(); });
$("#all-right").addEventListener("click", () => { [...grid.children].forEach(c => rotateCard(c, 90)); refresh(); });
$("#reset").addEventListener("click", () => {
  [...grid.children].forEach(c => { c.dataset.rot = "0"; c.classList.remove("rotated"); applyRotation(c); });
  refresh();
});

const rotations = () => {
  const result = {};
  [...grid.children].forEach(c => { if (c.dataset.rot !== "0") result[c.dataset.page] = Number(c.dataset.rot); });
  return result;
};

function refresh() {
  const count = Object.keys(rotations()).length;
  counter.textContent = doc ? (count ? `${plural(count, "page")} rotated.` : "No pages rotated yet.") : "";
  goButton.disabled = !doc || count === 0;
}

goButton.addEventListener("click", async () => {
  goButton.disabled = true;
  goButton.textContent = "Working…";
  clearError();
  try {
    window.location.href = await runTool("/api/rotate", { doc, rotations: rotations() });
  } catch (err) {
    showError(err.message);
    goButton.textContent = goLabel;
    refresh();
  }
});
