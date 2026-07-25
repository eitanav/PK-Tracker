# Changelog

All notable changes to **PK Tracker** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project aims to follow [Semantic Versioning](https://semver.org/).

> **Release policy.** App, installer, changelog, and GitHub release tags share one
> semantic version. The CI workflow derives the release tag straight from
> `pk_tracker.__version__` (e.g. `1.6.1` → `v1.6.1`) on every push to `main`, so a
> single version bump publishes a correctly-tagged release. `releases/latest`
> stays the stable download URL.

## [Unreleased]

Nothing yet — see [`TODO.md`](TODO.md) for the roadmap.

## [2.1.0] - 2026-07-25

### Fixed
- **Alcohol absorption was instantaneous.** A drink jumped straight to its peak
  BAC the moment it was logged, then fell in a straight line — so the chart was
  a vertical step followed by a slope, and the first hour was overstated by
  roughly a third. Ethanol actually reaches the blood over ~20–60 min, peaking
  around 30–45 min on an empty stomach (later and lower after a meal, because
  elimination runs while absorption continues). The absorption window now
  defaults to 30 minutes instead of 0.
  For one standard drink (14 g) in a 70 kg man, the peak moves from 0.029 g/dL
  *at the moment of the first sip* to 0.022 g/dL *half an hour in* — which is
  where the literature puts it. Existing profiles carry the old `0` explicitly,
  so they are migrated once; set it back under Calibration if you want it.
- `widmark_bac` now models the absorption window as **exact continuous
  absorption** (a piecewise-linear walk over drink starts and absorption ends)
  rather than ten discrete sub-doses, which had made the rising edge a visible
  staircase (~13% ripple) instead of a smooth climb. Overlapping drinks
  accumulate correctly.

### Notes
- The **falling** limb stays a straight line, and that is correct, not a bug:
  alcohol elimination is zero-order, unlike the exponential decay of caffeine.
  Tests now pin this down so it is not "fixed" into a curve later.
- The desktop and Android engines are checked against each other to 1e-9, so
  both apps report the same BAC for the same drink.

## [2.0.0] - 2026-07-25

Brings the desktop app in line with the Android redesign, and connects the two.

### Added
- **Cloud sync.** The dose log now syncs with the Android app through the same
  private Firebase project. Signing in with the same Google account yields the
  same Firebase `uid`, so both logs converge on `users/{uid}/doses/{doseUid}`.
  Merge is last-write-wins by `updatedAt` and honours soft deletes, so a
  deletion on the phone stays deleted here. Runs over plain HTTPS REST with no
  SDK and **no new dependencies**. Set-up and troubleshooting: [`docs/SYNC.md`](docs/SYNC.md).
  Drive it from **Settings → Cloud sync** (sign in, sync now, last-sync time)
  or from the command line (`python -m pk_tracker.sync.cli`).
- **Per-substance theming.** The active substance re-tints the whole
  window — plot, gauge, logo, tray icon and accents — in its own colour.
- **Hero gauge.** The status panel now leads with an animated circular gauge
  (sweep + count-up) showing the current level against its meaningful
  reference: jitter zone, effect %, or the legal BAC limit.
- **Insights view.** A second page on the timeline panel turning the log into
  patterns: busiest hours, weekly rhythm, doses per active day, this week's
  total, usual first-dose time, and a logging streak. The statistics mirror the
  Android app's exactly, so both report the same numbers.
- **New logo.** App, window and tray marks are now the pharmacokinetic curve
  itself (absorption → peak → clearance), re-tinted per substance.

### Fixed
- **The alcohol chart was unreadable.** The level axis was floored at `1.0`,
  which fits caffeine's mg/L but not alcohol's g/dL, so an entire evening's BAC
  curve was flattened into the bottom few percent of the plot. The axis now
  scales in the substance's own unit — a 0.060 g/dL peak fills ~80% of the plot
  height instead of ~6%.

### Changed
- Dose deletions are now **soft** (tombstone + `updated_at`) so removals
  propagate between devices instead of reappearing on the next sync. Existing
  databases migrate additively (schema v3): every dose gains a global `uid`,
  backfilled in place, with nothing lost.
- `updated_at` is strictly monotonic per row, so two edits inside one
  millisecond cannot tie and lose the later one during a sync.

## [1.6.1] - 2026-06-17

### Changed
- **Consistent release versioning.** The Windows build workflow now derives the
  GitHub release tag from `pk_tracker.__version__` instead of a hard-coded value,
  so bumping the version in one place publishes the matching `vX.Y.Z` release.
  (Fixes the "app says one version, GitHub says another" mismatch for good.)

### Verified
- Reviewed and validated the 1.6.0 timeline/UX work: Y-normalised graph with
  time-axis-only dragging, zoom-aware time labels, the on-graph hover readout, and
  the coloured what-if dose simulation — all exercised headless and passing.

## [1.6.0] - 2026-06-17

### Added
- **Interactive timeline polish.** The main graph now locks mouse dragging to the
  time axis, normalizes Y ranges on redraw, shows denser zoom-aware time labels,
  and displays an on-graph hover readout with exact local time, level, and effect.
- **Dose simulation overlay.** Caffeine-like substances can preview a hypothetical
  future dose on the graph in a different colour before it is logged.

### Changed
- Dashboard controls were simplified: Calibration, New substance, and About live
  in Settings; the dashboard keeps a compact widget show/hide toggle.
- The custom "minutes ago" dose field now steps in 15-minute increments while
  still accepting typed values.
- Version metadata is aligned at **1.6.0** across package metadata, installer, and
  changelog.


## [1.5.0] - 2026-06-06

Five simple-but-significant improvements.

### Added
- **📊 Daily total vs guideline.** "Today: X / 400 mg" on the dashboard and the
  widget, coloured as you approach (amber) or exceed (red) the FDA's ~400 mg/day
  caffeine guideline — the "how much have I had today?" answer.
- **↩ Undo last dose.** One click removes the most recently logged dose.
- **⏱️ Personal caffeine half-life** (Calibration). Override the population ~5 h —
  ~3-4 h if you smoke, ~10 h on oral contraceptives or in pregnancy. It
  personalises every caffeine curve, the sleep cutoff, and perfect timing.
- **💾 Export dose log** (CSV / JSON) from Settings → Data — a backup, or for
  spreadsheet analysis.
- **☕ "Latest coffee" on the widget.** The sleep-cutoff curfew time now shows on
  the always-visible floating widget, not just the dashboard.

## [1.4.0] - 2026-06-06

### Added
- **🎯 Perfect timing coach (caffeine).** Tell it a moment you need to be sharp
  (workout, exam, meeting) and it computes **exactly when — and how much — to
  drink** so caffeine peaks right then, with a live check against your sleep
  cutoff (✓ safe / ⚠ past your curfew). Inverse pharmacokinetics: a single dose
  peaks one Tmax after it's taken, so the optimal dose time is `target − Tmax`.
  Shown as a panel in the status column for caffeine.

## [1.3.3] - 2026-06-06

### Fixed
- **Widget appeared to "not open" when toggled.** A stale **off-screen saved
  position** (e.g. from a monitor that is no longer connected) placed it where it
  couldn't be seen, and in pinned mode it could open *behind* other windows. The
  saved position is now clamped onto a connected screen, and showing the widget
  brings it on-screen **and to the front** (`reveal()`), even in pinned mode.

### Added
- A **"Show floating widget" button on the dashboard**, so the widget can be
  brought back without using the tray.

## [1.3.2] - 2026-06-06

### Fixed
- **Floating widget could fail to open at all after an upgrade.** The ✕ button
  used to persist a "hidden" flag (`ui_widget_visible="0"`), and because user data
  in `~/.pk_tracker` survives reinstalls, the widget stayed hidden on every new
  install with no obvious way back. Now:
  - the ✕ button **dismisses the widget for the session only** — it reopens on the
    next launch, and shows a one-time tray hint pointing to the tray/Settings;
  - the persistent show/hide moved to a new `ui_widget_enabled` key (default on),
    so the stale hidden state is ignored and the widget **returns automatically**
    on upgrade. Turning it off for good still lives in Settings and the tray menu.

## [1.3.1] - 2026-05-31

### Changed
- **Caffeine in the body (mg) is now the primary metric; effect % is secondary.**
  The floating widget leads with e.g. **"88 mg"** and shows effect % as a small
  badge; the status panel's big number is the mg in body (with the jitter-zone
  ceiling), and effect % moves to a secondary row. The widget sparkline now tracks
  blood level (∝ mg) to match the headline.

## [1.3.0] - 2026-05-31

### Changed
- **Reworked the sleep cutoff around an intuitive, research-grounded model.** The
  old "Target by bed = X % of peak" control was confusing (the percentage referred
  to a single dose's own peak, and caffeine's ~5 h half-life made even 15 % land
  ~13 h before bed). It's replaced by a **"☕ Latest caffeine: HH:MM"** headline on
  the dashboard plus a method you choose in **Settings → Sleep cutoff**:
  - **Caffeine left at bedtime (mg)** — the default; keep caffeine in the body at
    bedtime at or below a target (~50 mg), dose-aware so it accounts for what
    you've already logged.
  - **Sensitivity preset** — Very sensitive / Average / Caffeine-resistant, mapped
    to ~25 / ~50 / ~100 mg.
  - **Hours before bed** — a flat "stop N hours before bed" rule.
  Defaults and the in-app explanation are grounded in caffeine/sleep dose-timing
  research (Drake 2013; SLEEP 2025), with a "not medical advice" note. Bedtime and
  method now live in Settings; the dashboard shows the answer.

## [1.2.2] - 2026-05-31

### Fixed
- **App icon stayed as the old (floppy/Python) one on the desktop shortcut,
  taskbar and in Explorer**, even though the running window showed the correct
  coffee icon. The window icon is painted at runtime, so it was always right; the
  *file* icon comes from the executable's embedded resource, which the previous
  build now embeds correctly (1.2.1) — but Windows kept serving the **cached** old
  icon for the same install path. The installer now refreshes the Windows icon
  cache (`ie4uinit -show`) after installing, so the new icon appears immediately
  instead of only after a reboot.

### Added
- Project **`CHANGELOG.md`** (this file) and a **`TODO.md`** roadmap of planned
  features and fixes.

### Changed
- App version bumped to **1.2.2**.

### Fixed
- **Uninstall left files behind** ("some elements could not be removed"). The
  tray-resident app held a lock on its own files; the uninstaller now force-closes
  `PKTracker.exe` first and removes the whole install folder. User data in
  `%UserProfile%\.pk_tracker` is intentionally preserved across reinstalls.
- **Executable showed the default PyInstaller (floppy/Python) icon.** The bundled
  `.ico` used PNG-compressed entries, which PyInstaller can silently drop when it
  runs without Pillow (as in CI). Regenerated as classic 32-bit BMP/DIB entries so
  the coffee-cup-and-clock icon embeds reliably.
- **Effect (blue) trace clipped at the top and didn't follow panning.** Its
  right-axis ViewBox now re-syncs geometry on resize and after every redraw, and
  the axis grows past 100 % when a just-logged, still-rising dose projects above
  the recent peak — so the curve stays fully visible and tracks the time axis.

### Added
- Optional **close (✕) button** on the floating widget, with a Settings toggle to
  show or hide it (`ui_widget_close_btn`).

## [1.2.0] - 2026-05-31

### Added
- **Settings panel** for app-wide preferences (theme, widget behaviour, sleep
  cutoff) reachable from the main window and the tray.
- **Light and dark themes**, switchable at runtime.
- **Plot legend** distinguishing blood level (solid) from effect % (dashed,
  right axis) and "so far" vs "projected".
- **Alcohol feedback**: explicit sober/legal-limit projections with clear copy
  that the model only ever predicts clearance, never suggests another drink.
- **Configurable sleep cutoff** (bedtime + target) with a "coffee curfew" readout.
- New **coffee-cup-and-clock app icon**.

## [1.1.0] - 2026-05-31

### Added
- Floating widget now **auto-shows on startup** and offers a **pin-to-desktop**
  mode (sits below other windows like a gadget) in addition to float-on-top. The
  widget remembers its position and visibility between launches.

### Fixed
- Installer **auto-closes a running instance before upgrading**, so in-place
  updates no longer fail with an "access denied" file lock.

## [1.0.0] - 2026-05-30

First complete, packaged release.

### Added
- **PK/PD engine** (milestone 1): tested one-compartment caffeine model
  (Bateman absorption/elimination), Emax effect model, and an alcohol Widmark
  zero-order model, with population-average constants and cited sources.
- **Persistence** (milestone 2): local SQLite store for doses, substances,
  profile and settings — local-only, never synced.
- **Desktop UI** (milestones 3–7): main dashboard with interactive timeline
  plot, dose logging with presets, history, a draggable always-available
  **floating widget**, a **system-tray** menu, and a **calibration** flow to
  personalise body mass / sensitivity.
- **Extended-release model & alcohol absorption ramp** (milestone 8), plus
  redose nudges and an overload ("diminishing returns") cue for caffeine.
- **One-click Windows installer** (Inno Setup) and a **portable build**, both
  produced by a GitHub Actions workflow.
- **Documentation**: README covering the science, math, constants, sources and
  scope limits, plus a Hebrew usage guide (`README.he.md`).

[Unreleased]: https://github.com/eitanav/coffe-thing/compare/v1.6.0...HEAD
[1.6.0]: https://github.com/eitanav/coffe-thing/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/eitanav/coffe-thing/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/eitanav/coffe-thing/compare/v1.3.3...v1.4.0
[1.3.3]: https://github.com/eitanav/coffe-thing/compare/v1.3.2...v1.3.3
[1.3.2]: https://github.com/eitanav/coffe-thing/compare/v1.3.1...v1.3.2
[1.3.1]: https://github.com/eitanav/coffe-thing/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/eitanav/coffe-thing/compare/v1.2.2...v1.3.0
[1.2.2]: https://github.com/eitanav/coffe-thing/compare/v1.2.0...v1.2.2
[1.2.0]: https://github.com/eitanav/coffe-thing/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/eitanav/coffe-thing/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/eitanav/coffe-thing/releases/tag/v1.0.0
