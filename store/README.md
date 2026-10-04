# Publishing Editora PDFEdit on the Microsoft Store

You need: a Windows PC, a Microsoft Partner Center developer account
(https://partner.microsoft.com/dashboard - registration terms/fees change, check the page),
and an internet connection for the first build.

## 1. Reserve the name and copy your identity
1. In Partner Center: **Apps and games -> New product -> MSIX or PWA app**, reserve **Editora PDFEdit**
   (if the name is taken, pick another and also change `DisplayName` in `AppxManifest.xml.template`).
2. Open **Product management -> Product identity** and copy these two values into
   `store\store_config.json`, exactly, character for character:
   - `Package/Identity/Name`      -> `identity_name`
   - `Package/Identity/Publisher` -> `publisher`   (starts with `CN=`)

## 2. Build the package
Double-click **`build_store.bat`** (in the project folder). It installs the packages, copies the OCR
engine in, builds the app folder and packs it. Result: `dist\EditoraPDFEdit_1.0.0.0_x64.msix`.

- It needs `makeappx.exe` from the free **Windows 10/11 SDK** (the script tells you if it is missing).
- The package is **unsigned on purpose** - the Store signs it for you after submission.
- The version comes from `APP_VERSION` in `app.py`. Raise it for every update you publish.

### GitHub Actions build

The workflow in `.github/workflows/build-msix.yml` runs on `windows-2022`. It installs the
dependencies and bundled OCR engine, runs the tests, builds the x64 app, creates the MSIX,
and uploads it as the `EditoraPDFEdit-MSIX` workflow artifact. Run it manually from the
Actions tab, or push a tag such as `v1.0.0`.

## 3. Try it before submitting (optional)
Run `dist\EditoraPDFEdit\EditoraPDFEdit.exe` directly. It should open the app in its own window,
and quit by itself a few minutes after you close that window. Also test OCR, drag & drop of files
and "Download" on the machine you build on.

## 4. Submit in Partner Center
- **Packages**: upload the `.msix`.
- **Submission options -> restricted capability `runFullTrust`**: paste (keep it short):
  > Editora PDFEdit is a classic Win32 desktop app (Python) packaged as MSIX. It needs full trust to
  > read the PDF/image files the user selects, run its bundled OCR engine (tesseract.exe) as a helper
  > process, run its local-only (127.0.0.1) processing server and show its window using the installed
  > Microsoft Edge. It reads no other data and sends nothing off the device.
- **Properties**: category *Productivity*. Age rating: answer the questionnaire (no user-generated
  content, no online interaction, no purchases).
- **Privacy policy URL**: Partner Center asks for one if an app collects personal information; this app
  collects none, but a URL is still good practice. Publish `PRIVACY.md` somewhere public
  (for example GitHub Pages) and paste the link.
- **Store listing**: use the text below. Logos: `store\listing\store_icon_300x300.png` (and the
  1080x1080 version). Add at least one **screenshot** (take 1366x768 or larger screenshots of the
  home page, Merge, Remove pages and OCR).
- Submit for certification. Review usually takes a few days.

## Store listing text (edit freely)
**Name:** Editora PDFEdit

**Short description:** Merge, split, convert, compress, OCR and protect PDFs - offline and private.

**Description:**
Editora PDFEdit is a complete PDF toolbox that works entirely on your PC. Your files are never uploaded.

- Merge PDFs - drag cards to set the order
- Split PDFs - by range, every page, or extract pages
- Remove, reorder and rotate pages - click or drag page thumbnails
- Compress PDFs to share them more easily
- OCR - turn scanned PDFs into searchable PDFs or text (English, Sinhala and Tamil included)
- Convert images to PDF, and PDF to JPG/PNG or Word
- Add page numbers and watermarks
- Protect a PDF with a password, or remove a password you know
- Preview every result and rename it before saving

**Keywords:** PDF, merge PDF, split PDF, compress PDF, OCR, PDF to Word, PDF to JPG, JPG to PDF, watermark, offline

## Things to know
- Microsoft Edge (preinstalled on Windows 10/11) is used to show the app window. If it is missing
  the app falls back to your default browser.
- Certification tests that the app launches without crashing; if something goes wrong at start-up the
  app writes `app.log` (in `%LOCALAPPDATA%\Editora PDFEdit`) and shows a message.
- OCR accuracy depends on scan quality. To add OCR languages, edit `OCR_LANGS` in `setup_build.bat`.
