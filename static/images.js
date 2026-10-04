"use strict";

const grid = $("#cards");
const options = $("#options");
const goButton = $("#go");
const status = $("#status");
const goLabel = goButton.textContent;

setupDropZone($("#dropzone"), $("#file-input"), addFiles, true, isImage, "image");
makeSortable(grid, refresh);
options.addEventListener("change", () => applyVisibility(options));
applyVisibility(options);

grid.addEventListener("click", e => {
  if (e.target.closest(".x")) {
    e.target.closest(".pdf-card").remove();
    refresh();
  }
});

function addFiles(files) {
  files.forEach(file => {
    const card = el("div", "card-item pdf-card loading");
    card.draggable = true;
    const remove = el("button", "x", "✕");
    remove.type = "button";
    remove.title = "Remove this image";
    const thumb = el("div", "thumb");
    const meta = el("div", "meta", "Uploading…");
    card.append(el("span", "badge"), remove, thumb, el("div", "name", file.name), meta);
    grid.append(card);

    uploadImage(file)
      .then(d => {
        card.dataset.doc = d.doc;
        card.title = d.name;
        const img = el("img");
        img.src = `/thumb/${d.doc}/1.jpg`;
        img.alt = "";
        img.draggable = false;
        thumb.append(img);
        meta.textContent = `${d.width} × ${d.height}`;
      })
      .catch(err => {
        card.classList.add("failed");
        meta.textContent = err.message;
      })
      .finally(() => { card.classList.remove("loading"); refresh(); });
  });
  refresh();
}

const readyCards = () => [...grid.children].filter(c => c.dataset.doc);

function refresh() {
  [...grid.children].forEach((card, i) => { card.querySelector(".badge").textContent = i + 1; });
  const busy = grid.querySelector(".loading") !== null;
  const ready = readyCards().length;
  goButton.disabled = busy || ready < 1;
  status.textContent = busy ? "Uploading…" : ready ? `${plural(ready, "image")} → ${plural(ready, "page")}` : "";
}

goButton.addEventListener("click", async () => {
  goButton.disabled = true;
  goButton.textContent = "Creating PDF…";
  clearError();
  try {
    const body = { docs: readyCards().map(c => c.dataset.doc), ...collectOptions(options) };
    window.location.href = await runTool("/api/image-to-pdf", body);
  } catch (err) {
    showError(err.message);
    goButton.textContent = goLabel;
    refresh();
  }
});
