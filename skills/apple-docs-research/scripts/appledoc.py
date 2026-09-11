#!/usr/bin/env python3
"""
appledoc.py — tooling for exhaustive Apple developer documentation research.

Apple's developer site is a JavaScript SPA: fetching the human URL returns an
empty shell. The real content lives at DocC JSON endpoints. This script handles
that mapping, plus the three things that are easy to get wrong by hand:

  1. Enumerating EVERY reference on a page (not the ones that look interesting).
  2. Searching page CONTENT only — image alt-text produces convincing false
     positives (e.g. "split view arrangement" in an icon description).
  3. Reading availability metadata, which reveals whether a symbol is missing
     from the web docs or merely newer than the published doc set.

Subcommands:
  refs   <url|path>              List every non-image reference, classified.
  get    <url|path> [--raw]      Fetch a page; print readable content (or raw JSON).
  probe  <sym> [<sym> ...]       HTTP status + introduced-in version per symbol.
  scan   <term,term> --pages a,b Search page content (not alt-text) for terms.

Paths may be full URLs or short forms:
  hig:layout                  -> design/human-interface-guidelines/layout
  swiftui/navigationsplitview -> documentation/swiftui/navigationsplitview
"""
import json, sys, re, argparse, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

BASE = "https://developer.apple.com/tutorials/data/"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def to_json_url(ref: str) -> str:
    """Map a human URL / doc path / short form to its DocC JSON endpoint."""
    r = ref.strip()
    if r.endswith(".json") and r.startswith("http"):
        return r
    if r.startswith("hig:"):
        r = "design/human-interface-guidelines/" + r[4:]
    r = re.sub(r"^https?://developer\.apple\.com/", "", r)
    r = r.strip("/")
    # doc:// scheme used inside DocC reference payloads
    r = re.sub(r"^doc://[^/]+/", "", r)
    if r.startswith("design/Human-Interface-Guidelines/"):
        r = r.replace("design/Human-Interface-Guidelines/",
                      "design/human-interface-guidelines/")
    if not (r.startswith("design/") or r.startswith("documentation/")):
        r = "documentation/" + r
    return BASE + r + ".json"


def fetch(ref: str, timeout=30):
    """Return (status, parsed_json_or_None)."""
    url = to_json_url(ref)
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return 0, {"__error__": str(e)}


# ---------- text extraction (content only, never image alt-text) ----------

def _inline(nodes):
    out = []
    for n in nodes or []:
        t = n.get("type")
        if t == "text":
            out.append(n.get("text", ""))
        elif t in ("codeVoice", "inlineHead"):
            out.append("`" + "".join(x.get("text", "") for x in n.get("inlineContent", []) or
                                     [{"text": n.get("code", "")}]) + "`")
        elif "inlineContent" in n:
            out.append(_inline(n["inlineContent"]))
        elif "content" in n:
            out.append(_blocks(n["content"]))
    return "".join(out)


def _blocks(blocks, depth=0):
    out = []
    for b in blocks or []:
        k = b.get("type")
        if k == "heading":
            out.append("\n" + "#" * max(1, b.get("level", 2)) + " " + b.get("text", "") + "\n")
        elif k == "paragraph":
            out.append(_inline(b.get("inlineContent")) + "\n")
        elif k == "codeListing":
            out.append("```" + (b.get("syntax") or "") + "\n" +
                       "\n".join(b.get("code", [])) + "\n```\n")
        elif k in ("unorderedList", "orderedList"):
            for i, it in enumerate(b.get("items", [])):
                out.append(("- " if k == "unorderedList" else f"{i+1}. ") +
                           _blocks(it.get("content"), depth + 1).strip() + "\n")
        elif k == "aside":
            out.append(f"> **{b.get('name', b.get('style',''))}:** " +
                       _blocks(b.get("content"), depth + 1).strip() + "\n")
        elif k == "table":
            for row in b.get("rows", []):
                out.append("| " + " | ".join(_blocks(c).strip() for c in row) + " |\n")
        elif "content" in b:
            out.append(_blocks(b["content"], depth + 1))
    return "".join(out)


def page_text(doc) -> str:
    """All human-readable prose on the page. Excludes references/alt-text."""
    if not doc:
        return ""
    parts = []
    if doc.get("abstract"):
        parts.append(_inline(doc["abstract"]) + "\n")
    for sec in doc.get("primaryContentSections", []) or []:
        if sec.get("kind") == "content":
            parts.append(_blocks(sec.get("content")))
        elif sec.get("kind") == "declarations":
            for d in sec.get("declarations", []):
                parts.append("```swift\n" +
                             "".join(t.get("text", "") for t in d.get("tokens", [])) + "\n```\n")
    for sec in doc.get("sections", []) or []:
        parts.append(_blocks(sec.get("content")))
    return "\n".join(parts)


def availability(doc):
    if not doc:
        return ""
    plats = (doc.get("metadata") or {}).get("platforms") or []
    return ", ".join(f"{p.get('name')} {p.get('introducedAt')}"
                     for p in plats if p.get("introducedAt"))


# ---------- subcommands ----------

def cmd_refs(args):
    status, doc = fetch(args.page)
    if not doc:
        print(f"HTTP {status} — no JSON. Videos (/videos/play/...) are fetched "
              f"directly as HTML, not via this endpoint.", file=sys.stderr)
        return 1
    refs = doc.get("references", {})
    rows, images = [], 0
    for k, v in refs.items():
        if v.get("type") == "image":
            images += 1
            continue
        url = v.get("url") or k
        kind = v.get("type", "?")
        if "/videos/play/" in url:
            kind = "VIDEO"
        elif "/documentation/" in url:
            kind = "API"
        elif "human-interface-guidelines" in url:
            kind = "HIG"
        elif url.startswith("http"):
            kind = "EXTERNAL"
        rows.append((kind, v.get("title", ""), url))
    print(f"# {(doc.get('metadata') or {}).get('title','?')}")
    print(f"# {len(refs)} total refs | {images} images | {len(rows)} real references\n")
    for kind, title, url in sorted(rows):
        anchor = "  (anchor)" if "#" in url and url.split("#")[0].rstrip("/") in args.page else ""
        print(f"[{kind:8}] {title[:52]:52} {url}{anchor}")
    print(f"\n{len(rows)} references to account for. "
          f"Fetch every one, or state explicitly why not.")
    return 0


def cmd_get(args):
    status, doc = fetch(args.page)
    if not doc:
        print(f"HTTP {status}", file=sys.stderr)
        return 1
    if args.raw:
        print(json.dumps(doc, indent=2))
        return 0
    md = (doc.get("metadata") or {})
    print(f"# {md.get('title','?')}   [{md.get('roleHeading') or md.get('symbolKind') or ''}]")
    av = availability(doc)
    if av:
        print(f"**Availability:** {av}")
    print()
    print(page_text(doc))
    return 0


def _probe_one(sym):
    status, doc = fetch(sym)
    return sym, status, availability(doc) if doc else ""


def cmd_probe(args):
    syms = []
    for s in args.symbols:
        syms.extend(x for x in s.split(",") if x.strip())
    ok = miss = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for sym, status, av in ex.map(_probe_one, syms):
            if status == 200:
                ok += 1
                print(f"  ✅ {sym:58} {av}")
            else:
                miss += 1
                print(f"  ❌ {sym:58} HTTP {status}")
    print(f"\ndocumented={ok}  undocumented={miss}")
    if miss:
        print("A 404 on a TYPE is strong evidence it is unpublished.\n"
              "A 404 on a MEMBER path may just be a wrong path spelling — confirm\n"
              "by grepping the parent page: appledoc.py scan <member> --pages <parent>")
    return 0


def _scan_one(page, terms, ctx):
    status, doc = fetch(page)
    if not doc:
        return page, status, []
    text = page_text(doc)
    hits = []
    for t in terms:
        for m in re.finditer(re.escape(t), text, re.I):
            a, b = max(0, m.start() - ctx), min(len(text), m.end() + ctx)
            hits.append((t, text[a:b].replace("\n", " ")))
    return page, status, hits


def cmd_scan(args):
    terms = [t for t in args.terms.split(",") if t.strip()]
    pages = [p for p in args.pages.split(",") if p.strip()]
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda p: _scan_one(p, terms, args.context), pages))
    for page, status, hits in results:
        if status != 200:
            print(f"MISS  {page}  (HTTP {status})")
        elif hits:
            print(f"HIT   {page}  ({len(hits)})")
            for t, c in hits[:args.max_hits]:
                print(f"        [{t}] …{c.strip()}…")
        else:
            print(f"----  {page}")
    print("\nOnly page CONTENT was searched; image alt-text is excluded, so these\n"
          "hits are real. (Alt-text is a notorious source of false positives.)")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("refs", help="list every non-image reference on a page")
    r.add_argument("page"); r.set_defaults(fn=cmd_refs)

    g = sub.add_parser("get", help="fetch a page as readable text")
    g.add_argument("page"); g.add_argument("--raw", action="store_true")
    g.set_defaults(fn=cmd_get)

    pr = sub.add_parser("probe", help="check which symbols are documented")
    pr.add_argument("symbols", nargs="+"); pr.set_defaults(fn=cmd_probe)

    sc = sub.add_parser("scan", help="search page content for terms")
    sc.add_argument("terms"); sc.add_argument("--pages", required=True)
    sc.add_argument("--context", type=int, default=90)
    sc.add_argument("--max-hits", type=int, default=4)
    sc.set_defaults(fn=cmd_scan)

    a = p.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
