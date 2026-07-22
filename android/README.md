# PK Tracker for Android

A native Android port of [PK Tracker](../README.md) — the same substance
pharmacokinetics tracker, rebuilt in **Kotlin + Jetpack Compose (Material 3)**
with the same dark visual style and feature set as the desktop app.

> 🌐 English · [עברית](#עברית) — the app ships full Hebrew with RTL.

<p>
  <img alt="dashboard" src="docs/dashboard.png" width="30%">
</p>

## ⬇️ Install

1. On your phone, open the latest **Android release** and download
   **`PKTracker-android.apk`**:
   **https://github.com/eitanav/PK-Tracker/releases** (look for the
   `android-v…` tag).
2. Open the downloaded APK. When Android asks, allow **installing unknown apps**
   from your browser/files app.
3. Tap **Install**. That's it — it's a self-contained app, no account, no
   network, all data stays on the device.

> This is a **debug build** (not a Play Store release), so Android shows the
> usual "unknown app" prompt. It's the same app the CI built from source.

## What's inside

- **Now** — substance selector (Caffeine, Alcohol, prescription stimulants),
  a live **blood-level + effect chart** (Canvas-drawn; drag your finger on it to
  read the exact time / level / effect at any point), the status readout (mg in
  the body, effect %, blood level, projected peak, today's total vs the 400 mg
  guideline), one-tap **dose logging** with presets and a "minutes ago" stepper,
  the **sleep cutoff** ("latest caffeine") card, the **🎯 perfect-timing** coach,
  and a **dose simulation** toggle (preview a hypothetical future coffee).
- **History** — every logged dose, with delete and undo-last.
- **Settings** — light/dark/system theme, **language (System / English / עברית)**
  with proper RTL, body mass & sex, **personal caffeine half-life**, tolerance,
  the sleep-cutoff method (mg / sensitivity preset / hours-before-bed), and a
  **CSV export**.

Estimates come from population-average pharmacokinetic models. **Not medical
advice.** Never use the alcohol figures to decide whether to drive.

## Project layout

```
android/
  engine/   pure-Kotlin PK/PD math (a faithful port of pk_tracker/core) + JUnit
  app/      Jetpack Compose UI, Room (dose log), DataStore (settings)
```

The `:engine` module has **no Android dependencies**, so its maths is unit-tested
on the JVM independently of the UI.

## Build from source

Requires JDK 17+. From this `android/` directory:

```bash
# run the engine tests (no Android SDK needed)
gradle -c settings.local.gradle.kts :engine:test

# build an installable debug APK (needs the Android SDK)
./gradlew :app:assembleDebug
# -> app/build/outputs/apk/debug/app-debug.apk
```

CI (`.github/workflows/build-android.yml`) does both on every push and publishes
the APK to a GitHub release from `main`.

Stack: Kotlin 2.0, Jetpack Compose (Material 3), Room, DataStore, Coroutines.
`minSdk 26` (Android 8.0), `targetSdk 35`.

---

## עברית

**PK Tracker לאנדרואיד** — אותה אפליקציה שבנינו למחשב, בגרסה נייטיבית לאנדרואיד
(Kotlin + Jetpack Compose), עם אותו עיצוב כהה וכל הפיצ'רים: גרף חי של רמת החומר
בדם והאפקט (אפשר לגעת בגרף כדי לראות זמן/רמה/אחוז מדויקים), רישום מנות, חתך שינה,
תזמון מושלם, סימולציית מנה, סך יומי מול תקרת 400 מ״ג, היסטוריה, והגדרות מלאות
כולל **החלפת שפה (עברית/אנגלית) עם תמיכת RTL**, חצי-חיים אישי לקפאין, וייצוא CSV.

**התקנה:** נכנסים ל-Releases, מורידים את `PKTracker-android.apk`, פותחים אותו
ומאשרים התקנה ממקור לא ידוע. הכול מקומי במכשיר, בלי חשבון ובלי רשת.

**הערכות בלבד — לא ייעוץ רפואי.** אף פעם אל תשתמש בנתוני אלכוהול כדי להחליט אם לנהוג.
