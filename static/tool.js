"use strict";

const tool = $("#tool");
const api = tool.dataset.api;
const allowEncrypted = tool.dataset.allowEncrypted === "1";
const workspace = $("#workspace");
const options = $("#options");
const goButton = $("#go");
const progress = $("#progress");
const goLabel = goButton.textContent;
let doc = null;

setupDropZone($("#dropzone"), $("#file-input"), files => load(files[0]), false);
options.addEventListener("input", () => applyVisibility(options));
options.addEventListener("change", () => applyVisibility(options));
applyVisibility(options);

async function load(file) {
  doc = null;
  goButton.disabled = true;
  workspace.hidden = false;
  $("#file-name").textContent = file.name;
  $("#file-meta").textContent = "Uploading…";
  const thumb = $("#first-thumb");
  thumb.hidden = true;
  try {
    const d = await uploadPdf(file, allowEncrypted);
    doc = d.doc;
    $("#file-meta").textContent = d.encrypted
      ? "🔒 Password protected — enter the password below"
      : `${plural(d.pages, "page")} · ${formatSize(d.size)}`;
    if (!d.encrypted) {
      thumb.src = `/thumb/${d.doc}/1.jpg`;
      thumb.hidden = false;
    }
    goButton.disabled = false;
  } catch (err) {
    workspace.hidden = true;
    showError(err.message);
  }
}

function setProgress(done, total) {
  progress.hidden = false;
  $("#bar-fill").style.width = `${total ? Math.round(100 * done / total) : 0}%`;
  $("#progress-text").textContent = `Page ${Math.min(done + 1, total)} of ${total}`;
}

goButton.addEventListener("click", async () => {
  const values = collectOptions(options);
  if ("confirm" in values && values.password !== values.confirm) {
    showError("The two passwords don't match.");
    return;
  }
  clearError();
  goButton.disabled = true;
  goButton.textContent = "Working…";
  try {
    const url = await runTool(api, { doc, ...values }, setProgress);
    window.location.href = url;
  } catch (err) {
    showError(err.message);
    goButton.textContent = goLabel;
    goButton.disabled = false;
    progress.hidden = true;
  }
});
