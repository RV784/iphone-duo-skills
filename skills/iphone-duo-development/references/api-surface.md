# iPhone Duo API surface

Working reference for the APIs introduced with iPhone Duo. Signatures are
recorded explicitly because, at the time of writing, **none of these have
published reference pages** — Apple's Tech Talks are the authoritative source.
Verify against the iOS 27.1 SDK headers once you can build against them.

## Contents
- [Reserved regions](#reserved-regions)
- [Arrangement views](#arrangement-views)
- [Vertical bars](#vertical-bars)
- [The hinge](#the-hinge)
- [Scenes, multitasking, accessories](#scenes-multitasking-accessories)
- [Cameras](#cameras)
- [Resizability foundations](#resizability-foundations)

---

## Reserved regions

Areas of the display that content should avoid. Two kinds:

| Kind | What it is | When active |
|---|---|---|
| `.division` | The fold. Splits the inner display into usable regions. | Only while partially folded; **zero width when flat** |
| `.occlusion` | The cameras. Outer camera is permanent; inner camera appears only while capturing. | Outer: always. Inner: while the camera is active |

```swift
// SwiftUI
GeometryReader { proxy in
    let fold    = proxy.reservedRegions(kind: .division)
    let cameras = proxy.reservedRegions(kind: .occlusion)
    let avoid   = (fold + cameras).map(\.frame)
    // position critical content clear of `avoid`
}

// Include regions that exist but aren't currently active
let potential = proxy.reservedRegions(kind: .division, options: .includeInactive)
```

```swift
// UIKit
let regions = view.reservedRegions(kind: .division)
let frames  = regions.map(\.frame)
```

Also available through SwiftUI's `onGeometryChange` modifier.

**Active vs inactive.** Only active regions are returned by default. Inactive
ones matter for decisions that shouldn't flip while the user folds — choosing an
even column count, for instance, is better made once from the *potential* fold
than re-derived each frame.

**These containers already handle the fold**, so reach for the API only for
custom layout: `NavigationStack`, `NavigationSplitView`, `TabView`, `List`,
`ScrollView`, plus alerts, action sheets, menus, popovers, and sheets.

**Displacement guidance.** Move elements independently when they can stand
alone, together when they read as a unit, and as little as possible either way —
large movement destroys the spatial relationships people navigate by. Do not
displace continuously scrolling content; let it scroll under the fold.

---

## Arrangement views

A container holding a **primary** and **secondary** view, positioned from size
classes, the container's aspect ratio, and any active fold. It decides both
whether a view is shown and what frame it gets.

```swift
// SwiftUI
NavigationStack {
    ArrangementView {
        DetailView()
    } secondary: {
        RelatedListView()
    }
    .arrangementViewStyle(.split)
}
```

```swift
// UIKit
let arrangement = UIArrangementViewController()
arrangement.setViewController(DetailViewController(), for: .primary)
arrangement.setViewController(RelatedListViewController(), for: .secondary)
let nav = UINavigationController(rootViewController: arrangement)
```

### Split

Divides the available area — **horizontally when wider than tall, vertically
when taller than wide**. Restrict the axis when only one makes sense; if it
cannot split along a permitted axis it shows a single view instead.

```swift
.arrangementViewStyle(.split.axes(.horizontal))

// UIKit
arrangement.updateArrangement(.split.axes(.horizontal))
```

### Overlay

Layers the two views, preferring above/below, and **moves them to either side of
the fold** when the device folds. The secondary can collapse.

```swift
.arrangementViewStyle(.overlay)
```

Read the z-index to adapt the layered view's density:

```swift
// SwiftUI
struct RelatedListView: View {
    @Environment(\.overlayArrangementZIndex) private var zIndex: Int
    var body: some View {
        RelatedList(style: zIndex > 0 ? .collapsed : .expanded)
    }
}

// UIKit
let state = arrangement.state(for: .primary)
let collapsed = (state?.zIndex ?? 0) > 0
```

### Choosing

Follow the layout you already have: an `HStack`/`VStack` pairing maps to
**split**, a `ZStack` to **overlay**. Without an existing pattern, choose
**overlay** when one view is genuinely foreground over background and obscuring
is acceptable, and **split** for a main/detail relationship where neither view
should be covered.

### Two hard constraints

- **No navigation containers inside.** An arrangement view lays out content and
  provides no navigation; put `NavigationStack` / `NavigationSplitView` /
  `TabView` *around* it.
- **Never inside a scrollable container** — `List` and `ScrollView` sizing is
  incompatible with how it measures.

---

## Vertical bars

On the outer display, and on the inner display in landscape, toolbars, tab bars,
and navigation controls move to the **side** to preserve vertical space. The
inner display in portrait keeps conventional horizontal bars.

**Opt in** by rebuilding against current SDKs *and* using bars owned by
`UINavigationController` / `UITabBarController` (SwiftUI: `NavigationStack` +
`.toolbar`). Standalone `UIToolbar` / `UITabBar` / `UINavigationBar` instances
are ignored by this system entirely.

Ordering along the axis: primary navigation (back/close) at the top, then
prominent actions, then everything else. Items **overflow bottom to top**.

```swift
// Back/close and pinned prominent action
.toolbar { ToolbarItem(placement: .cancellationAction) { CloseButton() } }
.toolbar { ToolbarItem(placement: .topBarPinnedTrailing) { DoneButton() } }

// UIKit
navigationItem.leftItemsSupplementBackButton = false
navigationItem.leadingItemGroups = [UIBarButtonItemGroup(...)]
navigationItem.pinnedTrailingGroup = UIBarButtonItemGroup(...)
```

**Which items go vertical:** a vertical bar has fixed width and flexible height,
so **items with a symbol go vertical; text-only items stay horizontal**. Always
supply a title anyway — it is used in overflow menus and expanded forms.

```swift
.toolbar { ToolbarItem { ProfileAvatar() } }.axisBehavior(.verticalPreferred)
.toolbar { ToolbarItem { SelectButton() } }.axisBehavior(.horizontalOnly)

// UIKit
item.axisBehavior = .verticalPreferred   // or .horizontalOnly
```

Prefer symbol-only items; a badge can turn a text-and-symbol item into one:

```swift
ToolbarItem { InboxButton().badge(unreadCount) }
item.badge = .count(unreadCount)          // UIKit
```

**Detect and adapt custom views:**

```swift
@Environment(\.toolbarVerticalEdge) var edge   // .leading / .trailing / .none
switch traitCollection.verticalBarEdge { … }   // UIKit
```

In a vertical bar there is no scroll edge effect by default, a background
appears under Reduce Transparency, **flexible spacers collapse to zero height**,
and fixed spacers keep their minimum.

**Overflow and compression.** Overflow occurs on the outer display in landscape,
or when a keyboard or competing UI appears. By default toolbars compress first,
preserving the tab bar — right for navigation-led apps. Invert it for
task-focused screens:

```swift
.toolbarVerticalCompressionBehavior(.prefersToolbarItems)
navigationItem.verticalBarCompressionBehavior = .prefersBarItems   // UIKit
```

Fold any custom overflow into the system menu, and reserve the ellipsis for
overflow alone:

```swift
.toolbar { ToolbarOverflowMenu { Button("Scan") { } ; Button("Connect") { } } }

navigationItem.additionalOverflowItems = UIDeferredMenuElement { provide in
    provide(self.persistentOverflowItems())
}
```

**Priorities** decide what survives compression. `ToolbarItemVisibilityPriority`
is `Comparable` with `.automatic`, `.high`, `.low`, plus `init(higherThan:)` and
`init(lowerThan:)` for a strict ordering across many items. Keep frequent
actions and badge-bearing status items visible longest.

**Opting out**, per surface, for immersive full-bleed UI — a media player, a
canvas, a calculator-style grid:

```swift
.toolbarVerticalBehavior(.disabled)

override var preferredVerticalBarBehavior: UIVerticalBarBehavior { .disabled }
```

Decide this per screen, not per app: a player surface may opt out while the
browse and detail screens around it keep system bars.

---

## The hinge

```swift
struct EffectView: View {
    @State private var openness: Double = 0

    var body: some View {
        ContentView(openness: openness)
            .onHingeChange { _, context in
                // nil hinge == device has no hinge; always handle it
                guard let hinge = context.hinge, hinge.status == .partiallyOpen else {
                    openness = 0
                    return
                }
                openness = normalized(hinge.angle)
            }
    }
}
```

UIKit: `UIHingeInteraction`. Status is `.closed` / `.partiallyOpen` /
`.fullyOpen`, alongside a continuous `angle`.

**Use it for interactive effects only.** Layout belongs to the arrangement and
reserved-region APIs. The angle changes continuously while a user folds, so
layout driven from it thrashes — which is precisely the problem the region APIs
solve.

---

## Scenes, multitasking, accessories

- Every app participates in Split View multitasking; two apps sit side by side,
  and video can stack with apps. Handle it with size classes and scene geometry,
  exactly as on iPad.
- Duo is the **first iPhone to support multiple UI instances**. Apps already
  multi-window on iPad carry over.
- **New windows can open only on the inner display.** Handle the failure;
  `UIWindowSceneActivation` hides itself when unavailable.

**Scene accessories** place supplementary content on the other display. The
system controls availability at runtime, so observe changes rather than assuming
it stays enabled.

```swift
CameraView(model: model)
    .sceneAccessory {
        CameraCaptureAccessory(isEnabled: $model.isEnabled) {
            SubjectFacingView(model: model)
        }
        .onAvailabilityChange { model.isAvailable = $0 }
    }
```

`CameraCaptureAccessory` is the camera-specific form, available when the app is
full screen on the inner display with an active capture session — it shows
content on the outer display to whoever is being photographed.

---

## Cameras

Both front cameras are square-sensor ultrawide: the outer up to 4K/120fps, the
inner 1080p/60. A **virtual front camera** switches between them automatically
and exposes only their common capabilities; address the physical devices
(`.builtInOuterUltraWideCamera`, `.builtInInnerUltraWideCamera`) when you need
more, including depth.

The subtlety worth knowing: on Duo **both front cameras report `.front`, but the
displays face opposite ways** — a "front" camera is not necessarily facing the
user. `AVCaptureDeviceDirectionCoordinator` (AVKit) resolves this. It is bound
to a view, main-actor isolated, and hands back a sendable
`AVCaptureDeviceDescriptor` rather than an `AVCaptureDevice`. Use one per display
view. Pair with `AVCaptureDeviceRotationCoordinator`, and control preview fill
with `videoGravity` and `AVCaptureDevice.dynamicAspectRatio`.

---

## Resizability foundations

Not Duo-specific, but prerequisite — and buildable on older SDKs.

```swift
// Size classes, never idiom or orientation
@Environment(\.horizontalSizeClass) private var hSize
traitCollection.horizontalSizeClass

// Screens come from the scene
let screen = window?.windowScene?.screen
let scale  = traitCollection.displayScale

// Asymmetric insets — inset the rect, never double one side
let usable = view.bounds.inset(by: view.safeAreaInsets).width

// Geometry changes; skip expensive work mid-resize
func windowScene(_ scene: UIWindowScene,
                 didUpdateEffectiveGeometry previous: UIWindowScene.Geometry) {
    let g = scene.effectiveGeometry
    guard !g.isInteractivelyResizing else { return }
    rebuild(for: g.coordinateSpace.bounds.size)
}
```

Opt into a sidebar on the inner display with
`.defaultTabBarPlacement(.sidebar)` (SwiftUI) or
`tabBarController.sidebar.preferredPlacement = .sidebar` (UIKit).
Remove `UIRequiresFullScreen`. Adopt the scene lifecycle — it is mandatory.
