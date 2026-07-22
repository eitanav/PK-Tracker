# Android — Changelog

All notable changes to the **PK Tracker Android app** are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Every push to `main` under `android/` builds a debug APK and publishes it to
[GitHub Releases](https://github.com/eitanav/PK-Tracker/releases) under the
tag `android-vX.Y.Z`, matching `versionName` in `app/build.gradle.kts`. The
in-app **Settings → About** card links straight to that releases page and
mirrors this changelog.

## [2.0.0] - 2026-07-22

### Added
- **Per-substance theming.** The active substance now tints the whole
  dashboard — gauge, chart, logo, nav and accents animate to its colour
  (amber caffeine, blue Ritalin, green Vyvanse, purple Adderall, rose
  alcohol).
- **Hero gauge.** The status card leads with a circular gauge that sweeps
  to your current load (mg vs jitter zone, effect %, or BAC vs limit) with
  an animated count-up, plus a 2×2 grid of stat tiles.
- **Insights tab** (replaces History). Turns the dose log into patterns:
  the hours you actually reach for it, your weekly rhythm, doses/day, this
  week's total, usual first-dose time, and a logging streak — with a
  compact recent-doses list (delete / undo) kept underneath.
- **New logo.** The launcher icon and in-app mark are now the
  pharmacokinetic curve itself (absorption → peak → clearance), re-tinting
  per substance.
- **Animations.** Gauge sweep, number count-up, and grow-in bars, all
  built on Compose's animation system.

## [1.0.4] - 2026-07-22

### Added
- **Download link + in-app changelog.** Settings → About now has a
  "Download latest release" button (opens the GitHub Releases page) and a
  short changelog, so the latest build is always one tap away from inside
  the app.

## [1.0.3] - 2026-07-22

### Added
- **Brand-name substance labels.** Prescription stimulants now show their
  common brand names (Ritalin/Attent, Concerta, Vyvanse, Adderall, Adderall
  XR) instead of pharmacological names, in both English and Hebrew.
- **Chart Y axes.** The timeline chart now draws a blood-level axis (left)
  and an effect % axis (right).
- **Pannable chart.** Drag the chart, or use the ◀ / recenter / ▶ controls,
  to move through past and future. A new "Graph window" setting (4–48 h)
  controls how much time is visible at once.

### Fixed
- Remaining hardcoded English strings (the simulation "min" suffix, body
  mass "kg", half-life "h", the BAC card title) now localise correctly in
  Hebrew.

## [1.0.2] - 2026-07-22

### Fixed
- **Crash on every launch.** `Theme.PKTracker` inherited from the platform
  `Theme.Material` instead of a `Theme.AppCompat` descendant, which crashed
  `AppCompatActivity` immediately on `onCreate`. This affected 1.0.0 and
  1.0.1 as well — 1.0.2 is the first build that actually runs.

## [1.0.1] - 2026-07-22

### Added
- `contentDescription` on the timeline chart so TalkBack announces it.
- A solid/dashed legend caption under the chart.

### Fixed
- Localised the simulation "min" suffix and the BAC card title, previously
  hardcoded in English.

## [1.0.0] - 2026-07-22

### Added
- First Android release: full native port of the desktop app in Kotlin +
  Jetpack Compose — dashboard, history, settings, Hebrew/English with RTL,
  dark/light theme, CSV export.
