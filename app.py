from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from google import genai
from pydantic import BaseModel
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key")

class Question(BaseModel):
    question: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: str


class Quiz(BaseModel):
    questions: list[Question]


client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

db = sqlite3.connect("study.db")

db.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL
    )
""")

db.execute("""
    CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        exam_date TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
""")

db.execute("""
    CREATE TABLE IF NOT EXISTS topics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        FOREIGN KEY (subject_id) REFERENCES subjects(id)
    )
""")

db.execute("""
    CREATE TABLE IF NOT EXISTS subtopics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Not Started',
        FOREIGN KEY (topic_id) REFERENCES topics(id)
    )
""")

db.execute("""
    CREATE TABLE IF NOT EXISTS study_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subtopic_id INTEGER NOT NULL,
        duration INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (subtopic_id) REFERENCES subtopics(id)
    )
""")

db.execute("""
    CREATE TABLE IF NOT EXISTS quizzes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subtopic_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (subtopic_id) REFERENCES subtopics(id)
    )
""")

db.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_id INTEGER NOT NULL,
        question TEXT NOT NULL,
        option_a TEXT NOT NULL,
        option_b TEXT NOT NULL,
        option_c TEXT NOT NULL,
        option_d TEXT NOT NULL,
        correct_answer TEXT NOT NULL,
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id)
    )
""")

db.execute("""
    CREATE TABLE IF NOT EXISTS quiz_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        score INTEGER NOT NULL,
        total_questions INTEGER NOT NULL,
        completed_at TEXT NOT NULL,
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
""")

db.execute("""
    CREATE TABLE IF NOT EXISTS prerequisites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subtopic_id INTEGER NOT NULL,
        prerequisite_id INTEGER NOT NULL,
        FOREIGN KEY (subtopic_id) REFERENCES subtopics(id),
        FOREIGN KEY (prerequisite_id) REFERENCES subtopics(id)
    )
""")

db.commit()
db.close()

@app.route("/")
def index():

    if "user_id" not in session:
        return redirect("/login")

    db = sqlite3.connect("study.db")
    db.row_factory = sqlite3.Row

    user = db.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    total_subjects = db.execute(
        """
        SELECT COUNT(*)
        FROM subjects
        WHERE user_id = ?
        """,
        (session["user_id"],)
    ).fetchone()[0]

    total_topics = db.execute(
        """
        SELECT COUNT(*)
        FROM topics
        JOIN subjects
            ON topics.subject_id = subjects.id
        WHERE subjects.user_id = ?
        """,
        (session["user_id"],)
    ).fetchone()[0]

    total_subtopics = db.execute(
        """
        SELECT COUNT(*)
        FROM subtopics
        JOIN topics
            ON subtopics.topic_id = topics.id
        JOIN subjects
            ON topics.subject_id = subjects.id
        WHERE subjects.user_id = ?
        """,
        (session["user_id"],)
    ).fetchone()[0]

    completed_subtopics = db.execute(
        """
        SELECT COUNT(*)
        FROM subtopics
        JOIN topics
            ON subtopics.topic_id = topics.id
        JOIN subjects
            ON topics.subject_id = subjects.id
        WHERE subjects.user_id = ?
        AND subtopics.status = 'Completed'
        """,
        (session["user_id"],)
    ).fetchone()[0]

    if total_subtopics > 0:
        progress = (
            completed_subtopics / total_subtopics
        ) * 100
    else:
        progress = 0

    recent_sessions = db.execute(
        """
        SELECT
            study_sessions.duration,
            study_sessions.created_at,
            subtopics.name AS subtopic_name,
            topics.name AS topic_name,
            subjects.name AS subject_name
        FROM study_sessions
        JOIN subtopics
            ON study_sessions.subtopic_id = subtopics.id
        JOIN topics
            ON subtopics.topic_id = topics.id
        JOIN subjects
            ON topics.subject_id = subjects.id
        WHERE study_sessions.user_id = ?
        ORDER BY study_sessions.created_at DESC
        LIMIT 5
        """,
        (session["user_id"],)
    ).fetchall()

    db.close()

    return render_template(
        "dashboard.html",
        user=user,
        total_subjects=total_subjects,
        total_topics=total_topics,
        total_subtopics=total_subtopics,
        completed_subtopics=completed_subtopics,
        progress=progress,
        recent_sessions=recent_sessions
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = generate_password_hash(request.form.get("password"))

        db = sqlite3.connect("study.db")

        db.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, password)
        )

        db.commit()
        db.close()

        return redirect("/")

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        db = sqlite3.connect("study.db")
        db.row_factory = sqlite3.Row

        user = db.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        db.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            return redirect("/")

        return "Invalid username or password"

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/subjects", methods=["GET", "POST"])
def subjects():
    if "user_id" not in session:
        return redirect("/login")

    db = sqlite3.connect("study.db")
    db.row_factory = sqlite3.Row

    if request.method == "POST":
        name = request.form.get("name")
        exam_date = request.form.get("exam_date")

        db.execute(
            "INSERT INTO subjects (user_id, name, exam_date) VALUES (?, ?, ?)",
            (session["user_id"], name, exam_date)
        )

        db.commit()

    subjects = db.execute(
        "SELECT * FROM subjects WHERE user_id = ?",
        (session["user_id"],)
    ).fetchall()

    db.close()

    return render_template("subjects.html", subjects=subjects)


@app.route("/topics/<int:subject_id>", methods=["GET", "POST"])
def topics(subject_id):
    if "user_id" not in session:
        return redirect("/login")

    db = sqlite3.connect("study.db")
    db.row_factory = sqlite3.Row

    subject = db.execute(
        "SELECT * FROM subjects WHERE id = ? AND user_id = ?",
        (subject_id, session["user_id"])
    ).fetchone()

    if subject is None:
        db.close()
        return "Subject not found", 404

    if request.method == "POST":
        name = request.form.get("name")

        db.execute(
            "INSERT INTO topics (subject_id, name) VALUES (?, ?)",
            (subject_id, name)
        )

        db.commit()

    topics = db.execute(
        "SELECT * FROM topics WHERE subject_id = ?",
        (subject_id,)
    ).fetchall()

    db.close()

    return render_template(
        "topics.html",
        subject=subject,
        topics=topics
    )


@app.route("/subtopics/<int:topic_id>", methods=["GET", "POST"])
def subtopics(topic_id):
    if "user_id" not in session:
        return redirect("/login")

    db = sqlite3.connect("study.db")
    db.row_factory = sqlite3.Row

    topic = db.execute(
        """
        SELECT topics.*
        FROM topics
        JOIN subjects ON topics.subject_id = subjects.id
        WHERE topics.id = ? AND subjects.user_id = ?
        """,
        (topic_id, session["user_id"])
    ).fetchone()

    if topic is None:
        db.close()
        return "Topic not found", 404

    if request.method == "POST":
        name = request.form.get("name")

        db.execute(
            "INSERT INTO subtopics (topic_id, name) VALUES (?, ?)",
            (topic_id, name)
        )

        db.commit()

    subtopics = db.execute(
        "SELECT * FROM subtopics WHERE topic_id = ?",
        (topic_id,)
    ).fetchall()

    total_subtopics = db.execute(
        "SELECT COUNT(*) FROM subtopics WHERE topic_id = ?",
        (topic_id,)
    ).fetchone()[0]

    completed_subtopics = db.execute(
        "SELECT COUNT(*) FROM subtopics WHERE topic_id = ? AND status = ?",
        (topic_id, "Completed")
    ).fetchone()[0]

    if total_subtopics == 0:
        progress = 0
    else:
        progress = (completed_subtopics / total_subtopics) * 100

    db.close()

    return render_template(
        "subtopics.html",
        topic=topic,
        subtopics=subtopics,
        total_subtopics=total_subtopics,
        completed_subtopics=completed_subtopics,
        progress=progress
    )


@app.route("/subtopics/<int:subtopic_id>/status", methods=["POST"])
def update_status(subtopic_id):
    if "user_id" not in session:
        return redirect("/login")

    status = request.form.get("status")

    if status not in ["Not Started", "In Progress", "Completed"]:
        return "Invalid status", 400

    db = sqlite3.connect("study.db")
    db.row_factory = sqlite3.Row

    subtopic = db.execute(
        """
        SELECT subtopics.*
        FROM subtopics
        JOIN topics ON subtopics.topic_id = topics.id
        JOIN subjects ON topics.subject_id = subjects.id
        WHERE subtopics.id = ? AND subjects.user_id = ?
        """,
        (subtopic_id, session["user_id"])
    ).fetchone()

    if subtopic is None:
        db.close()
        return "Subtopic not found", 404

    db.execute(
        "UPDATE subtopics SET status = ? WHERE id = ?",
        (status, subtopic_id)
    )

    db.commit()
    db.close()

    return redirect(f"/subtopics/{subtopic['topic_id']}")

@app.route("/timer/<int:subtopic_id>")
def timer(subtopic_id):
    if "user_id" not in session:
        return redirect("/login")

    db = sqlite3.connect("study.db")
    db.row_factory = sqlite3.Row

    subtopic = db.execute(
        """
        SELECT subtopics.*
        FROM subtopics
        JOIN topics ON subtopics.topic_id = topics.id
        JOIN subjects ON topics.subject_id = subjects.id
        WHERE subtopics.id = ? AND subjects.user_id = ?
        """,
        (subtopic_id, session["user_id"])
    ).fetchone()

    db.close()

    if subtopic is None:
        return "Subtopic not found", 404

    return render_template("timer.html", subtopic=subtopic)

@app.route("/timer/<int:subtopic_id>/finish", methods=["POST"])
def finish_session(subtopic_id):
    if "user_id" not in session:
        return "Not logged in", 401

    data = request.get_json()
    duration = data.get("duration")

    if duration is None or duration < 0:
        return "Invalid duration", 400

    db = sqlite3.connect("study.db")

    db.execute(
        """
        INSERT INTO study_sessions
        (user_id, subtopic_id, duration, created_at)
        VALUES (?, ?, ?, datetime('now'))
        """,
        (session["user_id"], subtopic_id, duration)
    )

    db.commit()
    db.close()

    return "Session saved"


@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect("/login")

    db = sqlite3.connect("study.db")
    db.row_factory = sqlite3.Row

    sessions = db.execute(
        """
        SELECT
            study_sessions.duration,
            study_sessions.created_at,
            subtopics.name AS subtopic_name,
            topics.name AS topic_name,
            subjects.name AS subject_name
        FROM study_sessions
        JOIN subtopics
            ON study_sessions.subtopic_id = subtopics.id
        JOIN topics
            ON subtopics.topic_id = topics.id
        JOIN subjects
            ON topics.subject_id = subjects.id
        WHERE study_sessions.user_id = ?
        ORDER BY study_sessions.created_at DESC
        """,
        (session["user_id"],)
    ).fetchall()

    db.close()

    return render_template("history.html", sessions=sessions)

@app.route("/quiz/<int:subtopic_id>", methods=["GET", "POST"])
def quiz(subtopic_id):
    if "user_id" not in session:
        return redirect("/login")

    db = sqlite3.connect("study.db")
    db.row_factory = sqlite3.Row

    subtopic = db.execute(
        """
        SELECT subtopics.*
        FROM subtopics
        JOIN topics ON subtopics.topic_id = topics.id
        JOIN subjects ON topics.subject_id = subjects.id
        WHERE subtopics.id = ? AND subjects.user_id = ?
        """,
        (subtopic_id, session["user_id"])
    ).fetchone()

    if subtopic is None:
        db.close()
        return "Subtopic not found", 404

    quiz = db.execute(
        """
        SELECT *
        FROM quizzes
        WHERE subtopic_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (subtopic_id,)
    ).fetchone()

    if quiz is None:
        db.close()
        return "No quiz available yet"

    questions = db.execute(
        """
        SELECT *
        FROM questions
        WHERE quiz_id = ?
        """,
        (quiz["id"],)
    ).fetchall()

    if request.method == "POST":
        score = 0

        for question in questions:
            answer = request.form.get(
                f"question_{question['id']}"
            )

            if answer == question["correct_answer"]:
                score += 1

        db.execute(
            """
            INSERT INTO quiz_attempts
            (
                quiz_id,
                user_id,
                score,
                total_questions,
                completed_at
            )
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            (
                quiz["id"],
                session["user_id"],
                score,
                len(questions)
            )
        )

        db.commit()

        percentage = (score / len(questions)) * 100

        if percentage >= 80:
            message = "Good job! You have a good understanding of this topic."
        elif percentage >= 60:
            message = "You're getting there. Keep studying this topic."
        else:
            message = "You should review this topic before moving on."

        db.close()

        return render_template(
        "quiz_result.html",
        score=score,
        total=len(questions),
        percentage=percentage,
        message=message,
        subtopic_id=subtopic_id,
        topic_id=subtopic["topic_id"]
)


    db.close()

    return render_template(
        "quiz.html",
        subtopic=subtopic,
        quiz=quiz,
        questions=questions
    )


@app.route("/quiz/<int:subtopic_id>/test")
def create_test_quiz(subtopic_id):
    if "user_id" not in session:
        return redirect("/login")

    db = sqlite3.connect("study.db")
    db.row_factory = sqlite3.Row

    subtopic = db.execute(
        """
        SELECT subtopics.*
        FROM subtopics
        JOIN topics ON subtopics.topic_id = topics.id
        JOIN subjects ON topics.subject_id = subjects.id
        WHERE subtopics.id = ? AND subjects.user_id = ?
        """,
        (subtopic_id, session["user_id"])
    ).fetchone()

    if subtopic is None:
        db.close()
        return "Subtopic not found", 404

    cursor = db.execute(
        """
        INSERT INTO quizzes (subtopic_id, created_at)
        VALUES (?, datetime('now'))
        """,
        (subtopic_id,)
    )

    quiz_id = cursor.lastrowid

    questions = [
        (
            "What is 2 + 2?",
            "3",
            "4",
            "5",
            "6",
            "B"
        ),
        (
            "Which language is Flask written in?",
            "Python",
            "Java",
            "C++",
            "Ruby",
            "A"
        ),
        (
            "Which data structure stores key-value pairs in Python?",
            "List",
            "Tuple",
            "Dictionary",
            "Set",
            "C"
        ),
        (
            "What does SQL primarily work with?",
            "Images",
            "Databases",
            "Animations",
            "Audio",
            "B"
        ),
        (
            "What does HTML stand for?",
            "HyperText Markup Language",
            "HighText Machine Language",
            "HyperTool Multi Language",
            "HomeText Markup Language",
            "A"
        )
    ]

    for question in questions:
        db.execute(
            """
            INSERT INTO questions
            (
                quiz_id,
                question,
                option_a,
                option_b,
                option_c,
                option_d,
                correct_answer
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (quiz_id, *question)
        )

    db.commit()
    db.close()

    return redirect(f"/quiz/{subtopic_id}")



@app.route("/quiz/<int:subtopic_id>/generate")
def generate_quiz(subtopic_id):

    if "user_id" not in session:
        return redirect("/login")

    db = sqlite3.connect("study.db")
    db.row_factory = sqlite3.Row

    subtopic = db.execute(
        """
        SELECT
            subtopics.*,
            topics.name AS topic_name,
            subjects.name AS subject_name
        FROM subtopics
        JOIN topics ON subtopics.topic_id = topics.id
        JOIN subjects ON topics.subject_id = subjects.id
        WHERE subtopics.id = ? AND subjects.user_id = ?
        """,
        (subtopic_id, session["user_id"])
    ).fetchone()

    if subtopic is None:
        db.close()
        return "Subtopic not found", 404

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=f"""
Create a quiz ONLY about this exact subtopic.

Subject: {subtopic['subject_name']}

Topic: {subtopic['topic_name']}

Subtopic: {subtopic['name']}

Create exactly 5 multiple-choice questions.

Rules:

- 4 options per question.
- Exactly one correct answer.
- correct_answer must be A, B, C, or D.
- Every question MUST be about the exact subtopic.
- Do not create generic questions.
- Mix easy and medium questions.
- Do not explain the answers.

MATHEMATICAL FORMATTING:

- Whenever you use mathematics, use LaTeX notation.
- Wrap inline mathematical expressions with \\( and \\).
- Wrap standalone equations with \\[ and \\].
- Use proper LaTeX for powers, fractions, square roots, subscripts, Greek letters, and mathematical symbols.
- For powers, use notation such as \\(x^2\\), NOT x^2 as plain text.
- For fractions, use \\(\\frac{{a}}{{b}}\\).
- For square roots, use \\(\\sqrt{{x}}\\).
- Do not use Markdown code blocks for mathematical expressions.
- Keep normal non-mathematical text as normal text.

Examples:

Instead of:
Solve x^2 + 5x + 6 = 0

Use:
Solve \\(x^2 + 5x + 6 = 0\\)

Instead of:
What is the value of (3x + 2) / 5?

Use:
What is the value of \\(\\frac{{3x+2}}{{5}}\\)?
""",
        config={
            "response_mime_type": "application/json",
            "response_schema": Quiz,
        }
    )

    quiz_data = response.parsed

    cursor = db.execute(
        """
        INSERT INTO quizzes (subtopic_id, created_at)
        VALUES (?, datetime('now'))
        """,
        (subtopic_id,)
    )

    quiz_id = cursor.lastrowid

    for question in quiz_data.questions:
        db.execute(
            """
            INSERT INTO questions
            (
                quiz_id,
                question,
                option_a,
                option_b,
                option_c,
                option_d,
                correct_answer
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                quiz_id,
                question.question,
                question.option_a,
                question.option_b,
                question.option_c,
                question.option_d,
                question.correct_answer
            )
        )

    db.commit()
    db.close()

    return redirect(f"/quiz/{subtopic_id}")



@app.route("/recommendation")
def recommendation():
    if "user_id" not in session:
        return redirect("/login")

    from datetime import date

    db = sqlite3.connect("study.db")
    db.row_factory = sqlite3.Row

    subtopics = db.execute(
        """
        SELECT
            subtopics.id,
            subtopics.name,
            subtopics.status,
            topics.name AS topic_name,
            subjects.name AS subject_name,
            subjects.exam_date,
            (
                SELECT quiz_attempts.score * 100.0 / quiz_attempts.total_questions
                FROM quiz_attempts
                JOIN quizzes
                    ON quiz_attempts.quiz_id = quizzes.id
                WHERE quizzes.subtopic_id = subtopics.id
                AND quiz_attempts.user_id = ?
                ORDER BY quiz_attempts.completed_at DESC
                LIMIT 1
            ) AS latest_score
        FROM subtopics
        JOIN topics
            ON subtopics.topic_id = topics.id
        JOIN subjects
            ON topics.subject_id = subjects.id
        WHERE subjects.user_id = ?
        AND subtopics.status != 'Completed'
        """,
        (session["user_id"], session["user_id"])
    ).fetchall()

    study_data = []
    priority_data = []

    today = date.today()

    prerequisite_data = {}

    for subtopic in subtopics:
        prerequisites = db.execute(
            """
            SELECT
                s.id,
                s.name,
                s.status,
                (
                    SELECT quiz_attempts.score * 100.0 / quiz_attempts.total_questions
                    FROM quiz_attempts
                    JOIN quizzes
                        ON quiz_attempts.quiz_id = quizzes.id
                    WHERE quizzes.subtopic_id = s.id
                    AND quiz_attempts.user_id = ?
                    ORDER BY quiz_attempts.completed_at DESC
                    LIMIT 1
                ) AS latest_score
            FROM prerequisites p
            JOIN subtopics s
                ON p.prerequisite_id = s.id
            WHERE p.subtopic_id = ?
            """,
            (session["user_id"], subtopic["id"])
        ).fetchall()

        prerequisite_data[subtopic["id"]] = prerequisites

    blocked_prerequisites = set()

    for subtopic in subtopics:
        prerequisites = prerequisite_data[subtopic["id"]]

        for prerequisite in prerequisites:
            prerequisite_score = prerequisite["latest_score"]

            if prerequisite_score is None or prerequisite_score < 80:
                blocked_prerequisites.add(prerequisite["id"])

    for subtopic in subtopics:
        score = subtopic["latest_score"]
        prerequisites = prerequisite_data[subtopic["id"]]

        if score is None:
            action = "STUDY"
        elif score < 60:
            action = "RETAKE_QUIZ"
        elif score < 80:
            action = "REVIEW_AND_RETAKE"
        else:
            action = "MOVE_FORWARD"

        prerequisites_ready = True

        for prerequisite in prerequisites:
            prerequisite_score = prerequisite["latest_score"]

            if prerequisite_score is None or prerequisite_score < 80:
                prerequisites_ready = False
                break

        candidate = True

        if score is not None and score >= 80:
            candidate = False

        if not prerequisites_ready:
            candidate = False

        if score is None:
            priority = 30
        elif score < 60:
            priority = 100
        elif score < 80:
            priority = 60
        else:
            priority = 20

        if subtopic["status"] == "In Progress":
            priority += 10

        if subtopic["exam_date"]:
            exam_date = date.fromisoformat(subtopic["exam_date"])
            days_left = (exam_date - today).days

            if days_left <= 3:
                priority += 40
            elif days_left <= 7:
                priority += 30
            elif days_left <= 14:
                priority += 20
            elif days_left <= 30:
                priority += 10

        recent_session = db.execute(
            """
            SELECT created_at, duration
            FROM study_sessions
            WHERE user_id = ?
            AND subtopic_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (session["user_id"], subtopic["id"])
        ).fetchone()

        if recent_session:
            study_date = date.fromisoformat(
                recent_session["created_at"][:10]
            )

            days_since_study = (today - study_date).days

            if days_since_study == 0:
                priority -= 20
            elif days_since_study == 1:
                priority -= 10
            elif days_since_study <= 3:
                priority -= 5

        if subtopic["id"] in blocked_prerequisites:
            priority += 50

        study_data.append({
            "subject": subtopic["subject_name"],
            "topic": subtopic["topic_name"],
            "subtopic": subtopic["name"],
            "status": subtopic["status"],
            "latest_quiz_score": score,
            "exam_date": subtopic["exam_date"],
            "action": action,
            "candidate": candidate,
            "is_blocking_prerequisite": (
                subtopic["id"] in blocked_prerequisites
            ),
            "prerequisites": [
                {
                    "name": prerequisite["name"],
                    "status": prerequisite["status"],
                    "latest_quiz_score": prerequisite["latest_score"]
                }
                for prerequisite in prerequisites
            ]
        })

        if candidate:
            priority_data.append({
                "subject": subtopic["subject_name"],
                "topic": subtopic["topic_name"],
                "subtopic": subtopic["name"],
                "priority": priority,
                "latest_quiz_score": score,
                "status": subtopic["status"],
                "exam_date": subtopic["exam_date"],
                "action": action,
                "is_blocking_prerequisite": (
                    subtopic["id"] in blocked_prerequisites
                )
            })

    priority_data.sort(
        key=lambda item: item["priority"],
        reverse=True
    )

    if not priority_data:
        db.close()

        return render_template(
            "recommendation.html",
            subtopics=subtopics,
            recommendation=(
                "You're caught up! There is no unfinished "
                "subtopic that currently needs attention."
            )
        )

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=f"""
You are a friendly study coach inside a study tracking application.

The application has already calculated the priority of each
unfinished subtopic.

Prioritized candidates:

{priority_data}

Full student study data:

{study_data}

IMPORTANT RULES:

- Recommend ONLY the highest-priority candidate.
- Do NOT reorder the candidates.
- Do NOT recommend a subtopic that is not in the prioritized candidates.
- Give ONE best next action, not a checklist.
- If a candidate is a blocking prerequisite, prioritize fixing
  that prerequisite before the dependent topic.
- A prerequisite with no quiz or a score below 80% is not ready.
- Do not recommend a dependent topic while one of its prerequisites
  is not ready.
- A topic with 80%+ quiz understanding normally does not need
  to be recommended.
- Exam urgency is already included in the priority.
- When an exam is approaching, you may briefly mention the exam
  date or urgency as part of the reason.
- Do not invent additional deadlines or exam information.
- Recent study activity is already included in the priority.
- Never mention the numerical priority score.
- Do not invent student information.
- Do not describe an 80%+ score as "mastered", "perfect",
  or "complete".
- Instead, say that the prerequisite is "ready" or that the
  student has demonstrated enough understanding to move forward.

ACTION MEANINGS:

STUDY:
The student has not taken a quiz yet.
Tell them to study the subtopic.

RETAKE_QUIZ:
The latest quiz score is below 60%.
Tell them to review/study the subtopic first and then retake the quiz.

REVIEW_AND_RETAKE:
The latest quiz score is between 60% and 79%.
Tell them to review the subtopic and then retake the quiz.

MOVE_FORWARD:
The student has demonstrated enough understanding to move forward.

Give:

1. The subtopic
2. A short reason
3. One simple action for today

Keep the response concise and practical.
"""
    )

    recommendation = response.text

    db.close()

    return render_template(
        "recommendation.html",
        subtopics=subtopics,
        recommendation=recommendation
    )


@app.route("/mentor", methods=["GET", "POST"])
def mentor():
    if "user_id" not in session:
        return redirect("/login")

    conversation = session.get("mentor_conversation", [])

    if request.method == "POST":
        question = request.form.get("question", "").strip()

        if not question:
            return render_template(
                "mentor.html",
                conversation=conversation
            )

        db = sqlite3.connect("study.db")
        db.row_factory = sqlite3.Row

        subtopics = db.execute(
            """
            SELECT
                subtopics.id,
                subtopics.name,
                subtopics.status,
                topics.name AS topic_name,
                subjects.name AS subject_name,
                subjects.exam_date,
                (
                    SELECT quiz_attempts.score * 100.0 / quiz_attempts.total_questions
                    FROM quiz_attempts
                    JOIN quizzes
                        ON quiz_attempts.quiz_id = quizzes.id
                    WHERE quizzes.subtopic_id = subtopics.id
                    AND quiz_attempts.user_id = ?
                    ORDER BY quiz_attempts.completed_at DESC
                    LIMIT 1
                ) AS latest_score
            FROM subtopics
            JOIN topics
                ON subtopics.topic_id = topics.id
            JOIN subjects
                ON topics.subject_id = subjects.id
            WHERE subjects.user_id = ?
            """,
            (session["user_id"], session["user_id"])
        ).fetchall()

        prerequisite_data = {}

        for subtopic in subtopics:
            prerequisites = db.execute(
                """
                SELECT
                    s.id,
                    s.name,
                    s.status,
                    (
                        SELECT quiz_attempts.score * 100.0 / quiz_attempts.total_questions
                        FROM quiz_attempts
                        JOIN quizzes
                            ON quiz_attempts.quiz_id = quizzes.id
                        WHERE quizzes.subtopic_id = s.id
                        AND quiz_attempts.user_id = ?
                        ORDER BY quiz_attempts.completed_at DESC
                        LIMIT 1
                    ) AS latest_score
                FROM prerequisites p
                JOIN subtopics s
                    ON p.prerequisite_id = s.id
                WHERE p.subtopic_id = ?
                """,
                (session["user_id"], subtopic["id"])
            ).fetchall()

            prerequisite_data[subtopic["id"]] = prerequisites

        study_sessions = db.execute(
            """
            SELECT
                study_sessions.duration,
                study_sessions.created_at,
                subtopics.name AS subtopic_name
            FROM study_sessions
            JOIN subtopics
                ON study_sessions.subtopic_id = subtopics.id
            WHERE study_sessions.user_id = ?
            ORDER BY study_sessions.created_at DESC
            """,
            (session["user_id"],)
        ).fetchall()

        study_data = []

        for subtopic in subtopics:
            study_data.append({
                "subject": subtopic["subject_name"],
                "topic": subtopic["topic_name"],
                "subtopic": subtopic["name"],
                "status": subtopic["status"],
                "latest_quiz_score": subtopic["latest_score"],
                "exam_date": subtopic["exam_date"],
                "prerequisites": [
                    {
                        "name": prerequisite["name"],
                        "status": prerequisite["status"],
                        "latest_quiz_score": prerequisite["latest_score"]
                    }
                    for prerequisite in prerequisite_data[subtopic["id"]]
                ]
            })

        study_history = []

        for study_session in study_sessions:
            study_history.append({
                "subtopic": study_session["subtopic_name"],
                "duration_seconds": study_session["duration"],
                "date": study_session["created_at"]
            })

        recent_conversation = conversation[-10:]

        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=f"""
You are the AI Mentor inside a study tracking application.

Your job is to help the student understand their studies,
make better decisions about what to study, and answer
academic questions clearly.

Student study data:
{study_data}

Recent study history:
{study_history}

Recent conversation:
{recent_conversation}

New student question:
{question}

IMPORTANT DATA RULES:

- Study session duration is stored in seconds.
- 10 means 10 seconds, not 10 minutes.
- 60 means 60 seconds, which equals 1 minute.
- Convert seconds to minutes only when useful.
- Do not assume the student studied something unless it
  appears in the study history.
- Do not invent information about the student.
- Use the student's actual study data when relevant.

UNDERSTANDING STUDENT PROGRESS:

Distinguish carefully between:

- Weak: the student has demonstrated low quiz performance.
- Unfinished: the status is In Progress.
- Not started: there is not enough evidence to judge the
  student's ability yet.

Do NOT automatically describe a Not Started topic as the
student's weakest topic.

Do NOT describe an 80% quiz score as weak.

Use prerequisite relationships when explaining why a topic
may be difficult.

Use exam dates when they are relevant.

CONVERSATION:

Use the recent conversation to understand follow-up
questions.

If the student asks a short follow-up such as "why?",
"which one?", or "what about that?", understand what they
are referring to from the conversation.

Do not repeat the entire previous explanation unless it is
actually necessary.

Answer the specific question first.

STYLE:

Be conversational, practical, and concise.

Do not use Markdown headings such as # or ###.

Do not use Markdown bold syntax such as **text**.

Do not escape asterisks with backslashes.

Use simple readable paragraphs and bullet points when useful.

If the student asks an academic question, teach the concept
rather than only giving the answer.

Do not overwhelm the student with unnecessary information.
"""
        )

        answer = response.text.strip()

        conversation.append({
            "role": "user",
            "content": question
        })

        conversation.append({
            "role": "mentor",
            "content": answer
        })

        # Keep the last 5 exchanges.
        conversation = conversation[-10:]

        session["mentor_conversation"] = conversation

        db.close()

        return render_template(
            "mentor.html",
            conversation=conversation
        )

    return render_template(
        "mentor.html",
        conversation=conversation
    )

@app.route("/mentor/clear", methods=["POST"])
def clear_mentor():
    if "user_id" not in session:
        return redirect("/login")

    session.pop("mentor_conversation", None)

    return redirect("/mentor")

@app.route("/mentor/ask", methods=["POST"])
def mentor_ask():
    if "user_id" not in session:
        return {"error": "Not logged in"}, 401

    data = request.get_json()

    if not data or not data.get("question", "").strip():
        return {"error": "Question is required"}, 400

    question = data["question"].strip()

    conversation = session.get("mentor_conversation", [])

    db = sqlite3.connect("study.db")
    db.row_factory = sqlite3.Row

    subtopics = db.execute(
        """
        SELECT
            subtopics.id,
            subtopics.name,
            subtopics.status,
            topics.name AS topic_name,
            subjects.name AS subject_name,
            subjects.exam_date,
            (
                SELECT quiz_attempts.score * 100.0 / quiz_attempts.total_questions
                FROM quiz_attempts
                JOIN quizzes
                    ON quiz_attempts.quiz_id = quizzes.id
                WHERE quizzes.subtopic_id = subtopics.id
                AND quiz_attempts.user_id = ?
                ORDER BY quiz_attempts.completed_at DESC
                LIMIT 1
            ) AS latest_score
        FROM subtopics
        JOIN topics
            ON subtopics.topic_id = topics.id
        JOIN subjects
            ON topics.subject_id = subjects.id
        WHERE subjects.user_id = ?
        """,
        (session["user_id"], session["user_id"])
    ).fetchall()

    prerequisite_data = {}

    for subtopic in subtopics:

        prerequisites = db.execute(
            """
            SELECT
                s.id,
                s.name,
                s.status,
                (
                    SELECT quiz_attempts.score * 100.0 / quiz_attempts.total_questions
                    FROM quiz_attempts
                    JOIN quizzes
                        ON quiz_attempts.quiz_id = quizzes.id
                    WHERE quizzes.subtopic_id = s.id
                    AND quiz_attempts.user_id = ?
                    ORDER BY quiz_attempts.completed_at DESC
                    LIMIT 1
                ) AS latest_score
            FROM prerequisites p
            JOIN subtopics s
                ON p.prerequisite_id = s.id
            WHERE p.subtopic_id = ?
            """,
            (session["user_id"], subtopic["id"])
        ).fetchall()

        prerequisite_data[subtopic["id"]] = prerequisites

    study_sessions = db.execute(
        """
        SELECT
            study_sessions.duration,
            study_sessions.created_at,
            subtopics.name AS subtopic_name
        FROM study_sessions
        JOIN subtopics
            ON study_sessions.subtopic_id = subtopics.id
        WHERE study_sessions.user_id = ?
        ORDER BY study_sessions.created_at DESC
        """,
        (session["user_id"],)
    ).fetchall()

    study_data = []

    for subtopic in subtopics:

        study_data.append({
            "subject": subtopic["subject_name"],
            "topic": subtopic["topic_name"],
            "subtopic": subtopic["name"],
            "status": subtopic["status"],
            "latest_quiz_score": subtopic["latest_score"],
            "exam_date": subtopic["exam_date"],
            "prerequisites": [
                {
                    "name": prerequisite["name"],
                    "status": prerequisite["status"],
                    "latest_quiz_score": prerequisite["latest_score"]
                }
                for prerequisite in prerequisite_data[subtopic["id"]]
            ]
        })

    study_history = []

    for study_session in study_sessions:

        study_history.append({
            "subtopic": study_session["subtopic_name"],
            "duration_seconds": study_session["duration"],
            "date": study_session["created_at"]
        })

    recent_conversation = conversation[-10:]

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=f"""
You are the AI Mentor inside a study tracking application.

Your job is to help the student understand their studies,
make better decisions about what to study, and answer
academic questions clearly.

Student study data:
{study_data}

Recent study history:
{study_history}

Recent conversation:
{recent_conversation}

New student question:
{question}

IMPORTANT DATA RULES:

- Study session duration is stored in seconds.
- 10 means 10 seconds, not 10 minutes.
- 60 means 60 seconds, which equals 1 minute.
- Convert seconds to minutes only when useful.
- Do not assume the student studied something unless it
  appears in the study history.
- Do not invent information about the student.
- Use the student's actual study data when relevant.

UNDERSTANDING STUDENT PROGRESS:

Distinguish carefully between:

- Weak: the student has demonstrated low quiz performance.
- Unfinished: the status is In Progress.
- Not started: there is not enough evidence to judge ability.

Do NOT automatically describe a Not Started topic as weak.

Do NOT describe an 80% quiz score as weak.

Use prerequisite relationships when explaining why a topic
may be difficult.

Use exam dates when they are relevant.

CONVERSATION:

Use the recent conversation to understand follow-up questions.

If the student asks a short follow-up such as "why?",
"which one?", or "what about that?", understand what they
are referring to from the conversation.

Do not repeat the entire previous explanation unless
necessary.

Answer the specific question first.

STYLE:

Be conversational, practical, and concise.

Do not use Markdown headings such as # or ###.

Do not use Markdown bold syntax such as **text**.

Do not escape asterisks with backslashes.

Use simple readable paragraphs and bullet points when useful.

If the student asks an academic question, teach the concept
rather than only giving the answer.

Do not overwhelm the student with unnecessary information.
"""
    )

    answer = response.text.strip()

    conversation.append({
        "role": "user",
        "content": question
    })

    conversation.append({
        "role": "mentor",
        "content": answer
    })

    conversation = conversation[-10:]

    session["mentor_conversation"] = conversation

    db.close()

    return {
        "answer": answer
    }
