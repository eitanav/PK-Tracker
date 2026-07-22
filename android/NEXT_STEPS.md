# Android App — Next Steps

The native Android port of PK Tracker is **code-complete** on branch `android-app` (commit 7fc2bb9).
All 20 engine unit tests pass locally and on CI. The app builds successfully.

## Immediate

- **Merge `android-app` → `main`** — CI will auto-build the APK and publish it to GitHub Releases as `android-v1.0.0`

## Testing (not yet done)

- [ ] **Device/emulator testing**
  - Install APK on real Android device (API 26+) or emulator
  - Test golden path: log dose, read chart, change settings, export CSV
  - Verify Hebrew UI (RTL text, string coverage)
  - Check chart interaction (drag, tap readout)
  - Verify dark/light theme switch
  - Test language switching (English ↔ Hebrew) and persistence across restart
  - Confirm all dose history operations (delete, undo-last)
  - Verify sleep cutoff, perfect timing, alcohol predictions with sample doses

- [ ] **Edge cases**
  - Log doses across midnight (daily total should reset)
  - Very old doses (should not appear on timeline, but count in history)
  - Scroll/zoom performance with large dose histories (50+ doses)
  - Rotation (screen orientation change) — state should persist

## Polish

- [ ] **Performance**
  - Profile memory usage (Room queries, StateFlows, Canvas redraws)
  - Optimize if needed (queries, coroutine batching, frame drops)

- [ ] **Accessibility (a11y)**
  - Add `contentDescription` to all icon buttons and images
  - Test with TalkBack on emulator
  - Verify touch target sizes meet Material 3 spec (48 dp min)

- [ ] **Typography & spacing**
  - Verify text sizes match Material 3 guidelines
  - Check line-height and letter-spacing for readability

## Distribution (future)

- [ ] **Google Play Store**
  - Create signing key (not in repo)
  - Build release APK
  - Set up Play Console project
  - Write app description, screenshots in English + Hebrew
  - Submit for review

- [ ] **Additional locales** (if desired)
  - Add more strings.xml files (e.g. `values-fr`, `values-es`)
  - Ensure RTL scripts (Arabic, Farsi) work if added

## Known Scope Limits

- **UI only tested on 1 device emulator during development** — real-world testing will reveal platform quirks
- **Tablet layout** — currently phone-optimized; tablet might benefit from side-by-side panes
- **Accessibility** — basic Material 3 compliance; deeper a11y audit needed
- **Backup/sync** — data is local-only by design (no cloud)
- **Widget** — not yet implemented (desktop app has floating widget; Android widget framework separate)

## Architecture Notes

- `:engine` module is **Android-independent** — all math is unit-tested on JVM
- `:app` module owns UI, database (Room), and settings (DataStore)
- StateFlow pattern keeps UI reactive to data changes
- Canvas chart uses interpolation for precise touch readout

## Files to Watch

- `android/app/build.gradle.kts` — dependency versions
- `android/app/src/main/kotlin/com/pktracker/android/AppViewModel.kt` — state computation
- `android/app/src/main/kotlin/com/pktracker/android/ui/screens/Dashboard.kt` — main UI
- `android/app/src/main/kotlin/com/pktracker/android/ui/TimelineChart.kt` — interactive chart
- `android/app/src/main/res/values/strings.xml` + `values-iw/strings.xml` — i18n
- `.github/workflows/build-android.yml` — CI config

## Metrics

- **Engine:** 20 passing tests, ~800 lines of math
- **App:** ~2500 lines of Compose UI + ViewModel
- **Build time:** ~90s on CI (first time) or ~30s incremental
- **APK size:** ~8 MB (unoptimized debug build)
- **Min SDK:** 26 (Android 8.0), Target: 35 (Android 15)

---

**Branches:**
- `main` — stable desktop releases + this Android app (once merged)
- `android-app` — ready to merge (all tests passing, builds successful)
- `claude/epic-gates-aEct2` — ongoing feature work (if any)

**To merge and release:**
```bash
git checkout main
git pull origin main
git merge android-app
git push origin main
# CI will build and publish APK to Releases/android-v1.0.0
```
