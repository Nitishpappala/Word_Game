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
