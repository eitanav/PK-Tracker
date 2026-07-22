# מסמך המשך עבודה — אפליקציית PK Tracker לאנדרואיד

> העתק את הקובץ הזה (או הפנה אליו) בצ'אט חדש כדי להמשיך מאותה נקודה.

## מה זה הפרויקט

אפליקציה שעוקבת אחרי השפעת חומרים בגוף (קפאין, אלכוהול, תרופות ממריצות)
לפי מודלים פרמקוקינטיים. יש גרסת מחשב (Windows, Python) שכבר עובדת, ובנינו
**פורט נייטיבי מלא לאנדרואיד** ב-Kotlin + Jetpack Compose.

## מצב נוכחי (עדכני ל-22.7.2026)

- ✅ האפליקציה **הושלמה מבחינת קוד** ומוזגה ל-`main`
- ✅ כל 20 בדיקות המנוע (unit tests) עוברות
- ✅ ה-build עובר ב-CI
- 🔄 ה-CI מריץ עכשיו build אחרי המיזוג ל-main — כשיסיים, יפרסם APK ל-Releases
  בתג `android-v1.0.0`
- **הריפו זז ל:** https://github.com/eitanav/PK-Tracker (הכתובת הישנה
  `coffe-thing` עדיין ממופה אליו)

## מבנה הפרויקט

```
android/
  engine/   מתמטיקה טהורה ב-Kotlin (פורט מדויק של pk_tracker/core) + JUnit
            אין תלות באנדרואיד — נבדק על JVM לבד
  app/      ממשק Jetpack Compose, Room (יומן מנות), DataStore (הגדרות)
```

קבצים מרכזיים:
- `android/app/.../AppViewModel.kt` — כל חישוב ה-state של הדשבורד
- `android/app/.../ui/screens/Dashboard.kt` — המסך הראשי
- `android/app/.../ui/TimelineChart.kt` — הגרף האינטראקטיבי (Canvas)
- `android/app/.../ui/screens/Settings.kt` — הגדרות
- `android/app/.../ui/screens/History.kt` — היסטוריית מנות
- `android/app/src/main/res/values/strings.xml` — מחרוזות אנגלית
- `android/app/src/main/res/values-iw/strings.xml` — מחרוזות עברית (RTL)
- `.github/workflows/build-android.yml` — ה-CI שבונה ומפרסם APK

## מה נשאר לעשות (לפי סדר עדיפות)

### 1. לוודא שה-Release פורסם בהצלחה
- בדוק ש-CI build האחרון על main הסתיים בירוק
- בדוק שה-APK הופיע ב-Releases תחת התג `android-v1.0.0`
- הורד אותו והתקן על טלפון/אמולטור

### 2. בדיקות על מכשיר אמיתי (עוד לא בוצע!)
זה החלק הכי חשוב שנשאר — הקוד נכתב אבל **לא הורץ על מכשיר**:
- מסלול זהב: רשום מנה → קרא את הגרף → שנה הגדרות → ייצא CSV
- ממשק עברית (RTL, כיסוי מחרוזות מלא)
- אינטראקציה עם הגרף (גרירת אצבע, קריאת ערך בנקודה)
- החלפת ערכת נושא (כהה/בהיר)
- החלפת שפה (אנגלית ↔ עברית) ושמירתה אחרי הפעלה מחדש
- מחיקת מנה + ביטול מנה אחרונה
- חתך שינה, תזמון מושלם, תחזיות אלכוהול עם מנות לדוגמה
- מקרי קצה: מנות סביב חצות (איפוס סך יומי), סיבוב מסך, היסטוריה גדולה (50+)

### 3. ליטוש
- ביצועים (פרופיילינג של Room, StateFlows, ציור Canvas)
- נגישות (a11y): `contentDescription` לכל האייקונים, בדיקת TalkBack,
  יעדי מגע במינימום 48dp

### 4. הפצה (עתידי)
- Google Play: מפתח חתימה, build של release, Play Console, תיאור + צילומי מסך
- שפות נוספות אם רוצים

## איך להמשיך בצ'אט חדש

1. פתח את הפרויקט (branch `main` הכי עדכני)
2. ספר ל-Claude: "אני ממשיך עבודה על אפליקציית האנדרואיד של PK Tracker.
   קרא את `android/HANDOFF.md` ו-`android/NEXT_STEPS.md` כדי להבין את המצב."
3. תגיד לו מה אתה רוצה לעשות עכשיו (למשל: "בוא נריץ את האפליקציה על אמולטור
   ונתקן באגים שנמצא", או "בוא נעבור על הנגישות")

## פקודות שימושיות

```bash
# להריץ את בדיקות המנוע (בלי Android SDK)
cd android && gradle -c settings.local.gradle.kts :engine:test

# לבנות APK להתקנה (צריך Android SDK)
cd android && ./gradlew :app:assembleDebug
# -> app/build/outputs/apk/debug/app-debug.apk
```

## מפרט טכני
- Kotlin 2.0, Jetpack Compose (Material 3), Room, DataStore, Coroutines
- minSdk 26 (Android 8.0), targetSdk 35 (Android 15)
- ערכת נושא כהה תואמת לגרסת המחשב (ענבר #d6a04a, כחול #4aa3ff)

---
**הערה חשובה:** כל ההערכות מבוססות על מודלים פרמקוקינטיים ממוצעים —
**לא ייעוץ רפואי.** אף פעם אל תשתמש בנתוני אלכוהול כדי להחליט אם לנהוג.
