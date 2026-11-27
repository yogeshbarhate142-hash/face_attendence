import os, sqlite3, uuid, secrets
import time
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from functools import wraps
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from deepface import DeepFace

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "attendance.db")
FACE_DIR = os.path.join(BASE, "private_faces")
os.makedirs(FACE_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "0") == "1"
MODEL = os.getenv("FACE_MODEL", "Facenet512")
IST = ZoneInfo("Asia/Kolkata")

def connect():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c

def init_db():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS organizations(
          id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT UNIQUE NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS admins(
          id TEXT PRIMARY KEY, org_id TEXT NOT NULL UNIQUE,
          email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
          FOREIGN KEY(org_id) REFERENCES organizations(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS people(
          id TEXT PRIMARY KEY, org_id TEXT NOT NULL, full_name TEXT NOT NULL,
          member_code TEXT NOT NULL, face_path TEXT NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(org_id, member_code),
          FOREIGN KEY(org_id) REFERENCES organizations(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS attendance(
          id INTEGER PRIMARY KEY AUTOINCREMENT, person_id TEXT NOT NULL,
          org_id TEXT NOT NULL, event_type TEXT NOT NULL DEFAULT 'CHECK_IN',
          marked_at TEXT NOT NULL,
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE,
          FOREIGN KEY(org_id) REFERENCES organizations(id) ON DELETE CASCADE
        );
        """)
        cols = [row["name"] for row in c.execute("PRAGMA table_info(attendance)").fetchall()]
        if "event_type" not in cols:
            c.execute("ALTER TABLE attendance ADD COLUMN event_type TEXT NOT NULL DEFAULT 'CHECK_IN'")
init_db()
def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("org_id") or not session.get("admin_id"):
            return jsonify(error="Please sign in as an organization administrator."), 401
        return fn(*args, **kwargs)
    return wrapper

def save_image(upload):
    if not upload or not upload.mimetype.startswith("image/"):
        raise ValueError("A camera image is required.")
    filename = secure_filename(uuid.uuid4().hex + ".jpg")
    path = os.path.join(FACE_DIR, filename)
    upload.save(path)
    return path

def validate_face(path):
    DeepFace.extract_faces(img_path=path, detector_backend="opencv",
                           enforce_detection=True, align=True)

def match_face(live_path, enrolled_path):
    result = DeepFace.verify(img1_path=live_path, img2_path=enrolled_path,
                             model_name=MODEL, detector_backend="opencv",
                             enforce_detection=True, anti_spoofing=False)
    return bool(result.get("verified")), float(result.get("distance", 1.0))

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/attendance")
def attendance_page():
    return render_template("attendance.html")

@app.get("/dashboard")
def dashboard_page():
    return render_template("dashboard.html",
                           signed_in=bool(session.get("admin_id")),
                           org_name=session.get("org_name"))

@app.post("/api/org/signup")
def org_signup():
    data = request.get_json(silent=True) or {}
    name, email = (data.get("org_name") or "").strip(), (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not name or not email or len(password) < 10:
        return jsonify(error="Enter an organization name, valid email, and password of at least 10 characters."), 400
    org_id, admin_id = str(uuid.uuid4()), str(uuid.uuid4())
    code = secrets.token_urlsafe(6).replace("-", "").replace("_", "").upper()[:8]
    try:
        with connect() as c:
            c.execute("INSERT INTO organizations VALUES(?,?,?,?)",
                      (org_id, name, code, datetime.now(timezone.utc).isoformat()))
            c.execute("INSERT INTO admins VALUES(?,?,?,?)",
                      (admin_id, org_id, email, generate_password_hash(password)))
        session.clear()
        session.update(admin_id=admin_id, org_id=org_id, org_name=name)
        return jsonify(message="Organization created.", organization_code=code)
    except sqlite3.IntegrityError:
        return jsonify(error="That email is already registered."), 409

@app.post("/api/admin/login")
def admin_login():
    data = request.get_json(silent=True) or {}
    email, password = (data.get("email") or "").strip().lower(), data.get("password") or ""
    with connect() as c:
        row = c.execute("""SELECT a.*, o.name AS org_name FROM admins a
                           JOIN organizations o ON o.id=a.org_id WHERE a.email=?""", (email,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify(error="Incorrect email or password."), 401
    session.clear()
    session.update(admin_id=row["id"], org_id=row["org_id"], org_name=row["org_name"])
    return jsonify(message="Signed in.", organization=row["org_name"])

@app.post("/api/admin/logout")
def admin_logout():
    session.clear()
    return jsonify(message="Signed out.")

@app.get("/api/admin/me")
@admin_required
def admin_me():
    with connect() as c:
        org = c.execute("SELECT name, code FROM organizations WHERE id=?", (session["org_id"],)).fetchone()
    return jsonify(organization=dict(org))

@app.post("/api/admin/members")
@admin_required
def add_member():
    name = (request.form.get("full_name") or "").strip()
    member_code = (request.form.get("member_code") or "").strip()
    if not name or not member_code:
        return jsonify(error="Name and member code are required."), 400
    path = None
    try:
        path = save_image(request.files.get("face"))
        validate_face(path)
        person_id = str(uuid.uuid4())
        with connect() as c:
            c.execute("INSERT INTO people VALUES(?,?,?,?,?,?)",
                      (person_id, session["org_id"], name, member_code, path,
                       datetime.now(timezone.utc).isoformat()))
        return jsonify(message="Member enrolled.", member_id=person_id)
    except sqlite3.IntegrityError:
        if path and os.path.exists(path): os.remove(path)
        return jsonify(error="That member code is already in use in this organization."), 409
    except Exception:
        if path and os.path.exists(path): os.remove(path)
        return jsonify(error="Could not enroll face. Use a clear, front-facing image."), 400

@app.post("/api/attendance")
def mark_attendance():
    org_code = (request.form.get("org_code") or "").strip().upper()
    member_code = (request.form.get("member_code") or "").strip()
    live_path = None
    try:
        live_path = save_image(request.files.get("face"))
        with connect() as c:
            person = c.execute("""SELECT p.* FROM people p JOIN organizations o ON o.id=p.org_id
                                  WHERE o.code=? AND p.member_code=?""",
                               (org_code, member_code)).fetchone()
            if not person:
                return jsonify(error="Organization code or member code not found."), 404
            matched, distance = match_face(live_path, person["face_path"])
            if not matched:
                return jsonify(error="Face did not match. Please try again."), 401
            now = datetime.now(timezone.utc).isoformat()
            c.execute("INSERT INTO attendance(person_id,org_id,marked_at) VALUES(?,?,?)",
                      (person["id"], person["org_id"], now))
        return jsonify(message="Face matched. Attendance recorded.",
                       member=person["full_name"], marked_at=now)
    except Exception:
        return jsonify(error="Verification failed. Try again with good lighting."), 400
    finally:
        if live_path and os.path.exists(live_path): os.remove(live_path)



@app.post("/api/kiosk/identify")
def kiosk_identify():
    """Shared mobile kiosk: identify a member and alternate check-in/check-out.
    Timestamps and daily attendance boundaries use Asia/Kolkata.
    """
    org_code = (request.form.get("org_code") or "").strip().upper()
    live_path = None
    try:
        live_path = save_image(request.files.get("face"))
        validate_face(live_path)
        with connect() as c:
            org = c.execute("SELECT id FROM organizations WHERE code=?", (org_code,)).fetchone()
            if not org:
                return jsonify(error="Organization code not recognized."), 404
            people = c.execute(
                "SELECT id, full_name, member_code, face_path FROM people WHERE org_id=?",
                (org["id"],)
            ).fetchall()

        if not people:
            return jsonify(error="No members are enrolled for this organization."), 404

        matches = []
        for person in people:
            try:
                ok, distance = match_face(live_path, person["face_path"])
                if ok:
                    matches.append((distance, person))
            except Exception:
                continue

        if not matches:
            return jsonify(status="no_match",
                           message="Face not recognized. Please try again or ask an administrator."), 200

        matches.sort(key=lambda item: item[0])
        best_distance, best = matches[0]
        if len(matches) > 1 and abs(matches[1][0] - best_distance) < 0.03:
            return jsonify(status="ambiguous",
                           message="Identity is uncertain. Please try again or contact an administrator."), 200

        now = datetime.now(IST)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        now_iso = now.isoformat(timespec="seconds")

        with connect() as c:
            events = c.execute("""
                SELECT event_type, marked_at FROM attendance
                WHERE person_id=? AND org_id=? AND marked_at>=?
                ORDER BY marked_at DESC LIMIT 1
            """, (best["id"], org["id"], day_start)).fetchone()

            if events is None:
                event_type = "CHECK_IN"
            elif events["event_type"] == "CHECK_IN":
                event_type = "CHECK_OUT"
            else:
                return jsonify(status="already_completed",
                               message="Today's check-in and check-out are already recorded.",
                               member=best["full_name"]), 200

            c.execute("""
                INSERT INTO attendance(person_id,org_id,event_type,marked_at)
                VALUES(?,?,?,?)
            """, (best["id"], org["id"], event_type, now_iso))

        label = "Check-in" if event_type == "CHECK_IN" else "Check-out"
        return jsonify(status="success", event_type=event_type, event_label=label,
                       message=f"{label} recorded successfully.",
                       member=best["full_name"], marked_at=now_iso,
                       timezone="Asia/Kolkata")
    except Exception:
        return jsonify(error="Kiosk scan failed. Check camera and lighting, then try again."), 400
    finally:
        if live_path and os.path.exists(live_path):
            os.remove(live_path)

@app.get("/api/admin/report")
@admin_required
def report():
    with connect() as c:
        rows = c.execute("""SELECT p.full_name,p.member_code,a.event_type,a.marked_at
                            FROM attendance a JOIN people p ON p.id=a.person_id
                            WHERE a.org_id=? ORDER BY a.marked_at DESC LIMIT 500""",
                         (session["org_id"],)).fetchall()
        count = c.execute("SELECT COUNT(*) FROM people WHERE org_id=?", (session["org_id"],)).fetchone()[0]
    return jsonify(member_count=count, records=[dict(r) for r in rows])

@app.get("/health")
def health():
    return jsonify(status="ok")


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)


