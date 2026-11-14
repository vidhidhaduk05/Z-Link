#!/usr/bin/env python3
"""
zotero_manuscript_linker.py
===========================
Permanent, reusable tool: turn ANY manuscript (.docx) that uses numbered
citations into a fully Zotero-managed document.

  1. Reads your Zotero library through the LOCAL API (http://localhost:23119/api/)
  2. Imports references from a RIS file that are not yet in your library
     (Zotero 10+; older versions: File -> Import the RIS, then rerun)
  3. Matches every reference by DOI and fetches its CSL-JSON
  4. Finds the numbered citations in the manuscript (parenthetical OR already
     superscript), converts them to AMA superscript if needed, and replaces
     them with native Zotero citation fields (ADDIN ZOTERO_ITEM)
  5. Wraps the numbered reference list in a Zotero bibliography field
     (ADDIN ZOTERO_BIBL) and writes AMA document preferences
  6. Saves <name>_zotero_linked.docx

After linking, add/remove references through the Zotero tab in Word
(Add/Edit Citation, Refresh) — Zotero renumbers everything automatically.

Requirements:  Python 3.10+, `pip install requests python-docx`
               Zotero desktop app RUNNING (local API enabled)

Usage:
  python zotero_manuscript_linker.py manuscript.docx references.ris
  python zotero_manuscript_linker.py manuscript.docx references.ris --dry-run
  python zotero_manuscript_linker.py manuscript.docx references.ris --yes
  python zotero_manuscript_linker.py manuscript.docx references.ris --style american-medical-association

Detection safety: the script shows every citation site it found (with context)
and asks for confirmation before writing unless --yes is given. It never
modifies the reference list text or any other prose.
"""

import argparse, json, random, re, string, sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: run  pip install requests")
try:
    import docx
except ImportError:
    sys.exit("Missing dependency: run  pip install python-docx")

from docx.oxml.ns import qn

API_BASE = "http://localhost:23119/api"
TIMEOUT = 30
DEFAULT_STYLE = "http://www.zotero.org/styles/american-medical-association"
DEFAULT_STYLE_NAME = "American Medical Association 11th edition"

CSL_CITATION_SCHEMA = ("https://github.com/citation-style-language/schema/"
                       "raw/master/csl-citation.json")

PAREN_CIT = re.compile(r'\((\d{1,3}(?:\s*[-–]\s*\d{1,3})?'
                       r'(?:\s*,\s*\d{1,3}(?:\s*[-–]\s*\d{1,3})?)*)\)')
SUP_CIT = re.compile(r'^\d{1,3}([,-]\d{1,3})*$')
REF_START = re.compile(r'^\d{1,3}\.\s')
REF_HEADER = re.compile(r'^(REFERENCES|Reference List|Bibliography)\s*$', re.I)
BODY_START = re.compile(r'^(ABSTRACT|SUMMARY STATEMENT|INTRODUCTION|Introduction'
                        r'|BACKGROUND|Key Results)\s*$')


# ------------------------------- RIS ----------------------------------------

def ris_entries(path):
    entries, cur = [], None
    line_re = re.compile(r'^([A-Z][A-Z0-9])  - (.*)$|^([A-Z][A-Z0-9]) - (.*)$')
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = line_re.match(line.rstrip('\n'))
        if not m:
            continue
        tag = m.group(1) or m.group(3)
        val = (m.group(2) if m.group(1) else m.group(4)).strip()
        if tag == 'TY':
            cur = {'authors': []}
            entries.append(cur)
        elif cur is None:
            continue
        elif tag == 'AU':
            cur['authors'].append(val)
        elif tag == 'TI':
            cur['title'] = val
        elif tag == 'JO':
            cur['journal'] = val
        elif tag == 'TA':
            cur['journal_abbr'] = val
        elif tag == 'PY':
            cur['year'] = val
        elif tag == 'VL':
            cur['volume'] = val
        elif tag == 'IP':
            cur['issue'] = val
        elif tag == 'SP':
            cur['pages'] = val
        elif tag == 'DO':
            cur['doi'] = val
    return entries


# ------------------------------ Zotero API ----------------------------------

def norm_doi(doi):
    if not doi:
        return None
    d = doi.strip().lower()
    d = re.sub(r'^https?://(dx\.)?doi\.org/', '', d)
    d = re.sub(r'^doi:\s*', '', d)
    return d or None


def fetch_all_items(base):
    items, start, limit = [], 0, 100
    while True:
        r = requests.get(f"{base}/users/0/items",
                         params={"format": "json", "limit": limit, "start": start},
                         timeout=TIMEOUT)
        r.raise_for_status()
        batch = r.json()
        items.extend(batch)
        if len(batch) < limit:
            break
        start += limit
    return items


def item_doi(it):
    data = it.get('data', {})
    return norm_doi(data.get('DOI') or data.get('doi'))


def item_uri(it):
    lib = it.get('library', {})
    lid, ltype = lib.get('id', 0), lib.get('type', 'user')
    return f"http://zotero.org/{ltype}s/{lid}/items/{it['key']}"


def zotero_item_payload(entry):
    creators = []
    for a in entry.get('authors', []):
        if ',' in a:
            last, first = a.split(',', 1)
            creators.append({"creatorType": "author",
                             "lastName": last.strip(), "firstName": first.strip()})
        else:
            creators.append({"creatorType": "author", "lastName": a.strip()})
    return {
        "itemType": "journalArticle",
        "title": entry.get('title', ''),
        "creators": creators,
        "publicationTitle": entry.get('journal', ''),
        "journalAbbreviation": entry.get('journal_abbr', ''),
        "volume": entry.get('volume', ''),
        "issue": entry.get('issue', ''),
        "pages": entry.get('pages', ''),
        "date": entry.get('year', ''),
        "DOI": entry.get('doi', ''),
        "url": f"https://doi.org/{entry['doi']}" if entry.get('doi') else '',
    }


def csl_for_item(base, key):
    r = requests.get(f"{base}/users/0/items/{key}",
                     params={"format": "csl_json"}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


# --------------------------- citation detection ------------------------------

def is_superscript(run):
    rPr = run._r.find(qn('w:rPr'))
    return rPr is not None and rPr.find(qn('w:vertAlign')) is not None


def find_body_range(paragraphs):
    """Return (first_body_idx, ref_header_idx) for citation scanning."""
    ref_hdr = next((i for i, p in enumerate(paragraphs)
                    if REF_HEADER.match(p.text.strip())), None)
    scan_end = ref_hdr if ref_hdr is not None else len(paragraphs)
    start = 0
    for i, p in enumerate(paragraphs[:scan_end]):
        if BODY_START.match(p.text.strip()):
            start = i
            break
    else:
        # fall back: skip the author block (ends at 'Corresponding author' para)
        for i, p in enumerate(paragraphs[:scan_end]):
            if 'Corresponding author' in p.text:
                start = i + 1
                break
    return start, scan_end


def detect_sites(doc, n_refs):
    """
    Detect citation sites. Returns list of dicts:
      {para, run, kind: 'sup'|'paren', text, context, nums}
    A superscript run counts as a citation only if it is a pure number pattern,
    every number is <= n_refs, and the preceding character is punctuation or a
    letter (never a digit — that excludes affiliation markers like 'MD1').
    """
    paras = doc.paragraphs
    s0, s1 = find_body_range(paras)
    sites = []
    # statistical exponents (R2, r2, chi2, tau2, I2) are not citations
    EXPONENT_PREV = set('RrχτIβ')
    for pi in range(s0, s1):
        p = paras[pi]
        runs = p.runs
        combined_prev = ''
        for ri, r in enumerate(runs):
            if is_superscript(r) and SUP_CIT.match(r.text or ''):
                nums = [int(x) for x in re.split(r'[,-]', r.text)]
                prev_char = combined_prev[-1:] if combined_prev else ''
                if not prev_char or prev_char.isdigit():
                    continue  # affiliation markers like 'MD1'
                if (prev_char in EXPONENT_PREV and r.text in ('2', '3')):
                    continue  # statistical exponents like R2, chi2
                if max(nums) <= n_refs:
                    sites.append({'para': pi, 'run': ri, 'kind': 'sup',
                                  'text': r.text,
                                  'context': combined_prev[-40:],
                                  'nums': sorted(set(nums))})
            elif PAREN_CIT.search(r.text or ''):
                for m in PAREN_CIT.finditer(r.text):
                    nums = [int(x) for x in re.split(r'\s*[,-]\s*',
                                                     m.group(1).replace('–', '-'))]
                    if max(nums) <= n_refs:
                        sites.append({'para': pi, 'run': ri, 'kind': 'paren',
                                      'text': m.group(0),
                                      'match_start': m.start(),
                                      'match_end': m.end(),
                                      'context': r.text[max(0, m.start() - 40):m.start()],
                                      'nums': sorted(set(nums))})
            combined_prev += (r.text or '')
    return sites


# --------------------------- docx field helpers ------------------------------

def fld_run(kind, instr=None):
    from lxml import etree
    r = etree.Element(qn('w:r'))
    rPr = etree.SubElement(r, qn('w:rPr'))
    etree.SubElement(rPr, qn('w:vanish'))
    if kind in ('begin', 'separate', 'end'):
        fc = etree.SubElement(r, qn('w:fldChar'))
        fc.set(qn('w:fldCharType'), kind)
    else:
        it = etree.SubElement(r, qn('w:instrText'))
        it.set(qn('xml:space'), 'preserve')
        it.text = f" {instr} "
    return r


def make_sup_run(model_run, text):
    import copy
    new_r = copy.deepcopy(model_run._r)
    for t in new_r.findall(qn('w:t')):
        new_r.remove(t)
    rPr = new_r.find(qn('w:rPr'))
    if rPr is None:
        rPr = new_r.makeelement(qn('w:rPr'), {})
        new_r.insert(0, rPr)
    for va in rPr.findall(qn('w:vertAlign')):
        rPr.remove(va)
    va = rPr.makeelement(qn('w:vertAlign'), {})
    va.set(qn('w:val'), 'superscript')
    rPr.append(va)
    t = new_r.makeelement(qn('w:t'), {})
    t.text = text
    t.set(qn('xml:space'), 'preserve')
    new_r.append(t)
    return new_r


def make_text_run(model_run, text):
    import copy
    new_r = copy.deepcopy(model_run._r)
    for t in new_r.findall(qn('w:t')):
        new_r.remove(t)
    rPr = new_r.find(qn('w:rPr'))
    if rPr is not None:
        for va in rPr.findall(qn('w:vertAlign')):
            rPr.remove(va)
    t = new_r.makeelement(qn('w:t'), {})
    t.text = text
    t.set(qn('xml:space'), 'preserve')
    new_r.append(t)
    return new_r


def convert_paren_site(p, run_idx, match_start, match_end):
    """Convert one parenthetical citation inside run run_idx to a superscript run.
    Returns the new superscript run element (already inserted)."""
    r = p.runs[run_idx]
    T = r.text
    before, cited, after = T[:match_start], T[match_start:match_end], T[match_end:]
    if before.endswith(' '):
        before = before[:-1]
    sup_text = ','.join(part.replace('–', '-').replace(' ', '')
                        for part in cited[1:-1].split(','))
    lead_punct = ''
    if after and after[0] in '.,;:':
        lead_punct, after = after[0], after[1:]
    r.text = before + lead_punct
    sup_r = make_sup_run(r, sup_text)
    r._r.addnext(sup_r)
    if after:
        sup_r.addnext(make_text_run(r, after))
    return sup_r


def inject_citation_field(sup_run_element, citation_json):
    instr = ("ADDIN ZOTERO_ITEM CSL_CITATION "
             + json.dumps(citation_json, ensure_ascii=False))
    sup_run_element.addprevious(fld_run('begin'))
    sup_run_element.addprevious(fld_run('instr', instr))
    sup_run_element.addprevious(fld_run('separate'))
    sup_run_element.addnext(fld_run('end'))


def inject_bibliography_field(doc, first_para, last_para):
    instr = ('ADDIN ZOTERO_BIBL {"uncited":[],"omitted":[],"custom":[]} '
             'CSL_BIBLIOGRAPHY')
    p_first, p_last = first_para._p, last_para._p
    pPr = p_first.find(qn('w:pPr'))
    prev = pPr
    for e in (fld_run('begin'), fld_run('instr', instr), fld_run('separate')):
        if prev is None:
            p_first.insert(0, e)
        else:
            prev.addnext(e)
        prev = e
    p_last.append(fld_run('end'))


def inject_doc_prefs(doc, style_id, style_name, library_id):
    prefs = {"styleName": style_name, "styleId": style_id, "locale": "en-US",
             "libraryID": library_id, "templateVersion": 1, "purge": False,
             "noteStyle": 0, "bibliographyStyle": 0}
    instr = "ADDIN ZOTERO_PREF_1 " + json.dumps(prefs, ensure_ascii=False)
    first_p = doc.paragraphs[0]._p
    pPr = first_p.find(qn('w:pPr'))
    prev = pPr
    for e in (fld_run('begin'), fld_run('instr', instr),
              fld_run('separate'), fld_run('end')):
        if prev is None:
            first_p.insert(0, e)
        else:
            prev.addnext(e)
        prev = e


# ---------------------------------- main -------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument('docx', help='manuscript .docx (numbered citations)')
    ap.add_argument('ris', help='RIS file with the corrected references')
    ap.add_argument('--out', default=None, help='output path (default: *_zotero_linked.docx)')
    ap.add_argument('--api', default=API_BASE)
    ap.add_argument('--style', default=DEFAULT_STYLE, help='CSL style id for doc prefs')
    ap.add_argument('--style-name', default=DEFAULT_STYLE_NAME)
    ap.add_argument('--dry-run', action='store_true',
                    help='match against Zotero and report; change nothing')
    ap.add_argument('--yes', action='store_true',
                    help='skip citation-site confirmation')
    args = ap.parse_args()

    entries = ris_entries(args.ris)
    n_refs = len(entries)
    print(f"[1/5] Parsed {n_refs} references from {Path(args.ris).name}")
    if n_refs == 0:
        sys.exit("  ERROR: no RIS entries found.")

    print(f"[2/5] Contacting Zotero local API at {args.api} ...")
    try:
        items = fetch_all_items(args.api)
    except Exception as e:
        sys.exit(f"  ERROR: cannot reach Zotero local API ({e}).\n"
                 "  Make sure the Zotero desktop app is running, then retry.")
    print(f"  Library contains {len(items)} items")

    by_doi = {}
    for it in items:
        d = item_doi(it)
        if d:
            by_doi.setdefault(d, it)

    dois = [norm_doi(e.get('doi', '')) for e in entries]
    matched = {d: by_doi[d] for d in dois if d and d in by_doi}
    missing = [e for e, d in zip(entries, dois) if not d or d not in by_doi]
    print(f"  Matched {len(matched)}/{n_refs} references by DOI")
    for e in missing:
        print(f"    missing: {e.get('title', '?')[:80]}")

    if missing and not args.dry_run:
        print("[3/5] Importing missing items via local API (Zotero 10+) ...")
        try:
            payload = {"items": [zotero_item_payload(e) for e in missing]}
            r = requests.post(f"{args.api}/users/0/items", json=payload,
                              timeout=TIMEOUT)
            r.raise_for_status()
            print(f"  Imported {len(missing)} items")
            items = fetch_all_items(args.api)
            by_doi = {}
            for it in items:
                d = item_doi(it)
                if d:
                    by_doi.setdefault(d, it)
            matched = {d: by_doi[d] for d in dois if d and d in by_doi}
            missing = [e for e, d in zip(entries, dois) if not d or d not in by_doi]
        except Exception as e:
            print(f"  Import via API failed ({e}).")
            print("  MANUAL STEP: Zotero -> File -> Import... -> choose the RIS "
                  "file, then run this script again.")
            sys.exit(2)
    if missing:
        print("  ERROR: unresolved references remain:")
        for e in missing:
            print(f"    - {e.get('title', '?')[:80]}")
        sys.exit(3)

    print("[3/5] Fetching CSL-JSON for matched items ...")
    csl = {d: csl_for_item(args.api, matched[d]['key']) for d in matched if d}
    print(f"  Fetched {len(csl)} CSL records")

    doc = docx.Document(args.docx)
    sites = detect_sites(doc, n_refs)
    print(f"[4/5] Detected {len(sites)} citation sites in {Path(args.docx).name}:")
    for s in sites:
        print(f"    p{s['para']:>3} run{s['run']:>3}  [{s['kind']:>5}] "
              f"'{s['text']}'  after: ...{s['context'][-35:]}")

    if args.dry_run:
        print("DRY RUN complete. Re-run with --yes (or confirm interactively) "
              "to write the linked document.")
        return

    if not args.yes:
        ans = input(f"Convert these {len(sites)} sites to Zotero fields? [y/N] ")
        if ans.strip().lower() != 'y':
            sys.exit("Aborted — nothing was written.")

    # process in reverse document order so indices stay valid
    for s in reversed(sites):
        p = doc.paragraphs[s['para']]
        if s['kind'] == 'paren':
            sup_el = convert_paren_site(p, s['run'], s['match_start'], s['match_end'])
        else:
            sup_el = p.runs[s['run']]._r
        citation_items = []
        for n in s['nums']:
            d = dois[n - 1]
            it = matched[d]
            citation_items.append({"id": it['key'], "uris": [item_uri(it)],
                                   "itemData": csl[d]})
        citation_json = {
            "citationID": ''.join(random.choices(string.ascii_letters + string.digits, k=8)),
            "properties": {"formattedCitation": sup_el.xpath('string(.)'),
                           "plainCitation": sup_el.xpath('string(.)'),
                           "noteIndex": 0},
            "citationItems": citation_items,
            "schema": CSL_CITATION_SCHEMA,
        }
        inject_citation_field(sup_el, citation_json)

    ref_paras = [p for p in doc.paragraphs if REF_START.match(p.text.strip())]
    if not ref_paras:
        sys.exit("  ERROR: could not find the numbered reference list.")
    inject_bibliography_field(doc, ref_paras[0], ref_paras[-1])

    library_id = next(iter(matched.values())).get('library', {}).get('id', 1)
    inject_doc_prefs(doc, args.style, args.style_name, library_id)

    out = args.out or str(Path(args.docx).with_name(
        Path(args.docx).stem + '_zotero_linked.docx'))
    doc.save(out)
    print(f"[5/5] Saved {out}")
    print("""
DONE. One-time verification:
  1. Open the output .docx in Word with Zotero running.
  2. Zotero tab -> Refresh (citations and bibliography re-render unchanged).
  3. Click any superscript number -> Add/Edit Citation opens the Zotero picker.
From now on, add or remove references with the Zotero plugin (Add/Edit
Citation) — numbering updates automatically. Never retype the numbers.
""")


if __name__ == '__main__':
    main()
