# v1.9.1 — Data Loading Hotfix

- טעינת הרבעון משתמשת כעת ב־`Promise.allSettled`, כך שכשל במודול אחד אינו מסתיר את שאר המידע.
- הודעת השגיאה מפרטת אילו רכיבים לא נטענו ואת הודעת השרת הראשונה.
- נוספה מיגרציה מאוחדת ובטוחה: `supabase/migration_v1.9_hotfix_missing_tables.sql`.
- המיגרציה משלימה את טבלאות הלמידה, Evidence Gate וה־Digital Twin מ־v1.4–v1.6 ללא מחיקת נתונים.
