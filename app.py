import os
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    user_id = session["user_id"]

    # Get user's stock holdings
    rows = db.execute("""
                      SELECT symbol, SUM(shares) AS total_shares
                      FROM transactions
                      WHERE user_id = ?
                      GROUP BY symbol
                      """, user_id)

    # Initialize data structure to hold stock data
    stocks = []
    total_stock_value = 0

    # Loop through each stock to get current price and total value
    for row in rows:
        symbol = row["symbol"]
        shares = row["total_shares"]
        stock_info = lookup(symbol)
        price = stock_info["price"]
        total_value = shares * price

        # Append stock info to the list
        stocks.append({
            "symbol": symbol,
            "shares": shares,
            "price": price,
            "total_value": total_value
        })

        # Add to total stock value
        total_stock_value += total_value

    # Get user's current cash balance
    user_cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]

    # Calculate grand total
    grand_total = total_stock_value + user_cash

    # Render the index page with the stock and cash data
    return render_template("index.html", stocks=stocks, cash=user_cash, grand_total=grand_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide a symbol", 403)

        # Ensure symbol is a valid one
        elif not lookup(request.form.get("symbol")):
            return apology("must provide a valid symbol", 400)

        # Ensure shares number are valid
        shares = request.form.get("shares")
        try:
            # Convert shares to a float first to check for decimal values
            shares = float(shares)

            # Ensure shares is an integer and greater than 0
            if shares != int(shares) or shares < 1:
                return apology("must provide a positive integer for shares", 400)

            # Convert to integer after validation
            shares = int(shares)

        except ValueError:
            return apology("must provide a valid integer for shares", 400)

        # Get symbol price
        dict = lookup(request.form.get("symbol"))
        price = dict["price"]

        # Get user cash ammount
        user_id = session["user_id"]
        rows = db.execute("SELECT * FROM users WHERE id = ?", user_id)
        user_cash = rows[0]["cash"]

        # Check if user has enough money
        if user_cash < (price * shares):
            return apology("Not Enought Money to purchase", 403)

        # Update the cash balance of the specified user && Insert the transactions details
        else:
            user_cash = user_cash - (price * shares)
            db.execute("UPDATE users SET cash = ? WHERE id = ?", user_cash, user_id)

            db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?,?, ?, ?)",
                       user_id, dict["symbol"], shares, price)
        # Upon completion, redirect the user to the home page.
        return redirect("/")

    else:
        return render_template("buy.html")

@app.template_filter('abs')
def abs_filter(value):
    return abs(value)

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Get user ID
    user_id = session["user_id"]

    # Query the transactions table for all transactions by the user
    transactions = db.execute("""
        SELECT symbol, shares, price, timestamp
        FROM transactions
        WHERE user_id = ?
        ORDER BY timestamp DESC
    """, user_id)

    # Render the history page, passing in the transactions
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Get the symbol from the form
        symbol = request.form.get("symbol")

        # Ensure symbol was submitted
        if not symbol:
            return apology("must provide a stock symbol", 400)

        # Lookup the stock symbol
        stock = lookup(symbol)

        # Ensure the stock symbol is valid
        if stock is None:
            return apology("invalid stock symbol", 400)

        dict = lookup(request.form.get("symbol"))
        dict["price"] = usd(dict["price"])
        return render_template("quoted.html", stock=dict)

    # User reached route via GET
    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id

    # User reached via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        if not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password confirmation was submitted
        if not request.form.get("confirmation"):
            return apology("must confirm your password", 400)

        # Ensure passwords match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        # Check if username is already taken
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        if len(rows) != 0:
            return apology("username already taken", 400)

        # Hash the password and insert the new user into the database
        hash = generate_password_hash(request.form.get("password"))
        db.execute(
            "INSERT INTO users (username, hash) VALUES (?, ?)", request.form.get("username"), hash
        )

        # Redirect to login page with a success message
        return redirect("/login")

    # User reached via GET (as by clicking a link or redirect)
    else:
        return render_template("register.html")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        # Ensure symbol was submitted
        symbol = request.form.get("symbol")


        if not symbol:
            return apology("must select a stock", 400)

        # Ensure shares number was submittes
        shares = request.form.get("shares")

        try:
            # Convert shares to a float first to check for decimal values
            shares = float(shares)

            # Ensure shares is an integer and greater than 0
            if shares != int(shares) or shares < 1:
                return apology("must provide a positive integer for shares", 400)

            # Convert to integer after validation
            shares = int(shares)
        except ValueError:
            return apology("must provide a valid integer for shares", 400)

        # Get user ID
        user_id = session["user_id"]

        # Get the number of shares owned by the user for selected stock
        rows = db.execute("""
                          SELECT SUM(shares) AS total_shares
                          FROM transactions
                          WHERE user_id = ? AND symbol = ?
                          GROUP BY symbol
                          """, user_id, symbol)


        # check if the user owns the stock and anough shares
        if len(rows) == 0 or rows[0]["total_shares"] < shares:
            return apology("not enough shares to sell", 400)

        # Get current price of the stock
        stock_info = lookup(symbol)
        price = stock_info["price"]

        # Update user's cash balance
        total_value = shares * price
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", total_value, user_id)

        # Insert the sale transaction
        db.execute("""
            INSERT INTO transactions (user_id, symbol, shares, price, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, user_id, symbol, -shares, price, datetime.now())

        # Redirect to home page
        return redirect("/")

    else:
        # Render the sell form
        # Get stocks owned by the user
        stocks = db.execute("""
            SELECT symbol
            FROM transactions
            WHERE user_id = ?
            GROUP BY symbol
        """, session["user_id"])

        return render_template("sell.html", stocks=[stock["symbol"] for stock in stocks])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
