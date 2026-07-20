# Release Notes v1.5 — Evidence-to-Number Gate

## מטרת הגרסה

v1.5 מונעת מהמערכת להציג דיוק מספרי מזויף. כל סכום, מחיר, כמות או השפעה מהותית בהמלצה חייבים להיות ניתנים לשחזור ממקור מאושר או להיות מסומנים במפורש כהנחה מותנית.

## מה נוסף

- מנוע `evidence_engine.py` לביקורת מספרים בהמלצות ובחבילות החלטה.
- שרשרת ראיות מלאה: מקור, Actual או הנחה, נוסחה, טווח Low/Base/High, ביטחון ופערי מידע.
- סטטוסים `pass`, `conditional` ו־`blocked` ברמת טענה, המלצה ורבעון.
- איתור סתירה בין מחיר או בסיס חישוב בהמלצה לבין Actual מאושר.
- חסימת אימוץ המלצה מספרית וחבילת החלטות כאשר הראיות אינן מספיקות.
- פירוט אינטראקטיבי **איך הגענו למספרים?** בכל כרטיס החלטה.
- כלי Agent חדש: `get_evidence_gate`.
- API חדש:
  - `GET /api/evidence-gate/{quarter}`
  - `POST /api/evidence-gate/{quarter}/audit`
  - `GET /api/evidence-gate-runs`
- טבלת Supabase חדשה `evidence_gate_runs` עם RLS והרשאת `service_role`.
- הכללת ריצות הביקורת בגיבוי ובשחזור.

## שדרוג ענן קיים

1. פתחו ב־Supabase את SQL Editor.
2. הריצו פעם אחת את `supabase/migration_v1.5_evidence_gate.sql`.
3. העלו את קוד v1.5 ל־GitHub ופרסו מחדש ב־Render.
4. בדקו ש־`/api/health` מחזיר `1.5.0-evidence-gate`.
5. פתחו את חדר ההחלטות ובדקו שבכל המלצה מספרית מופיע סטטוס ראיות וקישור לפירוט.

אין להוסיף מפתחות Supabase או OpenAI לקוד או ל־GitHub. הסודות נשארים רק ב־Environment Variables של Render.

## בדיקות

- 58 בדיקות אוטומטיות עברו.
- בדיקת JavaScript עברה באמצעות `node --check`.
- קומפילציית Python עברה.
- בדיקת Supabase אמיתי מדולגת כאשר משתני הענן אינם זמינים בסביבת הבדיקה.
