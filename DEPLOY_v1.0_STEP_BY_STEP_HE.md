# פריסת v1.0 — שלב אחר שלב

המדריך מיועד למערכת שכבר פועלת ב־Render וב־Supabase. הפעולות מוסיפות טבלאות ושדות; הן אינן מוחקות את Q1–Q3 או את הקבצים הקיימים.

## 1. גיבוי לפני השדרוג

1. פתחו את האפליקציה הקיימת.
2. עברו אל **הגדרות → גיבוי ושחזור**.
3. לחצו **הורדת גיבוי מלא** ושמרו את קובץ ה־ZIP מחוץ לתיקיית GitHub.
4. אל תמשיכו לפני שהקובץ ירד.

## 2. עדכון Supabase

1. היכנסו לפרויקט Supabase של האפליקציה.
2. פתחו **SQL Editor → New query**.
3. ב־GitHub פתחו את הקובץ `supabase/migration_v1.0.sql`.
4. העתיקו את כל תוכנו ל־SQL Editor.
5. לחצו **Run**.
6. אם Supabase מציג אזהרה על RLS, בחרו **Run without RLS**. הסיבה: הסקריפט עצמו מפעיל RLS, שולל גישה מ־`anon` ומ־`authenticated`, ומעניק גישה רק ל־`service_role`.
7. המתינו להודעת הצלחה.

אין להריץ `schema.sql` על פרויקט קיים; הוא מיועד להתקנה חדשה. אין למחוק טבלאות ישנות.

## 3. העלאת v1.0 ל־GitHub

1. חלצו את ZIP v1.0.
2. פתחו את המאגר שמחובר ל־Render.
3. העלו את כל תוכן התיקייה המחולצת לשורש המאגר.
4. כאשר GitHub שואל על קבצים בעלי אותו שם, אשרו את החלפתם בגרסה החדשה.
5. קבצים ישנים שאין להם גרסה חדשה יכולים להישאר, אך הם לא יופעלו.
6. ודאו שבשורש מופיעים:

```text
main.py
rulebook.py
analytics.py
agent_service.py
render.yaml
requirements.txt
static/
supabase/
tests/
```

7. Commit message מומלץ:

```text
Release v1.0 AI Decision OS
```

אין להעלות `.env`, מפתח OpenAI, מפתח Supabase, סיסמאות, דוחות אמיתיים או קובצי גיבוי.

## 4. משתני הסביבה ב־Render

פתחו את שירות ה־Web ב־Render ובחרו **Environment**. ודאו את הערכים הבאים:

| Key | Value |
|---|---|
| `INTOPIA_BACKEND` | `supabase` |
| `APP_ENV` | `production` |
| `SUPABASE_URL` | Project URL של Supabase |
| `SUPABASE_SECRET_KEY` | Secret key / service role של השרת |
| `SUPABASE_BUCKET` | `intopia-files` |
| `APP_REQUIRE_AUTH` | `true` |
| `APP_ACCESS_USER` | שם המשתמש המשותף |
| `APP_ACCESS_PASSWORD` | סיסמת צוות חזקה |
| `OPENAI_AGENT_ENABLED` | `true` |
| `OPENAI_API_KEY` | מפתח API של פרויקט OpenAI |
| `OPENAI_MODEL` | `gpt-5.6-sol` |
| `OPENAI_MAX_OUTPUT_TOKENS` | `2400` |

`SUPABASE_SECRET_KEY`, `APP_ACCESS_PASSWORD` ו־`OPENAI_API_KEY` הם סודות. מזינים אותם רק ב־Render. אין להדביק אותם בקוד, ב־GitHub, בצילום מסך או בצ׳אט.

## 5. פריסה

1. ב־Render לחצו **Manual Deploy → Deploy latest commit**.
2. המתינו לסטטוס **Live**.
3. פתחו את כתובת השירות.
4. בפתיחה הראשונה במסלול Free ייתכן עיכוב של כדקה.

## 6. בדיקות לאחר הפריסה

פתחו בדפדפן:

```text
https://YOUR-SERVICE.onrender.com/api/health
```

התגובה צריכה לכלול:

```json
{"status":"ok","version":"1.0.0-ai-decision-os","backend":"supabase","database":"ok","storage":"ok"}
```

לאחר מכן פתחו:

```text
https://YOUR-SERVICE.onrender.com/api/rulebook
```

ודאו שמופיעים `summary.version = 1.0.0` ולפחות 50 חוקים.

באפליקציה:

1. פתחו **הגדרות → מרכז החוקים**.
2. חפשו “מפעל”.
3. בדקו פעולה `A2-4` עם `Y7` ו־`X0`; היא צריכה להיחסם.
4. פתחו **צ׳אט AI** וודאו שהסטטוס פעיל.
5. הריצו תרחיש קטן ונסו ליצור חבילת החלטות.
6. הורידו גיבוי חדש.

## 7. בדיקת שמירת מצב

1. צרו החלטת טיוטה.
2. העלו קובץ בדיקה קטן.
3. בצעו Deploy נוסף של אותו commit.
4. ודאו שהטיוטה והקובץ נשארו.

אם הנתונים נשארו, PostgreSQL ו־Storage משמשים נכון כמקור האמת ולא הדיסק הזמני של Render.

## פתרון תקלות

- `relation does not exist` — `migration_v1.0.sql` לא הורץ בפרויקט Supabase הנכון.
- Agent disabled — ודאו `OPENAI_AGENT_ENABLED=true`, שמרו ובצעו Deploy.
- Agent missing key — הזינו `OPENAI_API_KEY` ב־Render בלבד.
- Rulebook ריק — בדקו Logs; לרוב טבלאות v1.0 לא נוצרו או שמפתח Supabase אינו `service_role`.
- 503 לאחר Deploy — המתינו לסיום ההפעלה ובדקו Render Logs.
