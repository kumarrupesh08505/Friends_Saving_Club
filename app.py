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


# =========================
# DATABASE CONNECTION
# =========================

def get_conn():
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise Exception("DATABASE_URL is not set")

    return psycopg.connect(
        database_url,
        row_factory=dict_row
    )


# =========================
# DATABASE INITIALIZATION
# =========================

def init_db():

    conn = get_conn()
    cur = conn.cursor()

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fsc_transactions (
            id SERIAL PRIMARY KEY,
            member_id INTEGER REFERENCES fsc_members(id) ON DELETE CASCADE,
            transaction_type TEXT NOT NULL,
            amount NUMERIC(12,2) NOT NULL,
            transaction_date DATE NOT NULL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fsc_users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            member_id INTEGER REFERENCES fsc_members(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Default admin
    cur.execute("""
        SELECT id
        FROM fsc_users
        WHERE username = 'admin'
    """)

    admin = cur.fetchone()

    if not admin:

        cur.execute("""
            INSERT INTO fsc_users
            (username, password, role)
            VALUES (%s, %s, %s)
        """, (
            "admin",
            generate_password_hash("1234"),
            "admin"
        ))

    conn.commit()

    cur.close()
    conn.close()


# =========================
# HELPERS
# =========================

def current_user():

    if "user_id" not in session:
        return None

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM fsc_users
        WHERE id = %s
    """, (session["user_id"],))

    user = cur.fetchone()

    cur.close()
    conn.close()

    return user


def is_admin():

    user = current_user()

    return user and user["role"] == "admin"


def get_member_for_user():

    user = current_user()

    if not user or not user["member_id"]:
        return None

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM fsc_members
        WHERE id = %s
    """, (user["member_id"],))

    member = cur.fetchone()

    cur.close()
    conn.close()

    return member


# =========================
# LOGIN PAGE
# =========================

LOGIN_HTML = """
<!DOCTYPE html>

<html>

<head>

<meta name="viewport" content="width=device-width, initial-scale=1">

<title>Friend Saving Club - Login</title>

<style>

body {
    font-family: Arial;
    background: linear-gradient(135deg,#667eea,#764ba2);
    margin: 0;
    padding: 0;
}

.box {
    width: 90%;
    max-width: 400px;
    margin: 100px auto;
    background: white;
    padding: 30px;
    border-radius: 15px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    box-sizing: border-box;
}

h1 {
    text-align: center;
    color: #333;
}

input {
    width: 100%;
    padding: 12px;
    margin: 8px 0;
    box-sizing: border-box;
    border: 1px solid #ccc;
    border-radius: 8px;
}

button {
    width: 100%;
    padding: 12px;
    background: #667eea;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 16px;
    cursor: pointer;
}

button:hover {
    background: #5568d8;
}

.error {
    color: red;
    text-align: center;
    margin-bottom: 10px;
}

</style>

</head>

<body>

<div class="box">

<h1>💰 Friend Saving Club</h1>

{% if error %}
<div class="error">{{ error }}</div>
{% endif %}

<form method="POST">

<input
type="text"
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

<button type="submit">
Login
</button>

</form>

</div>

</body>

</html>
"""


@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
            SELECT *
            FROM fsc_users
            WHERE username = %s
        """, (username,))

        user = cur.fetchone()

        cur.close()
        conn.close()

        if user and check_password_hash(user["password"], password):

            session["user_id"] = user["id"]
            session["role"] = user["role"]

            return redirect(url_for("dashboard"))

        return render_template_string(
            LOGIN_HTML,
            error="Invalid username or password"
        )

    return render_template_string(
        LOGIN_HTML,
        error=None
    )


# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# =========================
# DASHBOARD
# =========================

@app.route("/dashboard")
def dashboard():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    conn = get_conn()
    cur = conn.cursor()

    # Overall Jama and Payout
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

    total_jama = float(totals["total_jama"])
    total_payout = float(totals["total_payout"])

    # Total Amount = Current Balance
    total_amount = total_jama - total_payout

    # Member-wise Baaki/Wapas
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
                ), 0
            ) AS jama,

            COALESCE(
                SUM(
                    CASE
                        WHEN t.transaction_type = 'payout'
                        THEN t.amount
                        ELSE 0
                    END
                ), 0
            ) AS payout

        FROM fsc_members m

        LEFT JOIN fsc_transactions t
        ON m.id = t.member_id

        GROUP BY m.id, m.name
    """)

    members = cur.fetchall()

    total_baaki = 0
    total_wapas = 0

    for member in members:

        jama = float(member["jama"])
        payout = float(member["payout"])

        if payout > 0 and jama > payout:
            total_baaki += jama - payout

        if payout > jama:
            total_wapas += payout - jama

    # Member count
    cur.execute("""
        SELECT COUNT(*) AS count
        FROM fsc_members
    """)

    member_count = cur.fetchone()["count"]

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
    background: linear-gradient(135deg,#667eea,#764ba2);
    color: white;
    padding: 20px;
}

.header h1 {
    margin: 0;
}

.container {
    width: 94%;
    max-width: 1100px;
    margin: 20px auto;
}

.cards {
    display: grid;
    grid-template-columns:
    repeat(auto-fit,minmax(180px,1fr));

    gap: 15px;
}

.card {
    background: white;
    padding: 20px;
    border-radius: 14px;
    box-shadow:
    0 5px 15px rgba(0,0,0,0.08);
}

.card h3 {
    margin-top: 0;
    color: #555;
}

.amount {
    font-size: 25px;
    font-weight: bold;
    color: #222;
}

.menu {
    margin-top: 25px;
    display: grid;
    grid-template-columns:
    repeat(auto-fit,minmax(180px,1fr));
    gap: 12px;
}

.menu a {
    background: white;
    padding: 15px;
    border-radius: 10px;
    text-decoration: none;
    color: #333;
    box-shadow:
    0 4px 10px rgba(0,0,0,0.08);
}

.logout {
    float: right;
    color: white;
    text-decoration: none;
}

</style>

</head>

<body>

<div class="header">

<a class="logout"
href="/logout">
Logout
</a>

<h1>💰 Friend Saving Club</h1>

<p>
Welcome, {{ user["username"] }}
</p>

</div>

<div class="container">

<div class="cards">

<div class="card">

<h3>💵 Total Jama</h3>

<div class="amount">
₹{{ "%.2f"|format(total_jama) }}
</div>

</div>


<div class="card">

<h3>💸 Total Payout</h3>

<div class="amount">
₹{{ "%.2f"|format(total_payout) }}
</div>

</div>


<div class="card">

<h3>💰 Total Amount / Balance</h3>

<div class="amount">
₹{{ "%.2f"|format(total_amount) }}
</div>

</div>


<div class="card">

<h3>📌 Total Baaki</h3>

<div class="amount">
₹{{ "%.2f"|format(total_baaki) }}
</div>

</div>


<div class="card">

<h3>🔄 Wapas Karna Hai</h3>

<div class="amount">
₹{{ "%.2f"|format(total_wapas) }}
</div>

</div>


<div class="card">

<h3>👥 Members</h3>

<div class="amount">
{{ member_count }}
</div>

</div>

</div>


<div class="menu">

{% if user["role"] == "admin" %}

<a href="/members">
👥 Members
</a>

<a href="/add_member">
➕ Add Member
</a>

<a href="/add_transaction">
💰 Record Transaction
</a>

<a href="/transactions">
📋 Transaction History
</a>

<a href="/report">
📊 Monthly / Date Report
</a>

{% else %}

<a href="/my_transactions">
📋 My Transactions
</a>

<a href="/report">
📊 Report
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
        total_payout=total_payout,
        total_amount=total_amount,
        total_baaki=total_baaki,
        total_wapas=total_wapas,
        member_count=member_count
    )


# =========================
# MEMBERS
# =========================

@app.route("/members")
def members():

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
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
    0 4px 10px rgba(0,0,0,0.08);
}

a {
    text-decoration: none;
}

.btn {
    display: inline-block;
    padding: 9px 13px;
    background: #667eea;
    color: white;
    border-radius: 7px;
    margin: 3px;
}

.delete {
    background: #e74c3c;
}

.back {
    background: #555;
}

</style>

</head>

<body>

<div class="container">

<h1>👥 Members</h1>

<a class="btn"
href="/dashboard">
⬅ Dashboard
</a>

<a class="btn"
href="/add_member">
➕ Add Member
</a>

<hr>

{% for m in members %}

<div class="card">

<h2>
{{ m["name"] }}
</h2>

<p>
Username: {{ m["username"] }}
</p>

<p>
Phone: {{ m["phone"] or "-" }}
</p>

<a class="btn"
href="/edit_member/{{ m["id"] }}">
✏ Edit
</a>

<a class="btn delete"
href="/delete_member/{{ m["id"] }}"
onclick="return confirm('Delete this member?')">
🗑 Delete
</a>

</div>

{% else %}

<p>No members found.</p>

{% endfor %}

</div>

</body>

</html>

"""

    return render_template_string(
        html,
        members=members
    )


# =========================
# ADD MEMBER
# =========================

@app.route("/add_member", methods=["GET", "POST"])
def add_member():

    if not is_admin():
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        name = request.form.get("name")
        username = request.form.get("username")
        password = request.form.get("password")
        phone = request.form.get("phone")

        conn = get_conn()
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

            return """
            <h2>Username already exists.</h2>
            <a href="/add_member">Go Back</a>
            """

        cur.close()
        conn.close()

        return redirect(url_for("members"))

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

a {
    display: inline-block;
    margin-top: 15px;
}

</style>

</head>

<body>

<div class="box">

<h1>➕ Add Member</h1>

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
name="password"
placeholder="Password"
required
>

<input
name="phone"
placeholder="Phone Number"
>

<button type="submit">
Add Member
</button>

</form>

<a href="/members">
⬅ Back
</a>

</div>

</body>

</html>

"""

    return render_template_string(html)


# =========================
# EDIT MEMBER
# =========================

@app.route("/edit_member/<int:id>", methods=["GET", "POST"])
def edit_member(id):

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM fsc_members
        WHERE id = %s
    """, (id,))

    member = cur.fetchone()

    if not member:

        cur.close()
        conn.close()

        return "Member not found"

    if request.method == "POST":

        name = request.form.get("name")
        username = request.form.get("username")
        phone = request.form.get("phone")

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

        cur.close()
        conn.close()

        return redirect(url_for("members"))

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

<h1>✏ Edit Member</h1>

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

<button type="submit">
Update Member
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


# =========================
# DELETE MEMBER
# =========================

@app.route("/delete_member/<int:id>")
def delete_member(id):

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM fsc_members
        WHERE id = %s
    """, (id,))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(url_for("members"))


# =========================
# ADD TRANSACTION
# =========================

@app.route("/add_transaction", methods=["GET", "POST"])
def add_transaction():

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_conn()
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
        note = request.form.get("note")

        if transaction_type not in ["jama", "payout"]:

            cur.close()
            conn.close()

            return "Invalid transaction type"

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

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Add Transaction</title>

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

input,
select,
textarea {

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

<h1>💰 Record Transaction</h1>

<form method="POST">

<label>Member</label>

<select name="member_id" required>

<option value="">
Select Member
</option>

{% for m in members %}

<option value="{{ m["id"] }}">
{{ m["name"] }}
</option>

{% endfor %}

</select>


<label>Transaction Type</label>

<select name="transaction_type" required>

<option value="jama">
Jama / Deposit
</option>

<option value="payout">
Payout / Money Taken
</option>

</select>


<input
type="number"
step="0.01"
name="amount"
placeholder="Amount"
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
placeholder="Note"
></textarea>


<button type="submit">
Save Transaction
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
        today=datetime.now().strftime("%Y-%m-%d")
    )


# =========================
# TRANSACTION HISTORY
# =========================

@app.route("/transactions")
def transactions():

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            t.*,
            m.name

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

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Transaction History</title>

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

.card {
    background: white;
    padding: 15px;
    margin-bottom: 10px;
    border-radius: 10px;
}

.jama {
    color: green;
    font-weight: bold;
}

.payout {
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

<h1>📋 Transaction History</h1>

<a class="btn" href="/dashboard">
⬅ Dashboard
</a>

<a class="btn" href="/add_transaction">
➕ Add Transaction
</a>

<hr>

{% for t in transactions %}

<div class="card">

<h3>
{{ t["name"] }}
</h3>

<p>
📅 {{ t["transaction_date"] }}
</p>

{% if t["transaction_type"] == "jama" %}

<p class="jama">
➕ Jama: ₹{{ "%.2f"|format(t["amount"]|float) }}
</p>

{% else %}

<p class="payout">
➖ Payout: ₹{{ "%.2f"|format(t["amount"]|float) }}
</p>

{% endif %}

<p>
📝 {{ t["note"] or "-" }}
</p>

<a class="btn"
href="/edit_transaction/{{ t["id"] }}">
✏ Edit
</a>

<a class="btn delete"
href="/delete_transaction/{{ t["id"] }}"
onclick="return confirm('Delete this transaction?')">
🗑 Delete
</a>

</div>

{% else %}

<p>
No transactions found.
</p>

{% endfor %}

</div>

</body>

</html>

"""

    return render_template_string(
        html,
        transactions=transactions
    )


# =========================
# EDIT TRANSACTION
# =========================

@app.route("/edit_transaction/<int:id>", methods=["GET", "POST"])
def edit_transaction(id):

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM fsc_transactions
        WHERE id = %s
    """, (id,))

    transaction = cur.fetchone()

    if not transaction:

        cur.close()
        conn.close()

        return "Transaction not found"

    if request.method == "POST":

        transaction_type = request.form.get("transaction_type")
        amount = request.form.get("amount")
        transaction_date = request.form.get("transaction_date")
        note = request.form.get("note")

        cur.execute("""
            UPDATE fsc_transactions

            SET transaction_type = %s,
                amount = %s,
                transaction_date = %s,
                note = %s

            WHERE id = %s
        """, (
            transaction_type,
            amount,
            transaction_date,
            note,
            id
        ))

        conn.commit()

        cur.close()
        conn.close()

        return redirect(url_for("transactions"))

    cur.close()
    conn.close()

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Edit Transaction</title>

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

input,
select,
textarea {

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

<h1>✏ Edit Transaction</h1>

<form method="POST">

<select name="transaction_type">

<option
value="jama"
{% if transaction["transaction_type"] == "jama" %}
selected
{% endif %}
>
Jama
</option>

<option
value="payout"
{% if transaction["transaction_type"] == "payout" %}
selected
{% endif %}
>
Payout
</option>

</select>


<input
type="number"
step="0.01"
name="amount"
value="{{ transaction["amount"] }}"
required
>


<input
type="date"
name="transaction_date"
value="{{ transaction["transaction_date"] }}"
required
>


<textarea
name="note"
>{{ transaction["note"] or "" }}</textarea>


<button type="submit">
Update Transaction
</button>

</form>

<p>
<a href="/transactions">
⬅ Back
</a>
</p>

</div>

</body>

</html>

"""

    return render_template_string(
        html,
        transaction=transaction
    )


# =========================
# DELETE TRANSACTION
# =========================

@app.route("/delete_transaction/<int:id>")
def delete_transaction(id):

    if not is_admin():
        return redirect(url_for("dashboard"))

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM fsc_transactions
        WHERE id = %s
    """, (id,))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(url_for("transactions"))


# =========================
# MY TRANSACTIONS
# =========================

@app.route("/my_transactions")
def my_transactions():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    member = get_member_for_user()

    if not member:
        return redirect(url_for("dashboard"))

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            t.*

        FROM fsc_transactions t

        WHERE t.member_id = %s

        ORDER BY
            t.transaction_date DESC,
            t.id DESC
    """, (member["id"],))

    transactions = cur.fetchall()

    # Member total
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

        WHERE member_id = %s
    """, (member["id"],))

    totals = cur.fetchone()

    total_jama = float(totals["total_jama"])
    total_payout = float(totals["total_payout"])

    total_amount = total_jama - total_payout

    if total_payout > 0:
        total_baaki = max(
            total_jama - total_payout,
            0
        )
    else:
        total_baaki = 0

    total_wapas = max(
        total_payout - total_jama,
        0
    )

    cur.close()
    conn.close()

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>My Transactions</title>

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

.cards {
    display: grid;
    grid-template-columns:
    repeat(auto-fit,minmax(160px,1fr));

    gap: 12px;
}

.card {
    background: white;
    padding: 18px;
    border-radius: 12px;
    box-shadow:
    0 4px 10px rgba(0,0,0,0.08);
}

.amount {
    font-size: 23px;
    font-weight: bold;
}

.transaction {
    background: white;
    padding: 15px;
    margin-top: 10px;
    border-radius: 10px;
}

.jama {
    color: green;
}

.payout {
    color: red;
}

.blue {
    color: #1565c0;
}

.orange {
    color: #e65100;
}

.btn {
    display: inline-block;
    padding: 9px 13px;
    background: #667eea;
    color: white;
    text-decoration: none;
    border-radius: 7px;
}

</style>

</head>

<body>

<div class="container">

<h1>
📋 {{ member["name"] }} - Transactions
</h1>

<a class="btn"
href="/dashboard">
⬅ Dashboard
</a>

<br><br>


<div class="cards">

<div class="card">

<h3>💵 Total Jama</h3>

<div class="amount">
₹{{ "%.2f"|format(total_jama) }}
</div>

</div>


<div class="card">

<h3>💸 Total Payout</h3>

<div class="amount">
₹{{ "%.2f"|format(total_payout) }}
</div>

</div>


<div class="card">

<h3>💰 Total Amount / Balance</h3>

<div class="amount">
₹{{ "%.2f"|format(total_amount) }}
</div>

</div>


<div class="card">

<h3>📌 Baaki</h3>

<div class="amount blue">
₹{{ "%.2f"|format(total_baaki) }}
</div>

</div>


<div class="card">

<h3>🔄 Wapas Karna Hai</h3>

<div class="amount orange">
₹{{ "%.2f"|format(total_wapas) }}
</div>

</div>

</div>


<h2>
Transaction History
</h2>


{% for t in transactions %}

<div class="transaction">

<p>
📅 {{ t["transaction_date"] }}
</p>

{% if t["transaction_type"] == "jama" %}

<p class="jama">
➕ Jama:
<b>
₹{{ "%.2f"|format(t["amount"]|float) }}
</b>
</p>

{% else %}

<p class="payout">
➖ Payout:
<b>
₹{{ "%.2f"|format(t["amount"]|float) }}
</b>
</p>

{% endif %}

<p>
📝 {{ t["note"] or "-" }}
</p>

</div>

{% else %}

<p>
No transactions found.
</p>

{% endfor %}

</div>

</body>

</html>

"""

    return render_template_string(
        html,
        member=member,
        transactions=transactions,
        total_jama=total_jama,
        total_payout=total_payout,
        total_amount=total_amount,
        total_baaki=total_baaki,
        total_wapas=total_wapas
    )


# =========================
# REPORT
# =========================

@app.route("/report")
def report():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    conn = get_conn()
    cur = conn.cursor()

    if from_date and to_date:

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
                    ), 0
                ) AS jama,

                COALESCE(
                    SUM(
                        CASE
                            WHEN t.transaction_type = 'payout'
                            THEN t.amount
                            ELSE 0
                        END
                    ), 0
                ) AS payout

            FROM fsc_members m

            LEFT JOIN fsc_transactions t
            ON m.id = t.member_id
            AND t.transaction_date
                BETWEEN %s AND %s

            GROUP BY m.id, m.name

            ORDER BY m.name
        """, (
            from_date,
            to_date
        ))

    else:

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
                    ), 0
                ) AS jama,

                COALESCE(
                    SUM(
                        CASE
                            WHEN t.transaction_type = 'payout'
                            THEN t.amount
                            ELSE 0
                        END
                    ), 0
                ) AS payout

            FROM fsc_members m

            LEFT JOIN fsc_transactions t
            ON m.id = t.member_id

            GROUP BY m.id, m.name

            ORDER BY m.name
        """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    report_data = []

    total_jama = 0
    total_payout = 0
    total_baaki = 0
    total_wapas = 0

    for row in rows:

        jama = float(row["jama"])
        payout = float(row["payout"])

        balance = jama - payout

        # Baaki rule:
        # payout must be greater than 0
        if payout > 0:
            baaki = max(
                jama - payout,
                0
            )
        else:
            baaki = 0

        wapas = max(
            payout - jama,
            0
        )

        total_jama += jama
        total_payout += payout
        total_baaki += baaki
        total_wapas += wapas

        report_data.append({
            "name": row["name"],
            "jama": jama,
            "payout": payout,
            "balance": balance,
            "baaki": baaki,
            "wapas": wapas
        })

    total_amount = total_jama - total_payout

    html = """

<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Report</title>

<style>

body {
    font-family: Arial;
    background: #f4f6f9;
}

.container {
    width: 96%;
    max-width: 1200px;
    margin: 20px auto;
}

.filter {
    background: white;
    padding: 18px;
    border-radius: 12px;
    margin-bottom: 15px;
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
    repeat(auto-fit,minmax(160px,1fr));
    gap: 12px;
}

.card {
    background: white;
    padding: 18px;
    border-radius: 12px;
    box-shadow:
    0 4px 10px rgba(0,0,0,0.08);
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

th,
td {
    padding: 12px;
    border: 1px solid #ddd;
    text-align: center;
}

th {
    background: #667eea;
    color: white;
}

.baaki {
    color: #1565c0;
    font-weight: bold;
}

.wapas {
    color: #e65100;
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
📊 Friend Saving Club Report
</h1>

<a class="btn"
href="/dashboard">
⬅ Dashboard
</a>


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


<button type="submit">
🔍 Generate Report
</button>

</form>

</div>


<div class="cards">

<div class="card">

<h3>
💵 Total Jama
</h3>

<div class="amount">
₹{{ "%.2f"|format(total_jama) }}
</div>

</div>


<div class="card">

<h3>
💸 Total Payout
</h3>

<div class="amount">
₹{{ "%.2f"|format(total_payout) }}
</div>

</div>


<div class="card">

<h3>
💰 Total Amount / Balance
</h3>

<div class="amount">
₹{{ "%.2f"|format(total_amount) }}
</div>

</div>


<div class="card">

<h3>
📌 Total Baaki
</h3>

<div class="amount baaki">
₹{{ "%.2f"|format(total_baaki) }}
</div>

</div>


<div class="card">

<h3>
🔄 Total Wapas
</h3>

<div class="amount wapas">
₹{{ "%.2f"|format(total_wapas) }}
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
Jama
</th>

<th>
Payout
</th>

<th>
Balance
</th>

<th>
Baaki
</th>

<th>
Wapas
</th>

</tr>


{% for r in report_data %}

<tr>

<td>
{{ r["name"] }}
</td>

<td>
₹{{ "%.2f"|format(r["jama"]) }}
</td>

<td>
₹{{ "%.2f"|format(r["payout"]) }}
</td>

<td>
₹{{ "%.2f"|format(r["balance"]) }}
</td>

<td class="baaki">

₹{{ "%.2f"|format(r["baaki"]) }}

</td>

<td class="wapas">

₹{{ "%.2f"|format(r["wapas"]) }}

</td>

</tr>

{% else %}

<tr>

<td colspan="6">
No data found.
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
        report_data=report_data,
        total_jama=total_jama,
        total_payout=total_payout,
        total_amount=total_amount,
        total_baaki=total_baaki,
        total_wapas=total_wapas,
        from_date=from_date,
        to_date=to_date
    )


# =========================
# CHANGE PASSWORD
# =========================

@app.route("/change_password", methods=["GET", "POST"])
def change_password():

    user = current_user()

    if not user:
        return redirect(url_for("login"))

    message = None
    error = None

    if request.method == "POST":

        old_password = request.form.get("old_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        if not check_password_hash(
            user["password"],
            old_password
        ):

            error = "Old password is incorrect."

        elif new_password != confirm_password:

            error = "New passwords do not match."

        elif len(new_password) < 4:

            error = "Password must be at least 4 characters."

        else:

            conn = get_conn()
            cur = conn.cursor()

            new_hash = generate_password_hash(
                new_password
            )

            cur.execute("""
                UPDATE fsc_users

                SET password = %s

                WHERE id = %s
            """, (
                new_hash,
                user["id"]
            ))

            # If member, also update member password
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

            message = "Password changed successfully."

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

<button type="submit">
Change Password
</button>

</form>

<p>
<a href="/dashboard">
⬅ Back to Dashboard
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


# =========================
# START APP
# =========================

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
