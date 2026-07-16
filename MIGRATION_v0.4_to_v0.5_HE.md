# שדרוג v0.4 ל־v0.5 בלי למחוק נתונים

## לפני השדרוג

1. פתחו את אפליקציית v0.4 הקיימת.
2. עברו למסך **גיבוי ושחזור** והורידו גיבוי מלא.
3. ודאו שבקובץ ה־ZIP קיימים `manifest.json`, `database.json` ותיקיית `files`.
4. שמרו את הגיבוי מחוץ ל־GitHub.

## שדרוג Supabase

1. היכנסו ל־Supabase של המערכת הקיימת.
2. פתחו **SQL Editor → New query**.
3. פתחו ב־GitHub את `supabase/migration_v0.5.sql` והעתיקו את כל תוכנו.
4. הדביקו ולחצו **Run**.
5. ודאו שההרצה הסתיימה ללא שגיאה.
6. ב־Table Editor ודאו שנוספו הטבלאות:

```text
finance_by_area
report_imports
research_results
strategy_profiles
strategic_assessments
scenario_portfolios
quarter_snapshots
agent_threads
agent_messages
```

הסקריפט משתמש ב־`create table if not exists` וב־`add column if not exists`; הוא אינו מוחק טבלאות או נתוני v0.4.

## שדרוג GitHub ו־Render

1. העלו לשורש המאגר את תוכן חבילת v0.5. אל תעלו את תיקיית ה־ZIP עצמה.
2. ודאו ש־`main.py`, `requirements.txt`, `render.yaml`, `static/` ו־`supabase/` נמצאים בשורש.
3. בצעו Commit ל־`main`.
4. Render יבצע Deploy אוטומטי. אם לא, בחרו **Manual Deploy → Deploy latest commit**.
5. אין צורך לשנות `SUPABASE_URL`, `SUPABASE_SECRET_KEY` או `APP_ACCESS_PASSWORD` הקיימים.

## Decision Agent — אופציונלי

האפליקציה עולה גם בלי Agent. להפעלה, הוסיפו ב־Render Environment:

```text
OPENAI_AGENT_ENABLED=true
OPENAI_API_KEY=<מפתח API של OpenAI בצד השרת>
OPENAI_MODEL=<מודל שזמין בפרויקט ה-API>
```

שמרו ובחרו **Save, rebuild, and deploy**. אין להזין את המפתח באפליקציה או ב־GitHub.

## בדיקה לאחר השדרוג

1. פתחו `/api/health` וודאו `status: ok`, `database: ok`, `storage: ok`.
2. פתחו את האפליקציה וודאו שהמידע הישן עדיין מופיע.
3. העלו קובץ CSV קטן לרבעון בדיקה, בדקו את תצוגת החילוץ ואל תאשרו אם הוא אינו אמיתי.
4. פתחו חדר החלטות Q4 וודאו שנתוני Q1–Q3 משמשים כבסיס.
5. הורידו גיבוי חדש של v0.5.

## אם משהו נכשל

- אל תריצו Reset.
- שמרו את לוג השגיאה של Render ללא ערכי סודות.
- הריצו שוב את `migration_v0.5.sql`; הוא idempotent.
- אם האפליקציה הישנה עדיין זמינה, אין לשחזר גיבוי עד שבודקים את הסיבה. השחזור נועד למקרה שבו נדרש להחזיר את הנתונים, לא לתקן קוד.
