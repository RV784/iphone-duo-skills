#!/usr/bin/env bash
# audit_foldable_readiness.sh — find the patterns that break on iPhone Duo.
#
# Every rule maps to something Apple explicitly warns against for a device with
# two displays and a hinge. None are hypothetical: these are the assumptions
# that silently produce a wrong layout on a foldable, and most of them predate
# the device by a decade.
#
# Portability note: written for BSD/macOS tools, since that is where iOS
# development happens. Avoids GNU-only flags (notably `xargs -a`) and
# GNU-only regex escapes (`\s`).
#
# Usage:  ./audit_foldable_readiness.sh [path] [--verbose]
# Exit:   0 = clean, 1 = findings (usable as a CI gate)

set -uo pipefail

ROOT="."; VERBOSE=0
for a in "$@"; do
  case "$a" in
    --verbose|-v) VERBOSE=1 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) ROOT="$a" ;;
  esac
done
[ -d "$ROOT" ] || { echo "No such directory: $ROOT" >&2; exit 2; }

RED=$'\033[31m'; YEL=$'\033[33m'; GRN=$'\033[32m'; DIM=$'\033[2m'; OFF=$'\033[0m'
[ -t 1 ] || { RED=""; YEL=""; GRN=""; DIM=""; OFF=""; }

FILES=$(mktemp); trap 'rm -f "$FILES"' EXIT
find "$ROOT" -type f \( -name '*.swift' -o -name '*.m' -o -name '*.mm' \) \
  -not -path '*/Pods/*' -not -path '*/.build/*' -not -path '*/Carthage/*' \
  -not -path '*/DerivedData/*' -not -path '*/.git/*' -print0 > "$FILES"

COUNT=$(tr -dc '\0' < "$FILES" | wc -c | tr -d ' ')
if [ "$COUNT" -eq 0 ]; then
  echo "No Swift/Obj-C sources found under ${ROOT}" >&2; exit 2
fi
echo "iPhone Duo readiness audit — ${COUNT} source files under ${ROOT}"
echo "Findings are candidates to review, not confirmed bugs: a few patterns"
echo "(notably orientation) can match unrelated custom types."
echo

TOTAL=0; HIGH_N=0

# search <pattern> -> "file:line:content" lines, excluding comment-only matches
search() {
  xargs -0 grep -nE "$1" < "$FILES" 2>/dev/null | grep -vE ':[[:space:]]*(//|\*|/\*)' || true
}

check() { # severity, title, why, pattern
  local sev="$1" title="$2" why="$3" pat="$4"
  local hits n color
  hits=$(search "$pat")
  n=$(printf '%s' "$hits" | grep -c . 2>/dev/null || true)
  [ "${n:-0}" -eq 0 ] && return 0
  TOTAL=$((TOTAL + n))
  color=$YEL; [ "$sev" = "HIGH" ] && { color=$RED; HIGH_N=$((HIGH_N + n)); }
  printf '%s[%-4s]%s %s %s(%d)%s\n' "$color" "$sev" "$OFF" "$title" "$DIM" "$n" "$OFF"
  printf '        %s%s%s\n' "$DIM" "$why" "$OFF"
  if [ "$VERBOSE" -eq 1 ]; then
    printf '%s\n' "$hits" | sed 's/^/        /'
  else
    printf '%s\n' "$hits" | head -3 | sed 's/^/        /'
    [ "$n" -gt 3 ] && printf '        %s… %d more (run with --verbose)%s\n' "$DIM" "$((n - 3))" "$OFF"
  fi
  echo
}

check HIGH "Main-screen references" \
  "Ambiguous on a two-display device and slated for deprecation. Use window?.windowScene?.screen; for scale use traitCollection.displayScale." \
  'UIScreen\.main|\[UIScreen mainScreen\]'

check HIGH "Screen-bounds comparison" \
  "A view's bounds equalling the screen's is a common 'am I fullscreen' test. It is false in Split View, in a windowed scene, and on the inner display." \
  'bounds(\.(width|height|size))?[[:space:]]*==[[:space:]]*UIScreen|UIScreen\.main\.bounds(\.(width|height|size))?[[:space:]]*=='

check HIGH "Device-idiom branching" \
  "Idiom tells you what the device is called, not how much space you have. Branch on size classes instead." \
  'userInterfaceIdiom|UI_USER_INTERFACE_IDIOM'

check HIGH "Orientation-driven layout" \
  "The inner display does not honor supported interface orientations, so orientation is not a proxy for available space." \
  'UIDevice\.current\.orientation|interfaceOrientation|\.isLandscape\b|\.isPortrait\b|UIInterfaceOrientationIs'

check HIGH "Symmetric safe-area assumption" \
  "Duo places controls along ONE edge, so left and right insets differ. Inset the rect rather than doubling one side." \
  'safeAreaInsets\.(left|right|top|bottom)[[:space:]]*\*[[:space:]]*2'

check MED "Custom device/orientation wrappers" \
  "Helpers like isIPAD or isLandscape hide an idiom/orientation check behind a name, so neither this audit nor a reader sees it. Audit the helper itself, then every call site." \
  '(var|let|func)[[:space:]]+(isIPAD|isIPad|isIphone|isIPhone|isPad|isPhone|isLandscape|isPortrait|getOrientation|currentOrientation|deviceType|screenWidth|screenHeight)\\b'

check MED "Call sites of device/orientation wrappers" \
  "Each of these resolves to an idiom or orientation test. Replace the helper with a size-class decision rather than fixing call sites one by one." \
  '[^.[:alnum:]_](isIPAD|isIPad|isPad)[^[:alnum:]_(]|DRUtils\\.(isPortrait|isLandscape|getOrientation)'

check MED "Hardcoded device dimensions" \
  "Magic numbers copied from one iPhone. Apple publishes no Duo dimensions; query reserved regions at runtime." \
  'width:[[:space:]]*(320|375|390|393|414|428|430)(\.0)?[[:space:]]*[,)]|==[[:space:]]*(375|390|393|414|428|430)(\.0)?\b'

check MED "Fixed-width constraints" \
  "A fixed width cannot expand onto the inner display or collapse onto the outer one." \
  'widthAnchor\.constraint\(equalToConstant:|\.frame\(width:[[:space:]]*[0-9]'

check MED "Standalone bar instances" \
  "Bars you construct yourself are ignored by the vertical-bar system. Only bars owned by UINavigationController/UITabBarController move to the side." \
  '=[[:space:]]*UIToolbar\(\)|=[[:space:]]*UITabBar\(\)|=[[:space:]]*UINavigationBar\(\)'

check LOW "UIRequiresFullScreen in source" \
  "Deprecated opt-out of resizing." \
  'UIRequiresFullScreen'

# Info.plist sweep — separate, since plists are not in the source list
PL=$(find "$ROOT" -name 'Info.plist' -not -path '*/Pods/*' -not -path '*/DerivedData/*' -print0 2>/dev/null \
     | xargs -0 grep -l 'UIRequiresFullScreen' 2>/dev/null || true)
if [ -n "$PL" ]; then
  n=$(printf '%s\n' "$PL" | grep -c .); TOTAL=$((TOTAL + n))
  printf '%s[MED ]%s UIRequiresFullScreen in Info.plist %s(%d)%s\n' "$YEL" "$OFF" "$DIM" "$n" "$OFF"
  printf '        %sBlocks resizing. Remove it — it is ignored on current SDKs anyway.%s\n' "$DIM" "$OFF"
  printf '%s\n' "$PL" | sed 's/^/        /'; echo
fi

echo "────────────────────────────────────────────────────────"
if [ "$TOTAL" -eq 0 ]; then
  printf '%sNo foldable-readiness issues found.%s\n' "$GRN" "$OFF"
  echo "Next: adopt reserved regions and arrangement views for custom layouts."
  exit 0
fi
printf '%s%d finding(s)%s, %d high severity.\n' "$RED" "$TOTAL" "$OFF" "$HIGH_N"
echo "Each is a place the code assumes a single fixed screen."
echo "Fix HIGH first: those produce wrong layouts, not merely suboptimal ones."
exit 1
