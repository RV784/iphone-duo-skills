# iPhone Duo Skills

Two [Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills)
for working with **iPhone Duo**, Apple's folding iPhone — one for building apps
for it, one for researching Apple's documentation about it.

They work with Claude Code, the Claude Agent SDK, and anything else that reads
the Agent Skills format. The scripts are plain Bash and Python 3 with no
dependencies, so they're useful on their own too.

---

## `iphone-duo-development`

The adoption path for getting an existing iOS app onto the foldable.

Supporting Duo turns out to be mostly **subtraction** — removing assumptions
that a device has one fixed screen — before it is addition. So the skill starts
with an audit and works outward:

1. **Audit** the codebase for single-screen assumptions
2. **Resizability** — size classes, scene lifecycle, asymmetric safe areas
3. **Standard containers**, which adapt to every pose for free
4. **Vertical bars**, then **reserved regions** and **arrangement views** for custom layout

### The audit script

Runs standalone, no Claude required:

```bash
# Swift / Objective-C
./skills/iphone-duo-development/scripts/audit_foldable_readiness.sh /path/to/project
# .xib / .storyboard — where a UIKit app's layout actually lives
./skills/iphone-duo-development/scripts/audit_ib_layouts.py /path/to/project
```

```
iPhone Duo readiness audit — 412 source files under ./MyApp

[HIGH] Main-screen references (12)
        Ambiguous on a two-display device and slated for deprecation.
        Use window?.windowScene?.screen; for scale use traitCollection.displayScale.
        ./MyApp/Sources/LayoutHelper.swift:88:  let w = UIScreen.main.bounds.width
        …

74 finding(s), 51 high severity.
```

It flags `UIScreen.main`, screen-bounds comparisons, device-idiom branching,
orientation-driven layout, symmetric safe-area math, hardcoded device
dimensions, fixed widths, standalone bar instances, and `UIRequiresFullScreen`.
There's a second auditor for Interface Builder, because source greps can't see
`.xib`/`.storyboard` files — which is where a UIKit app's layout mostly lives. It
flags layouts that skip safe areas, edges pinned to the superview instead of the
safe-area guide, and large fixed dimensions. It deliberately does *not* flag
aspect-ratio or proportional constraints: those are what Apple recommends.

The safe-area findings matter most. Duo moves bars to the **side**, so a view
pinned to its superview's leading edge renders underneath them — a constraint
that looks perfectly fine on every current iPhone.

Both exit non-zero on findings, so they work as CI gates. Written for BSD/macOS
tools and Python 3 standard library, since that's where iOS development happens.

Findings are candidates to review rather than confirmed bugs — a couple of
patterns can match unrelated custom types. A mature app commonly returns
hundreds. That's a decade of single-screen assumptions surfacing at once, and
most resolve mechanically.

### What else is in it

`references/api-surface.md` documents reserved regions, arrangement views,
vertical bars, the hinge, scene accessories, and the camera-direction APIs, with
signatures — which matters because **none of these have published reference
pages yet**. Apple's Tech Talk transcripts are currently the only authoritative
source.

---

## `apple-docs-research`

For researching developer.apple.com without quietly missing half of it.

Apple's docs invite two specific mistakes:

**Silent triage.** A page links to `HStack`, `ZStack`, `UIBarButtonItem` and
it's tempting to skip them as already-known. But you're not deciding whether
*you* need the page — you're deciding what a report is based on, and a reader
can't tell which links were read and which were assumed. Apple also adds members
to old types constantly: a "boring" `GeometryProxy` link is exactly where a new
`reservedRegions(kind:)` would appear. So the rule is **you may skip a link, but
not silently** — every reference is fetched or listed as not-fetched, with a
reason.

**Trusting the rendered page.** developer.apple.com is a JavaScript SPA. Fetching
the human URL returns an empty shell that's easy to mistake for a thin page. The
real content is at DocC JSON endpoints.

### The script

```bash
S=skills/apple-docs-research/scripts/appledoc.py

python3 $S refs hig:designing-for-iphone-duo       # every reference, classified
python3 $S get  swiftui/navigationsplitview        # real content, not the SPA shell
python3 $S probe swiftui/arrangementview,swiftui/geometryproxy
python3 $S scan "hinge,reserved region" --pages hig:layout,hig:split-views
```

Two details that matter more than they look:

- **`scan` searches page prose only.** A naive `grep` over the raw JSON produces
  confident false positives from image alt-text — icon descriptions like *"two
  side-by-side windows in a split view arrangement"* match `arrangement` across
  unrelated pages, and `UISplitViewController` matches `fold` because it
  discusses Notes **folders**.
- **`probe` reports introduced-in versions.** Documented vs undocumented usually
  splits cleanly on an SDK boundary, because published docs lag the newest SDK.
  That single line separates "buildable today" from "blocked on a toolchain."

---

## Install

Clone anywhere, or drop a skill into your skills directory:

```bash
git clone https://github.com/<you>/iphone-duo-skills.git
cp -r iphone-duo-skills/skills/iphone-duo-development ~/.claude/skills/
cp -r iphone-duo-skills/skills/apple-docs-research   ~/.claude/skills/
```

Claude picks them up automatically and invokes them when a task matches. You can
also run either script directly without Claude.

## Requirements

- **Scripts:** Bash and Python 3 (standard library only). macOS or Linux.
- **The Duo APIs themselves:** Xcode 27.1 and the iOS 27.1 SDK. The
  resizability groundwork — size classes, scenes, safe areas — builds on older
  toolchains and pays off on iPad and iPhone Mirroring regardless.

## Accuracy and scope

These skills summarize Apple's published material — the
[Designing for iPhone Duo](https://developer.apple.com/design/human-interface-guidelines/designing-for-iphone-duo)
HIG page and Tech Talks 111461–111466. **Apple's documentation is the
authority**; this is a working summary written to be useful next to it, not a
replacement for it. API signatures were transcribed before reference pages
existed, so verify against the SDK headers.

Corrections and additions welcome — particularly as Apple publishes more, which
`apple-docs-research` is designed to help you check.

## License

MIT — see [LICENSE](LICENSE).
