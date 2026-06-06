# Changelog

All notable changes to **PK Tracker** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project aims to follow [Semantic Versioning](https://semver.org/).

> **Note on releases.** Windows binaries are currently published to a single
> rolling GitHub release tagged `v1.0.0` (the "latest" download channel), while
> the *app* version below tracks the real feature history. Aligning the two —
> one GitHub release per version — is tracked in [`TODO.md`](TODO.md).

## [Unreleased]

Nothing yet — see [`TODO.md`](TODO.md) for the roadmap.

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

[Unreleased]: https://github.com/eitanav/coffe-thing/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/eitanav/coffe-thing/releases/tag/v1.0.0
