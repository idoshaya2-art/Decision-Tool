from __future__ import annotations

import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "intopia.db"
UPLOAD_DIR = DATA_DIR / "uploads"


def main() -> None:
    print("פעולה זו תמחק את כל נתוני החברה והקבצים שהועלו.")
    answer = input("להקליד RESET כדי להמשיך: ").strip()
    if answer != "RESET":
        print("האיפוס בוטל.")
        return
    if DB_PATH.exists():
        DB_PATH.unlink()
    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / ".gitkeep").touch()
    print("הנתונים אופסו. בהפעלה הבאה ייווצר מסד נתונים ריק.")


if __name__ == "__main__":
    main()
