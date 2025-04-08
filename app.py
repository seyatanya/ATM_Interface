from flask import Flask, render_template, request, redirect, flash, session
import mysql.connector
from decimal import Decimal


app = Flask(__name__, static_folder='static')
app.secret_key = 'atm_interface'  # For flash messages

# Database connection
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="shreyapk",
    database="atm_db"
)
cur = conn.cursor()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    card_number = request.form.get('card_number')
    pin = request.form.get('pin')

    # Track login attempts in session
    if 'login_attempts' not in session:
        session['login_attempts'] = 0

    # Connect to database
    conn = mysql.connector.connect(
        host='localhost',
        user='root',
        password='shreyapk',
        database='atm_db'
    )
    cur = conn.cursor()

    # Check if the user is blocked and get the blocked time
    cur.execute("SELECT blocked, blocked_time FROM users WHERE card_number = %s", (card_number,))
    user_status = cur.fetchone()

    if user_status:
        blocked, blocked_time = user_status

        if blocked:
            # Get current time from DB
            cur.execute("SELECT NOW()")
            now = cur.fetchone()[0]

            # If 6 hours have passed, unblock the account
            if blocked_time and (now - blocked_time).total_seconds() >= 6 * 3600:
                cur.execute("UPDATE users SET blocked = 0, blocked_time = NULL WHERE card_number = %s", (card_number,))
                conn.commit()
            else:
                flash("Your account is blocked due to multiple failed login attempts. Try again later.", "danger")
                conn.close()
                return redirect('/')

    # Authenticate the user
    cur.execute("SELECT * FROM users WHERE card_number = %s AND pin_hash = %s", (card_number, pin))
    user = cur.fetchone()

    if user:
        # Login success
        session['card_number'] = card_number
        session['login_attempts'] = 0
        flash('Login successful!', 'success')
        conn.close()
        return redirect('/menu')
    else:
        # Login failed
        session['login_attempts'] += 1
        attempts_left = 3 - session['login_attempts']

        if attempts_left <= 0:
            # Block account and set blocked time
            cur.execute("UPDATE users SET blocked = 1, blocked_time = NOW() WHERE card_number = %s", (card_number,))
            conn.commit()
            flash("Account blocked after 3 failed attempts.", "danger")
        else:
            flash(f"Invalid card number or PIN!", "danger")

        conn.close()
        return redirect('/')


@app.route('/menu', methods=['GET', 'POST'])
def menu():
    if request.method == 'POST':
        transaction = request.form.get('menu')

        if transaction == 'balance':
            return render_template('balance_inquiry.html')
        elif transaction == 'withdraw':
            return render_template('withdraw.html')
        elif transaction == 'deposit':
            return redirect('/deposit')
        elif transaction == 'statement':
            return redirect('/mini_statement')
        elif transaction == 'change_pin':
            return render_template('change_pin.html')
        elif transaction == 'exit':
            return redirect('/exit')

    return render_template('menu.html')

@app.route('/balance_inquiry', methods=['GET'])
def balance_inquiry():
    card_number = session.get('card_number')

    if not card_number:
        flash("You are not logged in!", "error")
        return render_template('index.html')  # Use redirect instead of render_template

    try:
        conn = mysql.connector.connect(
            host='localhost',
            user='root',
            password='shreyapk',
            database='atm_db'
        )
        cur = conn.cursor()

        query = "SELECT balance FROM users WHERE card_number = %s"
        cur.execute(query, (card_number,))
        result = cur.fetchone()

        if result:
            balance = result[0]  # Since result contains a single value (balance), use index 0
            return render_template('balance_inquiry.html', balance=balance)
        else:
            flash("Account not found!", "error")
            return render_template('menu.html')

    except Exception as e:
        flash(f"Error fetching balance: {str(e)}", "error")
        return render_template('menu.html')

    finally:
        cur.close()
        conn.close()


@app.route('/withdraw', methods=['GET', 'POST'])
def withdraw():
    card_number = session.get('card_number')

    if not card_number:
        flash("You are not logged in!", "error")
        return render_template('index.html')

    if request.method == 'POST':
        account_type = request.form.get('account_type')

        if not account_type:
            flash("Please select an account type!", "error")
            return render_template('cash_withdraw.html')

        try:
            conn = mysql.connector.connect(
                host='localhost',
                user='root',
                password='shreyapk',
                database='atm_db'
            )
            cur = conn.cursor()

            # Get the balance of the selected account type
            query = "SELECT balance FROM users WHERE card_number = %s AND account_type = %s"
            cur.execute(query, (card_number, account_type))
            result = cur.fetchone()

            if result:
                balance = float(result[0])
                flash(f"Selected Account: {account_type.capitalize()}", "success")
                return render_template('withdraw.html', balance=balance, account_type=account_type)
            else:
                flash(f"No {account_type.capitalize()} account found for this card number!", "error")
                return render_template('cash_withdraw.html')

        except Exception as e:
            flash(f"Error retrieving account: {str(e)}", "error")
            return render_template('menu.html')

        finally:
            cur.close()
            conn.close()

    # GET request: show the account selection page
    return render_template('cash_withdraw.html')

@app.route('/perform_withdraw', methods=['POST'])
def perform_withdraw():
    card_number = session.get('card_number')
    account_type = request.form.get('account_type')  # Get the selected account type
    amount = float(request.form.get('amount', 0))  # Get the withdrawal amount

    if not card_number:
        flash("You are not logged in!", "error")
        return render_template('index.html')  # Redirect instead of render_template

    if account_type not in ['savings', 'current', 'credit']:
        flash("Invalid account type selected. Please choose a valid account type.", "error")
        return render_template('cash_withdraw.html')  # Redirect instead of render_template

    try:
        conn = mysql.connector.connect(
            host='localhost',
            user='root',
            password='shreyapk',
            database='atm_db'
        )
        cur = conn.cursor()

        # Check the user's balance
        query = "SELECT balance FROM users WHERE card_number = %s AND account_type = %s"
        cur.execute(query, (card_number, account_type))
        result = cur.fetchone()

        if result:
            balance = float(result[0])
            if amount > balance:
                flash("Insufficient balance for this withdrawal!", "error")
                return render_template('withdraw.html')

            # Perform the withdrawal
            new_balance = balance - amount
            update_query = "UPDATE users SET balance = %s WHERE card_number = %s AND account_type = %s"
            cur.execute(update_query, (new_balance, card_number, account_type))

            # Insert the transaction record
            transaction_query = """
                INSERT INTO transactions (card_number, transaction_type, amount, balance) 
                VALUES (%s, %s, %s, %s)
            """
            cur.execute(transaction_query, (card_number, 'Withdraw', amount, new_balance))
            conn.commit()

            flash(f"Withdrawal of {amount} successful!", "success")
            return render_template('index.html')  # Proper redirection

        else:
            flash(f"No {account_type.capitalize()} account found for this card number!", "error")
            return render_template('cashwithdraw.html')

    except Exception as e:
        flash(f"Error performing withdrawal: {str(e)}", "error")
        return render_template('menu'
        '.html')

    finally:
        cur.close()
        conn.close()

@app.route('/mini_statement', methods=['GET'])
def mini_statement():
    card_number = session.get('card_number')

    if not card_number:
        flash("You are not logged in!", "error")
        return render_template('index.html')

    try:
        conn = mysql.connector.connect(
            host='localhost',
            user='root',
            password='shreyapk',
            database='atm_db'
        )
        cur = conn.cursor()

        # Retrieve the last 10 transactions for the logged-in user
        query = """
    SELECT t.transaction_date, t.transaction_type, t.amount, t.balance, u.account_type
    FROM transactions t
    JOIN users u ON t.card_number = u.card_number
    WHERE t.card_number = %s
    ORDER BY t.transaction_date DESC
    LIMIT 10
"""

        cur.execute(query, (card_number,))
        transactions = cur.fetchall()

        return render_template('mini_statement.html', transactions=transactions)

    except Exception as e:
        flash(f"Error retrieving mini statement: {str(e)}", "error")
        return render_template('menu.html')

    finally:
        cur.close()
        conn.close()


@app.route('/change_pin', methods=['GET', 'POST'])
def change_pin():
    card_number = session.get('card_number')

    if request.method == 'POST':
        old_pin = request.form.get('old_pin')
        new_pin = request.form.get('new_pin')
        confirm_pin = request.form.get('confirm_pin')

        if not card_number:
            flash("You are not logged in!", "error")
            return render_template('index.html')

        if new_pin != confirm_pin:
            flash("New PIN and confirmation do not match!", "error")
            return render_template('change_pin.html')

        try:
            conn = mysql.connector.connect(
                host='localhost',
                user='root',
                password='shreyapk',
                database='atm_db'
            )
            cur = conn.cursor()

            # Check if the old PIN is correct
            query = "SELECT pin_hash FROM users WHERE card_number = %s"
            cur.execute(query, (card_number,))
            result = cur.fetchone()

            if result and result[0] == old_pin:
                # Update with the new PIN
                update_query = "UPDATE users SET pin_hash = %s WHERE card_number = %s"
                cur.execute(update_query, (new_pin, card_number))
                conn.commit()
                flash("PIN changed successfully!", "success")
                return render_template('index.html')
            else:
                flash("Incorrect old PIN!", "error")
                return render_template('change_pin.html')

        except Exception as e:
            flash(f"Error changing PIN: {str(e)}", "error")
            return render_template('index.html')

        finally:
            cur.close()
            conn.close()

    return render_template('change_pin.html')

@app.route('/exit', methods=['GET', 'POST'])
def exit():
    session.clear()
    flash("You have been logged out. Thank you for using the ATM!", "info")
    return redirect('/')

if __name__ == "__main__":
    app.run(debug=True)

