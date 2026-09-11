#!/usr/bin/env python3
"""
audit_ib_layouts.py — find Interface Builder layouts that break on iPhone Duo.

Source-code greps miss the place a UIKit app actually defines its layout: .xib
and .storyboard files. This parses them and reports the constraint patterns that
stop adapting once a device has two displays, a fold, and side-mounted bars.

What it looks for, and why each one matters on Duo:

  safe-area         Duo moves toolbars and tab bars to the SIDE. A view pinned
                    to its superview's leading/trailing edge slides underneath
                    them, and under the always-on outer camera. Safe-area
                    anchoring is what keeps content clear.
  fixed-size        A constant width/height cannot expand onto the inner
                    display or collapse onto the outer one. Aspect-ratio
                    constraints are NOT flagged: Apple prefers them.
  no-variation      No size-class variations, so one layout serves both a
                    compact outer display and a regular inner one.

Usage:  ./audit_ib_layouts.py [path] [--verbose] [--json]
Exit:   0 clean, 1 findings (CI gate), 2 nothing to scan
"""
import os, sys, json, argparse
import xml.etree.ElementTree as ET

EDGES = {"leading", "trailing", "left", "right", "top", "bottom"}
SIZES = {"width", "height"}


def scan_file(path):
    try:
        root = ET.parse(path).getroot()
    except Exception as e:
        return {"error": str(e)}

    # Safe-area layout guides declared anywhere in the document.
    safe_ids = {g.get("id") for g in root.iter("viewLayoutGuide")
                if g.get("key") == "safeArea" and g.get("id")}

    # Root views: a <view> that is the direct content of a controller/object,
    # i.e. what a subview's "superview" edge constraint would point at.
    root_view_ids = set()
    for parent in root.iter():
        if parent.tag in ("viewController", "tableViewController",
                          "collectionViewController", "navigationController",
                          "objects", "placeholder"):
            for child in parent:
                if child.tag.endswith("view") or child.tag == "view":
                    if child.get("id"):
                        root_view_ids.add(child.get("id"))
    for obj in root.iter("objects"):
        for child in obj:
            if child.tag == "view" and child.get("id"):
                root_view_ids.add(child.get("id"))

    uses_safe_area = bool(safe_ids) or 'YES' in {
        v.get("useSafeAreas") for v in root.iter() if v.get("useSafeAreas")}

    fixed, edge_to_super, safe_anchored, aspect = [], [], 0, 0

    for c in root.iter("constraint"):
        fa = (c.get("firstAttribute") or "").lower()
        sa = (c.get("secondAttribute") or "").lower()
        si = c.get("secondItem")
        const = c.get("constant")
        cid = c.get("id", "?")

        # fixed size: width/height to a constant, with no second item
        if fa in SIZES and si is None and const is not None:
            try:
                val = abs(float(const))
            except ValueError:
                val = 0.0
            fixed.append((fa, val, cid))
            continue

        # width/height related to another view = aspect ratio or proportional: fine
        if fa in SIZES and si is not None:
            aspect += 1
            continue

        # edge constraints: is the anchor the safe area or the raw superview?
        if fa in EDGES or sa in EDGES:
            if si in safe_ids:
                safe_anchored += 1
            elif si in root_view_ids:
                edge_to_super.append((fa or sa, cid))

    variations = sum(1 for _ in root.iter("variation"))

    return {
        "uses_safe_area": uses_safe_area,
        "fixed": fixed,
        "edge_to_super": edge_to_super,
        "safe_anchored": safe_anchored,
        "aspect": aspect,
        "variations": variations,
    }


def main():
    ap = argparse.ArgumentParser(add_help=True, description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--min-fixed", type=int, default=120,
                    help="only report fixed dimensions at least this large "
                         "(default 120pt; small constants are usually icons)")
    a = ap.parse_args()

    files = []
    for dirpath, dirnames, filenames in os.walk(a.path):
        dirnames[:] = [d for d in dirnames
                       if d not in ("Pods", "DerivedData", "Carthage", ".git", "build")]
        for fn in filenames:
            if fn.endswith((".xib", ".storyboard")):
                files.append(os.path.join(dirpath, fn))

    if not files:
        print(f"No .xib or .storyboard files under {a.path}", file=sys.stderr)
        return 2

    no_safe, big_fixed, super_pinned, parse_err = [], [], [], []
    tot_fixed = tot_var = 0

    for f in sorted(files):
        r = scan_file(f)
        if "error" in r:
            parse_err.append((f, r["error"])); continue
        if not r["uses_safe_area"]:
            no_safe.append(f)
        big = [x for x in r["fixed"] if x[1] >= a.min_fixed]
        tot_fixed += len(r["fixed"])
        tot_var += r["variations"]
        if big:
            big_fixed.append((f, big))
        if r["edge_to_super"]:
            super_pinned.append((f, r["edge_to_super"]))

    if a.json:
        print(json.dumps({
            "files": len(files), "no_safe_area": no_safe,
            "superview_pinned": {f: len(v) for f, v in super_pinned},
            "large_fixed": {f: len(v) for f, v in big_fixed},
            "total_fixed_constraints": tot_fixed, "total_variations": tot_var,
        }, indent=2))
        return 1 if (no_safe or super_pinned or big_fixed) else 0

    t = len(files)
    print(f"Interface Builder audit — {t} .xib/.storyboard files under {a.path}\n")

    findings = 0

    if no_safe:
        findings += len(no_safe)
        print(f"[HIGH] Layouts not using safe areas ({len(no_safe)}/{t})")
        print("        Duo moves toolbars and tab bars to the SIDE, and the outer")
        print("        camera is always present. Without safe-area anchoring this")
        print("        content renders underneath them.")
        for f in (no_safe if a.verbose else no_safe[:5]):
            print(f"        {f}")
        if not a.verbose and len(no_safe) > 5:
            print(f"        … {len(no_safe)-5} more (--verbose)")
        print()

    if super_pinned:
        n = sum(len(v) for _, v in super_pinned)
        findings += n
        print(f"[HIGH] Edges pinned to superview instead of safe area "
              f"({n} constraints in {len(super_pinned)} files)")
        print("        Same failure mode: these ignore the side bars and camera.")
        print("        Re-anchor leading/trailing/top/bottom to the safe-area guide.")
        for f, v in (super_pinned if a.verbose else super_pinned[:5]):
            print(f"        {f}  ({len(v)})")
        if not a.verbose and len(super_pinned) > 5:
            print(f"        … {len(super_pinned)-5} more files (--verbose)")
        print()

    if big_fixed:
        n = sum(len(v) for _, v in big_fixed)
        findings += n
        print(f"[MED ] Large fixed dimensions ≥{a.min_fixed}pt "
              f"({n} constraints in {len(big_fixed)} files)")
        print("        A constant width/height cannot expand onto the inner display")
        print("        or collapse onto the outer one. Aspect-ratio and proportional")
        print("        constraints are not counted here — Apple prefers those.")
        for f, v in (big_fixed if a.verbose else big_fixed[:5]):
            top = ", ".join(f"{d}={int(val)}" for d, val, _ in sorted(v, key=lambda x: -x[1])[:3])
            print(f"        {f}  ({len(v)}: {top})")
        if not a.verbose and len(big_fixed) > 5:
            print(f"        … {len(big_fixed)-5} more files (--verbose)")
        print()

    print(f"[INFO] {tot_fixed} fixed-size constraints total; "
          f"{tot_var} size-class variations across {t} files.")
    if tot_var == 0:
        print("        No size-class variations at all: one layout is serving both")
        print("        a compact outer display and a regular inner one.")
    if parse_err:
        print(f"[INFO] {len(parse_err)} file(s) could not be parsed.")

    print("\n" + "─" * 56)
    if findings == 0:
        print("No Interface Builder issues found.")
        return 0
    print(f"{findings} finding(s) across {t} IB files.")
    print("Safe-area items first: on Duo those put content under the side bars.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
