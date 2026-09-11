---
name: apple-docs-research
description: Exhaustively research Apple developer documentation — HIG pages, API reference, WWDC/Tech Talk sessions — by enumerating every linked reference programmatically and fetching all of them, never skipping one because it "looks like" a well-known API. Use this skill whenever the user asks you to read, go through, gather context from, or research anything on developer.apple.com: a HIG page, a framework or symbol's docs, a WWDC or Tech Talk session, release notes, or "everything about" a new Apple platform, device, OS version, or API. Also use it when the user asks what a new Apple API does, whether something is documented, or which SDK a symbol needs — and whenever they ask you to be thorough, complete, or exhaustive about Apple docs, or challenge whether you actually read all of it.
---

# Exhaustive Apple developer documentation research

## Why this skill exists

Apple's docs invite two specific mistakes, and both produce research that *looks*
complete and isn't.

**The first is silent triage.** A page links to `HStack`, `VStack`, `ZStack`,
`Label`, `UIBarButtonItem` — and it is very tempting to think "I know those" and
skip them. That reasoning is invalid, and it's worth being precise about why:
you are not deciding whether *you* need the page. You are deciding what the
*user's report* is based on. The reader has no way to tell which links you read
and which you assumed, so an unmarked gap reads as coverage. Worse, Apple
routinely adds new members to old types — a "boring" `GeometryProxy` link is
exactly where a brand-new `reservedRegions(kind:)` would live. Your prior about
a type's familiarity is evidence about the past, not about this page.

The rule that follows: **you may skip a link, but you may not skip it silently.**
Every reference is either fetched or explicitly listed as not-fetched with a
reason, in the output. Cheap to follow, and it converts an invisible assumption
into a visible, checkable claim.

**The second is trusting the rendered page.** developer.apple.com is a
JavaScript SPA. Fetching the human URL returns an empty shell — you get a title
and nothing else, which is easy to mistake for "this page is thin." The real
content is at DocC JSON endpoints. `scripts/appledoc.py` handles the mapping.

## The method

Run these in order. Steps 1–3 are the non-negotiable core; 4–6 are what turn a
transcript dump into something a reader can act on.

### 1. Fetch the root page as JSON, never as HTML

```bash
python3 scripts/appledoc.py get hig:designing-for-iphone-duo
python3 scripts/appledoc.py get swiftui/navigationsplitview
```

`hig:<page>` is shorthand for a Human Interface Guidelines page; anything else
is treated as a `documentation/` path. Full URLs work too. Add `--raw` for the
underlying JSON when you need metadata the text view drops.

**Video pages are the exception** — `/videos/play/wwdc20NN/NNN/` and
`/videos/play/tech-talks/NNNNN/` return real transcript content to an ordinary
web fetch. Use WebFetch for those, and ask for the transcript *verbatim with
every code snippet*, because for brand-new APIs the transcript is frequently the
only place a declaration exists anywhere (see step 4).

### 2. Enumerate every reference programmatically

```bash
python3 scripts/appledoc.py refs hig:designing-for-iphone-duo
```

Do this instead of eyeballing a prose summary of the page's links. A summary is
itself a lossy read, and it is the natural place for a link to quietly go
missing. The command prints a count — `32 real references` — that becomes your
accounting target.

Output is classified as `HIG` / `API` / `VIDEO` / `EXTERNAL` / `topic`. Images
are counted and excluded (a typical page is half image references, which is why
the raw reference count is misleadingly large).

### 3. Fetch all of them, and account for every one

Batch them. `refs` output feeds straight into `get`, and independent fetches
should go out in parallel rather than one per turn.

Two classes genuinely need no fetch, and naming them is part of the accounting:
site chrome (`Human Interface Guidelines` index, `Technologies`, `Getting
started`) and same-page anchors (`#Size-classes`). Everything else gets fetched.
**`EXTERNAL` links are the ones most often dropped** — Apple Design Resources,
GitHub plug-ins, sample-code downloads. They are also where device dimensions,
UI kits, and bezels live, so a question like "what are the screen dimensions"
is answered there or nowhere.

### 3b. Scope the rule sensibly on large symbol pages

The accounting rule is about **topical** links, not every symbol Apple's
generator emits. A HIG page carries 15–35 real references and all of them are
meaningful. A large UIKit class page carries 100+ — `UISplitViewController`
alone has 108 — because DocC lists every inherited member and protocol
conformance (`CVarArg`, `NSObjectProtocol`, `Equatable`…). Fetching those is
noise, not rigor.

So scope by the research question:

- **Root page and anything topically linked** — fetch everything. This is where
  silent triage does its damage.
- **Large symbol pages** — read the page itself, then enumerate its members
  in one pass (`topicSections`, or the members loop in `references/endpoints.md`)
  rather than fetching each member's page. One request shows the whole surface
  including members no session mentioned.
- **Boilerplate conformances** — skip, and say so once: "108 refs, 90 of which
  are inherited/conformance boilerplate; read the 18 topical ones."

The test isn't "did I fetch every URL," it's **"could a reader be misled about
what I actually read."** One honest line about what you skipped and why
satisfies it; silence does not.

### 4. Probe which symbols are actually documented

For any new platform or OS release, the tech talks will name APIs that have no
published reference page at all. Establishing *which* is a finding in itself.

```bash
python3 scripts/appledoc.py probe \
  swiftui/arrangementview swiftui/reservedregion \
  swiftui/toolbaritemvisibilitypriority uikit/uihingeinteraction
```

The output includes **introduced-in versions**, and this is where the real
insight usually hides. When you sort documented vs undocumented symbols by
availability, the split is rarely random — it typically falls exactly on an SDK
boundary, because the web doc set lags the newest SDK. That single observation
answers the question the user actually cares about: *which parts can I build
today, and which parts am I waiting on a toolchain for?*

Interpreting a 404 correctly matters:

- **404 on a type** (`swiftui/arrangementview`) — strong evidence it is unpublished.
- **404 on a member path** (`uikit/uibarbuttonitem/axisbehavior`) — weak evidence.
  You may simply have guessed the path wrong. Confirm against the parent page
  before claiming anything:
  ```bash
  python3 scripts/appledoc.py scan "axisBehavior,badge" --pages uikit/uibarbuttonitem
  ```
  In this exact case the parent page shows `badge` present and `axisBehavior`
  absent — so one 404 was a bad path and the other was a real gap. Reporting
  both as "undocumented" would have been wrong.

### 5. Sweep adjacent pages for the topic — searching content, not alt-text

To check whether a topic reaches beyond its own page:

```bash
python3 scripts/appledoc.py scan "iPhone Duo,hinge,reserved region" \
  --pages hig:layout,hig:multitasking,hig:split-views,hig:playing-video
```

`scan` searches **page prose only**. This is not a detail — a naive `grep` over
the raw JSON produces confident false positives from image alt-text. Icon
descriptions like *"two side-by-side windows in a split view arrangement"* match
`arrangement` on half a dozen unrelated pages, and `UISplitViewController`
matches `fold` because it discusses Notes **folders**. Both of those very nearly
became findings. `scan` excludes the reference/image payload so its hits are real.

A clean negative here is a genuine result — "this concept appears on exactly one
page and nowhere else in the HIG" tells the reader not to go looking.

### 6. Follow cross-referenced sessions, and check their dates

Sessions cite other sessions. Follow them, but verify the citation actually
pays out: a WWDC session from June cannot discuss hardware announced in
September, even when a talk lists it as related. Check what a session predates
before treating it as coverage — and when it contains nothing on the topic, say
so explicitly rather than omitting it, since "I checked and it's empty" and "I
didn't check" are indistinguishable to the reader otherwise.

## Reporting

Lead with a **source inventory**: every artifact, its type, and whether you
fetched it. Then the substance. Then — and this is the part most often dropped —
a **verified negatives** section.

Negatives earn their place because they are expensive to establish and cheap to
consume. "Apple has published nothing about video playback on this device; I
grepped 30+ HIG pages and the `playing-video` page has zero mentions" stops the
reader from repeating your search. State the *method* alongside the negative, so
they can judge how much to trust it.

Distinguish three things throughout, and label them:

- **Apple's text** — quote or reproduce it; for undocumented APIs the
  transcript snippet is the authoritative source and should be verbatim.
- **Verified absence** — you looked, with a named method, and it isn't there.
- **Your synthesis** — implications for the user's codebase. Mark it clearly as
  yours. It's usually the most valuable section and the one most damaged by
  being mistaken for Apple's guidance.

Flag the toolchain gate when it applies: if the APIs need a newer Xcode/SDK than
the user has (`xcodebuild -version`, `xcrun --sdk iphoneos --show-sdk-version`),
say so early — it changes whether the work is buildable now or plan-only.

## Failure modes worth remembering

| Symptom | Cause | Fix |
|---|---|---|
| Page returns only a title | SPA shell from the human URL | Use the JSON endpoint via `get` |
| Confident hits on unrelated pages | Matched image alt-text | Use `scan`, not raw grep |
| "Undocumented" member that exists | Guessed the wrong member path | `scan` the parent page |
| Missed dimensions / UI kits | Skipped `EXTERNAL` links | Fetch them; that's where downloads live |
| Session "covers" a topic it can't | Citation predates the announcement | Check dates before trusting |
| Report reads complete but isn't | Silent triage of "known" APIs | Account for every ref in the output |

## Reference

`references/endpoints.md` documents the URL→JSON mapping rules, the page JSON
structure, and how to pull availability and declaration fragments by hand if you
need something the script doesn't surface.
