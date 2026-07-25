# PK Tracker — Android · מסמך המשך עבודה (HANDOFF)

> המסמך הזה הוא **מקור האמת** למצב הפרויקט. פותחים אותו כדי להבין מיד איפה
> הכול עומד ואיך ממשיכים — מכל מכשיר, מכל צ'אט.
>
> קבצים נלווים: [`CHANGELOG.md`](CHANGELOG.md) (מה השתנה בכל גרסה) ·
> [`TODO.md`](TODO.md) (מה צריך/כדאי לעשות).

עדכון אחרון: **2026-07-25 · אנדרואיד 2.5.0 · דסקטופ 2.0.0**

---

## 1. מה זה הפרויקט

אפליקציה שעוקבת אחרי השפעת חומרים בגוף (קפאין, ממריצי מרשם, אלכוהול) לפי
מודלים פרמקוקינטיים. יש גרסת מחשב (Windows/Python) וגרסת **אנדרואיד נייטיבית
מלאה** (Kotlin + Jetpack Compose) שהיא המוקד הנוכחי.

- **ריפו:** https://github.com/eitanav/PK-Tracker (הענף `main`)
- **הורדות (APK):** https://github.com/eitanav/PK-Tracker/releases — כל
  דחיפה ל-`main` תחת `android/` בונה APK ומפרסמת Release בתג `android-vX.Y.Z`.
- **בתוך האפליקציה:** הגדרות → אודות → כפתור "הורדת הגרסה האחרונה" + צ'יינג'לוג.

## 2. מצב נוכחי (הכי חשוב)

- ✅ **האפליקציה עובדת ומותקנת** (הגרסה הראשונה שרצה בפועל הייתה 1.0.2 — לפני
  כן היה באג theme שהקריס בהפעלה).
- ✅ **אנדרואיד 2.5.0 מפורסם** ב-`main`: עיצוב פרימיום (ערכת צבע פר-חומר, גייג',
  מסך Insights, לוגו-עקומה, אנימציות), חתך שינה לממריצים, **תזכורות חכמות**,
  **ווידג'ט למסך הבית**, **סנכרון ענן**, ו**התחברות עם Google**.
  כולל `debug.keystore` קבוע כך שה-SHA-1 יציב בכל build.
- ✅ **דסקטופ 2.0.0** (על ענף הפיתוח): אותה שפת עיצוב כמו האנדרואיד
  (ערכת צבע פר-חומר, גייג' ראשי, Insights, לוגו), **וסנכרון מול אותו יומן**.
- ⏳ **צעד ידני אחד פתוח:** ליצור **OAuth client מסוג Desktop** ב-Google Cloud
  Console ולמלא `~/.pk_tracker/firebase.json`, אחרת הסנכרון במחשב לא יעבוד.
  ראה [`docs/SYNC.md`](../docs/SYNC.md).
- ⚠️ **אימות:** אני (Claude) לא יכול להריץ את האפליקציה — כל שינוי UI מאומת רק
  **קומפילציה** דרך ה-CI. בדיקת ריצה בפועל היא עליך, על המכשיר.

## 3. מפת ארכיטקטורה (איפה מה)

```
android/
  engine/                        מתמטיקה טהורה (JVM, 20 בדיקות, אין תלות אנדרואיד)
    Engine.kt                    SubstanceTimeline — חישוב ריכוז/אפקט מיומן מנות
    Scheduler.kt                 חתך שינה, מנה חוזרת, תזמון, אלכוהול, overload
    Models.kt / Substance.kt / Substances.kt   מודלים + ספריית החומרים
  app/                           ה-UI וה-state (Compose)
    AppViewModel.kt              כל חישוב ה-state של הדשבורד + InsightsState
    data/AppData.kt              Room (יומן מנות, v2 עם uid+מחיקה רכה) + DataStore (הגדרות)
    MainActivity.kt              Scaffold, ניווט (Now/Insights/Settings), topBar+לוגו, LocalAccent, תזמון תזכורות
    ui/
      Brand.kt                   LocalAccent (ערכת צבע פר-חומר) + PkLogo (עקומת PK)
      Gauge.kt                   הגייג' המעגלי
      Common.kt                  SectionCard, EntranceItem (אנימציית כניסה), עזרי פורמט
      TimelineChart.kt           הגרף האינטראקטיבי (Canvas): צירים, גרירה/גלילה
      screens/Dashboard.kt       מסך "עכשיו" — גייג', אריחים, גרף, רישום, שינה, תזמון
      screens/Insights.kt        מסך "תובנות" — שעות שיא, מקצב שבועי, ממוצעים, אחרונות
      screens/Settings.kt        הגדרות (כולל מתג תזכורות, חלון גרף, ייצוא CSV, אודות)
    notify/
      Reminders.kt               לוגיקת התזכורות החכמות + ערוץ + תזמון WorkManager
      ReminderWorker.kt          ה-worker התקופתי
    res/values/strings.xml       מחרוזות אנגלית
    res/values-iw/strings.xml    מחרוזות עברית (RTL) — חייב parity מלא מול אנגלית
  .github/workflows/build-android.yml   CI: בדיקות מנוע → assembleDebug → פרסום Release (main בלבד)
```

## 4. מה כבר נעשה (תמצית פיצ'רים)

- מסך **Now**: בורר חומרים, **גייג' ראשי** (מונפש) + אריחי סטטיסטיקה, **גרף**
  אינטראקטיבי עם צירים וגלילה עבר/עתיד + הגדרת חלון-זמן, רישום מנות עם presets,
  כרטיס **חתך שינה** (לקפאין **ולממריצים**), תזמון מושלם, סימולציית מנה.
- מסך **Insights**: שעות שיא, מקצב שבועי, ממוצעים (ליום/שבוע, כוס ראשונה, רצף),
  רשימת מנות אחרונות (מחיקה/ביטול).
- מסך **Settings**: ערכת נושא, שפה (עברית/אנגלית RTL), משקל/מין, זמן מחצית-חיים,
  סבילות, חתך שינה, חלון גרף, **תזכורות חכמות**, ייצוא CSV, אודות+צ'יינג'לוג.
- **ערכת צבע פר-חומר** בכל הממשק, **לוגו** = עקומת ה-PK, **אנימציות** כניסה.
- **תזכורות חכמות** (בהצטרפות): "קפה אחרון לפני חתך השינה", "מנה חוזרת כשהפוקוס צונח".
- **תשתית סנכרון מקומית**: uid גלובלי לכל מנה + מחיקה רכה (Room v2).

## 5. איך ממשיכים / פקודות

```bash
# בדיקות המנוע (המודול היחיד שמתקמפל בלי Android SDK)
cd android && gradle -c settings.local.gradle.kts :engine:test

# בנייה מקומית של APK (צריך Android SDK — לא זמין בסביבת ה-CI-agent)
cd android && ./gradlew :app:assembleDebug
```

**זרימת עבודה בגיט:** מפתחים על הענף `claude/pk-tracker-android-psrur6`,
עושים fast-forward ל-`main`, דוחפים — וה-CI בונה ומפרסם Release. כל גרסה
מעלה `versionCode`+`versionName` ב-`app/build.gradle.kts` + שורה ב-`CHANGELOG.md`
+ מחרוזת `changelog_X_Y_Z` בשתי השפות (מוצגת בהגדרות→אודות).

**כלל ברזל:** כל מפתח שמוסיף מחרוזת חייב להוסיף אותה **בשתי** השפות
(`values` + `values-iw`) — אחרת parity נשבר.

## 6. מגבלות ידועות / דברים לזכור

- אימות ריצה בפועל תלוי בך (אין הרצת אמולטור בצד שלי).
- ה-CI רץ רק על `main`/`android-app` — לא על ענף הפיתוח.
- `google-services.json` (של Firebase) **לא** בריפו — יוזרק דרך GitHub Secret
  (`GOOGLE_SERVICES_JSON`) ב-CI (הריפו ציבורי). פרויקט Firebase: `pk-tracker-2f600`.
- build הוא **debug** (לא Play Store) — ראה `TODO.md` להפצה עתידית.
- **SHA-1 של ה-debug keystore הקבוע:**
  `FD:27:0B:DC:89:0E:C4:0E:70:22:C9:80:5A:68:AC:B6:DF:9B:59:73`
  (וגם SHA-256: `51:AF:B7:FA:A7:D6:26:9B:AE:06:82:2E:8A:98:69:81:5F:DA:47:2F:EC:04:93:0E:91:0D:28:FF:49:8B:20:B6`).
  הקובץ עצמו: `android/app/debug.keystore` (סיסמאות: `android`/`android`,
  alias `androiddebugkey`). זה **לא סוד** — keystore של debug בלבד.

## 7. סנכרון בין הטלפון למחשב

שתי האפליקציות מדברות עם **אותו** פרויקט Firebase, ומזדהות מול **אותו חשבון
גוגל** — ולכן מקבלות אותו `uid` ומתכנסות לאותו יומן.

| | אנדרואיד | דסקטופ |
|---|---|---|
| הזדהות | Google Sign-In (SDK) | OAuth בדפדפן (loopback + PKCE) → `signInWithIdp` |
| גישה ל-Firestore | Firebase SDK | REST (`urllib`, בלי תלויות) |
| הפעלה | הגדרות → סנכרון ענן | הגדרות → Cloud sync, או `python -m pk_tracker.sync.cli` |

מודל הנתונים משותף: `users/{uid}/doses/{doseUid}` עם השדות
`substanceId, amount, unit, takenAtEpochMs, note, deleted, updatedAt`.
מיזוג last-write-wins לפי `updatedAt`, מחיקות רכות (tombstones).

⚠️ **שים לב:** הדסקטופ שומר זמנים כ-ISO 8601 והחוט משתמש ב-**אפוק מילישניות** —
ההמרה נמצאת ב-`pk_tracker/sync/cloudsync.py`. אם משנים את מבנה המסמך, צריך לשנות
את **שתי** האפליקציות יחד, אחרת כל אחת תקרא את השורות של השנייה כריקות.

**ההגדרה החד-פעמית (כולל יצירת OAuth client מסוג Desktop) מתועדת במלואה
ב-[`docs/SYNC.md`](../docs/SYNC.md), כולל טבלת פתרון תקלות.**

---

**הערה רפואית:** כל ההערכות מבוססות על מודלים ממוצעים — **לא ייעוץ רפואי**.
אף פעם אל תשתמש בנתוני אלכוהול כדי להחליט אם לנהוג.
