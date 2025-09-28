import sqlite3, random, re, datetime
from flask import Flask, request, session, redirect, url_for, flash, render_template

app = Flask(__name__)
app.secret_key = "supersecret"
DB = "wordle.db"

# Admin secret code
ADMIN_SECRET_CODE = "SUPERSECRET123"

# -------------------- DB Setup --------------------
def init_db():
    con = sqlite3.connect(DB)
    c = con.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS words(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT UNIQUE
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS games(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        word TEXT,
        date TEXT,
        success INTEGER
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS guesses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER,
        guess TEXT
    )""")
    con.commit()

    # Preload words if empty
    c.execute("SELECT COUNT(*) FROM words")
    if c.fetchone()[0] == 0:
        words = [
            "APPLE", "MANGO", "BERRY", "GRAPE", "PEACH",
            "LEMON", "OLIVE", "GUAVA", "MELON", "CHILI",
            "BREAD", "WATER", "STONE", "CANDY", "MOUSE",
            "HOUSE", "PLANT", "CLOUD", "RIVER", "EARTH"
        ]
        for w in words:
            c.execute("INSERT INTO words(word) VALUES(?)", (w,))
    con.commit()
    con.close()

init_db()


# -------------------- Helpers --------------------
def current_user():
    if "uid" not in session:
        return None
    con = sqlite3.connect(DB)
    c = con.cursor()
    c.execute("SELECT id,username,role FROM users WHERE id=?", (session["uid"],))
    row = c.fetchone()
    con.close()
    if row:
        return {"id": row[0], "username": row[1], "role": row[2]}
    return None

def validate_username(u):
    errors = []
    if len(u) < 5:
        errors.append("Username must be at least 5 characters")
    if not re.match(r'^[A-Za-z]+$', u):
        errors.append("Username must contain only letters (A-Z, a-z)")
    return errors

def validate_password(pw):
    errors = []
    if len(pw) < 5:
        errors.append("Password must be at least 5 characters")
    if not re.search(r'[A-Za-z]', pw):
        errors.append("Password must contain a letter")
    if not re.search(r'[0-9]', pw):
        errors.append("Password must contain a number")
    if not re.search(r'[$%@*]', pw):
        errors.append("Password must contain one special character ($, %, *, @)")
    return errors

def score_guess(secret, guess):
    
    res = ["grey"] * 5
    secret_list = list(secret)
    
    # First pass: mark correct letters in correct position (green)
    for i, ch in enumerate(guess):
        if secret[i] == ch:
            res[i] = "green"
            secret_list[i] = None  # Remove from consideration

    # Second pass: mark correct letters in wrong position (orange)
    for i, ch in enumerate(guess):
        if res[i] == "grey" and ch in secret_list:
            res[i] = "orange"
            secret_list[secret_list.index(ch)] = None  # Remove the matched letter

    # Combine letters and colors
    return list(zip(guess, res))


# -------------------- Routes --------------------
@app.route("/")
def index():
    return render_template("index.html", user=current_user())

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        u = request.form["username"]
        pw = request.form["password"]
        role = request.form["role"]
        admin_code = request.form.get("admin_code","")

        username_errors = validate_username(u)
        password_errors = validate_password(pw)

        if role=="admin" and admin_code != ADMIN_SECRET_CODE:
            flash("Invalid admin code","error")
            return render_template("register.html", user=current_user(), request=request)
        
        if username_errors or password_errors:
            for e in username_errors + password_errors:
                flash(e,"error")
            return render_template("register.html", user=current_user(), request=request)

        con = sqlite3.connect(DB)
        c = con.cursor()
        try:
            c.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)",(u,pw,role))
            con.commit()
            flash("Registration successful. Please login.")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username already exists","error")
        finally:
            con.close()
    return render_template("register.html", user=current_user(), request=request)

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        u = request.form["username"]
        pw = request.form["password"]
        con = sqlite3.connect(DB)
        c = con.cursor()
        c.execute("SELECT id,password FROM users WHERE username=?",(u,))
        row=c.fetchone()
        con.close()
        if row and row[1]==pw:
            session["uid"]=row[0]
            flash("Logged in successfully")
            return redirect(url_for("dashboard"))
        flash("Invalid credentials","error")
    return render_template("login.html", user=current_user(), request=request)

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out")
    return redirect(url_for("index"))
# -------------------- Play Game --------------------
@app.route("/play", methods=["GET", "POST"])
def play():
    user = current_user()
    if not user:
        flash("Please login first", "error")
        return redirect(url_for("login"))

    con = sqlite3.connect(DB)
    c = con.cursor()

    if user["role"] == "admin":
        flash("Admins cannot play the game. Please use reports.", "error")
        return redirect(url_for("dashboard"))

    today = datetime.date.today().isoformat()

    # Count finished games today
    c.execute(
        "SELECT COUNT(*) FROM games WHERE user_id=? AND date=? AND success IS NOT NULL",
        (user["id"], today)
    )
    finished_games_today = c.fetchone()[0]
    allowed_to_start = finished_games_today < 3

    # Check for active unfinished game today
    c.execute(
        "SELECT id, word FROM games WHERE user_id=? AND date=? AND success IS NULL",
        (user["id"], today)
    )
    row = c.fetchone()
    active_game = row[0] if row else None
    secret_word = row[1] if row else None

    finished = False
    finished_msg = ""
    guesses = []

    # Handle starting a new game
    if request.method == "POST" and request.form.get("start") == "1" and allowed_to_start and not active_game:
        c.execute("SELECT word FROM words ORDER BY RANDOM() LIMIT 1")
        secret_word = c.fetchone()[0]
        c.execute(
            "INSERT INTO games(user_id, word, date, success) VALUES (?, ?, ?, NULL)",
            (user["id"], secret_word, today)
        )
        con.commit()
        active_game = c.lastrowid

    # Handle submitting a guess
    if request.method == "POST" and request.form.get("guess") and active_game:
        guess = request.form["guess"].upper()
        if len(guess) != 5:
            flash("Guess must be 5 letters", "error")
        else:
            # Save guess
            c.execute("INSERT INTO guesses(game_id, guess) VALUES (?, ?)", (active_game, guess))
            con.commit()

    # Fetch all guesses for this game
    if active_game:
        c.execute("SELECT guess FROM guesses WHERE game_id=?", (active_game,))
        rows = c.fetchall()
        for g in rows:
            guesses.append(score_guess(secret_word, g[0]))

        # Check if game finished
        last_guess = ''.join([l for l, _ in guesses[-1]]) if guesses else ""
        if last_guess == secret_word:
            finished = True
            finished_msg = "Congratulations! You guessed the word!"
            c.execute("UPDATE games SET success=1 WHERE id=?", (active_game,))
            con.commit()
        elif len(guesses) >= 5:
            finished = True
            finished_msg = f"Better luck next time! The word was {secret_word}"
            c.execute("UPDATE games SET success=0 WHERE id=?", (active_game,))
            con.commit()

    con.close()
    return render_template(
        "play.html",
        user=user,
        allowed_to_start=allowed_to_start,
        active_game=active_game,
        guesses=guesses,
        finished=finished,
        finished_msg=finished_msg
    )

# -------------------- History --------------------
@app.route("/history")
def history():
    user = current_user()
    if not user:
        flash("Please login first","error")
        return redirect(url_for("login"))
    con = sqlite3.connect(DB)
    c = con.cursor()
    c.execute("SELECT date, word, COALESCE(success,0) FROM games WHERE user_id=? ORDER BY date DESC", (user["id"],))
    games = c.fetchall()
    con.close()
    return render_template("history.html", user=user, games=games)

# -------------------- Dashboard --------------------
@app.route("/dashboard")
def dashboard():
    user = current_user()
    if not user:
        flash("Please login first","error")
        return redirect(url_for("login"))
    today = datetime.date.today().isoformat()
    con = sqlite3.connect(DB)
    c = con.cursor()
    c.execute("SELECT COUNT(*) FROM games WHERE user_id=? AND date=?", (user["id"], today))
    games_today = c.fetchone()[0]
    con.close()
    return render_template("dashboard.html", user=user, games_today=games_today)

# -------------------- Admin Reports --------------------
@app.route("/admin_reports")
def admin_reports():
    user = current_user()
    if not user or user["role"]!="admin":
        flash("Access denied","error")
        return redirect(url_for("dashboard"))
    return render_template("admin_reports.html", user=user, daily=None, userreport=None)

@app.route("/admin_daily_report", methods=["POST"])
def admin_daily_report():
    user = current_user()
    if not user or user["role"] != "admin":
        flash("Access denied", "error")
        return redirect(url_for("dashboard"))

    date = request.form["date"]

    con = sqlite3.connect(DB)
    c = con.cursor()
    c.execute(
        "SELECT COUNT(DISTINCT user_id), COUNT(*), SUM(success) FROM games WHERE date=?",
        (date,)
    )
    row = c.fetchone()
    daily = {
        "date": date,
        "users": row[0],
        "games": row[1],
        "correct": row[2] or 0
    }
    con.close()

    return render_template("admin_reports.html", user=user, daily=daily, userreport=None)


@app.route("/admin_user_report", methods=["POST"])
def admin_user_report():
    user = current_user()
    if not user or user["role"] != "admin":
        flash("Access denied", "error")
        return redirect(url_for("dashboard"))

    uname = request.form["username"]

    con = sqlite3.connect(DB)
    c = con.cursor()

    # Get user id
    c.execute("SELECT id FROM users WHERE username=?", (uname,))
    row = c.fetchone()
    if not row:
        flash("User not found", "error")
        return redirect(url_for("admin_reports"))
    uid = row[0]

    # Fetch all games for the user, grouped by date
    c.execute("""
        SELECT date, word, success
        FROM games
        WHERE user_id=?
        ORDER BY date DESC
    """, (uid,))
    rows = c.fetchall()

    # Organize data per date
    report_dict = {}
    for date, word, success in rows:
        if date not in report_dict:
            report_dict[date] = {"games": 0, "correct": 0, "correct_words": [], "wrong_words": []}
        report_dict[date]["games"] += 1
        if success:
            report_dict[date]["correct"] += 1
            report_dict[date]["correct_words"].append(word)
        else:
            report_dict[date]["wrong_words"].append(word)

    # Prepare list of rows for template
    userreport = {
        "username": uname,
        "rows": [
            {
                "date": date,
                "games": info["games"],
                "correct": info["correct"],
                "correct_words": info["correct_words"],
                "wrong_words": info["wrong_words"]
            }
            for date, info in sorted(report_dict.items(), reverse=True)
        ]
    }

    con.close()
    return render_template("admin_reports.html", user=user, daily=None, userreport=userreport)

# -------------------- Run App --------------------
if __name__=="__main__":
    app.run(debug=True)
