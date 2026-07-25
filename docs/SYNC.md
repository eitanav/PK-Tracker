# Cloud sync — setup (סנכרון ענן)

הדסקטופ והאנדרואיד מסנכרנים את יומן המנות דרך **אותו** פרויקט Firebase. שתי
האפליקציות מזדהות מול אותו חשבון גוגל, ולכן מקבלות אותו `uid` — וזה מה שגורם
לשני היומנים להתכנס לאותו מצב.

- **מודל הנתונים:** `users/{uid}/doses/{doseUid}` ב-Firestore.
- **מיזוג:** last-write-wins לפי `updatedAt`, עם מחיקות רכות (tombstones) כדי
  שמחיקה במכשיר אחד לא "תקום לתחייה" מהמכשיר השני.
- **פרטיות:** כל משתמש נוגע רק ב-`uid` שלו, נאכף בכללי האבטחה של Firestore.

> ⚠️ הקבצים עם המפתחות **לא** נמצאים בריפו (הוא ציבורי). הם יושבים אצלך
> מקומית תחת `~/.pk_tracker/`.

---

## הגדרה חד-פעמית

### 1. יצירת OAuth client מסוג Desktop

זה הצעד היחיד שדורש משהו חדש בקונסולה. אפליקציית מחשב לא יכולה להשתמש
ב-client של אנדרואיד, כי היא נכנסת דרך דפדפן וחוזרת ל-`127.0.0.1`.

1. היכנס ל-[Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials)
   וּבחר למעלה את **אותו פרויקט** של Firebase (`pk-tracker-2f600`).
2. **Create credentials → OAuth client ID**.
3. **Application type: Desktop app**. תן שם (למשל `PK Tracker Desktop`) → **Create**.
4. העתק את **Client ID** ואת **Client secret**.
   (אצל אפליקציות מותקנות ה-secret הזה אינו סוד אמיתי — הוא נשלח בתוך כל
   עותק מותקן. מה שבאמת מגן על הנתונים הם כללי Firestore.)

### 2. איתור ה-Web API key

ב-[Firebase Console](https://console.firebase.google.com) → ⚙️ **Project settings**
→ לשונית **General** → השדה **Web API Key**.
(אותו ערך מופיע גם ב-`google-services.json` תחת `client[0].api_key[0].current_key`.)

### 3. כתיבת קובץ ההגדרות

```bash
python -m pk_tracker.sync.cli setup
```

זה יוצר `~/.pk_tracker/firebase.json`. ערוך אותו:

```json
{
  "project_id": "pk-tracker-2f600",
  "api_key": "AIza...",
  "oauth_client_id": "1234567890-xxxx.apps.googleusercontent.com",
  "oauth_client_secret": "GOCSPX-..."
}
```

לחלופין אפשר במשתני סביבה: `PK_TRACKER_PROJECT_ID`, `PK_TRACKER_API_KEY`,
`PK_TRACKER_OAUTH_CLIENT_ID`, `PK_TRACKER_OAUTH_CLIENT_SECRET`.

### 4. התחברות וסנכרון

```bash
python -m pk_tracker.sync.cli login    # פותח דפדפן — התחבר עם אותו חשבון גוגל כמו בטלפון
python -m pk_tracker.sync.cli status   # מי מחובר, מתי היה סנכרון אחרון
python -m pk_tracker.sync.cli sync     # מיזוג מול הענן עכשיו
```

**חשוב:** התחבר עם **אותו חשבון גוגל** שאיתו התחברת באפליקציית האנדרואיד
(הגדרות → סנכרון ענן → Sign in with Google). חשבון אחר = `uid` אחר = יומן נפרד.

---

## איך זה עובד מתחת למכסה

1. **OAuth 2.0 לאפליקציות מותקנות** — נפתח שרת מקומי זמני על `127.0.0.1`,
   הדפדפן נשלח לגוגל, וההפניה חוזרת עם authorization code (עם PKCE).
2. הקוד מוחלף ב-**Google ID token** מול `oauth2.googleapis.com`.
3. ה-token מוחלף ב-**Firebase ID token** מול `identitytoolkit` (`signInWithIdp`) —
   וכאן מתקבל ה-`uid` הזהה לזה של הטלפון.
4. קריאה/כתיבה ל-Firestore ב-REST עם ה-token כ-Bearer.

הכל בספרייה הסטנדרטית של פייתון — בלי SDK ובלי תלויות נוספות.

**אחסון מקומי:**
- `~/.pk_tracker/firebase.json` — הגדרות הפרויקט.
- `~/.pk_tracker/auth.json` — ה-tokens (הרשאות `600`). `logout` מוחק אותו.

---

## פתרון תקלות

| תסמין | סיבה סבירה |
|---|---|
| `Firestore rejected the request (403)` | כללי האבטחה חוסמים, או שאתה מחובר לחשבון אחר מזה שבטלפון. |
| `signInWithIdp failed (400)` | ה-`api_key` שגוי, או ש-Google אינו מופעל כספק ב-Authentication. |
| `timed out waiting for the browser sign-in` | הדפדפן לא נפתח/נסגר לפני ההשלמה. הרץ `login` שוב. |
| מנות מסונכרנות אך חלקן "נעלמות" | מנה בענן מפנה לחומר שלא קיים במחשב — הסנכרון מדווח כמה דילג. הוסף את החומר ותסנכרן שוב. |
