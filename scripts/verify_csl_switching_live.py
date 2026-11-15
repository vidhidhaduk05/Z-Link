#!/usr/bin/env python3.11
"""
Empirical verification script for dynamic CSL Citation Style Switching in Headless Chrome via CDP.
"""
import asyncio
import json
import subprocess
import time
import urllib.request
import docx
import io
import base64
import websockets

CHROME_BIN = "/home/vd00026/.local/bin/google-chrome"
PORT = 9222
APP_URL = "http://localhost:8765"

async def send_cdp(ws, method, params=None):
    call_id = int(time.time() * 1000) % 1000000
    msg = {"id": call_id, "method": method, "params": params or {}}
    await ws.send(json.dumps(msg))
    while True:
        resp = json.loads(await ws.recv())
        if resp.get("id") == call_id:
            if "error" in resp:
                raise RuntimeError(f"CDP Error in {method}: {resp['error']}")
            return resp.get("result", {})

async def eval_js(ws, expr):
    res = await send_cdp(ws, "Runtime.evaluate", {
        "expression": expr,
        "awaitPromise": True,
        "returnByValue": True
    })
    if "exceptionDetails" in res:
        raise RuntimeError(f"JS Exception: {res['exceptionDetails']}")
    return res.get("result", {}).get("value")

async def run_verification():
    # 1. Start headless chrome
    chrome_proc = subprocess.Popen([
        CHROME_BIN,
        f"--remote-debugging-port={PORT}",
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        APP_URL
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        time.sleep(2)
        # Find page websocket
        req = urllib.request.urlopen(f"http://localhost:{PORT}/json")
        tabs = json.loads(req.read().decode())
        page_tab = next(t for t in tabs if t.get("type") == "page")
        ws_url = page_tab["webSocketDebuggerUrl"]
        print(f"Connected to page: {ws_url}")

        async with websockets.connect(ws_url, max_size=200_000_000) as ws:
            await send_cdp(ws, "Page.enable")
            await send_cdp(ws, "Runtime.enable")

            # Wait for DOM ready
            for _ in range(20):
                ready = await eval_js(ws, "document.readyState === 'complete'")
                if ready:
                    break
                await asyncio.sleep(0.5)

            title = await eval_js(ws, "document.title")
            print(f"Page title: {title}")

            # Click ACTA2 button to load the full manuscript
            print("Triggering btnActa2.click()...")
            await eval_js(ws, "document.getElementById('btnActa2').click()")

            # Wait until parsedData is populated and table rows rendered
            for _ in range(40):
                loaded = await eval_js(ws, "window.appState && window.appState.parsedData && window.appState.parsedData.references.length > 0")
                if loaded:
                    break
                await asyncio.sleep(0.5)

            ref_count = await eval_js(ws, "window.appState.parsedData.references.length")
            site_count = await eval_js(ws, "window.appState.parsedData.sites.length")
            print(f"Loaded manuscript: {ref_count} references, {site_count} citation sites.")
            assert ref_count == 43, f"Expected 43 references, got {ref_count}"
            assert site_count == 33, f"Expected 33 citation sites, got {site_count}"

            # Verify initial style is AMA
            initial_style = await eval_js(ws, "window.appState.targetStyle")
            badge_text = await eval_js(ws, "document.getElementById('targetStyleBadge').textContent")
            print(f"Initial style: {initial_style}, Badge: {badge_text}")
            assert initial_style == "ama"
            assert "AMA" in badge_text

            # Check initial pills are numeric
            initial_pills = await eval_js(ws, """
                Array.from(document.querySelectorAll('#manuscriptViewer .cit-pill')).slice(0, 5).map(p => ({
                    text: p.textContent,
                    isSup: p.classList.contains('cit-sup'),
                    nums: p.dataset.nums
                }))
            """)
            print("Initial AMA Pills:", initial_pills)
            assert all(p["isSup"] for p in initial_pills), "AMA pills must be superscript"
            assert any(p["text"] in ["1", "2", "3", "4", "5", "1-3"] for p in initial_pills)

            # ---------------- TEST SWITCHING TO APA 7TH ----------------
            print("\n--- Switching Target Style to APA 7th Edition ---")
            await eval_js(ws, """
                (() => {
                    const select = document.getElementById('targetStyleSelect');
                    select.value = 'apa-7th';
                    select.dispatchEvent(new Event('change'));
                })()
            """)
            await asyncio.sleep(0.5)

            apa_style = await eval_js(ws, "window.appState.targetStyle")
            apa_badge = await eval_js(ws, "document.getElementById('targetStyleBadge').textContent")
            print(f"Active style: {apa_style}, Badge: {apa_badge}")
            assert apa_style == "apa-7th"
            assert "Psychological Association" in apa_badge or "APA" in apa_badge

            # Check pills in APA mode: must be author-date, NOT superscript
            apa_pills = await eval_js(ws, """
                Array.from(document.querySelectorAll('#manuscriptViewer .cit-pill')).slice(0, 5).map(p => ({
                    text: p.textContent,
                    isSup: p.classList.contains('cit-sup'),
                    nums: p.dataset.nums
                }))
            """)
            print("APA Pills (sample 5):", json.dumps(apa_pills, indent=2))
            for p in apa_pills:
                assert not p["isSup"], f"APA pill {p['text']} should not be superscript"
                assert p["text"].startswith("(") and p["text"].endswith(")"), f"APA pill {p['text']} must be enclosed in parentheses"
                assert any(c.isalpha() for c in p["text"]), f"APA pill {p['text']} must contain author name"

            # Check clinical counts immunity in APA mode (e.g. '13 patients' in P52)
            clinical_check = await eval_js(ws, """
                (() => {
                    const viewer = document.getElementById('manuscriptViewer');
                    const text = viewer.textContent;
                    const html = viewer.innerHTML;
                    return {
                        has13PatientsText: text.includes('13 patients'),
                        has13PatientsPure: html.includes('13 patients'),
                        hasCorrupted13Patients: html.includes('1<span class="cit-pill')
                    };
                })()
            """)
            print("Clinical counts immunity check in APA mode:", clinical_check)
            assert clinical_check["has13PatientsText"], "Must contain '13 patients'"
            assert clinical_check["has13PatientsPure"], "'13 patients' must remain uncorrupted plain text"
            assert not clinical_check["hasCorrupted13Patients"], "'13 patients' must not be chopped into a citation pill"

            # Check Reference Table Sorting in APA mode: Must be Alphabetical
            first_three_apa_rows = await eval_js(ws, """
                Array.from(document.querySelectorAll('#referencesTableBody tr')).slice(0, 5).map(tr => ({
                    cell1: tr.children[0].textContent.trim(),
                    authorDateTag: tr.children[0].querySelector('span') ? tr.children[0].querySelector('span').textContent.trim() : ''
                }))
            """)
            print("First 5 APA table rows:", json.dumps(first_three_apa_rows, indent=2))
            authors = [r["authorDateTag"].split(",")[0].strip().lower() for r in first_three_apa_rows]
            print("Extracted primary authors from tags:", authors)
            assert authors == sorted(authors), f"APA table rows must be sorted alphabetically: {authors}"

            # ---------------- TEST SWITCHING TO VANCOUVER BRACKET ----------------
            print("\n--- Switching Target Style to Vancouver (Square Brackets) ---")
            await eval_js(ws, """
                (() => {
                    const select = document.getElementById('targetStyleSelect');
                    select.value = 'vancouver-bracket';
                    select.dispatchEvent(new Event('change'));
                })()
            """)
            await asyncio.sleep(0.5)

            vanc_badge = await eval_js(ws, "document.getElementById('targetStyleBadge').textContent")
            print(f"Vancouver badge: {vanc_badge}")
            assert "Vancouver" in vanc_badge

            vanc_pills = await eval_js(ws, """
                Array.from(document.querySelectorAll('#manuscriptViewer .cit-pill')).slice(0, 5).map(p => ({
                    text: p.textContent,
                    isSup: p.classList.contains('cit-sup'),
                    nums: p.dataset.nums
                }))
            """)
            print("Vancouver Pills:", json.dumps(vanc_pills, indent=2))
            for p in vanc_pills:
                assert not p["isSup"], "Vancouver bracket citations should not be superscript"
                assert p["text"].startswith("[") and p["text"].endswith("]"), f"Vancouver citation {p['text']} must have square brackets"

            # ---------------- TEST IN-BROWSER DOCX EXPORT IN APA MODE ----------------
            print("\n--- Generating APA Linked Word Document via Browser Engine ---")
            docx_b64 = await eval_js(ws, """
                (async () => {
                    const { injectZoteroFieldsInBrowser } = await import('./static/js/docx_engine.js');
                    const blob = await injectZoteroFieldsInBrowser(
                        window.appState.parsedData,
                        window.appState.verdicts,
                        false, // renumberAma false for author-date
                        false, // clean mode
                        "Co-Scientist",
                        true,
                        "apa-7th"
                    );
                    const buf = await blob.arrayBuffer();
                    const bytes = new Uint8Array(buf);
                    let binary = '';
                    for (let i = 0; i < bytes.byteLength; i++) {
                        binary += String.fromCharCode(bytes[i]);
                    }
                    return btoa(binary);
                })()
            """)
            assert docx_b64, "Docx export returned null or empty"
            docx_bytes = base64.b64decode(docx_b64)
            print(f"Generated APA docx in browser: {len(docx_bytes)} bytes")
            assert len(docx_bytes) > 10000

            doc = docx.Document(io.BytesIO(docx_bytes))
            doc_xml = doc._part._element.xml

            # Check APA preference and hanging indents
            assert "apa" in doc_xml, "Generated docx must configure APA style in Zotero doc prefs"
            assert "ADDIN ZOTERO_BIBL" in doc_xml, "Generated docx must contain ADDIN ZOTERO_BIBL"
            assert 'w:hanging="720"' in doc_xml, "APA bibliography entries must have w:hanging='720'"
            print("✓ Docx OpenXML verified: APA style, ADDIN ZOTERO_BIBL, and w:hanging='720' confirmed.")

            print("\nALL LIVE BROWSER CSL VERIFICATION CHECKS PASSED PERFECTLY!")

    finally:
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=3)
        except Exception:
            chrome_proc.kill()

if __name__ == "__main__":
    asyncio.run(run_verification())
