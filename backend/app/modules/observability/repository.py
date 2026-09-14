from sqlalchemy import text
from sqlalchemy.orm import Session


def check_database(db: Session) -> bool:
    return db.execute(text("SELECT 1")).scalar_one() == 1
