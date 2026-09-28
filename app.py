from flask import Flask, request, redirect, url_for, session, render_template_string
import psycopg
from psycopg.rows import dict_row
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


# =========================================================
# FRIEND SAVING CLUB
# =========================================================

app = Flask("FriendSavingClub")

DB_NAME = "friend_saving_club.db"

app.secret_key = "friend-saving-club-secret-2026"


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn, table_name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    ).fetchone()

    return row is not None


def get_columns(conn, table_name):
    if not table_exists(conn, table_name):
        return []

    rows = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return [row["name"] for row in rows]


def first_existing(columns, possible_names):
    for name in possible_names:
        if name in columns:
            return name

    return None


# =========================================================
# INITIALIZE DATABASE
# =========================================================

def init_db():

    conn = get_db()

    # -----------------------------------------------------
    # New safe tables
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS fsc_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT UNIQUE,
            password_hash TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS fsc_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            transaction_type TEXT NOT NULL,
            txn_date TEXT NOT NULL,
            note TEXT,
            created_at TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS fsc_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'member',
            member_id INTEGER,
            active INTEGER DEFAULT 1
        )
    """)

    # -----------------------------------------------------
    # Default Admin
    # -----------------------------------------------------

    admin = conn.execute(
        "SELECT id FROM fsc_users WHERE username=?",
        ("admin",)
    ).fetchone()

    if not admin:

        conn.execute("""
            INSERT INTO fsc_users
            (username, password_hash, role, member_id, active)
            VALUES (?, ?, ?, ?, ?)
        """, (
            "admin",
            generate_password_hash("1234"),
            "admin",
            None,
            1
        ))

    conn.commit()

    # -----------------------------------------------------
    # Try to migrate old members table
    # -----------------------------------------------------

    try:

        if table_exists(conn, "members"):

            old_columns = get_columns(conn, "members")

            id_col = first_existing(
                old_columns,
                ["id", "member_id"]
            )

            name_col = first_existing(
                old_columns,
                ["name", "member_name", "member"]
            )

            username_col = first_existing(
                old_columns,
                ["username", "user_name", "login"]
            )

            active_col = first_existing(
                old_columns,
                ["active", "status"]
            )

            if name_col:

                old_rows = conn.execute(
                    "SELECT * FROM members"
                ).fetchall()

                for old in old_rows:

                    name = old[name_col]

                    if not name:
                        continue

                    username = None

                    if username_col:
                        username = old[username_col]

                    if not username:
                        username = (
                            str(name)
                            .lower()
                            .replace(" ", "")
                        )

                    existing = conn.execute(
                        "SELECT id FROM fsc_members WHERE name=?",
                        (name,)
                    ).fetchone()

                    if existing:
                        continue

                    conn.execute("""
                        INSERT INTO fsc_members
                        (name, username, password_hash, active, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        name,
                        username,
                        generate_password_hash("1234"),
                        1,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ))

                conn.commit()

    except Exception:
        pass

    # -----------------------------------------------------
    # Try to migrate old transactions table
    # -----------------------------------------------------

    try:

        if table_exists(conn, "transactions"):

            old_columns = get_columns(conn, "transactions")

            amount_col = first_existing(
                old_columns,
                ["amount", "value", "money", "price"]
            )

            type_col = first_existing(
                old_columns,
                ["transaction_type", "type", "kind"]
            )

            date_col = first_existing(
                old_columns,
                ["txn_date", "date", "transaction_date", "created_at"]
            )

            member_id_col = first_existing(
                old_columns,
                ["member_id", "member"]
            )

            member_name_col = first_existing(
                old_columns,
                ["member_name", "name"]
            )

            if amount_col and type_col:

                old_rows = conn.execute(
                    "SELECT * FROM transactions"
                ).fetchall()

                for old in old_rows:

                    try:
                        amount = float(old[amount_col])
                    except Exception:
                        continue

                    old_type = str(old[type_col]).lower()

                    if (
                        "deposit" in old_type
                        or "jama" in old_type
                        or "saving" in old_type
                    ):
                        transaction_type = "jama"

                    elif (
                        "withdraw" in old_type
                        or "payout" in old_type
                        or "taken" in old_type
                        or "payment" in old_type
                    ):
                        transaction_type = "payout"

                    else:
                        continue

                    member_id = None

                    if member_id_col:
                        try:
                            old_member_id = old[member_id_col]

                            if old_member_id:

                                member = conn.execute(
                                    "SELECT id FROM fsc_members WHERE id=?",
                                    (old_member_id,)
                                ).fetchone()

                                if member:
                                    member_id = member["id"]

                        except Exception:
                            pass

                    if member_id is None and member_name_col:

                        member_name = old[member_name_col]

                        member = conn.execute(
                            "SELECT id FROM fsc_members WHERE name=?",
                            (member_name,)
                        ).fetchone()

                        if member:
                            member_id = member["id"]

                    if member_id is None:
                        continue

                    txn_date = datetime.now().strftime("%Y-%m-%d")

                    if date_col:

                        try:

                            old_date = old[date_col]

                            if old_date:
                                txn_date = str(old_date)[:10]

                        except Exception:
                            pass

                    # Avoid obvious duplicate migration
                    existing = conn.execute("""
                        SELECT id
                        FROM fsc_transactions
                        WHERE member_id=?
                        AND amount=?
                        AND transaction_type=?
                        AND txn_date=?
                    """, (
                        member_id,
                        amount,
                        transaction_type,
                        txn_date
                    )).fetchone()

                    if existing:
                        continue

                    conn.execute("""
                        INSERT INTO fsc_transactions
                        (member_id, amount, transaction_type, txn_date, note, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        member_id,
                        amount,
                        transaction_type,
                        txn_date,
                        "Migrated old record",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ))

                conn.commit()

    except Exception:
        pass

    conn.close()


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def money(value):

    try:
        return "₹{:,.2f}".format(float(value))
    except Exception:
        return "₹0.00"


def safe_float(value):

    try:
        return float(value)
    except Exception:
        return 0.0


def current_user():

    user_id = session.get("user_id")

    if not user_id:
        return None

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM fsc_users
        WHERE id=?
        AND active=1
    """, (user_id,)).fetchone()

    conn.close()

    return user


def logged_in():

    return current_user() is not None


def is_admin():

    user = current_user()

    return user is not None and user["role"] == "admin"


def require_login():

    if not logged_in():
        return redirect(url_for("login"))

    return None


def require_admin():

    if not logged_in():
        return redirect(url_for("login"))

    if not is_admin():
        return redirect(url_for("dashboard"))

    return None


# =========================================================
# PAGE TEMPLATE
# =========================================================

def page(title, body, **context):

    user = current_user()

    if user:

        nav = """
        <nav>
            <a href="/dashboard">🏠 Dashboard</a>
            <a href="/members">👥 Members</a>
            <a href="/transaction/add">📥 Jama / Savings Deposit</a>
            <a href="/transactions">📋 Transaction History</a>
            <a href="/report">📊 Monthly Report</a>
            <a href="/change-password">🔐 Change Password</a>
            <a href="/logout">🚪 Logout</a>
        </nav>
        """

    else:

        nav = ""

    template = """
    <!DOCTYPE html>

    <html>

    <head>

        <meta charset="UTF-8">

        <meta name="viewport"
              content="width=device-width, initial-scale=1.0">

        <title>{{ title }} - Friend Saving Club</title>

        <style>

            * {
                box-sizing: border-box;
            }

            body {
                font-family: Arial, sans-serif;
                background: #f4f6f8;
                margin: 0;
                color: #222;
            }

            nav {
                background: #1f2937;
                padding: 14px;
            }

            nav a {
                color: white;
                text-decoration: none;
                margin-right: 15px;
                font-size: 14px;
                display: inline-block;
                margin-bottom: 5px;
            }

            nav a:hover {
                text-decoration: underline;
            }

            .container {
                max-width: 1150px;
                margin: 20px auto;
                padding: 15px;
            }

            .card {
                background: white;
                padding: 20px;
                margin-bottom: 20px;
                border-radius: 12px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }

            .cards {
                display: grid;
                grid-template-columns:
                    repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin-bottom: 20px;
            }

            .stat {
                background: white;
                padding: 20px;
                border-radius: 12px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }

            .stat h3 {
                margin-top: 0;
                font-size: 16px;
            }

            .stat p {
                font-size: 24px;
                font-weight: bold;
                margin-bottom: 0;
            }

            table {
                width: 100%;
                border-collapse: collapse;
                background: white;
            }

            th,
            td {
                padding: 10px;
                border-bottom: 1px solid #ddd;
                text-align: left;
            }

            th {
                background: #eef2f7;
            }

            input,
            select {
                width: 100%;
                padding: 10px;
                margin: 5px 0 12px 0;
                border-radius: 6px;
                border: 1px solid #ccc;
            }

            button,
            .btn {
                display: inline-block;
                padding: 9px 14px;
                border-radius: 6px;
                border: none;
                cursor: pointer;
                background: #2563eb;
                color: white;
                text-decoration: none;
                margin: 3px;
            }

            .btn-danger {
                background: #dc2626;
            }

            .btn-success {
                background: #16a34a;
            }

            .btn-warning {
                background: #d97706;
            }

            .btn-secondary {
                background: #6b7280;
            }

            .form-row {
                display: grid;
                grid-template-columns:
                    repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
            }

            .title {
                margin-top: 0;
            }

            .small {
                color: #666;
                font-size: 13px;
            }

            .login-box {
                max-width: 420px;
                margin: 70px auto;
            }

            .logo {
                text-align: center;
                font-size: 30px;
                font-weight: bold;
                margin-bottom: 20px;
            }

            .text-center {
                text-align: center;
            }

            @media(max-width: 700px) {

                nav a {
                    display: block;
                    margin: 8px 0;
                }

                table {
                    font-size: 13px;
                }

                th,
                td {
                    padding: 7px;
                }

                .container {
                    padding: 10px;
                }

                .card {
                    padding: 14px;
                }

            }

        </style>

    </head>

    <body>

        """ + nav + """

        <div class="container">

            """ + body + """

        </div>

    </body>

    </html>
    """

    context["title"] = title
    context["user"] = user
    context["money"] = money

    return render_template_string(template, **context)


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    if logged_in():
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()

        user = conn.execute("""
            SELECT *
            FROM fsc_users
            WHERE username=?
            AND active=1
        """, (username,)).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password_hash"],
            password
        ):

            session.clear()

            session["user_id"] = user["id"]

            return redirect(url_for("dashboard"))

        error = "Invalid username or password."

    else:

        error = ""

    body = """

    <div class="login-box">

        <div class="logo">
            💰 Friend Saving Club
        </div>

        <div class="card">

            <h2 class="text-center">
                Login / लॉगिन
            </h2>

            {% if error %}
                <p style="color:red;">
                    {{ error }}
                </p>
            {% endif %}

            <form method="POST">

                <label>
                    Username
                </label>

                <input
                    type="text"
                    name="username"
                    required
                >

                <label>
                    Password
                </label>

                <input
                    type="password"
                    name="password"
                    required
                >

                <button type="submit">
                    🔐 Login
                </button>

            </form>

            <p class="small">
                Default Admin Login:
                <br>
                Username: <b>admin</b>
                <br>
                Password: <b>1234</b>
            </p>

        </div>

    </div>

    """

    return page(
        "Login",
        body,
        error=error
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

    login_check = require_login()

    if login_check:
        return login_check

    user = current_user()

    today = datetime.now().strftime("%Y-%m-%d")

    from_date = request.args.get(
        "from_date",
        today[:7] + "-01"
    )

    to_date = request.args.get(
        "to_date",
        today
    )

    conn = get_db()

    # -----------------------------------------------------
    # Conditions
    # -----------------------------------------------------

    conditions = [
        "t.txn_date >= ?",
        "t.txn_date <= ?"
    ]

    params = [
        from_date,
        to_date
    ]

    if user["role"] != "admin":

        conditions.append(
            "t.member_id = ?"
        )

        params.append(user["member_id"])

    where = " AND ".join(conditions)

    # -----------------------------------------------------
    # Total Jama
    # -----------------------------------------------------

    row = conn.execute(f"""
        SELECT COALESCE(SUM(t.amount), 0) AS total
        FROM fsc_transactions t
        WHERE {where}
        AND t.transaction_type='jama'
    """, params).fetchone()

    jama = row["total"]

    # -----------------------------------------------------
    # Total Payout
    # -----------------------------------------------------

    row = conn.execute(f"""
        SELECT COALESCE(SUM(t.amount), 0) AS total
        FROM fsc_transactions t
        WHERE {where}
        AND t.transaction_type='payout'
    """, params).fetchone()

    payout = row["total"]

    balance = jama - payout

    # -----------------------------------------------------
    # Member-wise report
    # -----------------------------------------------------

    member_rows = []

    if user["role"] == "admin":

        members = conn.execute("""
            SELECT *
            FROM fsc_members
            WHERE active=1
            ORDER BY name
        """).fetchall()

    else:

        members = conn.execute("""
            SELECT *
            FROM fsc_members
            WHERE id=?
            AND active=1
        """, (user["member_id"],)).fetchall()

    for member in members:

        mrow = conn.execute("""
            SELECT
                COALESCE(
                    SUM(
                        CASE
                            WHEN transaction_type='jama'
                            THEN amount
                            ELSE 0
                        END
                    ), 0
                ) AS jama,

                COALESCE(
                    SUM(
                        CASE
                            WHEN transaction_type='payout'
                            THEN amount
                            ELSE 0
                        END
                    ), 0
                ) AS payout

            FROM fsc_transactions

            WHERE member_id=?
            AND txn_date >= ?
            AND txn_date <= ?
        """, (
            member["id"],
            from_date,
            to_date
        )).fetchone()

        m_jama = mrow["jama"]
        m_payout = mrow["payout"]

        # User requirement:
        # Wapas Karna Hai = max(Taken - Jama, 0)

        wapas = max(
            m_payout - m_jama,
            0
        )

        member_rows.append({
            "id": member["id"],
            "name": member["name"],
            "jama": m_jama,
            "payout": m_payout,
            "balance": m_jama - m_payout,
            "wapas": wapas
        })

    # -----------------------------------------------------
    # Recent transactions
    # -----------------------------------------------------

    transactions = conn.execute(f"""
        SELECT
            t.*,
            m.name AS member_name

        FROM fsc_transactions t

        LEFT JOIN fsc_members m
        ON m.id=t.member_id

        WHERE {where}

        ORDER BY t.txn_date DESC, t.id DESC

        LIMIT 20
    """, params).fetchall()

    conn.close()

    body = """

    <div class="card">

        <h1 class="title">
            💰 Friend Saving Club
        </h1>

        <p>
            Welcome,
            <b>{{ user['username'] }}</b>
        </p>

        <p class="small">
            Report Period:
            {{ from_date }} → {{ to_date }}
        </p>

    </div>


    <div class="card">

        <h2>
            📅 Select Period
        </h2>

        <form method="GET"
              action="/dashboard">

            <div class="form-row">

                <div>

                    <label>
                        From Date
                    </label>

                    <input
                        type="date"
                        name="from_date"
                        value="{{ from_date }}"
                        required
                    >

                </div>


                <div>

                    <label>
                        To Date
                    </label>

                    <input
                        type="date"
                        name="to_date"
                        value="{{ to_date }}"
                        required
                    >

                </div>

            </div>

            <button type="submit">
                🔍 View Report
            </button>

        </form>

    </div>


    <div class="cards">

        <div class="stat">

            <h3>
                📥 Total Jama
                <br>
                कुल जमा
            </h3>

            <p>
                {{ money(jama) }}
            </p>

        </div>


        <div class="stat">

            <h3>
                📤 Total Payout
                <br>
                कुल भुगतान
            </h3>

            <p>
                {{ money(payout) }}
            </p>

        </div>


        <div class="stat">

            <h3>
                💰 Balance
                <br>
                शेष राशि
            </h3>

            <p>
                {{ money(balance) }}
            </p>

        </div>

    </div>


    <div class="card">

        <h2>
            👥 Member-wise Summary
        </h2>

        <div style="overflow-x:auto;">

            <table>

                <tr>

                    <th>
                        Member
                        <br>
                        सदस्य
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


                {% for m in member_rows %}

                <tr>

                    <td>
                        <b>{{ m['name'] }}</b>
                    </td>

                    <td>
                        {{ money(m['jama']) }}
                    </td>

                    <td>
                        {{ money(m['payout']) }}
                    </td>

                    <td>
                        {{ money(m['balance']) }}
                    </td>

                    <td>
                        <b>{{ money(m['wapas']) }}</b>
                    </td>

                </tr>

                {% endfor %}

            </table>

        </div>

    </div>


    <div class="card">

        <h2>
            📋 Recent Transaction History
        </h2>

        <div style="overflow-x:auto;">

            <table>

                <tr>

                    <th>Date</th>

                    <th>Member</th>

                    <th>Type</th>

                    <th>Amount</th>

                    <th>Note</th>

                </tr>


                {% for t in transactions %}

                <tr>

                    <td>
                        {{ t['txn_date'] }}
                    </td>

                    <td>
                        {{ t['member_name'] or '-' }}
                    </td>

                    <td>

                        {% if t['transaction_type'] == 'jama' %}

                            📥 Jama / Deposit

                        {% else %}

                            📤 Payout / Withdrawal

                        {% endif %}

                    </td>

                    <td>
                        {{ money(t['amount']) }}
                    </td>

                    <td>
                        {{ t['note'] or '-' }}
                    </td>

                </tr>

                {% endfor %}

            </table>

        </div>

    </div>

    """

    return page(
        "Dashboard",
        body,
        from_date=from_date,
        to_date=to_date,
        jama=jama,
        payout=payout,
        balance=balance,
        member_rows=member_rows,
        transactions=transactions
    )


# =========================================================
# MEMBERS
# =========================================================

@app.route("/members")
def members():

    admin_check = require_admin()

    if admin_check:
        return admin_check

    conn = get_db()

    members = conn.execute("""
        SELECT *
        FROM fsc_members
        WHERE active=1
        ORDER BY name
    """).fetchall()

    conn.close()

    body = """

    <div class="card">

        <h1>
            👥 Members / सदस्य
        </h1>

        <a class="btn btn-success"
           href="/member/add">
            ➕ Add Member
        </a>

    </div>


    <div class="card">

        <div style="overflow-x:auto;">

            <table>

                <tr>

                    <th>
                        ID
                    </th>

                    <th>
                        Name
                    </th>

                    <th>
                        Username
                    </th>

                    <th>
                        Action
                    </th>

                </tr>


                {% for m in members %}

                <tr>

                    <td>
                        {{ m['id'] }}
                    </td>

                    <td>
                        {{ m['name'] }}
                    </td>

                    <td>
                        {{ m['username'] }}
                    </td>

                    <td>

                        <a
                            class="btn btn-warning"
                            href="/member/edit/{{ m['id'] }}">
                            ✏️ Edit
                        </a>

                        <a
                            class="btn btn-danger"
                            href="/member/delete/{{ m['id'] }}"
                            onclick="return confirm('Delete this member?')">
                            🗑️ Delete
                        </a>

                    </td>

                </tr>

                {% endfor %}

            </table>

        </div>

    </div>

    """

    return page(
        "Members",
        body,
        members=members
    )


# =========================================================
# ADD MEMBER
# =========================================================

@app.route("/member/add", methods=["GET", "POST"])
def add_member():

    admin_check = require_admin()

    if admin_check:
        return admin_check

    error = ""

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            "1234"
        )

        if not name or not username:

            error = "Name and username are required."

        else:

            conn = get_db()

            try:

                conn.execute("""
                    INSERT INTO fsc_members
                    (name, username, password_hash, active, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    name,
                    username,
                    generate_password_hash(password),
                    1,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))

                member_id = conn.execute(
                    "SELECT last_insert_rowid()"
                ).fetchone()[0]

                conn.execute("""
                    INSERT INTO fsc_users
                    (username, password_hash, role, member_id, active)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    username,
                    generate_password_hash(password),
                    "member",
                    member_id,
                    1
                ))

                conn.commit()

                conn.close()

                return redirect(
                    url_for("members")
                )

            except sqlite3.IntegrityError:

                conn.rollback()
                conn.close()

                error = (
                    "Username already exists."
                )

            except Exception as e:

                conn.rollback()
                conn.close()

                error = str(e)

    body = """

    <div class="card">

        <h1>
            ➕ Add Member
        </h1>

        {% if error %}

        <p style="color:red;">
            {{ error }}
        </p>

        {% endif %}


        <form method="POST">

            <label>
                Member Name
            </label>

            <input
                type="text"
                name="name"
                required
            >


            <label>
                Username
            </label>

            <input
                type="text"
                name="username"
                required
            >


            <label>
                Password
            </label>

            <input
                type="password"
                name="password"
                value="1234"
                required
            >


            <button type="submit">
                💾 Save Member
            </button>

            <a
                class="btn btn-secondary"
                href="/members">
                Cancel
            </a>

        </form>

    </div>

    """

    return page(
        "Add Member",
        body,
        error=error
    )


# =========================================================
# EDIT MEMBER
# =========================================================

@app.route("/member/edit/<int:member_id>", methods=["GET", "POST"])
def edit_member(member_id):

    admin_check = require_admin()

    if admin_check:
        return admin_check

    conn = get_db()

    member = conn.execute("""
        SELECT *
        FROM fsc_members
        WHERE id=?
    """, (member_id,)).fetchone()

    if not member:

        conn.close()

        return redirect(
            url_for("members")
        )

    error = ""

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        try:

            if password:

                conn.execute("""
                    UPDATE fsc_members
                    SET name=?,
                        username=?,
                        password_hash=?
                    WHERE id=?
                """, (
                    name,
                    username,
                    generate_password_hash(password),
                    member_id
                ))

                conn.execute("""
                    UPDATE fsc_users
                    SET username=?,
                        password_hash=?
                    WHERE member_id=?
                """, (
                    username,
                    generate_password_hash(password),
                    member_id
                ))

            else:

                conn.execute("""
                    UPDATE fsc_members
                    SET name=?,
                        username=?
                    WHERE id=?
                """, (
                    name,
                    username,
                    member_id
                ))

                conn.execute("""
                    UPDATE fsc_users
                    SET username=?
                    WHERE member_id=?
                """, (
                    username,
                    member_id
                ))

            conn.commit()

            conn.close()

            return redirect(
                url_for("members")
            )

        except sqlite3.IntegrityError:

            conn.rollback()

            error = "Username already exists."

    conn.close()

    body = """

    <div class="card">

        <h1>
            ✏️ Edit Member
        </h1>

        {% if error %}

        <p style="color:red;">
            {{ error }}
        </p>

        {% endif %}


        <form method="POST">

            <label>
                Member Name
            </label>

            <input
                type="text"
                name="name"
                value="{{ member['name'] }}"
                required
            >


            <label>
                Username
            </label>

            <input
                type="text"
                name="username"
                value="{{ member['username'] }}"
                required
            >


            <label>
                New Password
                <span class="small">
                    (blank = no change)
                </span>
            </label>

            <input
                type="password"
                name="password"
            >


            <button type="submit">
                💾 Update
            </button>

            <a
                class="btn btn-secondary"
                href="/members">
                Cancel
            </a>

        </form>

    </div>

    """

    return page(
        "Edit Member",
        body,
        member=member,
        error=error
    )


# =========================================================
# DELETE MEMBER
# =========================================================

@app.route("/member/delete/<int:member_id>")
def delete_member(member_id):

    admin_check = require_admin()

    if admin_check:
        return admin_check

    conn = get_db()

    conn.execute("""
        UPDATE fsc_members
        SET active=0
        WHERE id=?
    """, (member_id,))

    conn.execute("""
        UPDATE fsc_users
        SET active=0
        WHERE member_id=?
    """, (member_id,))

    conn.commit()

    conn.close()

    return redirect(
        url_for("members")
    )


# =========================================================
# ADD TRANSACTION
# =========================================================

@app.route("/transaction/add", methods=["GET", "POST"])
def add_transaction():

    login_check = require_login()

    if login_check:
        return login_check

    user = current_user()

    conn = get_db()

    if user["role"] == "admin":

        members = conn.execute("""
            SELECT *
            FROM fsc_members
            WHERE active=1
            ORDER BY name
        """).fetchall()

    else:

        members = conn.execute("""
            SELECT *
            FROM fsc_members
            WHERE id=?
            AND active=1
        """, (
            user["member_id"],
        )).fetchall()

    error = ""

    if request.method == "POST":

        if user["role"] == "admin":

            member_id = request.form.get(
                "member_id"
            )

        else:

            member_id = user["member_id"]

        amount = safe_float(
            request.form.get("amount")
        )

        transaction_type = request.form.get(
            "transaction_type"
        )

        txn_date = request.form.get(
            "txn_date"
        )

        note = request.form.get(
            "note",
            ""
        ).strip()

        if (
            not member_id
            or amount <= 0
            or transaction_type not in [
                "jama",
                "payout"
            ]
            or not txn_date
        ):

            error = "Please enter valid details."

        else:

            conn.execute("""
                INSERT INTO fsc_transactions
                (
                    member_id,
                    amount,
                    transaction_type,
                    txn_date,
                    note,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                member_id,
                amount,
                transaction_type,
                txn_date,
                note,
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            ))

            conn.commit()

            conn.close()

            return redirect(
                url_for("dashboard")
            )

    conn.close()

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    body = """

    <div class="card">

        <h1>
            📥 Jama / 📤 Payout
        </h1>

        <p class="small">
            Jama = Savings Deposit
            <br>
            Payout = Member Withdrawal /
            सदस्य को दी गई राशि
        </p>


        {% if error %}

        <p style="color:red;">
            {{ error }}
        </p>

        {% endif %}


        <form method="POST">


            {% if user['role'] == 'admin' %}

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

                {% for m in members %}

                <option value="{{ m['id'] }}">
                    {{ m['name'] }}
                </option>

                {% endfor %}

            </select>

            {% endif %}


            <label>
                Transaction Type
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
                name="amount"
                step="0.01"
                min="0.01"
                required
            >


            <label>
                Date
            </label>

            <input
                type="date"
                name="txn_date"
                value="{{ today }}"
                required
            >


            <label>
                Note / विवरण
            </label>

            <input
                type="text"
                name="note"
                placeholder="Optional"
            >


            <button type="submit">
                💾 Record Transaction
            </button>

        </form>

    </div>

    """

    return page(
        "Record Transaction",
        body,
        members=members,
        error=error,
        today=today
    )


# =========================================================
# TRANSACTIONS
# =========================================================

@app.route("/transactions")
def transactions():

    login_check = require_login()

    if login_check:
        return login_check

    user = current_user()

    conn = get_db()

    if user["role"] == "admin":

        rows = conn.execute("""
            SELECT
                t.*,
                m.name AS member_name

            FROM fsc_transactions t

            LEFT JOIN fsc_members m
            ON m.id=t.member_id

            ORDER BY
                t.txn_date DESC,
                t.id DESC
        """).fetchall()

    else:

        rows = conn.execute("""
            SELECT
                t.*,
                m.name AS member_name

            FROM fsc_transactions t

            LEFT JOIN fsc_members m
            ON m.id=t.member_id

            WHERE t.member_id=?

            ORDER BY
                t.txn_date DESC,
                t.id DESC
        """, (
            user["member_id"],
        )).fetchall()

    conn.close()

    body = """

    <div class="card">

        <h1>
            📋 Transaction History
            <br>
            <span class="small">
                लेन-देन विवरण
            </span>
        </h1>

        <a
            class="btn btn-success"
            href="/transaction/add">
            ➕ Record Transaction
        </a>

    </div>


    <div class="card">

        <div style="overflow-x:auto;">

            <table>

                <tr>

                    <th>
                        Date
                    </th>

                    <th>
                        Member
                    </th>

                    <th>
                        Type
                    </th>

                    <th>
                        Amount
                    </th>

                    <th>
                        Note
                    </th>

                    {% if user['role'] == 'admin' %}

                    <th>
                        Action
                    </th>

                    {% endif %}

                </tr>


                {% for t in rows %}

                <tr>

                    <td>
                        {{ t['txn_date'] }}
                    </td>

                    <td>
                        {{ t['member_name'] }}
                    </td>

                    <td>

                        {% if t['transaction_type'] == 'jama' %}

                            📥 Jama

                        {% else %}

                            📤 Payout

                        {% endif %}

                    </td>

                    <td>
                        {{ money(t['amount']) }}
                    </td>

                    <td>
                        {{ t['note'] or '-' }}
                    </td>


                    {% if user['role'] == 'admin' %}

                    <td>

                        <a
                            class="btn btn-warning"
                            href="/transaction/edit/{{ t['id'] }}">
                            ✏️ Edit
                        </a>

                        <a
                            class="btn btn-danger"
                            href="/transaction/delete/{{ t['id'] }}"
                            onclick="return confirm('Delete this transaction?')">
                            🗑️ Delete
                        </a>

                    </td>

                    {% endif %}

                </tr>

                {% endfor %}

            </table>

        </div>

    </div>

    """

    return page(
        "Transaction History",
        body,
        rows=rows
    )


# =========================================================
# EDIT TRANSACTION
# =========================================================

@app.route(
    "/transaction/edit/<int:transaction_id>",
    methods=["GET", "POST"]
)
def edit_transaction(transaction_id):

    admin_check = require_admin()

    if admin_check:
        return admin_check

    conn = get_db()

    transaction = conn.execute("""
        SELECT *
        FROM fsc_transactions
        WHERE id=?
    """, (
        transaction_id,
    )).fetchone()

    if not transaction:

        conn.close()

        return redirect(
            url_for("transactions")
        )

    members = conn.execute("""
        SELECT *
        FROM fsc_members
        WHERE active=1
        ORDER BY name
    """).fetchall()

    error = ""

    if request.method == "POST":

        member_id = request.form.get(
            "member_id"
        )

        amount = safe_float(
            request.form.get("amount")
        )

        transaction_type = request.form.get(
            "transaction_type"
        )

        txn_date = request.form.get(
            "txn_date"
        )

        note = request.form.get(
            "note",
            ""
        ).strip()

        if (
            not member_id
            or amount <= 0
            or transaction_type not in [
                "jama",
                "payout"
            ]
            or not txn_date
        ):

            error = "Please enter valid details."

        else:

            conn.execute("""
                UPDATE fsc_transactions

                SET member_id=?,
                    amount=?,
                    transaction_type=?,
                    txn_date=?,
                    note=?

                WHERE id=?
            """, (
                member_id,
                amount,
                transaction_type,
                txn_date,
                note,
                transaction_id
            ))

            conn.commit()

            conn.close()

            return redirect(
                url_for("transactions")
            )

    conn.close()

    body = """

    <div class="card">

        <h1>
            ✏️ Edit Transaction
        </h1>


        {% if error %}

        <p style="color:red;">
            {{ error }}
        </p>

        {% endif %}


        <form method="POST">

            <label>
                Member
            </label>

            <select
                name="member_id"
                required
            >

                {% for m in members %}

                <option
                    value="{{ m['id'] }}"
                    {% if m['id'] == transaction['member_id'] %}
                    selected
                    {% endif %}
                >
                    {{ m['name'] }}
                </option>

                {% endfor %}

            </select>


            <label>
                Transaction Type
            </label>

            <select
                name="transaction_type"
                required
            >

                <option
                    value="jama"
                    {% if transaction['transaction_type'] == 'jama' %}
                    selected
                    {% endif %}
                >
                    📥 Jama / Savings Deposit
                </option>

                <option
                    value="payout"
                    {% if transaction['transaction_type'] == 'payout' %}
                    selected
                    {% endif %}
                >
                    📤 Payout / Member Withdrawal
                </option>

            </select>


            <label>
                Amount
            </label>

            <input
                type="number"
                name="amount"
                step="0.01"
                value="{{ transaction['amount'] }}"
                required
            >


            <label>
                Date
            </label>

            <input
                type="date"
                name="txn_date"
                value="{{ transaction['txn_date'] }}"
                required
            >


            <label>
                Note
            </label>

            <input
                type="text"
                name="note"
                value="{{ transaction['note'] or '' }}"
            >


            <button type="submit">
                💾 Update Transaction
            </button>


            <a
                class="btn btn-secondary"
                href="/transactions">
                Cancel
            </a>

        </form>

    </div>

    """

    return page(
        "Edit Transaction",
        body,
        transaction=transaction,
        members=members,
        error=error
    )


# =========================================================
# DELETE TRANSACTION
# =========================================================

@app.route(
    "/transaction/delete/<int:transaction_id>"
)
def delete_transaction(transaction_id):

    admin_check = require_admin()

    if admin_check:
        return admin_check

    conn = get_db()

    conn.execute("""
        DELETE FROM fsc_transactions
        WHERE id=?
    """, (
        transaction_id,
    ))

    conn.commit()

    conn.close()

    return redirect(
        url_for("transactions")
    )


# =========================================================
# REPORT
# =========================================================

@app.route("/report")
def report():

    login_check = require_login()

    if login_check:
        return login_check

    user = current_user()

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    from_date = request.args.get(
        "from_date",
        today[:7] + "-01"
    )

    to_date = request.args.get(
        "to_date",
        today
    )

    conn = get_db()

    if user["role"] == "admin":

        members = conn.execute("""
            SELECT *
            FROM fsc_members
            WHERE active=1
            ORDER BY name
        """).fetchall()

    else:

        members = conn.execute("""
            SELECT *
            FROM fsc_members
            WHERE id=?
            AND active=1
        """, (
            user["member_id"],
        )).fetchall()

    report_rows = []

    for member in members:

        row = conn.execute("""
            SELECT

                COALESCE(
                    SUM(
                        CASE
                            WHEN transaction_type='jama'
                            THEN amount
                            ELSE 0
                        END
                    ), 0
                ) AS jama,

                COALESCE(
                    SUM(
                        CASE
                            WHEN transaction_type='payout'
                            THEN amount
                            ELSE 0
                        END
                    ), 0
                ) AS payout

            FROM fsc_transactions

            WHERE member_id=?
            AND txn_date >= ?
            AND txn_date <= ?
        """, (
            member["id"],
            from_date,
            to_date
        )).fetchone()

        jama = row["jama"]
        payout = row["payout"]

        wapas = max(
            payout - jama,
            0
        )

        report_rows.append({
            "name": member["name"],
            "jama": jama,
            "payout": payout,
            "balance": jama - payout,
            "wapas": wapas
        })

    conn.close()

    total_jama = sum(
        x["jama"]
        for x in report_rows
    )

    total_payout = sum(
        x["payout"]
        for x in report_rows
    )

    total_balance = (
        total_jama - total_payout
    )

    body = """

    <div class="card">

        <h1>
            📊 Monthly / Period Report
        </h1>

        <form method="GET">

            <div class="form-row">

                <div>

                    <label>
                        From Date
                    </label>

                    <input
                        type="date"
                        name="from_date"
                        value="{{ from_date }}"
                        required
                    >

                </div>


                <div>

                    <label>
                        To Date
                    </label>

                    <input
                        type="date"
                        name="to_date"
                        value="{{ to_date }}"
                        required
                    >

                </div>

            </div>


            <button type="submit">
                🔍 Generate Report
            </button>

        </form>

    </div>


    <div class="cards">

        <div class="stat">

            <h3>
                Total Jama
            </h3>

            <p>
                {{ money(total_jama) }}
            </p>

        </div>


        <div class="stat">

            <h3>
                Total Payout
            </h3>

            <p>
                {{ money(total_payout) }}
            </p>

        </div>


        <div class="stat">

            <h3>
                Group Balance
            </h3>

            <p>
                {{ money(total_balance) }}
            </p>

        </div>

    </div>


    <div class="card">

        <h2>
            Member-wise Report
        </h2>

        <div style="overflow-x:auto;">

            <table>

                <tr>

                    <th>
                        Member
                    </th>

                    <th>
                        Total Jama
                    </th>

                    <th>
                        Total Payout
                    </th>

                    <th>
                        Balance
                    </th>

                    <th>
                        Wapas Karna Hai
                    </th>

                </tr>


                {% for r in report_rows %}

                <tr>

                    <td>
                        <b>{{ r['name'] }}</b>
                    </td>

                    <td>
                        {{ money(r['jama']) }}
                    </td>

                    <td>
                        {{ money(r['payout']) }}
                    </td>

                    <td>
                        {{ money(r['balance']) }}
                    </td>

                    <td>
                        <b>
                            {{ money(r['wapas']) }}
                        </b>
                    </td>

                </tr>

                {% endfor %}

            </table>

        </div>

    </div>

    """

    return page(
        "Report",
        body,
        from_date=from_date,
        to_date=to_date,
        report_rows=report_rows,
        total_jama=total_jama,
        total_payout=total_payout,
        total_balance=total_balance
    )


# =========================================================
# CHANGE PASSWORD
# =========================================================

@app.route(
    "/change-password",
    methods=["GET", "POST"]
)
def change_password():

    login_check = require_login()

    if login_check:
        return login_check

    user = current_user()

    error = ""
    success = ""

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
            user["password_hash"],
            old_password
        ):

            error = "Old password is incorrect."

        elif len(new_password) < 4:

            error = (
                "New password must be at least "
                "4 characters."
            )

        elif new_password != confirm_password:

            error = "New passwords do not match."

        else:

            conn = get_db()

            conn.execute("""
                UPDATE fsc_users
                SET password_hash=?
                WHERE id=?
            """, (
                generate_password_hash(
                    new_password
                ),
                user["id"]
            ))

            if user["role"] == "member":

                conn.execute("""
                    UPDATE fsc_members
                    SET password_hash=?
                    WHERE id=?
                """, (
                    generate_password_hash(
                        new_password
                    ),
                    user["member_id"]
                ))

            conn.commit()

            conn.close()

            success = (
                "Password changed successfully."
            )

    body = """

    <div class="card">

        <h1>
            🔐 Change Password
        </h1>


        {% if error %}

        <p style="color:red;">
            {{ error }}
        </p>

        {% endif %}


        {% if success %}

        <p style="color:green;">
            {{ success }}
        </p>

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
                🔐 Change Password
            </button>

        </form>

    </div>

    """

    return page(
        "Change Password",
        body,
        error=error,
        success=success
    )


# =========================================================
# START APPLICATION
# =========================================================

# Render / Gunicorn ke liye database initialize karo
init_db()


if __name__ == "__main__":

    print("")
    print("======================================")
    print("     FRIEND SAVING CLUB")
    print("======================================")
    print("")
    print("Open in browser:")
    print("http://127.0.0.1:5000/")
    print("")
    print("Admin Username: admin")
    print("Admin Password: 1234")
    print("")
    print("Database:", os.path.abspath(DB_NAME))
    print("======================================")
    print("")

    app.run(
        debug=False,
        host="127.0.0.1",
        port=5000
    )
