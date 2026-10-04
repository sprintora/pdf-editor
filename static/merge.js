"use strict";

const grid = $("#cards");
const goButton = $("#go");
const status = $("#status");
const goLabel = goButton.textContent;

setupDropZone($("#dropzone"), $("#file-input"), addFiles, true);
makeSortable(grid, refresh);

grid.addEventListener("click", e => {
  if (e.target.closest(".x")) {
    e.target.closest(".pdf-card").remove();
    refresh();
  }
});

function addFiles(files) {
  files.forEach(file => {
    // The card appears straight away (in the order dropped) and fills in when the upload ends.
    const card = el("div", "card-item pdf-card loading");
    card.draggable = true;
    const remove = el("button", "x", "✕");
    remove.type = "button";
    remove.title = "Remove this file";
    const thumb = el("div", "thumb");
    const meta = el("div", "meta", "Uploading…");
    card.append(el("span", "badge"), remove, thumb, el("div", "name", file.name), meta);
    grid.append(card);

    uploadPdf(file)
      .then(d => {
        card.dataset.doc = d.doc;
        card.title = d.name;
        const img = el("img");
        img.src = `/thumb/${d.doc}/1.jpg`;
        img.alt = "";
        img.draggable = false;
        thumb.append(img);
        meta.textContent = plural(d.pages, "page");
      })
      .catch(err => {
        card.classList.add("failed");
        meta.textContent = err.message;
      })
      .finally(() => { card.classList.remove("loading"); refresh(); });
  });
  refresh();
}

function readyCards() {
  return [...grid.children].filter(c => c.dataset.doc);
}

function refresh() {
  [...grid.children].forEach((card, i) => { card.querySelector(".badge").textContent = i + 1; });
  const busy = grid.querySelector(".loading") !== null;
  const ready = readyCards().length;
  goButton.disabled = busy || ready < 2;
  status.textContent = busy ? "Uploading…"
    : ready === 0 ? ""
    : ready === 1 ? "Add at least one more PDF to merge."
    : `${plural(ready, "file")} will be merged in this order.`;
}

goButton.addEventListener("click", async () => {
  goButton.disabled = true;
  goButton.textContent = "Merging…";
  clearError();
  try {
    const { url } = await postJson("/api/merge", { docs: readyCards().map(c => c.dataset.doc) });
    window.location.href = url;
  } catch (err) {
    showError(err.message);
    goButton.textContent = goLabel;
    refresh();
  }
});
