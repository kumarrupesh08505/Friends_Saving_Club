from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    render_template_string,
    Response
)

import psycopg
from psycopg.rows import dict_row
from psycopg.errors import UniqueViolation

import os
import csv
import io

from datetime import datetime, date
from zoneinfo import ZoneInfo

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


# =========================================================
# APP
# =========================================================

app = Flask("FriendSavingClub")

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "friend-saving-club-secret-2026"
)

IST = ZoneInfo("Asia/Kolkata")


# =========================================================
# DATE HELPER
# =========================================================

def today_india():

    return datetime.now(
        IST
    ).strftime("%Y-%m-%d")


# =========================================================
# DATABASE
# =========================================================

def get_conn():

    database_url = os.environ.get(
        "DATABASE_URL"
    )

    if not database_url:
        raise Exception(
            "DATABASE_URL is not set"
        )

    return psycopg.connect(
        database_url,
        row_factory=dict_row
    )


# =========================================================
# INIT DATABASE
# =========================================================

def init_db():

    conn = get_conn()
    cur = conn.cursor()

    # =====================================================
    # MEMBERS
    # =====================================================

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

    # =====================================================
    # REGULAR TRANSACTIONS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fsc_transactions (
            id SERIAL PRIMARY KEY,
            member_id INTEGER
                REFERENCES fsc_members(id)
                ON DELETE CASCADE,

            transaction_type TEXT NOT NULL,

            amount NUMERIC(12,2) NOT NULL,

            transaction_date DATE NOT NULL,

            note TEXT,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # USERS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fsc_users (
            id SERIAL PRIMARY KEY,

            username TEXT UNIQUE NOT NULL,

            password TEXT NOT NULL,

            role TEXT NOT NULL,

            member_id INTEGER
                REFERENCES fsc_members(id)
                ON DELETE CASCADE,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # LOANS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fsc_loans (
            id SERIAL PRIMARY KEY,

            member_id INTEGER
                REFERENCES fsc_members(id)
                ON DELETE CASCADE,

            amount NUMERIC(12,2) NOT NULL,

            loan_date DATE NOT NULL,

            note TEXT,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # EMI
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fsc_loan_emi (
            id SERIAL PRIMARY KEY,

            loan_id INTEGER
                REFERENCES fsc_loans(id)
                ON DELETE CASCADE,

            member_id INTEGER
                REFERENCES fsc_members(id)
                ON DELETE CASCADE,

            amount NUMERIC(12,2) NOT NULL,

            emi_date DATE NOT NULL,

            note TEXT,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # MONTHLY DUE
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fsc_monthly_due (
            id SERIAL PRIMARY KEY,

            member_id INTEGER
                REFERENCES fsc_members(id)
                ON DELETE CASCADE,

            due_month DATE NOT NULL,

            saving_amount NUMERIC(12,2)
                DEFAULT 0,

            emi_amount NUMERIC(12,2)
                DEFAULT 0,

            note TEXT,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(member_id, due_month)
        )
    """)

    # =====================================================
    # DEFAULT ADMIN
    # =====================================================

    cur.execute("""
        SELECT id
        FROM fsc_users
        WHERE username = 'admin'
    """)

    admin = cur.fetchone()

    if not admin:

        cur.execute("""
            INSERT INTO fsc_users
            (
                username,
                password,
                role
            )

            VALUES (%s, %s, %s)
        """, (
            "admin",
            generate_password_hash("1234"),
            "admin"
        ))

    conn.commit()

    cur.close()
    conn.close()


# =========================================================
# USER HELPERS
# =========================================================

def current_user():

    if "user_id" not in session:
        return None

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM fsc_users
        WHERE id = %s
    """, (
        session["user_id"],
    ))

    user = cur.fetchone()

    cur.close()
    conn.close()

    return user


def is_admin():

    user = current_user()

    return bool(
        user
        and user["role"] == "admin"
    )


# =========================================================
# LOGIN
# =========================================================

LOGIN_HTML = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Friend Saving Club</title>

<style>

body {
    font-family: Arial;
    background:
    linear-gradient(
        135deg,
        #667eea,
        #764ba2
    );

    margin: 0;
}

.box {

    width: 90%;
    max-width: 400px;

    margin: 90px auto;

    background: white;

    padding: 30px;

    border-radius: 18px;

    box-sizing: border-box;

    box-shadow:
    0 10px 30px
    rgba(0,0,0,0.2);
}

h1 {
    text-align: center;
}

input {

    width: 100%;

    padding: 13px;

    margin: 8px 0;

    box-sizing: border-box;

    border-radius: 8px;

    border: 1px solid #ccc;
}

button {

    width: 100%;

    padding: 13px;

    background: #667eea;

    color: white;

    border: none;

    border-radius: 8px;

    font-size: 16px;

    cursor: pointer;
}

.error {

    color: red;

    text-align: center;
}

</style>

</head>

<body>

<div class="box">

<h1>
💰 Friend Saving Club
</h1>

<p style="text-align:center;color:#666;">
Savings • Loans • EMI • Reports
</p>

{% if error %}

<p class="error">
{{ error }}
</p>

{% endif %}

<form method="POST">

<input
name="username"
placeholder="Username"
required
>

<input
type="password"
name="password"
placeholder="Password"
required
>

<button>
Login
</button>

</form>

</div>

</body>

</html>

"""


@app.route(
    "/",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        username = request.form.get(
            "username"
        )

        password = request.form.get(
            "password"
        )

        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
            SELECT *
            FROM fsc_users
            WHERE username = %s
        """, (
            username,
        ))

        user = cur.fetchone()

        cur.close()
        conn.close()

        if (
            user
            and check_password_hash(
                user["password"],
                password
            )
        ):

            session["user_id"] = user["id"]

            session["role"] = user["role"]

            return redirect(
                url_for("dashboard")
            )

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

    return redirect(
        url_for("login")
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    user = current_user()

    if not user:

        return redirect(
            url_for("login")
        )

    conn = get_conn()
    cur = conn.cursor()

    # =====================================================
    # TOTAL JAMA
    # =====================================================

    cur.execute("""
        SELECT
            COALESCE(
                SUM(amount),
                0
            ) AS total_jama

        FROM fsc_transactions

        WHERE transaction_type = 'jama'
    """)

    total_jama = float(
        cur.fetchone()["total_jama"]
    )

    # =====================================================
    # TOTAL LOAN
    # =====================================================

    cur.execute("""
        SELECT
            COALESCE(
                SUM(amount),
                0
            ) AS total_loan

        FROM fsc_loans
    """)

    total_loan = float(
        cur.fetchone()["total_loan"]
    )

    # =====================================================
    # TOTAL EMI
    # =====================================================

    cur.execute("""
        SELECT
            COALESCE(
                SUM(amount),
                0
            ) AS total_emi

        FROM fsc_loan_emi
    """)

    total_emi = float(
        cur.fetchone()["total_emi"]
    )

    # =====================================================
    # GROUP BALANCE
    # =====================================================

    total_amount = (
        total_jama
        - total_loan
        + total_emi
    )

    outstanding_loan = max(
        total_loan - total_emi,
        0
    )

    # =====================================================
    # MEMBER COUNT
    # =====================================================

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM fsc_members
    """)

    member_count = cur.fetchone()["count"]

    # =====================================================
    # CURRENT MONTH
    # =====================================================

    current_month = datetime.now(
        IST
    ).strftime("%Y-%m-01")

    # =====================================================
    # CURRENT MONTH SAVING
    # =====================================================

    cur.execute("""
        SELECT
            COALESCE(
                SUM(amount),
                0
            ) AS amount

        FROM fsc_transactions

        WHERE transaction_type = 'jama'

        AND DATE_TRUNC(
            'month',
            transaction_date
        )
        =
        DATE_TRUNC(
            'month',
            %s::date
        )
    """, (
        current_month,
    ))

    current_month_saving = float(
        cur.fetchone()["amount"]
    )

    # =====================================================
    # CURRENT MONTH LOAN
    # =====================================================

    cur.execute("""
        SELECT
            COALESCE(
                SUM(amount),
                0
            ) AS amount

        FROM fsc_loans

        WHERE DATE_TRUNC(
            'month',
            loan_date
        )
        =
        DATE_TRUNC(
            'month',
            %s::date
        )
    """, (
        current_month,
    ))

    current_month_loan = float(
        cur.fetchone()["amount"]
    )

    # =====================================================
    # CURRENT MONTH EMI
    # =====================================================

    cur.execute("""
        SELECT
            COALESCE(
                SUM(amount),
                0
            ) AS amount

        FROM fsc_loan_emi

        WHERE DATE_TRUNC(
            'month',
            emi_date
        )
        =
        DATE_TRUNC(
            'month',
            %s::date
        )
    """, (
        current_month,
    ))

    current_month_emi = float(
        cur.fetchone()["amount"]
    )

    # =====================================================
    # CURRENT MONTH DUE
    # =====================================================

    cur.execute("""
        SELECT
            COALESCE(
                SUM(saving_amount),
                0
            ) AS saving,

            COALESCE(
                SUM(emi_amount),
                0
            ) AS emi

        FROM fsc_monthly_due

        WHERE due_month = %s
    """, (
        current_month,
    ))

    due = cur.fetchone()

    monthly_due_saving = float(
        due["saving"]
    )

    monthly_due_emi = float(
        due["emi"]
    )

    cur.close()
    conn.close()

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Dashboard</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;

    margin: 0;
}

.header {

    background:
    linear-gradient(
        135deg,
        #667eea,
        #764ba2
    );

    color: white;

    padding: 20px;
}

.logout {

    float: right;

    color: white;

    text-decoration: none;

    background:
    rgba(255,255,255,0.15);

    padding: 8px 12px;

    border-radius: 7px;
}

.container {

    width: 94%;

    max-width: 1200px;

    margin: 20px auto;
}

.cards {

    display: grid;

    grid-template-columns:
    repeat(
        auto-fit,
        minmax(180px,1fr)
    );

    gap: 15px;
}

.card {

    background: white;

    padding: 20px;

    border-radius: 14px;

    box-shadow:
    0 5px 15px
    rgba(0,0,0,0.08);
}

.card h3 {

    color: #555;

    margin-top: 0;
}

.amount {

    font-size: 24px;

    font-weight: bold;
}

.menu {

    margin-top: 25px;

    display: grid;

    grid-template-columns:
    repeat(
        auto-fit,
        minmax(190px,1fr)
    );

    gap: 12px;
}

.menu a {

    background: white;

    padding: 16px;

    border-radius: 10px;

    text-decoration: none;

    color: #333;

    box-shadow:
    0 4px 10px
    rgba(0,0,0,0.08);
}

.menu a:hover {

    transform: translateY(-2px);

}

.section-title {

    margin-top: 30px;

}

</style>

</head>

<body>

<div class="header">

<a
class="logout"
href="/logout">
Logout
</a>

<h1>
💰 Friend Saving Club
</h1>

<p>
Welcome, {{ user["username"] }}
</p>

</div>


<div class="container">

<h2 class="section-title">
📊 Overall Summary
</h2>

<div class="cards">

<div class="card">

<h3>
💵 Regular Jama
</h3>

<div class="amount">
₹{{ "%.2f"|format(total_jama) }}
</div>

</div>


<div class="card">

<h3>
🏦 Loan Given
</h3>

<div class="amount">
₹{{ "%.2f"|format(total_loan) }}
</div>

</div>


<div class="card">

<h3>
💳 EMI Received
</h3>

<div class="amount">
₹{{ "%.2f"|format(total_emi) }}
</div>

</div>


<div class="card">

<h3>
📌 Outstanding Loan
</h3>

<div class="amount">
₹{{ "%.2f"|format(outstanding_loan) }}
</div>

</div>


<div class="card">

<h3>
💰 Actual Group Balance
</h3>

<div class="amount">
₹{{ "%.2f"|format(total_amount) }}
</div>

</div>


<div class="card">

<h3>
👥 Members
</h3>

<div class="amount">
{{ member_count }}
</div>

</div>

</div>


<h2 class="section-title">
📅 Current Month
</h2>

<div class="cards">

<div class="card">

<h3>
💵 This Month Saving
</h3>

<div class="amount">
₹{{ "%.2f"|format(current_month_saving) }}
</div>

</div>


<div class="card">

<h3>
🏦 This Month Loan
</h3>

<div class="amount">
₹{{ "%.2f"|format(current_month_loan) }}
</div>

</div>


<div class="card">

<h3>
💳 This Month EMI
</h3>

<div class="amount">
₹{{ "%.2f"|format(current_month_emi) }}
</div>

</div>


<div class="card">

<h3>
📅 Saving Due
</h3>

<div class="amount">
₹{{ "%.2f"|format(monthly_due_saving) }}
</div>

</div>


<div class="card">

<h3>
📅 EMI Due
</h3>

<div class="amount">
₹{{ "%.2f"|format(monthly_due_emi) }}
</div>

</div>

</div>


<h2 class="section-title">
⚙️ Menu
</h2>

<div class="menu">

<a href="/members">
👥 All Members
</a>

<a href="/member_summary">
📊 Member Summary
</a>

<a href="/savings">
💵 Saving History
</a>

<a href="/loans">
🏦 Loan History
</a>

<a href="/emi">
💳 EMI History
</a>

<a href="/report">
📊 Complete Report
</a>

<a href="/due_summary">
📌 Due Summary
</a>

<a href="/monthly_dashboard">
📈 Monthly Dashboard
</a>

{% if user["role"] == "admin" %}

<a href="/add_member">
➕ Add Member
</a>

<a href="/add_saving">
➕ Add Monthly Saving
</a>

<a href="/add_loan">
🏦 Give Loan
</a>

<a href="/add_emi">
💳 Receive EMI
</a>

<a href="/monthly_due">
📅 Monthly Due Amount
</a>

{% endif %}

<a href="/change_password">
🔐 Change Password
</a>

</div>

</div>

</body>

</html>

"""

    return render_template_string(
        html,
        user=user,
        total_jama=total_jama,
        total_loan=total_loan,
        total_emi=total_emi,
        outstanding_loan=outstanding_loan,
        total_amount=total_amount,
        member_count=member_count,
        current_month_saving=current_month_saving,
        current_month_loan=current_month_loan,
        current_month_emi=current_month_emi,
        monthly_due_saving=monthly_due_saving,
        monthly_due_emi=monthly_due_emi
    )


# =========================================================
# MEMBERS
# =========================================================

@app.route("/members")
def members():

    user = current_user()

    if not user:
        return redirect(
            url_for("login")
        )

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM fsc_members
        ORDER BY name
    """)

    members = cur.fetchall()

    cur.close()
    conn.close()

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Members</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.container {

    width: 94%;

    max-width: 1000px;

    margin: 20px auto;
}

.card {

    background: white;

    padding: 18px;

    margin-bottom: 12px;

    border-radius: 12px;

    box-shadow:
    0 4px 10px
    rgba(0,0,0,0.08);
}

.btn {

    display: inline-block;

    padding: 9px 13px;

    background: #667eea;

    color: white;

    border-radius: 7px;

    text-decoration: none;

    margin: 3px;
}

.delete {

    background: #e74c3c;
}

.detail {

    background: #16a085;
}

</style>

</head>

<body>

<div class="container">

<h1>
👥 All Members
</h1>

<a class="btn"
href="/dashboard">
⬅ Dashboard
</a>

{% if user["role"] == "admin" %}

<a class="btn"
href="/add_member">
➕ Add Member
</a>

{% endif %}

<hr>

{% for m in members %}

<div class="card">

<h2>
{{ m["name"] }}
</h2>

<p>
👤 Username:
{{ m["username"] }}
</p>

<p>
📱 Phone:
{{ m["phone"] or "-" }}
</p>

<a
class="btn detail"
href="/member_detail/{{ m["id"] }}">
📊 View Details
</a>

{% if user["role"] == "admin" %}

<a
class="btn"
href="/edit_member/{{ m["id"] }}">
✏ Edit
</a>

<a
class="btn delete"
href="/delete_member/{{ m["id"] }}"
onclick="return confirm('Delete this member?')">
🗑 Delete
</a>

{% endif %}

</div>

{% endfor %}

</div>

</body>

</html>

"""

    return render_template_string(
        html,
        members=members,
        user=user
    )


# =========================================================
# ADD MEMBER
# =========================================================

@app.route(
    "/add_member",
    methods=["GET", "POST"]
)
def add_member():

    if not is_admin():
        return redirect(
            url_for("dashboard")
        )

    if request.method == "POST":

        name = request.form.get("name")

        username = request.form.get(
            "username"
        )

        password = request.form.get(
            "password"
        )

        phone = request.form.get(
            "phone"
        )

        conn = get_conn()
        cur = conn.cursor()

        try:

            hashed_password = (
                generate_password_hash(
                    password
                )
            )

            cur.execute("""
                INSERT INTO fsc_members
                (
                    name,
                    username,
                    password,
                    phone
                )

                VALUES (%s,%s,%s,%s)

                RETURNING id
            """, (
                name,
                username,
                hashed_password,
                phone
            ))

            member_id = cur.fetchone()["id"]

            cur.execute("""
                INSERT INTO fsc_users
                (
                    username,
                    password,
                    role,
                    member_id
                )

                VALUES (%s,%s,%s,%s)
            """, (
                username,
                hashed_password,
                "member",
                member_id
            ))

            conn.commit()

        except UniqueViolation:

            conn.rollback()

            cur.close()
            conn.close()

            return """
            <h2>
            Username already exists.
            </h2>

            <a href="/add_member">
            Go Back
            </a>
            """

        cur.close()
        conn.close()

        return redirect(
            url_for("members")
        )

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Add Member</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.box {

    width: 94%;

    max-width: 500px;

    margin: 30px auto;

    background: white;

    padding: 25px;

    border-radius: 14px;
}

input {

    width: 100%;

    padding: 12px;

    margin: 8px 0;

    box-sizing: border-box;
}

button {

    width: 100%;

    padding: 12px;

    background: #667eea;

    color: white;

    border: none;

    border-radius: 8px;
}

</style>

</head>

<body>

<div class="box">

<h1>
➕ Add Member
</h1>

<form method="POST">

<input
name="name"
placeholder="Member Name"
required
>

<input
name="username"
placeholder="Username"
required
>

<input
type="password"
name="password"
placeholder="Password"
required
>

<input
name="phone"
placeholder="Phone Number"
>

<button>
Add Member
</button>

</form>

<p>
<a href="/members">
⬅ Back
</a>
</p>

</div>

</body>

</html>

"""

    return render_template_string(
        html
    )


# =========================================================
# EDIT MEMBER
# =========================================================

@app.route(
    "/edit_member/<int:id>",
    methods=["GET", "POST"]
)
def edit_member(id):

    if not is_admin():
        return redirect(
            url_for("dashboard")
        )

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM fsc_members
        WHERE id = %s
    """, (
        id,
    ))

    member = cur.fetchone()

    if not member:

        cur.close()
        conn.close()

        return "Member not found"

    if request.method == "POST":

        name = request.form.get("name")

        username = request.form.get(
            "username"
        )

        phone = request.form.get(
            "phone"
        )

        try:

            cur.execute("""
                UPDATE fsc_members

                SET
                    name = %s,
                    username = %s,
                    phone = %s

                WHERE id = %s
            """, (
                name,
                username,
                phone,
                id
            ))

            cur.execute("""
                UPDATE fsc_users

                SET username = %s

                WHERE member_id = %s
            """, (
                username,
                id
            ))

            conn.commit()

        except UniqueViolation:

            conn.rollback()

            cur.close()
            conn.close()

            return """
            <h2>
            Username already exists.
            </h2>

            <a href="/members">
            Back
            </a>
            """

        cur.close()
        conn.close()

        return redirect(
            url_for("members")
        )

    cur.close()
    conn.close()

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Edit Member</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.box {

    width: 94%;

    max-width: 500px;

    margin: 30px auto;

    background: white;

    padding: 25px;

    border-radius: 14px;
}

input {

    width: 100%;

    padding: 12px;

    margin: 8px 0;

    box-sizing: border-box;
}

button {

    width: 100%;

    padding: 12px;

    background: #667eea;

    color: white;

    border: none;

    border-radius: 8px;
}

</style>

</head>

<body>

<div class="box">

<h1>
✏ Edit Member
</h1>

<form method="POST">

<input
name="name"
value="{{ member["name"] }}"
required
>

<input
name="username"
value="{{ member["username"] }}"
required
>

<input
name="phone"
value="{{ member["phone"] or "" }}"
>

<button>
Update
</button>

</form>

<p>
<a href="/members">
⬅ Back
</a>
</p>

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

@app.route(
    "/delete_member/<int:id>"
)
def delete_member(id):

    if not is_admin():
        return redirect(
            url_for("dashboard")
        )

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM fsc_members

        WHERE id = %s
    """, (
        id,
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        url_for("members")
    )


# =========================================================
# MEMBER DETAIL
# =========================================================

@app.route(
    "/member_detail/<int:id>"
)
def member_detail(id):

    user = current_user()

    if not user:
        return redirect(
            url_for("login")
        )

    conn = get_conn()
    cur = conn.cursor()

    # Member
    cur.execute("""
        SELECT *
        FROM fsc_members
        WHERE id = %s
    """, (
        id,
    ))

    member = cur.fetchone()

    if not member:

        cur.close()
        conn.close()

        return "Member not found"

    # Jama
    cur.execute("""
        SELECT
            COALESCE(
                SUM(amount),
                0
            ) AS amount

        FROM fsc_transactions

        WHERE member_id = %s

        AND transaction_type = 'jama'
    """, (
        id,
    ))

    jama = float(
        cur.fetchone()["amount"]
    )

    # Loan
    cur.execute("""
        SELECT
            COALESCE(
                SUM(amount),
                0
            ) AS amount

        FROM fsc_loans

        WHERE member_id = %s
    """, (
        id,
    ))

    loan = float(
        cur.fetchone()["amount"]
    )

    # EMI
    cur.execute("""
        SELECT
            COALESCE(
                SUM(amount),
                0
            ) AS amount

        FROM fsc_loan_emi

        WHERE member_id = %s
    """, (
        id,
    ))

    emi = float(
        cur.fetchone()["amount"]
    )

    outstanding = max(
        loan - emi,
        0
    )

    # Transactions
    cur.execute("""
        SELECT
            t.id,
            t.amount,
            t.transaction_date,
            t.note

        FROM fsc_transactions t

        WHERE t.member_id = %s

        AND t.transaction_type = 'jama'

        ORDER BY
            t.transaction_date DESC,
            t.id DESC
    """, (
        id,
    ))

    savings = cur.fetchall()

    # Loans
    cur.execute("""
        SELECT
            l.id,
            l.amount,
            l.loan_date,
            l.note

        FROM fsc_loans l

        WHERE l.member_id = %s

        ORDER BY
            l.loan_date DESC,
            l.id DESC
    """, (
        id,
    ))

    loans = cur.fetchall()

    # EMI
    cur.execute("""
        SELECT
            e.id,
            e.amount,
            e.emi_date,
            e.note

        FROM fsc_loan_emi e

        WHERE e.member_id = %s

        ORDER BY
            e.emi_date DESC,
            e.id DESC
    """, (
        id,
    ))

    emis = cur.fetchall()

    cur.close()
    conn.close()

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Member Detail</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.container {

    width: 94%;

    max-width: 1100px;

    margin: 20px auto;
}

.profile {

    background:
    linear-gradient(
        135deg,
        #667eea,
        #764ba2
    );

    color: white;

    padding: 22px;

    border-radius: 15px;
}

.cards {

    display: grid;

    grid-template-columns:
    repeat(
        auto-fit,
        minmax(180px,1fr)
    );

    gap: 12px;

    margin-top: 15px;
}

.card {

    background: white;

    padding: 18px;

    border-radius: 12px;

    box-shadow:
    0 4px 10px
    rgba(0,0,0,0.08);
}

.amount {

    font-size: 22px;

    font-weight: bold;
}

table {

    width: 100%;

    border-collapse: collapse;

    background: white;

    margin-top: 12px;
}

th, td {

    padding: 10px;

    border: 1px solid #ddd;

    text-align: center;
}

th {

    background: #667eea;

    color: white;
}

.section {

    margin-top: 25px;
}

.btn {

    display: inline-block;

    padding: 9px 13px;

    background: #555;

    color: white;

    text-decoration: none;

    border-radius: 7px;

    margin-top: 10px;
}

.green {

    color: green;

    font-weight: bold;
}

.red {

    color: red;

    font-weight: bold;
}

.purple {

    color: #8e44ad;

    font-weight: bold;
}

</style>

</head>

<body>

<div class="container">

<div class="profile">

<h1>
{{ member["name"] }}
</h1>

<p>
👤 Username:
{{ member["username"] }}
</p>

<p>
📱 Phone:
{{ member["phone"] or "-" }}
</p>

<a
class="btn"
style="background:white;color:#333;"
href="/members">
⬅ Members
</a>

</div>


<div class="cards">

<div class="card">

<h3>
💵 Regular Jama
</h3>

<div class="amount">
₹{{ "%.2f"|format(jama) }}
</div>

</div>


<div class="card">

<h3>
🏦 Loan Given
</h3>

<div class="amount">
₹{{ "%.2f"|format(loan) }}
</div>

</div>


<div class="card">

<h3>
💳 EMI Received
</h3>

<div class="amount">
₹{{ "%.2f"|format(emi) }}
</div>

</div>


<div class="card">

<h3>
📌 Outstanding
</h3>

<div class="amount">
₹{{ "%.2f"|format(outstanding) }}
</div>

</div>

</div>


<div class="section">

<h2>
💵 Saving History
</h2>

<div style="overflow-x:auto;">

<table>

<tr>

<th>
Date
</th>

<th>
Amount
</th>

<th>
Note
</th>

{% if user["role"] == "admin" %}
<th>
Action
</th>
{% endif %}

</tr>

{% for s in savings %}

<tr>

<td>
{{ s["transaction_date"] }}
</td>

<td class="green">
₹{{ "%.2f"|format(s["amount"]|float) }}
</td>

<td>
{{ s["note"] or "-" }}
</td>

{% if user["role"] == "admin" %}

<td>

<a href="/edit_saving/{{ s["id"] }}">
✏ Edit
</a>

</td>

{% endif %}

</tr>

{% endfor %}

</table>

</div>

</div>


<div class="section">

<h2>
🏦 Loan History
</h2>

<div style="overflow-x:auto;">

<table>

<tr>

<th>
Date
</th>

<th>
Loan
</th>

<th>
Note
</th>

</tr>

{% for l in loans %}

<tr>

<td>
{{ l["loan_date"] }}
</td>

<td class="purple">
₹{{ "%.2f"|format(l["amount"]|float) }}
</td>

<td>
{{ l["note"] or "-" }}
</td>

</tr>

{% endfor %}

</table>

</div>

</div>


<div class="section">

<h2>
💳 EMI History
</h2>

<div style="overflow-x:auto;">

<table>

<tr>

<th>
Date
</th>

<th>
EMI
</th>

<th>
Note
</th>

</tr>

{% for e in emis %}

<tr>

<td>
{{ e["emi_date"] }}
</td>

<td class="green">
₹{{ "%.2f"|format(e["amount"]|float) }}
</td>

<td>
{{ e["note"] or "-" }}
</td>

</tr>

{% endfor %}

</table>

</div>

</div>

</div>

</body>

</html>

"""

    return render_template_string(
        html,
        member=member,
        jama=jama,
        loan=loan,
        emi=emi,
        outstanding=outstanding,
        savings=savings,
        loans=loans,
        emis=emis,
        user=user
    )


# =========================================================
# ADD SAVING
# =========================================================

@app.route(
    "/add_saving",
    methods=["GET", "POST"]
)
def add_saving():

    if not is_admin():
        return redirect(
            url_for("dashboard")
        )

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            name

        FROM fsc_members

        ORDER BY name
    """)

    members = cur.fetchall()

    if request.method == "POST":

        member_id = request.form.get(
            "member_id"
        )

        amount = request.form.get(
            "amount"
        )

        transaction_date = request.form.get(
            "transaction_date"
        )

        note = request.form.get(
            "note"
        )

        cur.execute("""
            INSERT INTO fsc_transactions
            (
                member_id,
                transaction_type,
                amount,
                transaction_date,
                note
            )

            VALUES
            (
                %s,
                'jama',
                %s,
                %s,
                %s
            )
        """, (
            member_id,
            amount,
            transaction_date,
            note
        ))

        conn.commit()

        cur.close()
        conn.close()

        return redirect(
            url_for("savings")
        )

    cur.close()
    conn.close()

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Monthly Saving</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.box {

    width: 94%;

    max-width: 500px;

    margin: 30px auto;

    background: white;

    padding: 25px;

    border-radius: 14px;
}

input, select, textarea {

    width: 100%;

    padding: 12px;

    margin: 8px 0;

    box-sizing: border-box;
}

button {

    width: 100%;

    padding: 12px;

    background: #667eea;

    color: white;

    border: none;

    border-radius: 8px;
}

</style>

</head>

<body>

<div class="box">

<h1>
💵 Add Monthly Saving
</h1>

<form method="POST">

<select
name="member_id"
required
>

<option value="">
Select Member
</option>

{% for m in members %}

<option value="{{ m["id"] }}">
{{ m["name"] }}
</option>

{% endfor %}

</select>

<input
type="number"
step="0.01"
name="amount"
placeholder="Saving Amount"
required
>

<input
type="date"
name="transaction_date"
value="{{ today }}"
required
>

<textarea
name="note"
placeholder="Month / Note"
></textarea>

<button>
Save Monthly Jama
</button>

</form>

<p>
<a href="/dashboard">
⬅ Dashboard
</a>
</p>

</div>

</body>

</html>

"""

    return render_template_string(
        html,
        members=members,
        today=today_india()
    )


# =========================================================
# SAVING HISTORY
# =========================================================

@app.route("/savings")
def savings():

    user = current_user()

    if not user:
        return redirect(
            url_for("login")
        )

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            t.*,
            m.name

        FROM fsc_transactions t

        JOIN fsc_members m
        ON t.member_id = m.id

        WHERE t.transaction_type = 'jama'

        ORDER BY
            t.transaction_date DESC,
            t.id DESC
    """)

    savings = cur.fetchall()

    cur.close()
    conn.close()

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Saving History</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.container {

    width: 94%;

    max-width: 1100px;

    margin: 20px auto;
}

.card {

    background: white;

    padding: 15px;

    margin-bottom: 10px;

    border-radius: 10px;
}

.green {

    color: green;

    font-weight: bold;
}

.btn {

    display: inline-block;

    padding: 8px 12px;

    background: #667eea;

    color: white;

    text-decoration: none;

    border-radius: 6px;

    margin: 3px;
}

.red {

    background: #e74c3c;
}

</style>

</head>

<body>

<div class="container">

<h1>
💵 Monthly Saving History
</h1>

<a class="btn"
href="/dashboard">
⬅ Dashboard
</a>

{% if user["role"] == "admin" %}

<a class="btn"
href="/add_saving">
➕ Add Saving
</a>

{% endif %}

<hr>

{% for s in savings %}

<div class="card">

<h3>
{{ s["name"] }}
</h3>

<p>
📅 {{ s["transaction_date"] }}
</p>

<p class="green">
💵 Jama:
₹{{ "%.2f"|format(s["amount"]|float) }}
</p>

<p>
📝 {{ s["note"] or "-" }}
</p>

{% if user["role"] == "admin" %}

<a
class="btn"
href="/edit_saving/{{ s["id"] }}">
✏ Edit
</a>

<a
class="btn red"
href="/delete_saving/{{ s["id"] }}"
onclick="return confirm('Delete this saving?')">
🗑 Delete
</a>

{% endif %}

</div>

{% endfor %}

</div>

</body>

</html>

"""

    return render_template_string(
        html,
        savings=savings,
        user=user
    )


# =========================================================
# EDIT SAVING
# =========================================================

@app.route(
    "/edit_saving/<int:id>",
    methods=["GET", "POST"]
)
def edit_saving(id):

    if not is_admin():
        return redirect(
            url_for("dashboard")
        )

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM fsc_transactions

        WHERE id = %s

        AND transaction_type = 'jama'
    """, (
        id,
    ))

    saving = cur.fetchone()

    if not saving:

        cur.close()
        conn.close()

        return "Saving transaction not found"

    if request.method == "POST":

        amount = request.form.get(
            "amount"
        )

        transaction_date = request.form.get(
            "transaction_date"
        )

        note = request.form.get(
            "note"
        )

        cur.execute("""
            UPDATE fsc_transactions

            SET
                amount = %s,
                transaction_date = %s,
                note = %s

            WHERE id = %s

            AND transaction_type = 'jama'
        """, (
            amount,
            transaction_date,
            note,
            id
        ))

        conn.commit()

        cur.close()
        conn.close()

        return redirect(
            url_for("savings")
        )

    cur.close()
    conn.close()

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Edit Saving</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.box {

    width: 94%;

    max-width: 500px;

    margin: 30px auto;

    background: white;

    padding: 25px;

    border-radius: 14px;
}

input, textarea {

    width: 100%;

    padding: 12px;

    margin: 8px 0;

    box-sizing: border-box;
}

button {

    width: 100%;

    padding: 12px;

    background: #667eea;

    color: white;

    border: none;

    border-radius: 8px;
}

</style>

</head>

<body>

<div class="box">

<h1>
✏ Edit Saving
</h1>

<form method="POST">

<input
type="number"
step="0.01"
name="amount"
value="{{ saving["amount"] }}"
required
>

<input
type="date"
name="transaction_date"
value="{{ saving["transaction_date"] }}"
required
>

<textarea
name="note"
placeholder="Note"
>{{ saving["note"] or "" }}</textarea>

<button>
Update Saving
</button>

</form>

<p>
<a href="/savings">
⬅ Back
</a>
</p>

</div>

</body>

</html>

"""

    return render_template_string(
        html,
        saving=saving
    )


# =========================================================
# DELETE SAVING
# =========================================================

@app.route(
    "/delete_saving/<int:id>"
)
def delete_saving(id):

    if not is_admin():
        return redirect(
            url_for("dashboard")
        )

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM fsc_transactions

        WHERE id = %s

        AND transaction_type = 'jama'
    """, (
        id,
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        url_for("savings")
    )


# =========================================================
# ADD LOAN
# =========================================================

@app.route(
    "/add_loan",
    methods=["GET", "POST"]
)
def add_loan():

    if not is_admin():
        return redirect(
            url_for("dashboard")
        )

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            name

        FROM fsc_members

        ORDER BY name
    """)

    members = cur.fetchall()

    if request.method == "POST":

        member_id = request.form.get(
            "member_id"
        )

        amount = request.form.get(
            "amount"
        )

        loan_date = request.form.get(
            "loan_date"
        )

        note = request.form.get(
            "note"
        )

        cur.execute("""
            INSERT INTO fsc_loans
            (
                member_id,
                amount,
                loan_date,
                note
            )

            VALUES
            (
                %s,
                %s,
                %s,
                %s
            )
        """, (
            member_id,
            amount,
            loan_date,
            note
        ))

        conn.commit()

        cur.close()
        conn.close()

        return redirect(
            url_for("loans")
        )

    cur.close()
    conn.close()

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Give Loan</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.box {

    width: 94%;

    max-width: 500px;

    margin: 30px auto;

    background: white;

    padding: 25px;

    border-radius: 14px;
}

input, select, textarea {

    width: 100%;

    padding: 12px;

    margin: 8px 0;

    box-sizing: border-box;
}

button {

    width: 100%;

    padding: 12px;

    background: #667eea;

    color: white;

    border: none;

    border-radius: 8px;
}

</style>

</head>

<body>

<div class="box">

<h1>
🏦 Give Loan
</h1>

<form method="POST">

<select
name="member_id"
required
>

<option value="">
Select Member
</option>

{% for m in members %}

<option value="{{ m["id"] }}">
{{ m["name"] }}
</option>

{% endfor %}

</select>

<input
type="number"
step="0.01"
name="amount"
placeholder="Loan Amount"
required
>

<input
type="date"
name="loan_date"
value="{{ today }}"
required
>

<textarea
name="note"
placeholder="Loan Note"
></textarea>

<button>
Save Loan
</button>

</form>

<p>
<a href="/dashboard">
⬅ Dashboard
</a>
</p>

</div>

</body>

</html>

"""

    return render_template_string(
        html,
        members=members,
        today=today_india()
    )


# =========================================================
# LOAN HISTORY
# =========================================================

@app.route("/loans")
def loans():

    user = current_user()

    if not user:
        return redirect(
            url_for("login")
        )

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            l.*,
            m.name,

            COALESCE(
                (
                    SELECT SUM(e.amount)

                    FROM fsc_loan_emi e

                    WHERE e.loan_id = l.id
                ),
                0
            ) AS emi_paid

        FROM fsc_loans l

        JOIN fsc_members m
        ON l.member_id = m.id

        ORDER BY
            l.loan_date DESC,
            l.id DESC
    """)

    loans = cur.fetchall()

    cur.close()
    conn.close()

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Loan History</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.container {

    width: 94%;

    max-width: 1100px;

    margin: 20px auto;
}

.card {

    background: white;

    padding: 18px;

    margin-bottom: 12px;

    border-radius: 12px;
}

.loan {

    color: #8e44ad;

    font-weight: bold;
}

.emi {

    color: green;

    font-weight: bold;
}

.outstanding {

    color: red;

    font-weight: bold;
}

.btn {

    display: inline-block;

    padding: 8px 12px;

    background: #667eea;

    color: white;

    text-decoration: none;

    border-radius: 6px;

    margin: 3px;
}

.delete {

    background: #e74c3c;
}

</style>

</head>

<body>

<div class="container">

<h1>
🏦 Loan History
</h1>

<a class="btn"
href="/dashboard">
⬅ Dashboard
</a>

{% if user["role"] == "admin" %}

<a class="btn"
href="/add_loan">
➕ Give Loan
</a>

{% endif %}

<hr>

{% for l in loans %}

{% set loan_amount =
l["amount"]|float
%}

{% set emi_paid =
l["emi_paid"]|float
%}

{% set outstanding =
loan_amount - emi_paid
%}

<div class="card">

<h2>
{{ l["name"] }}
</h2>

<p>
📅 {{ l["loan_date"] }}
</p>

<p class="loan">
🏦 Loan Given:
₹{{ "%.2f"|format(loan_amount) }}
</p>

<p class="emi">
💳 EMI Received:
₹{{ "%.2f"|format(emi_paid) }}
</p>

<p class="outstanding">
📌 Outstanding:
₹{{ "%.2f"|format(
outstanding if outstanding > 0 else 0
) }}
</p>

<p>
📝 {{ l["note"] or "-" }}
</p>

{% if user["role"] == "admin" %}

<a
class="btn"
href="/add_emi?loan_id={{ l["id"] }}">
💳 Receive EMI
</a>

<a
class="btn delete"
href="/delete_loan/{{ l["id"] }}"
onclick="return confirm('Delete this loan? All EMI records will also be deleted.')">
🗑 Delete
</a>

{% endif %}

</div>

{% endfor %}

</div>

</body>

</html>

"""

    return render_template_string(
        html,
        loans=loans,
        user=user
    )


# =========================================================
# DELETE LOAN
# =========================================================

@app.route(
    "/delete_loan/<int:id>"
)
def delete_loan(id):

    if not is_admin():
        return redirect(
            url_for("dashboard")
        )

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM fsc_loans

        WHERE id = %s
    """, (
        id,
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        url_for("loans")
    )


# =========================================================
# ADD EMI
# =========================================================

@app.route(
    "/add_emi",
    methods=["GET", "POST"]
)
def add_emi():

    if not is_admin():
        return redirect(
            url_for("dashboard")
        )

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            l.id,
            l.member_id,
            l.amount,
            l.loan_date,
            m.name,

            COALESCE(
                (
                    SELECT SUM(e.amount)

                    FROM fsc_loan_emi e

                    WHERE e.loan_id = l.id
                ),
                0
            ) AS emi_paid

        FROM fsc_loans l

        JOIN fsc_members m
        ON l.member_id = m.id

        ORDER BY
            l.loan_date DESC
    """)

    loans = cur.fetchall()

    selected_loan_id = request.args.get(
        "loan_id"
    )

    if request.method == "POST":

        loan_id = request.form.get(
            "loan_id"
        )

        amount = request.form.get(
            "amount"
        )

        emi_date = request.form.get(
            "emi_date"
        )

        note = request.form.get(
            "note"
        )

        cur.execute("""
            SELECT
                member_id,
                amount

            FROM fsc_loans

            WHERE id = %s
        """, (
            loan_id,
        ))

        loan = cur.fetchone()

        if not loan:

            cur.close()
            conn.close()

            return "Loan not found"

        cur.execute("""
            SELECT
                COALESCE(
                    SUM(amount),
                    0
                ) AS paid

            FROM fsc_loan_emi

            WHERE loan_id = %s
        """, (
            loan_id,
        ))

        paid = float(
            cur.fetchone()["paid"]
        )

        loan_amount = float(
            loan["amount"]
        )

        emi_amount = float(
            amount
        )

        remaining = (
            loan_amount - paid
        )

        if emi_amount <= 0:

            cur.close()
            conn.close()

            return """
            <h2>
            EMI amount must be greater than 0.
            </h2>

            <a href="/add_emi">
            Back
            </a>
            """

        if emi_amount > remaining:

            cur.close()
            conn.close()

            return """
            <h2>
            EMI cannot be greater than
            outstanding loan.
            </h2>

            <a href="/add_emi">
            Back
            </a>
            """

        cur.execute("""
            INSERT INTO fsc_loan_emi
            (
                loan_id,
                member_id,
                amount,
                emi_date,
                note
            )

            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s
            )
        """, (
            loan_id,
            loan["member_id"],
            amount,
            emi_date,
            note
        ))

        conn.commit()

        cur.close()
        conn.close()

        return redirect(
            url_for("emi")
        )

    cur.close()
    conn.close()

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Receive EMI</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.box {

    width: 94%;

    max-width: 500px;

    margin: 30px auto;

    background: white;

    padding: 25px;

    border-radius: 14px;
}

select, input, textarea {

    width: 100%;

    padding: 12px;

    margin: 8px 0;

    box-sizing: border-box;
}

button {

    width: 100%;

    padding: 12px;

    background: #667eea;

    color: white;

    border: none;

    border-radius: 8px;
}

</style>

</head>

<body>

<div class="box">

<h1>
💳 Receive Loan EMI
</h1>

<form method="POST">

<select
name="loan_id"
required
>

<option value="">
Select Loan
</option>

{% for l in loans %}

{% set outstanding =
(l["amount"]|float)
-
(l["emi_paid"]|float)
%}

{% if outstanding > 0 %}

<option
value="{{ l["id"] }}"
{% if selected_loan_id
and selected_loan_id|string
==
l["id"]|string %}
selected
{% endif %}
>

{{ l["name"] }}

-
Loan ₹{{ "%.2f"|format(
l["amount"]|float
) }}

-
Remaining ₹{{ "%.2f"|format(
outstanding
) }}

</option>

{% endif %}

{% endfor %}

</select>

<input
type="number"
step="0.01"
name="amount"
placeholder="EMI Amount"
required
>

<input
type="date"
name="emi_date"
value="{{ today }}"
required
>

<textarea
name="note"
placeholder="EMI Note"
></textarea>

<button>
Save EMI
</button>

</form>

<p>
<a href="/loans">
⬅ Back
</a>
</p>

</div>

</body>

</html>

"""

    return render_template_string(
        html,
        loans=loans,
        selected_loan_id=selected_loan_id,
        today=today_india()
    )


# =========================================================
# EMI HISTORY
# =========================================================

@app.route("/emi")
def emi():

    user = current_user()

    if not user:
        return redirect(
            url_for("login")
        )

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            e.*,
            m.name

        FROM fsc_loan_emi e

        JOIN fsc_members m
        ON e.member_id = m.id

        ORDER BY
            e.emi_date DESC,
            e.id DESC
    """)

    emis = cur.fetchall()

    cur.close()
    conn.close()

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>EMI History</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.container {

    width: 94%;

    max-width: 1000px;

    margin: 20px auto;
}

.card {

    background: white;

    padding: 16px;

    margin-bottom: 10px;

    border-radius: 10px;
}

.green {

    color: green;

    font-weight: bold;
}

.btn {

    display: inline-block;

    padding: 8px 12px;

    background: #667eea;

    color: white;

    text-decoration: none;

    border-radius: 6px;

    margin: 3px;
}

.delete {

    background: #e74c3c;
}

</style>

</head>

<body>

<div class="container">

<h1>
💳 EMI History
</h1>

<a class="btn"
href="/dashboard">
⬅ Dashboard
</a>

{% if user["role"] == "admin" %}

<a class="btn"
href="/add_emi">
➕ Receive EMI
</a>

{% endif %}

<hr>

{% for e in emis %}

<div class="card">

<h3>
{{ e["name"] }}
</h3>

<p>
📅 {{ e["emi_date"] }}
</p>

<p class="green">
💳 EMI Received:
₹{{ "%.2f"|format(
e["amount"]|float
) }}
</p>

<p>
📝 {{ e["note"] or "-" }}
</p>

{% if user["role"] == "admin" %}

<a
class="btn delete"
href="/delete_emi/{{ e["id"] }}"
onclick="return confirm('Delete this EMI?')">
🗑 Delete
</a>

{% endif %}

</div>

{% endfor %}

</div>

</body>

</html>

"""

    return render_template_string(
        html,
        emis=emis,
        user=user
    )


# =========================================================
# DELETE EMI
# =========================================================

@app.route(
    "/delete_emi/<int:id>"
)
def delete_emi(id):

    if not is_admin():
        return redirect(
            url_for("dashboard")
        )

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM fsc_loan_emi

        WHERE id = %s
    """, (
        id,
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        url_for("emi")
    )


# =========================================================
# MEMBER SUMMARY
# =========================================================

@app.route("/member_summary")
def member_summary():

    user = current_user()

    if not user:
        return redirect(
            url_for("login")
        )

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            m.id,
            m.name,

            COALESCE(
                (
                    SELECT SUM(t.amount)

                    FROM fsc_transactions t

                    WHERE t.member_id = m.id

                    AND t.transaction_type = 'jama'
                ),
                0
            ) AS jama,

            COALESCE(
                (
                    SELECT SUM(l.amount)

                    FROM fsc_loans l

                    WHERE l.member_id = m.id
                ),
                0
            ) AS loan,

            COALESCE(
                (
                    SELECT SUM(e.amount)

                    FROM fsc_loan_emi e

                    WHERE e.member_id = m.id
                ),
                0
            ) AS emi

        FROM fsc_members m

        ORDER BY m.name
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    summary = []

    for r in rows:

        jama = float(r["jama"])

        loan = float(r["loan"])

        emi = float(r["emi"])

        outstanding = max(
            loan - emi,
            0
        )

        summary.append({
            "id": r["id"],
            "name": r["name"],
            "jama": jama,
            "loan": loan,
            "emi": emi,
            "outstanding": outstanding
        })

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Member Summary</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.container {

    width: 98%;

    max-width: 1200px;

    margin: 20px auto;
}

table {

    width: 100%;

    border-collapse: collapse;

    background: white;
}

th, td {

    padding: 12px;

    border: 1px solid #ddd;

    text-align: center;
}

th {

    background: #667eea;

    color: white;
}

.loan {

    color: #8e44ad;
}

.emi {

    color: green;
}

.outstanding {

    color: red;

    font-weight: bold;
}

.btn {

    display: inline-block;

    padding: 9px 13px;

    background: #555;

    color: white;

    text-decoration: none;

    border-radius: 7px;
}

.detail {

    background: #16a085;
}

</style>

</head>

<body>

<div class="container">

<h1>
📊 Member-wise Summary
</h1>

<a
class="btn"
href="/dashboard">
⬅ Dashboard
</a>

<br><br>

<div style="overflow-x:auto;">

<table>

<tr>

<th>
Member
</th>

<th>
Regular Jama
</th>

<th>
Loan Given
</th>

<th>
EMI Received
</th>

<th>
Outstanding Loan
</th>

<th>
Details
</th>

</tr>

{% for r in summary %}

<tr>

<td>
{{ r["name"] }}
</td>

<td>
₹{{ "%.2f"|format(r["jama"]) }}
</td>

<td class="loan">
₹{{ "%.2f"|format(r["loan"]) }}
</td>

<td class="emi">
₹{{ "%.2f"|format(r["emi"]) }}
</td>

<td class="outstanding">
₹{{ "%.2f"|format(r["outstanding"]) }}
</td>

<td>

<a
class="btn detail"
href="/member_detail/{{ r["id"] }}">
View
</a>

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
        summary=summary
    )


# =========================================================
# MONTHLY DUE ADMIN
# =========================================================

@app.route(
    "/monthly_due",
    methods=["GET", "POST"]
)
def monthly_due():

    if not is_admin():
        return redirect(
            url_for("dashboard")
        )

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            name

        FROM fsc_members

        ORDER BY name
    """)

    members = cur.fetchall()

    if request.method == "POST":

        member_id = request.form.get(
            "member_id"
        )

        due_month_raw = request.form.get(
            "due_month"
        )

        saving_amount = request.form.get(
            "saving_amount"
        ) or 0

        emi_amount = request.form.get(
            "emi_amount"
        ) or 0

        note = request.form.get(
            "note"
        )

        if not due_month_raw:

            cur.close()
            conn.close()

            return "Month is required"

        # HTML month input:
        # 2026-10
        #
        # PostgreSQL DATE:
        # 2026-10-01

        due_month = (
            due_month_raw + "-01"
        )

        cur.execute("""
            INSERT INTO fsc_monthly_due
            (
                member_id,
                due_month,
                saving_amount,
                emi_amount,
                note
            )

            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s
            )

            ON CONFLICT
            (
                member_id,
                due_month
            )

            DO UPDATE SET

                saving_amount =
                    EXCLUDED.saving_amount,

                emi_amount =
                    EXCLUDED.emi_amount,

                note =
                    EXCLUDED.note
        """, (
            member_id,
            due_month,
            saving_amount,
            emi_amount,
            note
        ))

        conn.commit()

        cur.close()
        conn.close()

        return redirect(
            url_for("monthly_due")
        )

    # =====================================================
    # EXISTING DUES
    # =====================================================

    cur.execute("""
        SELECT
            d.*,
            m.name

        FROM fsc_monthly_due d

        JOIN fsc_members m
        ON d.member_id = m.id

        ORDER BY
            d.due_month DESC,
            m.name
    """)

    dues = cur.fetchall()

    cur.close()
    conn.close()

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Monthly Due</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.container {

    width: 96%;

    max-width: 1100px;

    margin: 20px auto;
}

.box {

    background: white;

    padding: 20px;

    border-radius: 14px;
}

input, select, textarea {

    width: 100%;

    padding: 11px;

    margin: 7px 0;

    box-sizing: border-box;
}

button {

    width: 100%;

    padding: 12px;

    background: #667eea;

    color: white;

    border: none;

    border-radius: 8px;
}

table {

    width: 100%;

    border-collapse: collapse;

    background: white;

    margin-top: 20px;
}

th, td {

    padding: 10px;

    border: 1px solid #ddd;

    text-align: center;
}

th {

    background: #667eea;

    color: white;
}

.btn {

    display: inline-block;

    padding: 9px 13px;

    background: #555;

    color: white;

    text-decoration: none;

    border-radius: 7px;
}

.green {

    color: green;

    font-weight: bold;
}

.blue {

    color: #2980b9;

    font-weight: bold;
}

</style>

</head>

<body>

<div class="container">

<h1>
📅 Monthly Due Amount
</h1>

<a
class="btn"
href="/dashboard">
⬅ Dashboard
</a>

<br><br>

<div class="box">

<h2>
Set / Update Monthly Due
</h2>

<p style="color:#666;">
Each member can have a different saving
and EMI amount for every month.
</p>

<form method="POST">

<label>
Member
</label>

<select
name="member_id"
required
>

<option value="">
Select Member
</option>

{% for m in members %}

<option value="{{ m["id"] }}">
{{ m["name"] }}
</option>

{% endfor %}

</select>

<label>
Month
</label>

<input
type="month"
name="due_month"
required
>

<label>
Monthly Saving Amount
</label>

<input
type="number"
step="0.01"
min="0"
name="saving_amount"
placeholder="Example: 1500"
value="0"
>

<label>
EMI Due Amount
</label>

<input
type="number"
step="0.01"
min="0"
name="emi_amount"
placeholder="Example: 2000"
value="0"
>

<textarea
name="note"
placeholder="Note"
></textarea>

<button>
💾 Save / Update Due
</button>

</form>

</div>


<h2>
Saved Monthly Due
</h2>

<div style="overflow-x:auto;">

<table>

<tr>

<th>
Month
</th>

<th>
Member
</th>

<th>
Saving Due
</th>

<th>
EMI Due
</th>

<th>
Note
</th>

</tr>

{% for d in dues %}

<tr>

<td>
{{ d["due_month"].strftime("%B %Y") }}
</td>

<td>
{{ d["name"] }}
</td>

<td class="green">
₹{{ "%.2f"|format(
d["saving_amount"]|float
) }}
</td>

<td class="blue">
₹{{ "%.2f"|format(
d["emi_amount"]|float
) }}
</td>

<td>
{{ d["note"] or "-" }}
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
        dues=dues
    )


# =========================================================
# DUE SUMMARY
# =========================================================

@app.route("/due_summary")
def due_summary():

    user = current_user()

    if not user:
        return redirect(
            url_for("login")
        )

    month_raw = request.args.get(
        "month"
    )

    if not month_raw:

        month_raw = datetime.now(
            IST
        ).strftime("%Y-%m")

    due_month = month_raw + "-01"

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            m.id,
            m.name,

            COALESCE(
                d.saving_amount,
                0
            ) AS saving_due,

            COALESCE(
                d.emi_amount,
                0
            ) AS emi_due,

            d.note

        FROM fsc_members m

        LEFT JOIN fsc_monthly_due d

        ON d.member_id = m.id

        AND d.due_month = %s

        ORDER BY m.name
    """, (
        due_month,
    ))

    rows = cur.fetchall()

    cur.close()
    conn.close()

    total_saving_due = 0

    total_emi_due = 0

    for r in rows:

        total_saving_due += float(
            r["saving_due"]
        )

        total_emi_due += float(
            r["emi_due"]
        )

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Due Summary</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.container {

    width: 98%;

    max-width: 1200px;

    margin: 20px auto;
}

.filter {

    background: white;

    padding: 18px;

    border-radius: 12px;
}

input {

    padding: 10px;
}

button {

    padding: 10px 15px;

    background: #667eea;

    color: white;

    border: none;

    border-radius: 7px;
}

.cards {

    display: grid;

    grid-template-columns:
    repeat(
        auto-fit,
        minmax(180px,1fr)
    );

    gap: 12px;

    margin-top: 15px;
}

.card {

    background: white;

    padding: 18px;

    border-radius: 12px;
}

.amount {

    font-size: 22px;

    font-weight: bold;
}

table {

    width: 100%;

    border-collapse: collapse;

    background: white;

    margin-top: 20px;
}

th, td {

    padding: 12px;

    border: 1px solid #ddd;

    text-align: center;
}

th {

    background: #667eea;

    color: white;
}

</style>

</head>

<body>

<div class="container">

<h1>
📌 Monthly Due Summary
</h1>

<a href="/dashboard">
⬅ Dashboard
</a>

<br><br>

<div class="filter">

<form method="GET">

<label>
Select Month:
</label>

<input
type="month"
name="month"
value="{{ month_raw }}"
required
>

<button>
🔍 View Due
</button>

</form>

</div>


<div class="cards">

<div class="card">

<h3>
💵 Total Saving Due
</h3>

<div class="amount">
₹{{ "%.2f"|format(
total_saving_due
) }}
</div>

</div>


<div class="card">

<h3>
💳 Total EMI Due
</h3>

<div class="amount">
₹{{ "%.2f"|format(
total_emi_due
) }}
</div>

</div>

</div>


<h2>
Member-wise Due
</h2>

<div style="overflow-x:auto;">

<table>

<tr>

<th>
Member
</th>

<th>
Saving Due
</th>

<th>
EMI Due
</th>

<th>
Total Due
</th>

<th>
Note
</th>

</tr>

{% for r in rows %}

{% set saving =
r["saving_due"]|float
%}

{% set emi =
r["emi_due"]|float
%}

<tr>

<td>
{{ r["name"] }}
</td>

<td>
₹{{ "%.2f"|format(saving) }}
</td>

<td>
₹{{ "%.2f"|format(emi) }}
</td>

<td>
<strong>
₹{{ "%.2f"|format(
saving + emi
) }}
</strong>
</td>

<td>
{{ r["note"] or "-" }}
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
        rows=rows,
        month_raw=month_raw,
        total_saving_due=total_saving_due,
        total_emi_due=total_emi_due
    )


# =========================================================
# MONTHLY DASHBOARD
# =========================================================

@app.route("/monthly_dashboard")
def monthly_dashboard():

    user = current_user()

    if not user:
        return redirect(
            url_for("login")
        )

    month_raw = request.args.get(
        "month"
    )

    if not month_raw:

        month_raw = datetime.now(
            IST
        ).strftime("%Y-%m")

    start_date = (
        month_raw + "-01"
    )

    conn = get_conn()
    cur = conn.cursor()

    # =====================================================
    # SAVING
    # =====================================================

    cur.execute("""
        SELECT
            COALESCE(
                SUM(amount),
                0
            ) AS amount

        FROM fsc_transactions

        WHERE transaction_type = 'jama'

        AND DATE_TRUNC(
            'month',
            transaction_date
        )
        =
        DATE_TRUNC(
            'month',
            %s::date
        )
    """, (
        start_date,
    ))

    saving = float(
        cur.fetchone()["amount"]
    )

    # =====================================================
    # LOAN
    # =====================================================

    cur.execute("""
        SELECT
            COALESCE(
                SUM(amount),
                0
            ) AS amount

        FROM fsc_loans

        WHERE DATE_TRUNC(
            'month',
            loan_date
        )
        =
        DATE_TRUNC(
            'month',
            %s::date
        )
    """, (
        start_date,
    ))

    loan = float(
        cur.fetchone()["amount"]
    )

    # =====================================================
    # EMI
    # =====================================================

    cur.execute("""
        SELECT
            COALESCE(
                SUM(amount),
                0
            ) AS amount

        FROM fsc_loan_emi

        WHERE DATE_TRUNC(
            'month',
            emi_date
        )
        =
        DATE_TRUNC(
            'month',
            %s::date
        )
    """, (
        start_date,
    ))

    emi = float(
        cur.fetchone()["amount"]
    )

    # =====================================================
    # DUE
    # =====================================================

    cur.execute("""
        SELECT
            COALESCE(
                SUM(saving_amount),
                0
            ) AS saving_due,

            COALESCE(
                SUM(emi_amount),
                0
            ) AS emi_due

        FROM fsc_monthly_due

        WHERE due_month = %s
    """, (
        start_date,
    ))

    due = cur.fetchone()

    saving_due = float(
        due["saving_due"]
    )

    emi_due = float(
        due["emi_due"]
    )

    cur.close()
    conn.close()

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Monthly Dashboard</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.container {

    width: 94%;

    max-width: 1100px;

    margin: 20px auto;
}

.filter {

    background: white;

    padding: 18px;

    border-radius: 12px;
}

input {

    padding: 10px;
}

button {

    padding: 10px 15px;

    background: #667eea;

    color: white;

    border: none;

    border-radius: 7px;
}

.cards {

    display: grid;

    grid-template-columns:
    repeat(
        auto-fit,
        minmax(190px,1fr)
    );

    gap: 15px;

    margin-top: 20px;
}

.card {

    background: white;

    padding: 20px;

    border-radius: 14px;

    box-shadow:
    0 4px 10px
    rgba(0,0,0,0.08);
}

.amount {

    font-size: 25px;

    font-weight: bold;
}

.green {

    color: green;
}

.purple {

    color: #8e44ad;
}

.blue {

    color: #2980b9;
}

.red {

    color: red;
}

</style>

</head>

<body>

<div class="container">

<h1>
📈 Monthly Dashboard
</h1>

<a href="/dashboard">
⬅ Dashboard
</a>

<br><br>

<div class="filter">

<form method="GET">

<input
type="month"
name="month"
value="{{ month_raw }}"
required
>

<button>
🔍 View Month
</button>

</form>

</div>


<div class="cards">

<div class="card">

<h3>
💵 Saving Collected
</h3>

<div class="amount green">
₹{{ "%.2f"|format(saving) }}
</div>

</div>


<div class="card">

<h3>
🏦 Loan Given
</h3>

<div class="amount purple">
₹{{ "%.2f"|format(loan) }}
</div>

</div>


<div class="card">

<h3>
💳 EMI Received
</h3>

<div class="amount green">
₹{{ "%.2f"|format(emi) }}
</div>

</div>


<div class="card">

<h3>
📅 Saving Due
</h3>

<div class="amount blue">
₹{{ "%.2f"|format(saving_due) }}
</div>

</div>


<div class="card">

<h3>
📅 EMI Due
</h3>

<div class="amount blue">
₹{{ "%.2f"|format(emi_due) }}
</div>

</div>


<div class="card">

<h3>
📌 Total Due
</h3>

<div class="amount red">
₹{{ "%.2f"|format(
saving_due + emi_due
) }}
</div>

</div>

</div>

</div>

</body>

</html>

"""

    return render_template_string(
        html,
        month_raw=month_raw,
        saving=saving,
        loan=loan,
        emi=emi,
        saving_due=saving_due,
        emi_due=emi_due
    )


# =========================================================
# COMPLETE REPORT
# =========================================================

@app.route("/report")
def report():

    user = current_user()

    if not user:
        return redirect(
            url_for("login")
        )

    from_date = request.args.get(
        "from_date"
    )

    to_date = request.args.get(
        "to_date"
    )

    conn = get_conn()
    cur = conn.cursor()

    if from_date and to_date:

        cur.execute("""
            SELECT
                m.id,
                m.name,

                COALESCE(
                    (
                        SELECT SUM(t.amount)

                        FROM fsc_transactions t

                        WHERE t.member_id = m.id

                        AND t.transaction_type = 'jama'

                        AND t.transaction_date
                        BETWEEN %s AND %s
                    ),
                    0
                ) AS jama,

                COALESCE(
                    (
                        SELECT SUM(l.amount)

                        FROM fsc_loans l

                        WHERE l.member_id = m.id

                        AND l.loan_date
                        BETWEEN %s AND %s
                    ),
                    0
                ) AS loan,

                COALESCE(
                    (
                        SELECT SUM(e.amount)

                        FROM fsc_loan_emi e

                        WHERE e.member_id = m.id

                        AND e.emi_date
                        BETWEEN %s AND %s
                    ),
                    0
                ) AS emi

            FROM fsc_members m

            ORDER BY m.name
        """, (
            from_date,
            to_date,
            from_date,
            to_date,
            from_date,
            to_date
        ))

    else:

        cur.execute("""
            SELECT
                m.id,
                m.name,

                COALESCE(
                    (
                        SELECT SUM(t.amount)

                        FROM fsc_transactions t

                        WHERE t.member_id = m.id

                        AND t.transaction_type = 'jama'
                    ),
                    0
                ) AS jama,

                COALESCE(
                    (
                        SELECT SUM(l.amount)

                        FROM fsc_loans l

                        WHERE l.member_id = m.id
                    ),
                    0
                ) AS loan,

                COALESCE(
                    (
                        SELECT SUM(e.amount)

                        FROM fsc_loan_emi e

                        WHERE e.member_id = m.id
                    ),
                    0
                ) AS emi

            FROM fsc_members m

            ORDER BY m.name
        """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    total_jama = 0
    total_loan = 0
    total_emi = 0

    data = []

    for r in rows:

        jama = float(r["jama"])

        loan = float(r["loan"])

        emi = float(r["emi"])

        outstanding = max(
            loan - emi,
            0
        )

        total_jama += jama

        total_loan += loan

        total_emi += emi

        data.append({
            "id": r["id"],
            "name": r["name"],
            "jama": jama,
            "loan": loan,
            "emi": emi,
            "outstanding": outstanding
        })

    total_amount = (
        total_jama
        - total_loan
        + total_emi
    )

    total_outstanding = max(
        total_loan - total_emi,
        0
    )

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Complete Report</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.container {

    width: 98%;

    max-width: 1200px;

    margin: 20px auto;
}

.filter {

    background: white;

    padding: 18px;

    border-radius: 12px;
}

input {

    padding: 10px;

    margin: 5px;
}

button {

    padding: 10px 15px;

    background: #667eea;

    color: white;

    border: none;

    border-radius: 7px;
}

.cards {

    display: grid;

    grid-template-columns:
    repeat(
        auto-fit,
        minmax(170px,1fr)
    );

    gap: 12px;

    margin-top: 15px;
}

.card {

    background: white;

    padding: 18px;

    border-radius: 12px;
}

.amount {

    font-size: 22px;

    font-weight: bold;
}

table {

    width: 100%;

    border-collapse: collapse;

    background: white;

    margin-top: 20px;
}

th, td {

    padding: 12px;

    border: 1px solid #ddd;

    text-align: center;
}

th {

    background: #667eea;

    color: white;
}

.loan {

    color: #8e44ad;
}

.emi {

    color: green;
}

.outstanding {

    color: red;

    font-weight: bold;
}

.btn {

    display: inline-block;

    padding: 9px 13px;

    background: #555;

    color: white;

    text-decoration: none;

    border-radius: 7px;
}

</style>

</head>

<body>

<div class="container">

<h1>
📊 Complete Report
</h1>

<a class="btn"
href="/dashboard">
⬅ Dashboard
</a>

<a class="btn"
href="/export_report?from_date={{ from_date or '' }}&to_date={{ to_date or '' }}">
⬇ Download CSV
</a>

<br><br>

<div class="filter">

<form method="GET">

<label>
From:
</label>

<input
type="date"
name="from_date"
value="{{ from_date or '' }}"
required
>

<label>
To:
</label>

<input
type="date"
name="to_date"
value="{{ to_date or '' }}"
required
>

<button>
🔍 Generate Report
</button>

</form>

</div>


<div class="cards">

<div class="card">

<h3>
💵 Regular Jama
</h3>

<div class="amount">
₹{{ "%.2f"|format(total_jama) }}
</div>

</div>


<div class="card">

<h3>
🏦 Loan Given
</h3>

<div class="amount">
₹{{ "%.2f"|format(total_loan) }}
</div>

</div>


<div class="card">

<h3>
💳 EMI Received
</h3>

<div class="amount">
₹{{ "%.2f"|format(total_emi) }}
</div>

</div>


<div class="card">

<h3>
📌 Outstanding Loan
</h3>

<div class="amount">
₹{{ "%.2f"|format(
total_outstanding
) }}
</div>

</div>


<div class="card">

<h3>
💰 Actual Group Balance
</h3>

<div class="amount">
₹{{ "%.2f"|format(
total_amount
) }}
</div>

</div>

</div>


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
Regular Jama
</th>

<th>
Loan Given
</th>

<th>
EMI Received
</th>

<th>
Outstanding Loan
</th>

</tr>

{% for r in data %}

<tr>

<td>
{{ r["name"] }}
</td>

<td>
₹{{ "%.2f"|format(r["jama"]) }}
</td>

<td class="loan">
₹{{ "%.2f"|format(r["loan"]) }}
</td>

<td class="emi">
₹{{ "%.2f"|format(r["emi"]) }}
</td>

<td class="outstanding">
₹{{ "%.2f"|format(
r["outstanding"]
) }}
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
        data=data,
        total_jama=total_jama,
        total_loan=total_loan,
        total_emi=total_emi,
        total_outstanding=total_outstanding,
        total_amount=total_amount,
        from_date=from_date,
        to_date=to_date
    )


# =========================================================
# EXPORT REPORT CSV
# =========================================================

@app.route("/export_report")
def export_report():

    user = current_user()

    if not user:
        return redirect(
            url_for("login")
        )

    from_date = request.args.get(
        "from_date"
    )

    to_date = request.args.get(
        "to_date"
    )

    conn = get_conn()
    cur = conn.cursor()

    if from_date and to_date:

        cur.execute("""
            SELECT
                m.name,

                COALESCE(
                    (
                        SELECT SUM(t.amount)

                        FROM fsc_transactions t

                        WHERE t.member_id = m.id

                        AND t.transaction_type = 'jama'

                        AND t.transaction_date
                        BETWEEN %s AND %s
                    ),
                    0
                ) AS jama,

                COALESCE(
                    (
                        SELECT SUM(l.amount)

                        FROM fsc_loans l

                        WHERE l.member_id = m.id

                        AND l.loan_date
                        BETWEEN %s AND %s
                    ),
                    0
                ) AS loan,

                COALESCE(
                    (
                        SELECT SUM(e.amount)

                        FROM fsc_loan_emi e

                        WHERE e.member_id = m.id

                        AND e.emi_date
                        BETWEEN %s AND %s
                    ),
                    0
                ) AS emi

            FROM fsc_members m

            ORDER BY m.name
        """, (
            from_date,
            to_date,
            from_date,
            to_date,
            from_date,
            to_date
        ))

    else:

        cur.execute("""
            SELECT
                m.name,

                COALESCE(
                    (
                        SELECT SUM(t.amount)

                        FROM fsc_transactions t

                        WHERE t.member_id = m.id

                        AND t.transaction_type = 'jama'
                    ),
                    0
                ) AS jama,

                COALESCE(
                    (
                        SELECT SUM(l.amount)

                        FROM fsc_loans l

                        WHERE l.member_id = m.id
                    ),
                    0
                ) AS loan,

                COALESCE(
                    (
                        SELECT SUM(e.amount)

                        FROM fsc_loan_emi e

                        WHERE e.member_id = m.id
                    ),
                    0
                ) AS emi

            FROM fsc_members m

            ORDER BY m.name
        """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    output = io.StringIO()

    writer = csv.writer(
        output
    )

    writer.writerow([
        "Member",
        "Regular Jama",
        "Loan Given",
        "EMI Received",
        "Outstanding Loan",
        "Actual Balance"
    ])

    for r in rows:

        jama = float(r["jama"])

        loan = float(r["loan"])

        emi = float(r["emi"])

        outstanding = max(
            loan - emi,
            0
        )

        balance = (
            jama
            - loan
            + emi
        )

        writer.writerow([
            r["name"],
            f"{jama:.2f}",
            f"{loan:.2f}",
            f"{emi:.2f}",
            f"{outstanding:.2f}",
            f"{balance:.2f}"
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
            "attachment; filename=friend_saving_report.csv"
        }
    )


# =========================================================
# CHANGE PASSWORD
# =========================================================

@app.route(
    "/change_password",
    methods=["GET", "POST"]
)
def change_password():

    user = current_user()

    if not user:
        return redirect(
            url_for("login")
        )

    message = None

    error = None

    if request.method == "POST":

        old_password = request.form.get(
            "old_password"
        )

        new_password = request.form.get(
            "new_password"
        )

        confirm_password = request.form.get(
            "confirm_password"
        )

        if not check_password_hash(
            user["password"],
            old_password
        ):

            error = (
                "Old password is incorrect."
            )

        elif new_password != confirm_password:

            error = (
                "New passwords do not match."
            )

        elif len(new_password) < 4:

            error = (
                "Password must be at least 4 characters."
            )

        else:

            conn = get_conn()
            cur = conn.cursor()

            new_hash = (
                generate_password_hash(
                    new_password
                )
            )

            cur.execute("""
                UPDATE fsc_users

                SET password = %s

                WHERE id = %s
            """, (
                new_hash,
                user["id"]
            ))

            if user["member_id"]:

                cur.execute("""
                    UPDATE fsc_members

                    SET password = %s

                    WHERE id = %s
                """, (
                    new_hash,
                    user["member_id"]
                ))

            conn.commit()

            cur.close()
            conn.close()

            message = (
                "Password changed successfully."
            )

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Change Password</title>

<style>

body {

    font-family: Arial;

    background: #f4f6f9;
}

.box {

    width: 94%;

    max-width: 500px;

    margin: 40px auto;

    background: white;

    padding: 25px;

    border-radius: 14px;
}

input {

    width: 100%;

    padding: 12px;

    margin: 8px 0;

    box-sizing: border-box;
}

button {

    width: 100%;

    padding: 12px;

    background: #667eea;

    color: white;

    border: none;

    border-radius: 8px;
}

.success {

    color: green;
}

.error {

    color: red;
}

</style>

</head>

<body>

<div class="box">

<h1>
🔐 Change Password
</h1>

{% if message %}

<p class="success">
{{ message }}
</p>

{% endif %}

{% if error %}

<p class="error">
{{ error }}
</p>

{% endif %}

<form method="POST">

<input
type="password"
name="old_password"
placeholder="Old Password"
required
>

<input
type="password"
name="new_password"
placeholder="New Password"
required
>

<input
type="password"
name="confirm_password"
placeholder="Confirm New Password"
required
>

<button>
Change Password
</button>

</form>

<p>
<a href="/dashboard">
⬅ Dashboard
</a>
</p>

</div>

</body>

</html>

"""

    return render_template_string(
        html,
        message=message,
        error=error
    )


# =========================================================
# START
# =========================================================

init_db()


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",

        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),

        debug=True
    )
