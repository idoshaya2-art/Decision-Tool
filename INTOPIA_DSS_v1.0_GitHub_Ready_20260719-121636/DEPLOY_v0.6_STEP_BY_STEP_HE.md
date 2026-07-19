# פריסת v0.6 — צעד אחר צעד

## 1. לפני השדרוג

1. היכנסו לאפליקציה הקיימת והורידו **גיבוי מלא**.
2. שמרו את קובץ הגיבוי במחשב. אין למחוק טבלאות, bucket או נתונים ב־Supabase.

## 2. העלאת הקוד ל־GitHub

1. חלצו את `INTOPIA_DSS_v0.6_Cloud.zip`.
2. פתחו את המאגר הקיים ב־GitHub.
3. העלו את **כל התוכן שבתיקייה המחולצת** לשורש המאגר.
4. אשרו החלפה של קבצים בעלי אותו שם והוספה של קבצים חדשים.
5. ודאו ש־`main.py`, `requirements.txt`, `render.yaml`, `static/` ו־`supabase/` נמצאים ישירות בשורש המאגר.
6. אין להעלות `.env`, מפתחות API, גיבויים או דוחות Q1–Q3 אמיתיים.

## 3. עדכון Supabase

בשדרוג ממערכת v0.5 קיימת:

1. פתחו Supabase → SQL Editor → New query.
2. העתיקו את תוכן `supabase/migration_v0.6.sql`.
3. לחצו Run פעם אחת. המיגרציה מוסיפה עמודה בלבד ואינה מוחקת נתונים.

בהתקנה חדשה בלבד, הפעילו במקום זאת את `supabase/schema.sql` וודאו שקיים bucket פרטי בשם `intopia-files`.

## 4. משתני הסביבה ב־Render

פתחו Render → שירות האפליקציה → Environment. הזינו בעצמכם, ללא מרכאות:

| Key | Value |
|---|---|
| `INTOPIA_BACKEND` | `supabase` |
| `APP_ENV` | `production` |
| `SUPABASE_URL` | כתובת הפרויקט מ־Supabase |
| `SUPABASE_SECRET_KEY` | מפתח השרת הסודי / service role של Supabase |
| `SUPABASE_BUCKET` | `intopia-files` |
| `APP_REQUIRE_AUTH` | `true` |
| `APP_ACCESS_USER` | שם המשתמש הרצוי, למשל `intopia` |
| `APP_ACCESS_PASSWORD` | סיסמה חזקה שתבחרו |
| `MAX_UPLOAD_MB` | `10` |
| `MAX_RESTORE_MB` | `100` |
| `OPENAI_AGENT_ENABLED` | `true` |
| `OPENAI_API_KEY` | מפתח API פעיל מחשבון OpenAI API |
| `OPENAI_MODEL` | `gpt-5.6-terra` (המלצת איזון איכות/עלות; נדרש שיהיה זמין בחשבון) |
| `OPENAI_MAX_OUTPUT_TOKENS` | `1200` |

חשוב: מנוי ChatGPT אינו מחליף מפתח OpenAI API. אין להכניס אף מפתח לקוד או ל־GitHub.

## 5. Deploy ובדיקות

1. ב־Render לחצו Manual Deploy → Deploy latest commit.
2. המתינו ל־Live.
3. פתחו `https://YOUR-APP.onrender.com/api/health`.
4. ודאו שמופיעים `status: ok`, ‏`version: 0.6.0-intopia-exact`, ‏`database: ok` ו־`storage: ok`.
5. פתחו `https://YOUR-APP.onrender.com/api/agent/status`.
6. להפעלת הסוכן צריכים להופיע `ready: true` ו־`status: ready`. אם לא, השדה `missing` יציין בדיוק איזה משתנה חסר.

## 6. טעינת היסטוריית Q1–Q3

1. במסך העלאת דוחות השאירו את התקופה על **זיהוי רבעון אוטומטי**.
2. העלו את Q1, בדקו את תצוגת החילוץ ואשרו.
3. חזרו על הפעולה עבור Q2 ולאחר מכן Q3.
4. מחקרי השוק שבתוך חוברות התוצאות נקלטים אוטומטית; אין להעלות אותם שוב בנפרד.
5. לאחר אישור Q3, עברו לחדר ההחלטות ולמעבדת התרחישים לקראת Q4.

## 7. בדיקת persistence

1. שמרו רשומה והעלו קובץ קטן.
2. בצעו Deploy נוסף.
3. ודאו שהרשומה והקובץ נשארו.
4. הורידו גיבוי מלא לאחר קליטת Q1–Q3 ולפני סגירת כל רבעון.
