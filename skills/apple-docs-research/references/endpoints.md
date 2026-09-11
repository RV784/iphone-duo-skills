# Apple developer docs — endpoint mechanics

Reference for when `scripts/appledoc.py` doesn't surface what you need and you
have to go at the JSON directly.

## Contents
- [URL → JSON mapping](#url--json-mapping)
- [What is NOT a JSON endpoint](#what-is-not-a-json-endpoint)
- [Page JSON structure](#page-json-structure)
- [Pulling fields by hand](#pulling-fields-by-hand)
- [Availability and the SDK-lag signal](#availability-and-the-sdk-lag-signal)
- [Interpreting 404s](#interpreting-404s)

## URL → JSON mapping

Base: `https://developer.apple.com/tutorials/data/`

| Human URL | JSON endpoint |
|---|---|
| `/design/human-interface-guidelines/<page>` | `…/data/design/human-interface-guidelines/<page>.json` |
| `/documentation/<framework>` | `…/data/documentation/<framework>.json` |
| `/documentation/<framework>/<symbol>` | `…/data/documentation/<framework>/<symbol>.json` |
| `/documentation/<fw>/<type>/<member>` | `…/data/documentation/<fw>/<type>/<member>.json` |

Paths are **lowercased** (`swiftui/navigationsplitview`, not
`SwiftUI/NavigationSplitView`). Case-correct spellings 404.

Inside page JSON, references use a `doc://` scheme
(`doc://com.apple.documentation/documentation/SwiftUI/HStack`,
`doc://com.apple.HIG/design/Human-Interface-Guidelines/layout`). Strip the
scheme and authority, lowercase, and the remainder maps as above.

## What is NOT a JSON endpoint

- **Video pages** — `/videos/play/wwdc20NN/NNN/`, `/videos/play/tech-talks/NNNNN/`.
  Plain web fetch returns the transcript. Request it verbatim with code snippets.
- **Marketing / landing pages** — `/iphone-duo/`, `/design/resources/`, `/xcode/`.
  Ordinary HTML; fetch normally. Design Resources is where UI kits, bezels, and
  device artwork live.
- **Release notes** are documentation paths and *do* have JSON
  (`documentation/ios-ipados-release-notes`, `documentation/Updates/SwiftUI`).

## Page JSON structure

```
metadata.title                      page/symbol name
metadata.roleHeading / .symbolKind  "Structure", "Instance Property", …
metadata.platforms[]                {name, introducedAt, beta, deprecated}
abstract[]                          one-line summary (inline nodes)
primaryContentSections[]            kind: "content" | "declarations" | "parameters"
sections[]                          HIG pages put body content here
references{}                        EVERY link + EVERY image, keyed by doc:// id
topicSections[]                     child-symbol groupings
seeAlsoSections[]                   related symbols
```

`references` is the important one — it holds both real links and image assets.
Filter `type == "image"` out; a typical HIG page is ~50% images, so the raw
count badly overstates how much there is to read.

Video references appear here too, as `topic` entries whose URL contains
`/videos/play/`, which is how you discover sessions a page links without
scraping the rendered page.

## Pulling fields by hand

```python
import json, urllib.request
u = "https://developer.apple.com/tutorials/data/documentation/swiftui/toolbaritemvisibilitypriority.json"
d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})))

# declaration
for s in d.get("primaryContentSections", []):
    if s.get("kind") == "declarations":
        for dec in s["declarations"]:
            print("".join(t["text"] for t in dec["tokens"]))

# members + their one-line abstracts (fast way to see a whole type's surface)
for k, v in d["references"].items():
    if v.get("fragments"):
        ab = "".join(x.get("text", "") for x in v.get("abstract") or [])
        print(v.get("title"), "—", ab)
```

That members loop is how you find things a session never mentioned. It is what
surfaced `init(higherThan:)` / `init(lowerThan:)` on `ToolbarItemVisibilityPriority`
(the talk only said "high, low, or custom") and `overflowPresentationSource` on
`UINavigationItem` (mentioned in no session at all).

## Availability and the SDK-lag signal

`metadata.platforms[].introducedAt` gives the introducing OS version.

The web doc set trails the newest SDK. So when you probe a batch of symbols from
a brand-new platform, documented-vs-undocumented usually splits cleanly on a
version boundary rather than scattering. Establishing that boundary is often the
single most useful output of the research, because it separates "build this now"
from "blocked on a toolchain."

Confirm the user's own toolchain before drawing conclusions:

```bash
xcodebuild -version
xcrun --sdk iphoneos --show-sdk-version
```

A symbol can be documented on the web and still unavailable locally — published
docs track the shipped SDK, not the one installed on this machine.

## Interpreting 404s

| Probe | Result | Strength |
|---|---|---|
| Type (`swiftui/arrangementview`) | 404 | **Strong** — unpublished |
| Member (`uikit/uibarbuttonitem/axisbehavior`) | 404 | **Weak** — may be a wrong path |
| Control symbol (`swiftui/navigationsplitview`) | 404 | Your method is broken, not Apple's docs |

Always include a known-good control in a probe batch. If the control 404s, the
endpoint shape or spelling is wrong and every other result in the batch is
meaningless.

For member 404s, confirm against the parent page before asserting absence:

```bash
python3 scripts/appledoc.py scan "axisBehavior,badge" --pages uikit/uibarbuttonitem
```
