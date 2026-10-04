"use strict";

const workspace = $("#workspace");
const grid = $("#pages");
const goButton = $("#go");
const status = $("#status");
const fileInfo = $("#file-info");
const goLabel = goButton.textContent;

let doc = null;

setupDropZone($("#dropzone"), $("#file-input"), files => load(files[0]), false);
makeSortable(grid, refresh);

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
    if (d.pages < 2) showError("This PDF has only one page, so there is nothing to reorder.");
    for (let n = 1; n <= d.pages; n++) {
      grid.append(pageCard(doc, n, { draggable: true, badge: true }));
    }
    refresh();
  } catch (err) {
    workspace.hidden = true;
    showError(err.message);
  }
}

const currentOrder = () => [...grid.children].map(c => Number(c.dataset.page));

function refresh() {
  const order = currentOrder();
  order.forEach((_, i) => { grid.children[i].querySelector(".badge").textContent = i + 1; });
  const changed = order.some((n, i) => n !== i + 1);
  goButton.disabled = !doc || !changed;
  status.textContent = changed ? "" : (doc ? "Drag a page to a new place to enable this." : "");
}

function place(cards) {            // put cards back in the grid in the given order
  cards.forEach(c => grid.append(c));
  refresh();
}

$("#reverse-btn").addEventListener("click", () => place([...grid.children].reverse()));

$("#shuffle-btn").addEventListener("click", () => {
  const cards = [...grid.children];
  for (let i = cards.length - 1; i > 0; i--) {          // Fisher–Yates shuffle
    const j = Math.floor(Math.random() * (i + 1));
    [cards[i], cards[j]] = [cards[j], cards[i]];
  }
  place(cards);
});

$("#reset-btn").addEventListener("click", () =>
  place([...grid.children].sort((a, b) => a.dataset.page - b.dataset.page)));

goButton.addEventListener("click", async () => {
  goButton.disabled = true;
  goButton.textContent = "Working…";
  clearError();
  try {
    const { url } = await postJson("/api/organize", { doc, order: currentOrder() });
    window.location.href = url;
  } catch (err) {
    showError(err.message);
    goButton.textContent = goLabel;
    refresh();
  }
});
