from __future__ import annotations

import db


def main() -> None:
    print("פעולה זו תמחק את כל נתוני החברה ואת כל הקבצים שהועלו ל-Supabase Storage.")
    answer = input("להקליד RESET כדי להמשיך: ").strip()
    if answer != "RESET":
        print("האיפוס בוטל.")
        return
    db.init_db()
    db.reset_company_data(delete_files=True)
    print("הנתונים אופסו. קטלוגי המבנה נשמרו.")


if __name__ == "__main__":
    main()
