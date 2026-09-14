"""
Target App — CreditUnion Pro (Legacy-style)
Mimics a real bank back-office app:
  - Table-based HTML, no test IDs
  - Server-rendered, multi-step flow
  - search → detail page → transfer form
Run: python target_app/app.py
"""

from flask import Flask, render_template_string, request, redirect, url_for

app = Flask(__name__)

# Fake member database
MEMBERS = {
    "12345": {
        "name": "Alice Johnson",
        "savings_balance": "$4,230.50",
        "checking_balance": "$1,120.00",
        "account_status": "Active",
        "branch": "Main Street",
    },
    "67890": {
        "name": "Bob Smith",
        "savings_balance": "$890.00",
        "checking_balance": "$340.75",
        "account_status": "Active",
        "branch": "Downtown",
    },
}

# Intentionally legacy HTML — no IDs, table layout
HOME_HTML = """<!DOCTYPE html>
<html><head><title>CreditUnion Pro</title></head>
<body bgcolor="#e8e8e8">
<table width="100%" border="0" cellpadding="4" bgcolor="#003366">
  <tr><td><font color="white" size="4"><b>&nbsp;CreditUnion Pro v2.1</b></font></td></tr>
</table>
<br>
<table width="580" border="1" cellpadding="10" bgcolor="white" align="center">
  <tr bgcolor="#336699"><td><font color="white"><b>Member Lookup</b></font></td></tr>
  <tr><td>
    <form method="POST" action="/lookup">
      Member ID: <input type="text" name="member_id" size="20">
      &nbsp;<input type="submit" value="Search Member">
    </form>
  </td></tr>
</table>
</body></html>"""

MEMBER_HTML = """<!DOCTYPE html>
<html><head><title>Member {{ member_id }}</title></head>
<body bgcolor="#e8e8e8">
<table width="100%" border="0" cellpadding="4" bgcolor="#003366">
  <tr><td><font color="white" size="4"><b>&nbsp;CreditUnion Pro v2.1</b></font></td></tr>
</table>
<br>
<table width="580" border="1" cellpadding="10" bgcolor="white" align="center">
  <tr bgcolor="#336699"><td colspan="2"><font color="white"><b>Member Account Details</b></font></td></tr>
  <tr><td><b>Member ID</b></td><td>{{ member_id }}</td></tr>
  <tr><td><b>Full Name</b></td><td>{{ name }}</td></tr>
  <tr><td><b>Account Status</b></td><td>{{ account_status }}</td></tr>
  <tr><td><b>Branch</b></td><td>{{ branch }}</td></tr>
  <tr bgcolor="#ffffcc"><td><b>Savings Balance</b></td><td><b>{{ savings_balance }}</b></td></tr>
  <tr bgcolor="#ffffcc"><td><b>Checking Balance</b></td><td><b>{{ checking_balance }}</b></td></tr>
  <tr><td colspan="2">
    <a href="/">Back to Search</a> &nbsp;|&nbsp;
    <a href="/transfer/{{ member_id }}">Initiate Transfer</a>
  </td></tr>
</table>
</body></html>"""

NOT_FOUND_HTML = """<!DOCTYPE html>
<html><head><title>Not Found</title></head>
<body bgcolor="#e8e8e8">
<table width="580" border="1" cellpadding="10" bgcolor="white" align="center">
  <tr bgcolor="#cc3333"><td><font color="white"><b>Member Not Found</b></font></td></tr>
  <tr><td>No member record found for ID: <b>{{ member_id }}</b></td></tr>
  <tr><td><a href="/">Return to Search</a></td></tr>
</table>
</body></html>"""

@app.route("/")
def home():
    return render_template_string(HOME_HTML)

@app.route("/lookup", methods=["POST"])
def lookup():
    member_id = request.form.get("member_id", "").strip()
    if member_id in MEMBERS:
        return redirect(url_for("member_detail", member_id=member_id))
    return render_template_string(NOT_FOUND_HTML, member_id=member_id), 404

@app.route("/member/<member_id>")
def member_detail(member_id):
    if member_id not in MEMBERS:
        return render_template_string(NOT_FOUND_HTML, member_id=member_id), 404
    return render_template_string(MEMBER_HTML, member_id=member_id, **MEMBERS[member_id])

@app.route("/transfer/<member_id>", methods=["GET", "POST"])
def transfer(member_id):
    if request.method == "POST":
        amount = request.form.get("amount", "0")
        return f"<h2>Transfer of ${amount} submitted for member {member_id}</h2><a href='/'>Back</a>"
    return f"""<html><body>
    <form method="POST">
      Amount: <input name="amount" type="text">
      <input type="submit" value="Submit Transfer" style="background:red;color:white">
    </form></body></html>"""

if __name__ == "__main__":
    print("Running at http://localhost:5000")
    app.run(port=5000, debug=True)