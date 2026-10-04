"use strict";

const workspace = $("#workspace");
const grid = $("#pages");
const goButton = $("#go");
const counter = $("#counter");
const fileInfo = $("#file-info");
const specInput = $("#spec");
const goLabel = goButton.textContent;

let doc = null;       // server-side id of the uploaded PDF
let total = 0;
let anchor = null;    // last clicked card (for Shift+click ranges)

setupDropZone($("#dropzone"), $("#file-input"), files => load(files[0]), false);

async function load(file) {
  doc = null; anchor = null;
  grid.replaceChildren();
  workspace.hidden = false;
  fileInfo.textContent = `Uploading ${file.name}…`;
  refresh();
  try {
    const d = await uploadPdf(file);
    doc = d.doc; total = d.pages;
    fileInfo.textContent = `${d.name} — ${plural(d.pages, "page")}`;
    for (let n = 1; n <= total; n++) {
      const card = pageCard(doc, n);
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      card.setAttribute("aria-pressed", "false");
      grid.append(card);
    }
    refresh();
  } catch (err) {
    workspace.hidden = true;
    showError(err.message);
  }
}

const isMarked = card => card.classList.contains("marked");
function setMarked(card, on) {
  card.classList.toggle("marked", on);
  card.setAttribute("aria-pressed", String(on));
}
const markedPages = () => [...grid.children].filter(isMarked).map(c => Number(c.dataset.page));

grid.addEventListener("click", e => {
  const card = e.target.closest(".page-card");
  if (!card) return;
  if (e.shiftKey && anchor && anchor !== card) {
    const cards = [...grid.children];
    const [a, b] = [cards.indexOf(anchor), cards.indexOf(card)].sort((x, y) => x - y);
    const state = !isMarked(card);
    cards.slice(a, b + 1).forEach(c => setMarked(c, state));
  } else {
    setMarked(card, !isMarked(card));
  }
  anchor = card;
  refresh();
});

grid.addEventListener("keydown", e => {
  if ((e.key === "Enter" || e.key === " ") && e.target.classList.contains("page-card")) {
    e.preventDefault();
    e.target.click();
  }
});

$("#mark-btn").addEventListener("click", async () => {
  if (!doc) return;
  try {
    const { pages } = await postJson("/api/parse-pages", { doc, spec: specInput.value });
    pages.forEach(n => setMarked(grid.children[n - 1], true));
    clearError();
    refresh();
  } catch (err) {
    showError(err.message);
  }
});
specInput.addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); $("#mark-btn").click(); }
});

$("#clear-btn").addEventListener("click", () => {
  [...grid.children].forEach(c => setMarked(c, false));
  refresh();
});

function refresh() {
  const count = markedPages().length;
  counter.textContent = !total ? ""
    : count === total ? "All pages are marked — at least one page must stay."
    : count === 0 ? "No pages marked yet."
    : `${plural(count, "page")} marked for removal (${total - count} will remain).`;
  goButton.disabled = !doc || count === 0 || count === total;
}

goButton.addEventListener("click", async () => {
  goButton.disabled = true;
  goButton.textContent = "Working…";
  clearError();
  try {
    const { url } = await postJson("/api/remove", { doc, pages: markedPages() });
    window.location.href = url;
  } catch (err) {
    showError(err.message);
    goButton.textContent = goLabel;
    refresh();
  }
});
