# Co-Scientist Reference Auditor & Zotero Linker

An academic editorial platform for auditing biomedical and scholarly manuscripts, validating DOI reachability against Crossref and PubMed, mapping in-text citation usage down to the exact sentence, and injecting native Zotero Word field codes (`ADDIN ZOTERO_ITEM`, `ADDIN ZOTERO_BIBL`, `ADDIN ZOTERO_PREF_1`) into `.docx` files.

Designed for zero-cost static hosting on **GitHub Pages** with an optional local/HPC Python backend.

---

## 🌟 Key Capabilities

1. **In-Browser Word (.docx) Processing**:
   - Parses `.docx` files directly in the user's browser using `JSZip` and XML DOM parsing.
   - Detects numbered citations in both parenthetical `(1, 2)` / `(1-3)` and superscript formats.
   - Isolates the bibliography and extracts author lists, journal titles, years, and DOIs.

2. **Live Reachability & Crossref Validation**:
   - Direct browser-to-scholarly CORS requests to **Crossref REST API** (`https://api.crossref.org/works/{doi}`) and **PubMed E-utilities**.
   - Validates whether DOIs resolve to active publisher landing pages.
   - Real-time status badges:
     - 🟢 **Reachable (200 OK)**: Registered and live publisher landing verified.
     - 🔴 **Broken Link (404)**: Dead or malformed DOI flagged for author correction.
     - ⚪ **Missing DOI**: Flagged for retrieval via PubMed or manual input.

3. **In-Manuscript Sentence & Usage Mapping**:
   - Interactive split-pane explorer: displays every paragraph and exact sentence where each reference is cited.
   - **AMA Consecutive Order Audit**: Flags any references that are cited out of order on first mention.

4. **Native Zotero Field Injection & RIS Export**:
   - Injects native Microsoft Word field codes (`ADDIN ZOTERO_ITEM` with CSL-JSON) into body paragraphs.
   - Wraps the bibliography in an `ADDIN ZOTERO_BIBL` field and configures AMA 11th Edition document preferences.
   - Exports clean, standardized `.ris` files for 1-click import into reference managers.
   - When the linked `.docx` is opened in Word with the official Zotero plugin, clicking **Refresh** populates the bibliography and enables automated renumbering!

---

## 🚀 GitHub Pages Deployment (Zero Server Required)

This repository is pre-configured to be hosted directly on **GitHub Pages**:

1. **Push to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Deploy Co-Scientist Reference Auditor & Zotero Linker"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<your-repo-name>.git
   git push -u origin main
   ```

2. **Enable GitHub Pages**:
   - Navigate to your repository on GitHub.
   - Go to **Settings** → **Pages**.
   - Under **Build and deployment** → **Source**, select **Deploy from a branch**.
   - Under **Branch**, select `main` and folder `/ (root)`.
   - Click **Save**.

3. **Live Application URL**:
   Your site will be live at:
   `https://<your-username>.github.io/<your-repo-name>/`

---

## 💻 Running Locally (Optional Python Backend)

You can also run the application locally or connect it to an HPC workstation:

```bash
# Run the local server on port 8765
python3.11 run_server.py
```

Open your browser to: **`http://localhost:8765`**

### Running the Test Suite:
```bash
python3.11 -m unittest tests/test_engine.py
```

---

## 🎨 Academic Editorial Master Theme

The interface strictly adheres to the 7-color academic editorial standard:
- **Primary Wine:** `#3a0f34`
- **Deepest Plum:** `#1a0017`
- **Paper Canvas:** `#fbf9f4`
- **Surface White:** `#ffffff`
- **Editorial Plum:** `#814d75`
- **Reading Inks:** `#4f444b`, `#62535d`
- **Border Outline:** `#d2c2cb`
- **Typography:** Bodoni Moda (Headings), Newsreader (Reading Body), Work Sans (Controls).

---

## 📄 License

MIT License. Designed for reproducible scholarly communication.

