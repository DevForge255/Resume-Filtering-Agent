# sqlite3 import kar rahe hain taaki local SQLite database create aur query kar saken
import sqlite3

# os import path handling ke liye use hoga (database file ka absolute path banane ke liye)
import os

# typing se Optional import kar rahe hain taaki function type hints clear ho
from typing import Optional

# CURRENT_DIR current file ka folder path store karta hai
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# DB_PATH SQLite file ka absolute path banata hai
DB_PATH = os.path.join(CURRENT_DIR, "db", "candidates.db")


# _get_connection helper function DB connection return karta hai
# Har DB operation is function ke through consistent connection setup use karega

def _get_connection() -> sqlite3.Connection:
    # db folder ensure karte hain taaki SQLite file create ho sake
    os.makedirs(os.path.join(CURRENT_DIR, "db"), exist_ok=True)

    # SQLite connection open karte hain
    connection = sqlite3.connect(DB_PATH)

    # Row factory set karte hain taaki rows dict-like access ke saath mil sakein
    connection.row_factory = sqlite3.Row

    # Connection return karte hain
    return connection


# init_db function table create karta hai agar table pehle se exist na kare

def init_db() -> None:
    # DB connection context manager ke saath open karte hain (auto commit/close handling)
    with _get_connection() as connection:
        # Cursor object SQL execute karne ke liye banate hain
        cursor = connection.cursor()

        # candidates table create statement run karte hain
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                candidate_name TEXT,
                resume_text TEXT,
                resume_score INTEGER,
                resume_feedback TEXT,
                negative_feedback TEXT,
                score2 INTEGER,
                overall_feedback TEXT,
                interview_status INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Useful indexes banate hain taaki filtering aur display fast ho
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_candidates_email ON candidates(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_candidates_score2 ON candidates(score2)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(interview_status)")

        # Table creation aur indexes DB mein persist karne ke liye commit karte hain
        connection.commit()


# _normalize_email helper email ko trim + lowercase karta hai for consistent dedupe

def _normalize_email(email: str) -> str:
    # Empty-safe conversion ke saath lowercase normalized value return karte hain
    return (email or "").strip().lower()


# insert_candidate_if_not_exists selected resume data insert karta hai agar email pehle se na ho

def insert_candidate_if_not_exists(
    email: str,
    candidate_name: str,
    resume_text: str,
    resume_score: Optional[int],
    resume_feedback: str,
    negative_feedback: str,
) -> bool:
    # DB schema ensure karne ke liye init_db call karte hain
    init_db()

    # Email normalize karte hain taaki duplicate checks reliable ho
    normalized_email = _normalize_email(email)

    # Agar email invalid/empty hai toh insert skip karte hain aur False return karte hain
    if not normalized_email:
        return False

    # DB connection context manager ke saath open karte hain
    with _get_connection() as connection:
        # Cursor object banate hain SQL operations ke liye
        cursor = connection.cursor()

        # Email ke basis par pehle check karte hain candidate already present hai ya nahi
        cursor.execute("SELECT id FROM candidates WHERE email = ?", (normalized_email,))

        # Existing row fetch karte hain
        existing_row = cursor.fetchone()

        # Agar row mil gayi toh duplicate insert avoid karte hain
        if existing_row:
            return False

        # Candidate insert query chalate hain (naya record add hoga)
        cursor.execute(
            """
            INSERT INTO candidates (
                email,
                candidate_name,
                resume_text,
                resume_score,
                resume_feedback,
                negative_feedback,
                score2,
                overall_feedback,
                interview_status,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, 0, CURRENT_TIMESTAMP)
            """,
            (
                normalized_email,
                candidate_name,
                resume_text,
                resume_score,
                resume_feedback,
                negative_feedback,
            ),
        )

        # Insert operation persist karne ke liye commit karte hain
        connection.commit()

    # Insert successful hua toh True return karte hain
    return True


# update_interview_result analyzer ke final outputs (score2 + feedback + status) update karta hai

def update_interview_result(email: str, score2: Optional[int], overall_feedback: str) -> bool:
    # DB schema ensure karte hain taaki table missing error na aaye
    init_db()

    # Email normalize karte hain consistent matching ke liye
    normalized_email = _normalize_email(email)

    # Invalid email pe update skip karte hain
    if not normalized_email:
        return False

    # overall_feedback text ko safe trim karte hain
    feedback_text = (overall_feedback or "").strip()

    # Status rule apply karte hain: feedback agar diya gaya hai toh status true (1), warna false (0)
    interview_status_value = 1 if feedback_text else 0

    # DB connection open karte hain
    with _get_connection() as connection:
        # Cursor object banate hain
        cursor = connection.cursor()

        # Update query run karte hain specific candidate email ke against
        cursor.execute(
            """
            UPDATE candidates
            SET score2 = ?,
                overall_feedback = ?,
                interview_status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE email = ?
            """,
            (score2, feedback_text, interview_status_value, normalized_email),
        )

        # Update persist karne ke liye commit karte hain
        connection.commit()

        # rowcount check karke pata karte hain update hua ya candidate mila hi nahi
        return cursor.rowcount > 0


# get_candidates_above_score dashboard filtering ke liye helper deta hai (e.g., score2 > 85)

def get_candidates_above_score(min_score2: int = 85) -> list[sqlite3.Row]:
    # DB schema ensure karte hain
    init_db()

    # DB connection open karte hain
    with _get_connection() as connection:
        # Cursor object banate hain
        cursor = connection.cursor()

        # Query execute karte hain: sirf completed interview aur threshold se upar score2 wale candidates
        cursor.execute(
            """
            SELECT id, email, candidate_name, score2, overall_feedback, interview_status, updated_at
            FROM candidates
            WHERE interview_status = 1
              AND score2 > ?
            ORDER BY score2 DESC, updated_at DESC
            """,
            (min_score2,),
        )

        # All matching rows return karte hain
        return cursor.fetchall()


# get_shortlisted_candidates filtering stage ke shortlisted candidates DB se laata hai

def get_shortlisted_candidates(min_resume_score: int = 70) -> list[sqlite3.Row]:
    # DB schema ensure karte hain
    init_db()

    # DB connection open karte hain
    with _get_connection() as connection:
        # Cursor object banate hain
        cursor = connection.cursor()

        # Query execute karte hain: resume filtering score threshold ke basis par shortlist
        cursor.execute(
            """
            SELECT id, email, candidate_name, resume_text, resume_score, resume_feedback, negative_feedback, updated_at
            FROM candidates
            WHERE resume_score >= ?
            ORDER BY resume_score DESC, updated_at DESC
            """,
            (min_resume_score,),
        )

        # Matching shortlisted rows return karte hain
        return cursor.fetchall()
