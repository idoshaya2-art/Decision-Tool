# פריסה חינמית — Supabase + GitHub + Render

## א. Supabase

### מערכת v1.6 קיימת — השדרוג הנוכחי ל־v1.9

1. הורידו גיבוי מלא מהאפליקציה לפני השדרוג.
2. פתחו **SQL Editor → New query**.
3. העתיקו והריצו פעם אחת את `supabase/migration_v1.7_market_intelligence.sql`.
4. לאחר שהסתיים בהצלחה, העתיקו והריצו פעם אחת את `supabase/migration_v1.9_group_governance.sql`.
5. ודאו שנוצרו `market_intelligence_runs`, `decision_sessions` ו־`decision_votes`.
6. אין מיגרציה נפרדת ל־v1.8; האופטימיזציה משתמשת בטבלת `optimization_runs` הקיימת.
7. הסקריפטים מוסיפים טבלאות בלבד ואינם מוחקים Actuals, דוחות או קבצים.

### מערכת ישנה מ־v1.6

לאחר גיבוי, הריצו לפי הסדר ורק את המיגרציות שטרם הורצו:

```text
supabase/migration_v1.0.sql
supabase/migration_v1.4_learning.sql
supabase/migration_v1.5_evidence_gate.sql
supabase/migration_v1.6_digital_twin.sql
supabase/migration_v1.7_market_intelligence.sql
supabase/migration_v1.9_group_governance.sql
```

### מערכת חדשה

1. צרו פרויקט ב־Supabase ושמרו את סיסמת מסד הנתונים במקום בטוח.
2. פתחו **SQL Editor → New query**.
3. העתיקו את כל `supabase/schema.sql`, הדביקו ולחצו **Run**.
4. ודאו ב־Storage שקיים bucket פרטי בשם `intopia-files`.

### מערכת v0.4 קיימת

1. הורידו קודם גיבוי מלא מהאפליקציה.
2. הריצו רק את `supabase/migration_v0.5.sql`.
3. הסקריפט מוסיף טבלאות ושדות; הוא אינו מוחק נתוני חברה.

### מערכת v0.5 קיימת

1. הורידו גיבוי מלא מהאפליקציה.
2. הריצו פעם אחת את `supabase/migration_v0.6.sql` ב־SQL Editor.
3. הסקריפט מוסיף רק את `operations.fx_to_sf`; הוא אינו מוחק או מאפס נתונים.

### העתיקו שני פרטים

ב־Supabase פתחו **Project Settings → API Keys** או **Connect**:

- Project URL → ישמש כ־`SUPABASE_URL`.
- Secret key שמיועד לשרת, או `service_role` הישן → ישמש כ־`SUPABASE_SECRET_KEY`.

אל תשתמשו ב־anon/publishable key. אל תעלו את ה־Secret key ל־GitHub ואל תשלחו אותו לחברי הצוות.

## ב. GitHub

1. חלצו את חבילת ה־ZIP.
2. העלו את **כל מה שבתוך התיקייה**, לא את קובץ ה־ZIP ולא תיקיית מעטפת נוספת.
3. בשורש המאגר חייבים להופיע:

```text
main.py
analytics.py
agent_service.py
import_service.py
requirements.txt
render.yaml
static/
supabase/
tests/
```

4. אסור להעלות `.env`, מפתחות, דוחות אמיתיים, קובצי גיבוי או SQLite.

## ג. Render

### הדרך הקלה — Blueprint

1. היכנסו ל־Render וחברו את GitHub.
2. בחרו **New → Blueprint**.
3. בחרו את המאגר. Render יקרא את `render.yaml`.
4. הזינו כאשר תתבקשו:

| Key | ערך |
|---|---|
| `SUPABASE_URL` | Project URL שהעתקתם |
| `SUPABASE_SECRET_KEY` | Secret/service-role key של השרת |
| `APP_ACCESS_PASSWORD` | סיסמת צוות חדשה וחזקה |
| `OPENAI_API_KEY` | מפתח שרת של OpenAI API; לא מפתח Supabase ולא סיסמת ChatGPT |
| `OPENAI_MODEL` | שם מודל Responses API הזמין בפרויקט OpenAI שלכם |

5. אשרו Deploy.

### אם יוצרים Web Service ידנית

```text
Language: Python 3
Build Command: pip install -r requirements.txt
Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
Health Check Path: /api/health
Plan: Free
```

הגדירו גם:

```text
INTOPIA_BACKEND=supabase
APP_ENV=production
SUPABASE_BUCKET=intopia-files
APP_REQUIRE_AUTH=true
APP_ACCESS_USER=intopia
MAX_UPLOAD_MB=10
MAX_RESTORE_MB=100
OPENAI_AGENT_ENABLED=true
OPENAI_MAX_OUTPUT_TOKENS=2400
```

## ד. בדיקה

1. פתחו `https://YOUR-SERVICE.onrender.com/api/health`.
2. התוצאה התקינה כוללת:

```json
{
  "status": "ok",
  "backend": "supabase",
  "database": "ok",
  "storage": "ok"
}
```

3. פתחו את הלינק הרגיל. שם המשתמש הוא `intopia` וסיסמת הצוות היא `APP_ACCESS_PASSWORD`.
4. שמרו הגדרה, העלו קובץ קטן, סגרו ופתחו שוב.
5. ב־Render בצעו **Manual Deploy → Deploy latest commit**. ודאו שהנתון והקובץ נשארו.
6. ודאו ב־Supabase שהרשומה קיימת ב־Table Editor והקובץ ב־Storage.
7. פתחו `/api/q9-optimization/Q4/runs` וודאו שה־API מחזיר תשובה תקינה.
8. צרו ישיבת החלטה בלוג, הצביעו מתפקיד אחד, רעננו את הדף וודאו שההצבעה נשמרה.

## ה. בדיקת Decision Agent

ב־Render → Environment ודאו שקיימים:

```text
OPENAI_AGENT_ENABLED=true
OPENAI_API_KEY=<OpenAI API key של השרת>
OPENAI_MODEL=<מודל הזמין בפרויקט ה-API שלכם>
```

לחצו **Save, rebuild, and deploy**. אל תדביקו את המפתח ב־GitHub או במסך האפליקציה. OpenAI API עשוי להיות בתשלום; כאשר ה־Agent כבוי, כל שאר המערכת ממשיכה לפעול.

פתחו לאחר הפריסה:

```text
https://YOUR-SERVICE.onrender.com/api/agent/status
```

תוצאה תקינה כוללת `"ready": true`. אם מתקבל `false`, השדה `missing` מציין בדיוק איזה משתנה חסר. הערכים הסודיים עצמם לעולם אינם מוחזרים.

## ו. התחלת העבודה

1. העלו אסטרטגיה ויעדי Q9 תחת `Setup`.
2. בחרו זיהוי אוטומטי, העלו ואשרו בנפרד Q1, Q2 ו־Q3.
3. בחרו Q4 בחלק העליון.
4. בדקו מצב כספי, תחזית Q9 והמלצות.
5. הריצו את אופטימיזציית Q9 ובדקו את הסל המנצח ואת רגישות המשקלים.
6. פתחו ישיבת החלטה, השלימו הצבעות ואשרו רק לאחר שכל הבקרות עברו.
7. הורידו גיבוי מלא.

## תקלות נפוצות

- `Supabase ... missing` — משתנה חסר ב־Render.
- `permission denied` — הוזן anon key במקום Secret/service-role.
- `relation does not exist` — schema/migration לא הורץ במלואו.
- Agent לא זמין — הוא כבוי או שחסרים `OPENAI_API_KEY`/`OPENAI_MODEL`.
- PDF לא חולץ — ייתכן שהוא סרוק; הקובץ נשמר ומסומן לבדיקת OCR.
- פתיחה ראשונה איטית — Render Free עשוי להתעורר משינה.

בכל שינוי Environment יש לבחור **Save, rebuild, and deploy**.
