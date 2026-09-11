---
name: iphone-duo-development
description: Build and adapt iOS apps for iPhone Duo, Apple's foldable iPhone with an inner and outer display and a hinge. Covers the adoption path — auditing an existing codebase for assumptions that break on two displays, then adopting reserved regions, arrangement views, vertical toolbars, the hinge API, and multi-scene/accessory support. Use this skill whenever the user mentions iPhone Duo, a foldable or folding iPhone, dual displays, the hinge or fold or crease, ArrangementView, reserved regions, vertical tab bars or toolbars, scene accessories, or asks how to make an iOS app adapt, resize, or work on the foldable. Also use it when an app needs auditing for size-class, UIScreen.main, device-idiom, or orientation assumptions, even if the foldable is not named explicitly.
---

# Building for iPhone Duo

iPhone Duo is a folding iPhone: an outer display used closed, a larger inner
display revealed when open, a hinge between them, and a range of physical poses
(book-fold, flat, propped). Apple's framing is worth internalizing before any
code — **you are still building an iPhone app.** Nothing about the platform
changes. What changes is that a single fixed screen size is no longer a safe
assumption, and a decade of code quietly assumes it.

## The one idea that prevents most mistakes

**Adapt to available space, not to poses.** The instinct on seeing a device with
several physical configurations is to detect the configuration and lay out for
each. That approach fails: it multiplies your layout count, it breaks the moment
Apple adds a pose, and it produces jarring rearrangement as the user folds.

Apple's model instead is that **the outer display is compact width, the inner
display is regular width**, and every pose falls out of that plus the fold's
geometry. If your app already adapts between iPhone and iPad, you have most of
it. So:

- Layout decisions come from **size classes**, safe areas, and layout margins.
- The fold and cameras are exposed as **reserved regions** you query, not poses
  you branch on.
- The **hinge angle is for effects, never layout** — Apple is explicit here.
  Driving layout from the angle produces exactly the jitter the region APIs exist
  to avoid.

Two consequences that surprise people: the inner display **does not honor
supported interface orientations**, so orientation tells you nothing about
available space; and because controls sit along **one** edge, **safe-area insets
are asymmetric** — `left` and `right` differ.

## Start with an audit, not with new APIs

Most of the work of supporting Duo is removing old assumptions, not adding new
calls. Run this first:

```bash
./scripts/audit_foldable_readiness.sh /path/to/project   # Swift / Obj-C
./scripts/audit_ib_layouts.py          /path/to/project   # .xib / .storyboard
# both take --verbose and exit 1 on findings, so they work as CI gates
```

Run **both**. Source greps cannot see the place a UIKit app actually defines its
layout: Interface Builder files. The IB auditor flags layouts that skip safe
areas, edges pinned to the superview rather than the safe-area guide, and large
fixed dimensions — while deliberately *not* flagging aspect-ratio or
proportional constraints, which are what Apple wants you to use instead.

The source auditor flags `UIScreen.main`, screen-bounds comparisons (including
component-wise ones like `bounds.width == UIScreen.main.bounds.width`),
device-idiom branching, orientation-driven layout, custom wrappers that hide
those checks behind a name, symmetric safe-area math, hardcoded dimensions,
fixed widths, standalone bar instances, and `UIRequiresFullScreen`.

The safe-area findings from the IB auditor deserve priority attention: because
Duo moves bars to the **side**, a view pinned to its superview's leading or
trailing edge renders *underneath* them. On a conventional iPhone the same
constraint looks fine, which is why this class of bug is invisible until the
device changes shape.
Treat the output as **candidates to review** — a couple of patterns can match
unrelated custom types — but the HIGH items are almost always genuine, and they
produce *wrong* layouts rather than merely suboptimal ones.

A mature app commonly returns hundreds of findings. That is normal and not a
crisis: it is a decade of single-screen assumptions surfacing at once, and most
resolve mechanically.

| Instead of | Use |
|---|---|
| `UIScreen.main` | `window?.windowScene?.screen` |
| `UIScreen.main.scale` | `traitCollection.displayScale` |
| `view.bounds == UIScreen.main.bounds` | `windowScene.effectiveGeometry`, or don't ask |
| `userInterfaceIdiom == .pad` | horizontal/vertical size class |
| `isLandscape` / `interfaceOrientation` | size classes |
| `width - insets.left * 2` | `bounds.inset(by: safeAreaInsets).width` |

## Gates to check before planning work

- **Scene lifecycle is mandatory.** Apps built against current SDKs that lack
  `UISceneDelegate` do not launch. It is also the foundation for fold
  continuity and multiple windows, so this is a prerequisite, not a chore.
- **SDK level changes behavior**, and apps run unmodified without it: building
  against the iOS 27 SDK extends the app past the status bar on the inner
  display; the iOS 27.1 SDK reaches the screen edge and enables vertical
  navigation and toolbar buttons.
- **Verify the local toolchain early** — the Duo APIs need Xcode 27.1 and the
  iOS 27.1 SDK:
  ```bash
  xcodebuild -version && xcrun --sdk iphoneos --show-sdk-version
  ```
  On an older toolchain the adaptive work (size classes, safe areas, scenes) is
  still fully buildable; only the Duo-specific APIs are blocked. Say so plainly
  rather than writing code that cannot compile.
- **Test poses in Device Hub**, which drives the simulator through open, closed,
  rotated, and folded states.

## Adoption order

Work in this sequence — each stage is useful on its own, which matters because
the later stages may be toolchain-blocked.

1. **Resizability.** Clear the audit's HIGH findings, adopt scenes, handle
   asymmetric insets. Pays off immediately on iPad and iPhone Mirroring, no new
   SDK required.
2. **Standard containers.** `NavigationStack`, `NavigationSplitView`, `TabView`,
   `List`, `ScrollView`, and system presentations already adapt to every pose and
   route around the fold. Replacing a hand-rolled split with a standard one is
   usually the single highest-leverage change.
3. **Vertical bars.** Largely automatic *if* your bars belong to a navigation
   container. Then tune ordering, priorities, and overflow.
4. **Custom layout.** Reserved regions and arrangement views, for the parts the
   system cannot place for you.

## The API surface

Detail, signatures, and worked examples are in
**`references/api-surface.md`** — read it when you're implementing. The shape:

- **Reserved regions** — query `.division` (the fold; active only when folded,
  zero width when flat) and `.occlusion` (cameras) from a `GeometryProxy` or
  `UIView`, and keep critical content out of them.
- **Arrangement views** — `ArrangementView` / `UIArrangementViewController` hold
  a primary and secondary view and place them by size, aspect ratio, and active
  fold. `.split` divides the area; `.overlay` layers them and moves them to
  either side of the fold. Navigation goes *around* an arrangement view, never
  inside it, and an arrangement view never goes inside a scroll view.
- **Vertical bars** — on the outer display and inner landscape, system bars move
  to the side. Opt in by using container-owned bars; tune with visibility
  priority, axis behavior, and compression behavior; opt out per surface with
  `.toolbarVerticalBehavior(.disabled)` for immersive, full-bleed UI.
- **Hinge** — `onHingeChange` / `UIHingeInteraction` give status
  (closed/partially open/fully open) plus a continuous angle. Effects only.
- **Multiple scenes and accessories** — Duo is the first iPhone supporting
  multiple UI instances. New windows open **only on the inner display**, so
  handle that failure. Scene accessories put supplementary content on the outer
  display, with availability the system controls at runtime.

## Design rules worth honoring

- Keep **functionality identical** across displays and poses; vary how much is
  shown, never what exists.
- Prefer **small adjustments** as the device folds. Controls that vanish or jump
  are hard to track.
- Prefer an **even number of grid columns** so content divides cleanly.
- For full-bleed content, **fill the display** and prefer changing aspect ratio
  over letterboxing; if padding is unavoidable, fill it with artwork.
- Give every non-text bar item **both a title and a symbol** — the title is used
  in overflow menus even when not displayed.
- Keep interactive elements out of the fold. Scrolling content is the exception.

## Documentation reality (as of the Duo launch)

Worth knowing so you don't waste time searching: the Duo-specific APIs
(`ArrangementView`, reserved regions, `onHingeChange`, vertical-bar modifiers,
scene accessories) have **no published reference pages**. The Tech Talk
transcripts are currently the authoritative source, which is why
`references/api-surface.md` records signatures explicitly.

Only one HIG page covers the device. The iOS 27.0 toolbar APIs that Duo builds on
(visibility priority, overflow menus, pinned placements) *are* documented, so the
overflow and priority work can be researched normally.

Verify signatures against the SDK headers once you're on Xcode 27.1 — and if
you're checking whether Apple has since published more, the companion
`apple-docs-research` skill automates that sweep.

## Sources

Everything here derives from Apple's published material — the
[Designing for iPhone Duo](https://developer.apple.com/design/human-interface-guidelines/designing-for-iphone-duo)
HIG page and Tech Talks [111461](https://developer.apple.com/videos/play/tech-talks/111461/),
[111462](https://developer.apple.com/videos/play/tech-talks/111462/),
[111463](https://developer.apple.com/videos/play/tech-talks/111463/),
[111464](https://developer.apple.com/videos/play/tech-talks/111464/),
[111465](https://developer.apple.com/videos/play/tech-talks/111465/),
[111466](https://developer.apple.com/videos/play/tech-talks/111466/).
Consult Apple's originals as the authority; this skill is a developer's working
summary, not a substitute.
