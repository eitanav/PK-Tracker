# PK Tracker — Roadmap & Ideas

A living backlog of ways to improve the app: new features, fixes to the current
behaviour, science upgrades, distribution, and quality. Roughly ordered within
each section by value-to-effort. Nothing here is committed — it's a menu.

Shipped items move to [`CHANGELOG.md`](CHANGELOG.md).

> A few ideas below (optional cloud sync, auto-update) would **revisit the
> README's current "local-only / no network calls" non-goals**. They're listed as
> options to consider, not commitments — keeping them opt-in and off by default
> would preserve the privacy stance.

Legend: 🔥 high impact · 🧪 needs validation/research · 🩹 fixes current behaviour
· 🌱 nice-to-have

---

## Sleep & timing (active redesign)

1. 🔥🩹 **Rework the sleep-cutoff control.** Replace "Target by bed = X % of peak"
   (unintuitive — % of a single dose's peak, and caffeine's ~5 h half-life makes
   even 15 % fall ~13 h before bed) with one of: *(a)* caffeine left at bedtime in
   **mg**, *(b)* a **sensitivity preset** (sensitive / average / resistant), or
   *(c)* a flat **hours-before-bed** cutoff. Decision pending.
2. 🔥 **"Latest coffee: HH:MM" headline.** Whatever the model, show the answer as
   one obvious time plus a plain-English reason ("a coffee after 14:30 would still
   leave >50 mg in you at 23:00").
3. 🧪 **Learned personal curfew.** Each morning log sleep quality (1–5); correlate
   with the prior day's caffeine timing/amount and surface *your* real cutoff.
4. 🌱 **Per-day bedtimes** (weekday vs weekend), optionally auto-detected.
5. 🌱 **Wind-down notification** a chosen interval before the cutoff time.
6. 🌱 Optional hook into OS **bedtime / focus modes** to set bedtime automatically.

## Science & model accuracy

7. 🔥🧪 **Personal caffeine half-life.** Let users set or estimate it — smoking
   (~3–4 h), oral contraceptives/pregnancy (~10–15 h), and CYP1A2 genotype move it
   a lot. Today everyone shares the population average.
8. 🧪 **Tolerance / habituation over weeks.** Chronic intake shifts the effect
   curve (EC50); model a slow-moving tolerance term from recent history.
9. 🧪 **Confidence bands** on the curves instead of a single false-precise line.
10. 🧪 **Food / fed-state absorption.** Taking caffeine with a meal slows Tmax;
    expose a "with food" toggle per dose.
11. 🌱 **Richer source library.** Chocolate, soda, pre-workout, energy gels, green
    vs black tea, decaf residuals — with accurate mg presets.
12. 🌱 **More substances:** L-theanine (caffeine synergy/jitter reduction),
    nicotine, melatonin, theobromine.
13. 🩹🧪 **Validate the alcohol Widmark params** (sex/food/first-pass) and add a
    standard-drinks helper and drink-type presets.

## Logging & data

14. 🔥 **Undo last action** (dose add/edit/delete).
15. 🔥 **Backup / export / import** (CSV + JSON) so data survives reinstalls and
    moves between machines.
16. 🩹 **Faster predating.** A quick "had it N min/hours ago" stepper and a
    calendar/time picker for back-logging.
17. 🌱 **Tags on doses** (work / gym / social) and history search/filter.
18. 🌱 **Daily & weekly summaries:** total mg, peak, time over the daily ceiling,
    curfew adherence.
19. 🌱 **Gentle insights & streaks** ("under 400 mg five days running").
20. 🌱🧪 **Optional encrypted cloud sync** across devices (off by default).

## Widget & UX

21. 🔥 **Resizable widget** + compact/expanded presets.
22. 🔥 **"Latest coffee" countdown** on the widget face.
23. 🩹 **Edge/corner snapping** when dragging; remember per-monitor position.
24. 🌱 **Opacity slider** and an idle click-through mode.
25. 🌱 **Right-click context menu** on the widget (quick-log a preset, hide,
    settings) and a **global hotkey** to log a dose without opening the app.
26. 🌱 **Tray readout:** current mg in a tooltip / small badge on the tray icon.
27. 🌱 **Multiple substances on the widget** at once (caffeine + alcohol).
28. 🩹 **Pin-to-desktop robustness on Windows** (verify stays-on-bottom across
    multi-monitor and virtual desktops; fall back gracefully).

## Calibration & personalization

29. 🔥 **Onboarding wizard:** body mass, typical bedtime, sensitivity, usual
    drinks — so the first session is already personalized.
30. 🧪 **Calibrate from feel:** log subjective alertness over a few hours and fit
    personal EC50 / half-life to it.
31. 🌱 **Multiple profiles** on one machine.

## Notifications & reminders

32. 🔥 **Redose nudge notification** when effect drops below the chosen threshold
    ("good time for a top-up") — opt-in, with quiet hours.
33. 🌱 **Daily-ceiling / overload nudge** when body burden passes the soft limit.
34. 🌱 **Hydration reminders** tied to caffeine intake.

## Platform & distribution

35. 🔥 **macOS & Linux builds** (PySide6 already cross-platform; add packaging
    targets and CI runners).
36. 🔥🩹 **Code-sign the Windows installer** (kills the SmartScreen "unknown
    publisher" warning) and notarize the future macOS build.
37. 🔥 **Auto-update**: check the latest release and offer a one-click update.
38. 🩹 **Smaller / faster binary**: evaluate one-dir vs one-file and prune unused
    Qt plugins to cut the ~100 MB download.
39. 🩹 **Align release tags with the app version** (drive the workflow's `version`
    from `MyAppVersion`; one GitHub release per version instead of a rolling
    `v1.0.0`).

## Quality, trust & docs

40. 🔥 **UI/integration tests** (pytest-qt) for widget, settings, plots, tray.
41. 🩹 **Lint + type-check in CI** (ruff/black, mypy) alongside the existing tests.
42. 🌱 **In-app "How the math works"** panel: formulas, constants, and source
    links, with the always-on "not medical advice" framing.
43. 🌱 **Full Hebrew (RTL) UI**, not just the README; a localization framework.
44. 🌱 **Accessibility pass:** keyboard navigation, screen-reader labels, high-
    contrast theme, larger-text mode.
45. 🌱 **Privacy statement in-app**: reaffirm local-only, no telemetry, where data
    lives (`~/.pk_tracker`).
