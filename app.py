from flask import Flask, request, redirect, url_for, session, render_template_string
import psycopg
from psycopg.rows import dict_row
from psycopg.errors import UniqueViolation
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask("FriendSavingClub")

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "friend-saving-club-secret-2026"
)


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db():
    conn = psycopg.connect(
        os.environ["DATABASE_URL"],
        row_factory=dict_row
    )
    return conn


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db():

    conn = get_db()
    cur = conn.cursor()

    # Members table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fsc_members (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Transactions table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fsc_transactions (
            id SERIAL PRIMARY KEY,
            member_id INTEGER NOT NULL,
            transaction_type TEXT NOT NULL,
            amount NUMERIC(12,2) NOT NULL,
            transaction_date DATE NOT NULL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (member_id)
                REFERENCES fsc_members(id)
                ON DELETE CASCADE
        )
    """)

    # Users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fsc_users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            member_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (member_id)
                REFERENCES fsc_members(id)
                ON DELETE CASCADE
        )
    """)

    conn.commit()

    # Create default admin if not present
    cur.execute(
        "SELECT id FROM fsc_users WHERE username = %s",
        ("admin",)
    )

    admin = cur.fetchone()

    if not admin:
        cur.execute(
            """
            INSERT INTO fsc_users
            (username, password, role)
            VALUES (%s, %s, %s)
            """,
            (
                "admin",
                generate_password_hash("1234"),
                "admin"
            )
        )
        conn.commit()

    cur.close()
    conn.close()


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def current_user():
    if "user_id" not in session:
        return None

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM fsc_users WHERE id = %s",
        (session["user_id"],)
    )

    user = cur.fetchone()

    cur.close()
    conn.close()

    return user


def is_admin():
    user = current_user()
    return user and user["role"] == "admin"


def get_member_for_user():

    user = current_user()

    if not user:
        return None

    if user["role"] == "admin":
        return None

    if not user["member_id"]:
        return None

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM fsc_members WHERE id = %s",
        (user["member_id"],)
    )

    member = cur.fetchone()

    cur.close()
    conn.close()

    return member


# =========================================================
# LOGIN
# =========================================================

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Friend Saving Club - Login</title>

    <meta name="viewport"
          content="width=device-width, initial-scale=1">

    <style>

        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: #f1f5f9;
        }

        .container {
            width: 92%;
            max-width: 420px;
            margin: 70px auto;
        }

        .card {
            background: white;
            padding: 28px;
            border-radius: 18px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.12);
        }

        h1 {
            text-align: center;
            color: #1e3a8a;
            margin-bottom: 5px;
        }

        .subtitle {
            text-align: center;
            color: #64748b;
            margin-bottom: 25px;
        }

        label {
            font-weight: bold;
            display: block;
            margin-top: 15px;
        }

        input {
            width: 100%;
            box-sizing: border-box;
            padding: 12px;
            margin-top: 7px;
            border: 1px solid #cbd5e1;
            border-radius: 10px;
            font-size: 16px;
        }

        button {
            width: 100%;
            padding: 13px;
            margin-top: 22px;
            border: none;
            border-radius: 10px;
            background: #2563eb;
            color: white;
            font-size: 17px;
            font-weight: bold;
        }

        .error {
            background: #fee2e2;
            color: #991b1b;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 15px;
            text-align: center;
        }

    </style>
</head>

<body>

<div class="container">

    <div class="card">

        <h1>Friend Saving Club</h1>

        <div class="subtitle">
            Login / लॉगिन
        </div>

        {% if error %}
        <div class="error">
            {{ error }}
        </div>
        {% endif %}

        <form method="POST">

            <label>
                Username / यूज़रनेम
            </label>

            <input
                type="text"
                name="username"
                required
            >

            <label>
                Password / पासवर्ड
            </label>

            <input
                type="password"
                name="password"
                required
            >

            <button type="submit">
                Login / लॉगिन
            </button>

        </form>

    </div>

</div>

</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "SELECT * FROM fsc_users WHERE username = %s",
            (username,)
        )

        user = cur.fetchone()

        cur.close()
        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session.clear()
            session["user_id"] = user["id"]

            return redirect(url_for("dashboard"))

        return render_template_string(
            LOGIN_HTML,
            error="Invalid username or password"
        )

    return render_template_string(
        LOGIN_HTML,
        error=None
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    # सभी members का overall total
    cur.execute("""
        SELECT
            COALESCE(
                SUM(
                    CASE
                        WHEN transaction_type = 'jama'
                        THEN amount
                        ELSE 0
                    END
                ), 0
            ) AS total_jama,

            COALESCE(
                SUM(
                    CASE
                        WHEN transaction_type = 'payout'
                        THEN amount
                        ELSE 0
                    END
                ), 0
            ) AS total_payout

        FROM fsc_transactions
    """)

    totals = cur.fetchone()

    # Total members
    cur.execute("""
        SELECT COUNT(*) AS count
        FROM fsc_members
    """)

    member_count = cur.fetchone()["count"]

    total_jama = float(totals["total_jama"])
    total_payout = float(totals["total_payout"])

    balance = total_jama - total_payout

    # Overall Wapas Karna Hai
    total_wapas = max(total_payout - total_jama, 0)

    cur.close()
    conn.close()

    html = """
    <!DOCTYPE html>
    <html>

    <head>

        <title>Dashboard - Friend Saving Club</title>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <style>

            body {
                margin: 0;
                font-family: Arial, sans-serif;
                background: #f1f5f9;
            }

            header {
                background: #1e3a8a;
                color: white;
                padding: 18px;
            }

            header h2 {
                margin: 0;
            }

            nav {
                margin-top: 10px;
            }

            nav a {
                color: white;
                text-decoration: none;
                margin-right: 15px;
                font-size: 14px;
            }

            .container {
                width: 94%;
                max-width: 1100px;
                margin: 20px auto;
            }

            .cards {
                display: grid;
                grid-template-columns:
                    repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
            }

            .card {
                background: white;
                padding: 20px;
                border-radius: 15px;
                box-shadow: 0 3px 12px rgba(0,0,0,0.08);
            }

            .title {
                color: #64748b;
                font-size: 14px;
            }

            .value {
                font-size: 28px;
                font-weight: bold;
                margin-top: 8px;
            }

            .green {
                color: #15803d;
            }

            .red {
                color: #dc2626;
            }

            .blue {
                color: #2563eb;
            }

            .orange {
                color: #ea580c;
            }

            .links {
                margin-top: 20px;
            }

            .links a {
                display: inline-block;
                background: white;
                padding: 14px 18px;
                margin: 5px;
                border-radius: 10px;
                text-decoration: none;
                color: #1e3a8a;
                font-weight: bold;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }

        </style>

    </head>

    <body>

    <header>

        <h2>
            Friend Saving Club
        </h2>

        <nav>

            <a href="/dashboard">
                Dashboard
            </a>

            {% if user["role"] == "admin" %}

            <a href="/members">
                Members
            </a>

            <a href="/add_transaction">
                Record Payout
            </a>

            <a href="/report">
                Monthly Report
            </a>

            {% else %}

            <a href="/my_transactions">
                My Transactions
            </a>

            <a href="/report">
                📊 Report
            </a>

            {% endif %}

            <a href="/change_password">
                Change Password
            </a>

            <a href="/logout">
                Logout
            </a>

        </nav>

    </header>


    <div class="container">

        <div class="cards">

            <div class="card">

                <div class="title">
                    📥 Total Jama / कुल जमा
                </div>

                <div class="value green">
                    ₹{{ "%.2f"|format(total_jama) }}
                </div>

            </div>


            <div class="card">

                <div class="title">
                    📤 Total Payout / कुल भुगतान
                </div>

                <div class="value red">
                    ₹{{ "%.2f"|format(total_payout) }}
                </div>

            </div>


            <div class="card">

                <div class="title">
                    💰 Balance / शेष राशि
                </div>

                <div class="value blue">
                    ₹{{ "%.2f"|format(balance) }}
                </div>

            </div>


            <div class="card">

                <div class="title">
                    🔄 Wapas Karna Hai / वापस करना है
                </div>

                <div class="value orange">
                    ₹{{ "%.2f"|format(total_wapas) }}
                </div>

            </div>


            <div class="card">

                <div class="title">
                    👥 Members / सदस्य
                </div>

                <div class="value">
                    {{ member_count }}
                </div>

            </div>

        </div>


        <div class="links">

            {% if user["role"] == "admin" %}

            <a href="/members">
                👥 Manage Members
            </a>

            <a href="/add_transaction">
                📤 Record Payout
            </a>

            <a href="/report">
                📊 Monthly Report
            </a>

            <a href="/transactions">
                📋 Transaction History
            </a>

            {% else %}

            <a href="/my_transactions">
                📋 All Transaction History
            </a>

            <a href="/report">
                📊 Date-wise Report
            </a>

            {% endif %}

        </div>

    </div>

    </body>
    </html>
    """

    return render_template_string(
        html,
        user=user,
        total_jama=total_jama,
        total_payout=total_payout,
        balance=balance,
        total_wapas=total_wapas,
        member_count=member_count
    )


# =========================================================
# MEMBERS
# =========================================================

@app.route("/members")
def members():

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            name,
            username,
            phone,
            created_at
        FROM fsc_members
        ORDER BY id DESC
    """)

    members = cur.fetchall()

    cur.close()
    conn.close()

    html = """
    <!DOCTYPE html>
    <html>

    <head>

        <title>Members - Friend Saving Club</title>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <style>

            body {
                font-family: Arial;
                background: #f1f5f9;
                margin: 0;
            }

            header {
                background: #1e3a8a;
                color: white;
                padding: 18px;
            }

            .container {
                width: 94%;
                max-width: 1100px;
                margin: 20px auto;
            }

            .btn {
                display: inline-block;
                background: #2563eb;
                color: white;
                padding: 10px 15px;
                border-radius: 8px;
                text-decoration: none;
                margin-bottom: 15px;
            }

            .card {
                background: white;
                padding: 15px;
                border-radius: 12px;
                margin-bottom: 12px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }

            .actions a {
                margin-right: 10px;
                text-decoration: none;
            }

            .delete {
                color: #dc2626;
            }

            .edit {
                color: #2563eb;
            }

        </style>

    </head>

    <body>

    <header>

        <h2>
            👥 Members / सदस्य
        </h2>

        <a href="/dashboard"
           style="color:white;">
            Dashboard
        </a>

    </header>


    <div class="container">

        <a class="btn"
           href="/add_member">
            ➕ Add Member / सदस्य जोड़ें
        </a>


        {% for member in members %}

        <div class="card">

            <h3>
                {{ member["name"] }}
            </h3>

            <p>
                Username:
                {{ member["username"] }}
            </p>

            <p>
                Phone:
                {{ member["phone"] or "-" }}
            </p>

            <div class="actions">

                <a class="edit"
                   href="/edit_member/{{ member["id"] }}">
                    ✏️ Edit
                </a>

                <a class="delete"
                   href="/delete_member/{{ member["id"] }}"
                   onclick="return confirm('Delete this member?')">
                    🗑 Delete
                </a>

            </div>

        </div>

        {% else %}

        <div class="card">
            No members found.
        </div>

        {% endfor %}

    </div>

    </body>
    </html>
    """

    return render_template_string(
        html,
        members=members
    )


# =========================================================
# ADD MEMBER
# =========================================================

@app.route("/add_member", methods=["GET", "POST"])
def add_member():

    if not is_admin():
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "1234")

        if not name or not username:
            return "Name and username are required."

        conn = get_db()
        cur = conn.cursor()

        try:

            cur.execute("""
                INSERT INTO fsc_members
                (name, username, password, phone)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (
                name,
                username,
                generate_password_hash(password),
                phone
            ))

            member_id = cur.fetchone()["id"]

            cur.execute("""
                INSERT INTO fsc_users
                (username, password, role, member_id)
                VALUES (%s, %s, %s, %s)
            """, (
                username,
                generate_password_hash(password),
                "member",
                member_id
            ))

            conn.commit()

        except UniqueViolation:

            conn.rollback()
            cur.close()
            conn.close()

            return "Username already exists."

        cur.close()
        conn.close()

        return redirect(url_for("members"))


    html = """
    <!DOCTYPE html>
    <html>

    <head>

        <title>Add Member</title>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <style>

            body {
                font-family: Arial;
                background: #f1f5f9;
            }

            .container {
                width: 92%;
                max-width: 500px;
                margin: 30px auto;
            }

            .card {
                background: white;
                padding: 25px;
                border-radius: 15px;
            }

            input {
                width: 100%;
                box-sizing: border-box;
                padding: 12px;
                margin: 7px 0 15px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
            }

            button {
                width: 100%;
                padding: 12px;
                background: #2563eb;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
            }

        </style>

    </head>

    <body>

    <div class="container">

        <div class="card">

            <h2>
                ➕ Add Member
            </h2>

            <form method="POST">

                <label>Name / नाम</label>

                <input
                    type="text"
                    name="name"
                    required
                >


                <label>Username</label>

                <input
                    type="text"
                    name="username"
                    required
                >


                <label>Phone / मोबाइल</label>

                <input
                    type="text"
                    name="phone"
                >


                <label>Password / पासवर्ड</label>

                <input
                    type="text"
                    name="password"
                    value="1234"
                >


                <button type="submit">
                    Save Member
                </button>

            </form>

        </div>

    </div>

    </body>
    </html>
    """

    return render_template_string(html)


# =========================================================
# EDIT MEMBER
# =========================================================

@app.route("/edit_member/<int:member_id>", methods=["GET", "POST"])
def edit_member(member_id):

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM fsc_members WHERE id = %s",
        (member_id,)
    )

    member = cur.fetchone()

    if not member:
        cur.close()
        conn.close()
        return "Member not found."

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        phone = request.form.get("phone", "").strip()

        cur.execute("""
            UPDATE fsc_members
            SET name = %s,
                username = %s,
                phone = %s
            WHERE id = %s
        """, (
            name,
            username,
            phone,
            member_id
        ))

        cur.execute("""
            UPDATE fsc_users
            SET username = %s
            WHERE member_id = %s
        """, (
            username,
            member_id
        ))

        conn.commit()

        cur.close()
        conn.close()

        return redirect(url_for("members"))

    cur.close()
    conn.close()

    html = """
    <!DOCTYPE html>
    <html>

    <head>

        <title>Edit Member</title>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <style>

            body {
                font-family: Arial;
                background: #f1f5f9;
            }

            .container {
                width: 92%;
                max-width: 500px;
                margin: 30px auto;
            }

            .card {
                background: white;
                padding: 25px;
                border-radius: 15px;
            }

            input {
                width: 100%;
                box-sizing: border-box;
                padding: 12px;
                margin: 7px 0 15px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
            }

            button {
                width: 100%;
                padding: 12px;
                background: #2563eb;
                color: white;
                border: none;
                border-radius: 8px;
            }

        </style>

    </head>

    <body>

    <div class="container">

        <div class="card">

            <h2>
                ✏️ Edit Member
            </h2>

            <form method="POST">

                <label>Name</label>

                <input
                    type="text"
                    name="name"
                    value="{{ member['name'] }}"
                    required
                >


                <label>Username</label>

                <input
                    type="text"
                    name="username"
                    value="{{ member['username'] }}"
                    required
                >


                <label>Phone</label>

                <input
                    type="text"
                    name="phone"
                    value="{{ member['phone'] or '' }}"
                >


                <button type="submit">
                    Update Member
                </button>

            </form>

        </div>

    </div>

    </body>
    </html>
    """

    return render_template_string(
        html,
        member=member
    )


# =========================================================
# DELETE MEMBER
# =========================================================

@app.route("/delete_member/<int:member_id>")
def delete_member(member_id):

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT username FROM fsc_members WHERE id = %s",
        (member_id,)
    )

    member = cur.fetchone()

    if member:

        cur.execute(
            "DELETE FROM fsc_users WHERE member_id = %s",
            (member_id,)
        )

        cur.execute(
            "DELETE FROM fsc_members WHERE id = %s",
            (member_id,)
        )

        conn.commit()

    cur.close()
    conn.close()

    return redirect(url_for("members"))


# =========================================================
# ADD TRANSACTION
# =========================================================

@app.route("/add_transaction", methods=["GET", "POST"])
def add_transaction():

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, name
        FROM fsc_members
        ORDER BY name
    """)

    members = cur.fetchall()

    if request.method == "POST":

        member_id = request.form.get("member_id")
        transaction_type = request.form.get("transaction_type")
        amount = request.form.get("amount")
        transaction_date = request.form.get("transaction_date")
        note = request.form.get("note", "").strip()

        cur.execute("""
            INSERT INTO fsc_transactions
            (
                member_id,
                transaction_type,
                amount,
                transaction_date,
                note
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            member_id,
            transaction_type,
            amount,
            transaction_date,
            note
        ))

        conn.commit()

        cur.close()
        conn.close()

        return redirect(url_for("transactions"))

    cur.close()
    conn.close()

    today = datetime.now().strftime("%Y-%m-%d")

    html = """
    <!DOCTYPE html>
    <html>

    <head>

        <title>Record Transaction</title>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <style>

            body {
                font-family: Arial;
                background: #f1f5f9;
            }

            .container {
                width: 92%;
                max-width: 500px;
                margin: 30px auto;
            }

            .card {
                background: white;
                padding: 25px;
                border-radius: 15px;
            }

            input, select, textarea {
                width: 100%;
                box-sizing: border-box;
                padding: 12px;
                margin: 7px 0 15px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
            }

            button {
                width: 100%;
                padding: 12px;
                background: #2563eb;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
            }

        </style>

    </head>

    <body>

    <div class="container">

        <div class="card">

            <h2>
                📤 Record Transaction
            </h2>

            <form method="POST">

                <label>
                    Member / सदस्य
                </label>

                <select
                    name="member_id"
                    required
                >

                    <option value="">
                        Select Member
                    </option>

                    {% for member in members %}

                    <option value="{{ member['id'] }}">
                        {{ member['name'] }}
                    </option>

                    {% endfor %}

                </select>


                <label>
                    Type / प्रकार
                </label>

                <select
                    name="transaction_type"
                    required
                >

                    <option value="jama">
                        📥 Jama / Savings Deposit
                    </option>

                    <option value="payout">
                        📤 Payout / Member Withdrawal
                    </option>

                </select>


                <label>
                    Amount / राशि
                </label>

                <input
                    type="number"
                    step="0.01"
                    name="amount"
                    required
                >


                <label>
                    Date / तारीख
                </label>

                <input
                    type="date"
                    name="transaction_date"
                    value="{{ today }}"
                    required
                >


                <label>
                    Note / विवरण
                </label>

                <textarea
                    name="note"
                    rows="3"
                ></textarea>


                <button type="submit">
                    Save Transaction
                </button>

            </form>

        </div>

    </div>

    </body>
    </html>
    """

    return render_template_string(
        html,
        members=members,
        today=today
    )


# =========================================================
# TRANSACTION HISTORY - ADMIN
# =========================================================

@app.route("/transactions")
def transactions():

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            t.id,
            t.transaction_type,
            t.amount,
            t.transaction_date,
            t.note,
            m.name AS member_name

        FROM fsc_transactions t

        JOIN fsc_members m
        ON t.member_id = m.id

        ORDER BY
            t.transaction_date DESC,
            t.id DESC
    """)

    transactions = cur.fetchall()

    cur.close()
    conn.close()

    html = """
    <!DOCTYPE html>
    <html>

    <head>

        <title>Transaction History</title>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <style>

            body {
                font-family: Arial;
                background: #f1f5f9;
                margin: 0;
            }

            header {
                background: #1e3a8a;
                color: white;
                padding: 18px;
            }

            .container {
                width: 94%;
                max-width: 1100px;
                margin: 20px auto;
            }

            .card {
                background: white;
                padding: 15px;
                border-radius: 12px;
                margin-bottom: 12px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }

            .jama {
                color: #15803d;
                font-weight: bold;
            }

            .payout {
                color: #dc2626;
                font-weight: bold;
            }

            .delete {
                color: #dc2626;
                text-decoration: none;
            }

        </style>

    </head>

    <body>

    <header>

        <h2>
            📋 Transaction History
        </h2>

        <a href="/dashboard"
           style="color:white;">
            Dashboard
        </a>

    </header>


    <div class="container">

        {% for t in transactions %}

        <div class="card">

            <h3>
                {{ t["member_name"] }}
            </h3>

            {% if t["transaction_type"] == "jama" %}

            <div class="jama">
                📥 Jama: ₹{{ "%.2f"|format(t["amount"]) }}
            </div>

            {% else %}

            <div class="payout">
                📤 Payout: ₹{{ "%.2f"|format(t["amount"]) }}
            </div>

            {% endif %}

            <p>
                Date:
                {{ t["transaction_date"] }}
            </p>

            <p>
                Note:
                {{ t["note"] or "-" }}
            </p>

        <a href="/edit_transaction/{{ t['id'] }}"
   style="margin-right:10px;">
    ✏️ Edit
</a>

<a class="delete"
   href="/delete_transaction/{{ t['id'] }}"
   onclick="return confirm('Delete this transaction?')">
    🗑 Delete
</a>

        </div>

        {% else %}

        <div class="card">
            No transactions found.
        </div>

        {% endfor %}

    </div>

    </body>
    </html>
    """

    return render_template_string(
        html,
        transactions=transactions
    )


# =========================================================
# DELETE TRANSACTION
# =========================================================

@app.route("/edit_transaction/<int:transaction_id>", methods=["GET", "POST"])
def edit_transaction(transaction_id):

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        member_id = request.form.get("member_id")
        transaction_type = request.form.get("transaction_type")
        amount = request.form.get("amount")
        transaction_date = request.form.get("transaction_date")
        note = request.form.get("note")

        cur.execute(
            """
            UPDATE fsc_transactions
            SET member_id = %s,
                transaction_type = %s,
                amount = %s,
                transaction_date = %s,
                note = %s
            WHERE id = %s
            """,
            (
                member_id,
                transaction_type,
                amount,
                transaction_date,
                note,
                transaction_id
            )
        )

        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for("transactions"))

    cur.execute(
        """
        SELECT *
        FROM fsc_transactions
        WHERE id = %s
        """,
        (transaction_id,)
    )

    transaction = cur.fetchone()

    cur.execute(
        """
        SELECT id, name
        FROM fsc_members
        ORDER BY name
        """
    )

    members = cur.fetchall()

    cur.close()
    conn.close()

    if not transaction:
        return redirect(url_for("transactions"))

    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Edit Transaction</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>

<body style="font-family:Arial; max-width:600px; margin:30px auto; padding:20px;">

<h2>✏️ Edit Transaction</h2>

<form method="POST">

<label>Member</label><br>
<select name="member_id" required style="width:100%; padding:10px; margin-bottom:15px;">
    {% for member in members %}
        <option value="{{ member.id }}"
            {% if member.id == transaction.member_id %}selected{% endif %}>
            {{ member.name }}
        </option>
    {% endfor %}
</select>

<label>Transaction Type</label><br>
<select name="transaction_type" required style="width:100%; padding:10px; margin-bottom:15px;">
    <option value="jama"
        {% if transaction.transaction_type == "jama" %}selected{% endif %}>
        Jama / Savings Deposit
    </option>

    <option value="payout"
        {% if transaction.transaction_type == "payout" %}selected{% endif %}>
        Payout / Member Withdrawal
    </option>
</select>

<label>Amount</label><br>
<input type="number"
       name="amount"
       value="{{ transaction.amount }}"
       step="0.01"
       min="0"
       required
       style="width:100%; padding:10px; margin-bottom:15px;">

<label>Date</label><br>
<input type="date"
       name="transaction_date"
       value="{{ transaction.transaction_date }}"
       required
       style="width:100%; padding:10px; margin-bottom:15px;">

<label>Note</label><br>
<input type="text"
       name="note"
       value="{{ transaction.note or '' }}"
       style="width:100%; padding:10px; margin-bottom:20px;">

<button type="submit"
        style="padding:12px 20px; cursor:pointer;">
    💾 Update Transaction
</button>

</form>

<br>

<a href="{{ url_for('transactions') }}">⬅️ Back to Transaction History</a>

</body>
</html>
""", transaction=transaction, members=members)


@app.route("/delete_transaction/<int:transaction_id>")
def delete_transaction(transaction_id):

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        DELETE FROM fsc_transactions
        WHERE id = %s
        """,
        (transaction_id,)
    )

    conn.commit()

    cur.close()
    conn.close()

    return redirect(url_for("transactions"))


# =========================================================
# MEMBER TRANSACTIONS
# =========================================================

@app.route("/my_transactions")
def my_transactions():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    # सभी members की summary
    cur.execute("""
        SELECT
            m.id,
            m.name,
            COALESCE(SUM(
                CASE
                    WHEN t.transaction_type = 'jama'
                    THEN t.amount
                    ELSE 0
                END
            ), 0) AS total_jama,

            COALESCE(SUM(
                CASE
                    WHEN t.transaction_type = 'payout'
                    THEN t.amount
                    ELSE 0
                END
            ), 0) AS total_payout

        FROM fsc_members m

        LEFT JOIN fsc_transactions t
            ON m.id = t.member_id

        GROUP BY m.id, m.name

        ORDER BY m.name
    """)

    members = cur.fetchall()

    # सभी transactions
    cur.execute("""
        SELECT
            t.id,
            m.name AS member_name,
            t.transaction_type,
            t.amount,
            t.transaction_date,
            t.note

        FROM fsc_transactions t

        JOIN fsc_members m
            ON m.id = t.member_id

        ORDER BY
            t.transaction_date DESC,
            t.id DESC
    """)

    transactions = cur.fetchall()

    cur.close()
    conn.close()

    # Overall totals
    total_jama = sum(
        float(m["total_jama"])
        for m in members
    )

    total_payout = sum(
        float(m["total_payout"])
        for m in members
    )

    balance = total_jama - total_payout

    html = """
    <!DOCTYPE html>
    <html>

    <head>

        <title>All Transactions</title>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <style>

            body {
                font-family: Arial;
                background: #f1f5f9;
                margin: 0;
            }

            header {
                background: #1e3a8a;
                color: white;
                padding: 18px;
            }

            .container {
                width: 94%;
                max-width: 1000px;
                margin: 20px auto;
            }

            .summary {
                display: grid;
                grid-template-columns:
                    repeat(auto-fit, minmax(180px, 1fr));
                gap: 12px;
            }

            .card {
                background: white;
                padding: 15px;
                border-radius: 12px;
                margin-bottom: 12px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.08);
            }

            .green {
                color: #15803d;
            }

            .red {
                color: #dc2626;
            }

            .blue {
                color: #2563eb;
            }

            .orange {
                color: #ea580c;
            }

            table {
                width: 100%;
                border-collapse: collapse;
                background: white;
                border-radius: 10px;
                overflow: hidden;
            }

            th, td {
                padding: 10px;
                border-bottom: 1px solid #e5e7eb;
                text-align: left;
            }

            th {
                background: #e2e8f0;
            }

            .table-container {
                overflow-x: auto;
            }

        </style>

    </head>

    <body>

    <header>

        <h2>
            👥 All Members Transactions
        </h2>

        <a href="/dashboard"
           style="color:white;">
            Dashboard
        </a>

    </header>


    <div class="container">

        <div class="summary">

            <div class="card green">
                <b>Total Jama</b>
                <h2>
                    ₹{{ "%.2f"|format(total_jama) }}
                </h2>
            </div>

            <div class="card red">
                <b>Total Payout</b>
                <h2>
                    ₹{{ "%.2f"|format(total_payout) }}
                </h2>
            </div>

            <div class="card blue">
                <b>Balance</b>
                <h2>
                    ₹{{ "%.2f"|format(balance) }}
                </h2>
            </div>

        </div>


        <h2>📊 Member-wise Summary</h2>


        {% for m in members %}

        {% set member_balance =
            m["total_jama"]|float -
            m["total_payout"]|float
        %}

        {% set return_amount =
            m["total_payout"]|float -
            m["total_jama"]|float
        %}

        <div class="card">

            <h3>
                👤 {{ m["name"] }}
            </h3>

            <p class="green">
                📥 Total Jama:
                <b>
                    ₹{{ "%.2f"|format(m["total_jama"]|float) }}
                </b>
            </p>

            <p class="red">
                📤 Total Payout:
                <b>
                    ₹{{ "%.2f"|format(m["total_payout"]|float) }}
                </b>
            </p>

            <p class="blue">
                💰 Balance:
                <b>
                    ₹{{ "%.2f"|format(member_balance) }}
                </b>
            </p>

            <p class="orange">
                🔄 Wapas Karna Hai:
                <b>
                    ₹{{ "%.2f"|format(return_amount if return_amount > 0 else 0) }}
                </b>
            </p>

        </div>

        {% endfor %}


        <h2>📋 Complete Transaction History</h2>


        <div class="table-container">

        <table>

            <tr>
                <th>Member</th>
                <th>Type</th>
                <th>Amount</th>
                <th>Date</th>
                <th>Note</th>
            </tr>


            {% for t in transactions %}

            <tr>

                <td>
                    {{ t["member_name"] }}
                </td>

                <td>

                    {% if t["transaction_type"] == "jama" %}

                    <span class="green">
                        📥 Jama
                    </span>

                    {% else %}

                    <span class="red">
                        📤 Payout
                    </span>

                    {% endif %}

                </td>

                <td>
                    ₹{{ "%.2f"|format(t["amount"]|float) }}
                </td>

                <td>
                    {{ t["transaction_date"] }}
                </td>

                <td>
                    {{ t["note"] or "-" }}
                </td>

            </tr>

            {% else %}

            <tr>
                <td colspan="5">
                    No transactions found.
                </td>
            </tr>

            {% endfor %}

        </table>

        </div>

    </div>

    </body>
    </html>
    """

    return render_template_string(
        html,
        members=members,
        transactions=transactions,
        total_jama=total_jama,
        total_payout=total_payout,
        balance=balance
    )

# =========================================================
# REPORT
# =========================================================

@app.route("/report", methods=["GET", "POST"])
def report():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    from_date = request.form.get("from_date", "")
    to_date = request.form.get("to_date", "")

    report_data = []

    totals = {
        "jama": 0,
        "payout": 0,
        "balance": 0
    }

    if from_date and to_date:

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                m.id,
                m.name,

                COALESCE(
                    SUM(
                        CASE
                            WHEN t.transaction_type = 'jama'
                            THEN t.amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS jama,

                COALESCE(
                    SUM(
                        CASE
                            WHEN t.transaction_type = 'payout'
                            THEN t.amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS payout

            FROM fsc_members m

            LEFT JOIN fsc_transactions t
            ON m.id = t.member_id

            AND t.transaction_date
            BETWEEN %s AND %s

            GROUP BY
                m.id,
                m.name

            ORDER BY
                m.name
        """, (
            from_date,
            to_date
        ))

        rows = cur.fetchall()

        for row in rows:

            jama = float(row["jama"])
            payout = float(row["payout"])

            balance = jama - payout

            wapas = max(payout - jama, 0)

            report_data.append({
                "name": row["name"],
                "jama": jama,
                "payout": payout,
                "balance": balance,
                "wapas": wapas
            })

            totals["jama"] += jama
            totals["payout"] += payout

        totals["balance"] = (
            totals["jama"] -
            totals["payout"]
        )

        cur.close()
        conn.close()


    html = """
    <!DOCTYPE html>
    <html>

    <head>

        <title>Date-wise Report</title>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <style>

            body {
                font-family: Arial;
                background: #f1f5f9;
                margin: 0;
            }

            header {
                background: #1e3a8a;
                color: white;
                padding: 18px;
            }

            .container {
                width: 94%;
                max-width: 1100px;
                margin: 20px auto;
            }

            .card {
                background: white;
                padding: 18px;
                border-radius: 12px;
                margin-bottom: 15px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.08);
            }

            input {
                padding: 10px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                margin: 5px;
            }

            button {
                padding: 11px 18px;
                background: #2563eb;
                color: white;
                border: none;
                border-radius: 8px;
                cursor: pointer;
            }

            table {
                width: 100%;
                border-collapse: collapse;
                background: white;
            }

            th, td {
                padding: 10px;
                border-bottom: 1px solid #e2e8f0;
                text-align: left;
            }

            th {
                background: #e2e8f0;
            }

            .green {
                color: #15803d;
            }

            .red {
                color: #dc2626;
            }

            .blue {
                color: #2563eb;
            }

            .orange {
                color: #ea580c;
            }

            .table-container {
                overflow-x: auto;
            }

            @media(max-width:700px) {

                table {
                    font-size: 13px;
                }

                th, td {
                    padding: 7px;
                }

                input {
                    width: 90%;
                    margin: 5px 0;
                }

                button {
                    margin-top: 8px;
                }

            }

        </style>

    </head>

    <body>

    <header>

        <h2>
            📊 Date-wise Report / तारीख अनुसार रिपोर्ट
        </h2>

        <a href="/dashboard"
           style="color:white;">
            Dashboard
        </a>

    </header>


    <div class="container">


        <div class="card">

            <h3>
                📅 Select Period
            </h3>

            <form method="POST">

                <label>
                    From Date:
                </label>

                <input
                    type="date"
                    name="from_date"
                    value="{{ from_date }}"
                    required
                >

                <br>

                <label>
                    To Date:
                </label>

                <input
                    type="date"
                    name="to_date"
                    value="{{ to_date }}"
                    required
                >

                <br>

                <button type="submit">
                    📊 Generate Report
                </button>

            </form>

        </div>


        {% if report_data %}

        <div class="card">

            <h3>
                📅 Period:
                {{ from_date }}
                →
                {{ to_date }}
            </h3>

            <p class="green">
                📥 Total Jama:
                <b>
                    ₹{{ "%.2f"|format(totals["jama"]) }}
                </b>
            </p>

            <p class="red">
                📤 Total Payout:
                <b>
                    ₹{{ "%.2f"|format(totals["payout"]) }}
                </b>
            </p>

            <p class="blue">
                💰 Group Balance:
                <b>
                    ₹{{ "%.2f"|format(totals["balance"]) }}
                </b>
            </p>

        </div>


        <div class="card">

            <h3>
                👥 Member-wise Summary
            </h3>

            <div class="table-container">

            <table>

                <tr>

                    <th>
                        Member
                    </th>

                    <th>
                        Jama
                    </th>

                    <th>
                        Payout
                    </th>

                    <th>
                        Balance
                    </th>

                    <th>
                        Wapas Karna Hai
                    </th>

                </tr>


                {% for r in report_data %}

                <tr>

                    <td>
                        👤 {{ r["name"] }}
                    </td>

                    <td class="green">
                        ₹{{ "%.2f"|format(r["jama"]) }}
                    </td>

                    <td class="red">
                        ₹{{ "%.2f"|format(r["payout"]) }}
                    </td>

                    <td>
                        ₹{{ "%.2f"|format(r["balance"]) }}
                    </td>

                    <td class="orange">
                        ₹{{ "%.2f"|format(r["wapas"]) }}
                    </td>

                </tr>

                {% endfor %}

            </table>

            </div>

        </div>

        {% elif from_date and to_date %}

        <div class="card">

            No records found for this period.

        </div>

        {% endif %}


    </div>

    </body>

    </html>
    """

    return render_template_string(
        html,
        report_data=report_data,
        totals=totals,
        from_date=from_date,
        to_date=to_date
    )


# =========================================================
# CHANGE PASSWORD
# =========================================================

@app.route("/change_password", methods=["GET", "POST"])
def change_password():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    message = ""

    if request.method == "POST":

        old_password = request.form.get(
            "old_password",
            ""
        )

        new_password = request.form.get(
            "new_password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        if not check_password_hash(
            user["password"],
            old_password
        ):

            message = "Old password is incorrect."

        elif new_password != confirm_password:

            message = "New passwords do not match."

        elif len(new_password) < 4:

            message = "Password must be at least 4 characters."

        else:

            conn = get_db()
            cur = conn.cursor()

            cur.execute("""
                UPDATE fsc_users
                SET password = %s
                WHERE id = %s
            """, (
                generate_password_hash(new_password),
                user["id"]
            ))

            # Also update member password
            if user["member_id"]:

                cur.execute("""
                    UPDATE fsc_members
                    SET password = %s
                    WHERE id = %s
                """, (
                    generate_password_hash(new_password),
                    user["member_id"]
                ))

            conn.commit()

            cur.close()
            conn.close()

            message = "Password changed successfully."

    html = """
    <!DOCTYPE html>
    <html>

    <head>

        <title>Change Password</title>

        <meta name="viewport"
              content="width=device-width, initial-scale=1">

        <style>

            body {
                font-family: Arial;
                background: #f1f5f9;
            }

            .container {
                width: 92%;
                max-width: 500px;
                margin: 30px auto;
            }

            .card {
                background: white;
                padding: 25px;
                border-radius: 15px;
            }

            input {
                width: 100%;
                box-sizing: border-box;
                padding: 12px;
                margin: 7px 0 15px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
            }

            button {
                width: 100%;
                padding: 12px;
                background: #2563eb;
                color: white;
                border: none;
                border-radius: 8px;
            }

            .message {
                padding: 10px;
                background: #dbeafe;
                border-radius: 8px;
                margin-bottom: 15px;
            }

        </style>

    </head>

    <body>

    <div class="container">

        <div class="card">

            <h2>
                🔐 Change Password
            </h2>

            {% if message %}

            <div class="message">
                {{ message }}
            </div>

            {% endif %}

            <form method="POST">

                <label>
                    Old Password
                </label>

                <input
                    type="password"
                    name="old_password"
                    required
                >


                <label>
                    New Password
                </label>

                <input
                    type="password"
                    name="new_password"
                    required
                >


                <label>
                    Confirm New Password
                </label>

                <input
                    type="password"
                    name="confirm_password"
                    required
                >


                <button type="submit">
                    Change Password
                </button>

            </form>

        </div>

    </div>

    </body>
    </html>
    """

    return render_template_string(
        html,
        message=message
    )


# =========================================================
# INITIALIZE DATABASE
# =========================================================

init_db()


# =========================================================
# RUN LOCAL
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=False,
        host="127.0.0.1",
        port=5000
    )
