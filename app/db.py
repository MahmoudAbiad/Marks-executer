"""
إدارة قاعدة بيانات Turso (libsql)
"""
import libsql_client

from app import config
from app.utils import normalize_arabic


def get_db():
    return libsql_client.create_client(url=config.TURSO_DB_URL, auth_token=config.TURSO_AUTH_TOKEN)


async def init_db():
    async with get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS students (
                chat_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                seat_number TEXT NOT NULL,
                year TEXT NOT NULL,
                major TEXT NOT NULL
            );
        """)


async def save_student(chat_id: int, full_name: str, seat_number: str, year: str, major: str):
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO students (chat_id, full_name, seat_number, year, major)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                full_name = excluded.full_name,
                seat_number = excluded.seat_number,
                year = excluded.year,
                major = excluded.major;
            """,
            (chat_id, full_name, seat_number, year, major)
        )


async def get_student(chat_id: int):
    async with get_db() as db:
        rs = await db.execute("SELECT full_name, seat_number, year, major FROM students WHERE chat_id = ?;", (chat_id,))
        return rs.rows[0] if rs.rows else None


async def get_students_by_target(year: str, major: str):
    async with get_db() as db:
        rs = await db.execute("SELECT chat_id, full_name, seat_number, year, major FROM students;")
        matched = []
        norm_target_year = normalize_arabic(year)
        norm_target_major = normalize_arabic(major)

        for r in rs.rows:
            st = {"chat_id": r[0], "full_name": r[1], "seat_number": str(r[2]), "year": r[3], "major": r[4]}
            norm_db_year = normalize_arabic(st["year"])
            norm_db_major = normalize_arabic(st["major"])

            # مطابقة ذكية مع تجنب النصوص الفارغة
            year_match = bool(norm_target_year and (norm_target_year in norm_db_year or norm_db_year in norm_target_year))
            major_match = bool(norm_target_major and (norm_target_major in norm_db_major or norm_db_major in norm_target_major))

            if year_match and major_match:
                matched.append(st)
        return matched
