from datetime import datetime
from flask import Flask, render_template, request, redirect, flash, session, url_for
from decimal import Decimal
import mysql.connector

app = Flask(__name__, static_folder='static')
app.secret_key = 'atm_interface'  # For flash messages

# Database connection
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="shreyapk",
        database="atm_db"
    )

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        card_number = request.form.get('card_number')
        password = request.form.get('password')

        if not card_number or not password:
            flash("Card number and password are required.", "danger")
            return redirect('/')

        conn = get_db_connection()
        cur = conn.cursor()

        # Check if the user exists and get relevant info
        cur.execute("SELECT id, password, blocked, blocked_time, pin_attempts FROM users WHERE card_number = %s", (card_number,))
        user_data = cur.fetchone()

        if not user_data:
            flash("Invalid card number or password.", "danger")
            return redirect('/')

        user_id, db_password, blocked, blocked_time, pin_attempts = user_data

        if blocked:
            cur.execute("SELECT NOW()")
            now = cur.fetchone()[0]
            if blocked_time and (now - blocked_time).total_seconds() >= 6 * 3600:
                # Unblock after 6 hours
                cur.execute("UPDATE users SET blocked = 0, blocked_time = NULL, pin_attempts = 0 WHERE card_number = %s", (card_number,))
                conn.commit()
            else:
                flash("Your account is blocked due to multiple failed login attempts. Try again later.", "danger")
                conn.close()
                return redirect('/')

        if password == db_password:
            # Successful login
            cur.execute("UPDATE users SET pin_attempts = 0 WHERE card_number = %s", (card_number,))
            conn.commit()
            session['card_number'] = card_number
            session['user_id'] = user_id  # ✅ Store user_id for later use
            flash("Login successful!", "success")
            conn.close()
            return redirect('/select-language')
        else:
            # Increment login attempts
            pin_attempts += 1
            if pin_attempts >= 3:
                cur.execute("UPDATE users SET blocked = 1, blocked_time = NOW(), pin_attempts = %s WHERE card_number = %s", (pin_attempts, card_number))
                flash("Account blocked. Try again later.", "danger")
            else:
                cur.execute("UPDATE users SET pin_attempts = %s WHERE card_number = %s", (pin_attempts, card_number))
                flash("Invalid card number or password. Try Again", "danger")

            conn.commit()
            conn.close()
            return redirect('/')
    else:
        return render_template('index.html')  # Show login form if GET request

@app.route('/menu', methods=['GET', 'POST'])
def menu():
    if request.method == 'POST':
        transaction = request.form.get('menu')
        templates = {
            'balance': 'balance_inquiry.html',
            'withdraw': 'withdraw.html',
            'change_pin': 'change_pin.html',
        }
        redirects = {
            'statement': '/mini_statement',
            'exit': '/exit',
        }

        if transaction in templates:
            return render_template(templates[transaction])
        elif transaction in redirects:
            return redirect(redirects[transaction])

    return render_template('menu.html')

@app.route('/balance_inquiry', methods=['GET'])
def balance_inquiry():
    card_number = session.get('card_number')

    if not card_number:
        flash("You are not logged in!", "error")
        return redirect('/') # Use redirect instead of render_template

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        query = "SELECT balance FROM users WHERE card_number = %s"
        cur.execute(query, (card_number,))
        result = cur.fetchone()

        if result:
            balance = result[0]  # Since result contains a single value (balance), use index 0
            return render_template('balance_inquiry.html', balance=balance)
        flash("Account not found!", "error")
        return render_template('menu.html')
    except mysql.connector.Error as e:
        flash(f"Error fetching balance: {str(e)}", "error")
        return render_template('menu.html')

    finally:
        cur.close()
        conn.close()

@app.route('/withdraw', methods=['GET', 'POST'])
def withdraw():
    account_type = None  # Default value in case it's not passed from a form

    if request.method == 'POST':
        # Get the account type selected by the user
        account_type = request.form.get('account_type')
        if account_type:
            account_type = account_type.capitalize()  # Normalize the case


        if not account_type:
            flash("Please select an account type!", "error")
            return render_template('withdraw.html')

        # Store the account type in session to persist it across routes
        session['account_type'] = account_type

        # Ensure the account type is valid before continuing
        valid_account_types = ['Savings', 'Current', 'Credit']

        if account_type not in valid_account_types:
            flash(f"{account_type} is not a valid account type!", "error")
            return render_template('withdraw.html')

        # Redirect to withdraw_amount to enter withdrawal details
        return redirect(url_for('withdraw_amount'))

    return render_template('withdraw.html', account_type=account_type)

@app.route('/withdraw_amount', methods=['GET', 'POST'])
def withdraw_amount():
    card_number = session.get('card_number')
    selected_account_type = session.get('account_type')

    if not card_number:
        flash("You are not logged in!", "error")
        return redirect(url_for('login'))  # or render_template('index.html')

    if not selected_account_type:
        flash("No account type selected!", "error")
        return redirect(url_for('withdraw'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Step 1: Get the actual account type for this user
    cursor.execute("SELECT account_type, balance FROM users WHERE card_number = %s", (card_number,))
    user_data = cursor.fetchone()

    if not user_data:
        flash("User account not found!", "error")
        conn.close()
        return redirect(url_for('withdraw'))

    actual_account_type, current_balance = user_data

    # Step 2: Compare selected account type with actual account type in DB
    if selected_account_type != actual_account_type:
        flash(f"You do not have a {selected_account_type} account!", "error")
        conn.close()
        return redirect(url_for('withdraw'))

    if request.method == 'POST':
        amount = request.form.get('amount')

        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError
        except (ValueError, TypeError):
            flash("Please enter a valid amount to withdraw!", "error")
            conn.close()
            return render_template('cash_withdraw.html', account_type=actual_account_type)

        # Convert amount to decimal for precision
        amount = Decimal(amount)

        if amount > current_balance:
            flash("Insufficient funds. Please enter a lesser amount.", "error")
            conn.close()
            return render_template('cash_withdraw.html', account_type=actual_account_type, balance=current_balance)

        # Perform withdrawal
        new_balance = current_balance - amount

        # Update the balance in the database
        cursor.execute("UPDATE users SET balance = %s WHERE card_number = %s", (new_balance, card_number))
        
        # Step 3: Insert the transaction into the transactions table
        cursor.execute("""
            INSERT INTO transactions (card_number, transaction_type, amount, balance)
            VALUES (%s, 'Withdraw', %s, %s)
        """, (card_number, amount, new_balance))
        
        conn.commit()

        # All good, store amount in session and proceed to PIN check
        session['withdraw_amount'] = amount
        conn.close()
        return redirect(url_for('enter_pin'))

    conn.close()
    return render_template('cash_withdraw.html', account_type=actual_account_type)

@app.route('/enter_pin', methods=['GET', 'POST'])
def enter_pin():
    card_number = session.get('card_number')

    if not card_number:
        flash("You are not logged in!", "error")
        return render_template('index.html')

    if request.method == 'POST':
        pin = request.form.get('pin')

        if not pin:
            flash("Please enter your PIN!", "error")
            return render_template('enter_pin.html')

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT pin, blocked, blocked_time, pin_attempts FROM users WHERE card_number = %s", (card_number,))
            user = cursor.fetchone()

            if user:
                # If user is blocked, check the time difference
                if user['blocked']:
                    now = datetime.utcnow()
                    if user['blocked_time'] and (now - user['blocked_time']).total_seconds() >= 6 * 3600:
                        # Unblock after 6 hours
                        cursor.execute("UPDATE users SET blocked = 0, blocked_time = NULL, pin_attempts = 0 WHERE card_number = %s", (card_number,))
                        conn.commit()
                    else:
                        flash("Your account is blocked due to multiple failed PIN attempts. Try again later.", "danger")
                        conn.close()
                        return render_template('enter_pin.html')

                # Validate PIN
                if pin != user['pin']:
                    new_pin_attempts = user['pin_attempts'] + 1
                    if new_pin_attempts >= 3:
                        # Lock the account after 3 failed PIN attempts
                        cursor.execute("UPDATE users SET blocked = 1, blocked_time = NOW(), pin_attempts = %s WHERE card_number = %s", (new_pin_attempts, card_number))
                        flash("Incorrect PIN entered 3 times. Your account is now blocked for 6 hours.", "danger")
                    else:
                        cursor.execute("UPDATE users SET pin_attempts = %s WHERE card_number = %s", (new_pin_attempts, card_number))
                        flash(f"Incorrect PIN. Try Again", "danger")

                    conn.commit()
                    conn.close()
                    return render_template('enter_pin.html')

                # Correct PIN entered, reset failed attempts and blocked status
                cursor.execute("UPDATE users SET pin_attempts = 0, blocked = 0, blocked_time = NULL WHERE card_number = %s", (card_number,))
                conn.commit()

                # Step 6: After PIN validation, complete the withdrawal process
                withdraw_amount = session.get('withdraw_amount')
                if withdraw_amount:
                    flash("Withdrawal successful! Thank you for using the ATM.", "success")
                    return redirect(url_for('login'))  # Redirect to login or next step

            else:
                flash("User not found.", "error")
                conn.close()
                return render_template('enter_pin.html')

        except Exception as e:
            flash(f"Error: {str(e)}", "error")
            conn.close()
            return render_template('enter_pin.html')
    return render_template('enter_pin.html')  # Show PIN entry form

@app.route('/select-language', methods=['GET', 'POST'])
def select_language():
    if request.method == 'POST':
        selected_language = request.form.get('language')
        session['language'] = selected_language  # store selected language in session
        flash(f"You selected {selected_language}.", "success")
        return redirect('/menu')  # change this to wherever you want to go next

    return render_template('select_language.html')

# @app.route('/confirm_withdraw', methods=['GET', 'POST'])
# def confirm_withdraw():
#     # Get the form data
#     amount = request.form['amount']
#     account_type = request.form['account_type']

#     # Retrieve the session data (you should already have the amount and account_type in the session or from the form)
#     card_number = session.get('card_number')  # Assuming the card number is saved in the session
#     pin = request.form['pin']  # Assuming PIN is submitted through the form

#     if not card_number or not amount or not pin or not account_type:
#         flash("Missing form data. Please try again.", "error")
#         return render_template('enter_pin.html', amount=amount, account_type=account_type)

#     try:
#         # Establish database connection
#         conn = get_db_connection()
#         cur = conn.cursor()

#         # Verify the PIN and get the account balance
#         cur.execute("SELECT pin, balance, blocked FROM users WHERE card_number = %s AND account_type = %s", 
#                     (card_number, account_type))
#         result = cur.fetchone()

#         if not result:
#             flash("Account not found.", "error")
#             return render_template('enter_pin.html', amount=amount, account_type=account_type)

#         db_pin, balance, blocked = result

#         if blocked:
#             flash("Your account is blocked. Please contact the bank.", "error")
#             return redirect(url_for('index'))  # Redirect to login if blocked

#         # Check if the PIN matches
#         if pin != db_pin:
#             flash("Incorrect PIN.", "error")
#             return render_template('enter_pin.html', amount=amount, account_type=account_type)

#         # Check if sufficient balance is available
#         if float(amount) > float(balance):
#             flash("Insufficient balance.", "error")
#             return render_template('enter_pin.html', amount=amount, account_type=account_type)

#         # Proceed with the withdrawal: Deduct the amount from the account
#         new_balance = float(balance) - float(amount)

#         # Update the user's balance in the database
#         cur.execute("UPDATE users SET balance = %s WHERE card_number = %s AND account_type = %s",
#                     (new_balance, card_number, account_type))

#         # Log the transaction in the 'transactions' table
#         cur.execute("""
#             INSERT INTO transactions (card_number, transaction_type, amount, balance)
#             VALUES (%s, %s, %s, %s)
#         """, (card_number, 'Withdraw', amount, new_balance))

#         # Commit the transaction
#         conn.commit()

#         flash("Withdrawal successful!", "success")

#         # Close the cursor and connection
#         cur.close()
#         conn.close()

#         # Redirect to the login page (or any other page as per your flow)
#         return redirect(url_for('index'))  # Redirect to login page after success

#     except mysql.connector.Error as e:
#         flash(f"Database error: {str(e)}", "error")
#         return render_template('enter_pin.html', amount=amount, account_type=account_type)

#     finally:
#         # Ensure the cursor and connection are always closed
#         if 'cur' in locals():
#             cur.close()
#         if 'conn' in locals():
#             conn.close()

# @app.route('/perform_withdraw', methods=['GET','POST'])
# def perform_withdraw():
#     card_number = request.form.get('card_number')
#     amount = request.form.get('amount')
#     pin = request.form.get('pin')
#     account_type = request.form.get('account_type')

#     if not card_number or not amount or not pin or not account_type:
#         flash("Missing form data. Please try again.", "error")
#         return render_template('withdraw.html')

#     try:
#         conn = get_db_connection()
#         cur = conn.cursor()

#         # Verify PIN and check block status
#         cur.execute("SELECT pin, blocked, balance FROM users WHERE card_number = %s AND account_type = %s", 
#                     (card_number, account_type))
#         result = cur.fetchone()

#         if not result:
#             flash("Account not found.", "error")
#             return render_template('withdraw.html')

#         db_pin, blocked, balance = result

#         if blocked:
#             flash("Your account is blocked. Please contact the bank.", "error")
#             return render_template('index.html')

#         if pin != db_pin:
#             flash("Incorrect PIN.", "error")
#             return render_template('withdraw.html')

#         if float(amount) > float(balance):
#             flash("Insufficient balance.", "error")
#             return render_template('withdraw.html')

#         new_balance = float(balance) - float(amount)

#         cur.execute("UPDATE users SET balance = %s WHERE card_number = %s AND account_type = %s",
#                     (new_balance, card_number, account_type))

#         cur.execute("""
#             INSERT INTO transactions (card_number, transaction_type, amount, balance)
#             VALUES (%s, %s, %s, %s)
#         """, (card_number, 'Withdraw', amount, new_balance))

#         conn.commit()

#         flash("Withdrawal successful!", "success")
#         return render_template('index.html')

#     except mysql.connector.Error as e:
#         flash(f"Database error: {str(e)}", "error")
#         return render_template('withdraw.html')

#     finally:
#         cur.close()
#         conn.close()

# @app.route('/perform_withdraw', methods=['POST'])
# def perform_withdraw():
#     card_number = session.get('card_number')
#     account_type = request.form.get('account_type')  # Get the selected account type
#     amount = float(request.form.get('amount', 0))  # Get the withdrawal amount

#     if not card_number:
#         flash("You are not logged in!", "error")
#         return render_template('index.html')  # Redirect instead of render_template

#     if account_type not in ['savings', 'current', 'credit']:
#         flash("Invalid account type selected. "
#         "Please choose a valid account type.", "error")
#         return render_template('cash_withdraw.html')  # Redirect instead of render_template

#     try:
#         conn = get_db_connection()
#         cur = conn.cursor()
        
#         # Check the user's balance
#         query = "SELECT balance FROM users WHERE card_number = %s AND account_type = %s"
#         cur.execute(query, (card_number, account_type))
#         result = cur.fetchone()

#         if result:
#             balance = float(result[0])
#             if amount > balance:
#                 flash("Insufficient balance for this withdrawal!", "error")
#                 return render_template('withdraw.html')

#             # Perform the withdrawal
#             new_balance = balance - amount
#             update_query = "UPDATE users SET balance = %s WHERE card_number = %s AND account_type = %s"
#             cur.execute(update_query, (new_balance, card_number, account_type))
            
#             # Insert the transaction record
#             transaction_query = """
#                 INSERT INTO transactions (card_number, transaction_type, amount, balance) 
#                 VALUES (%s, %s, %s, %s)
#             """
#             cur.execute(transaction_query, (card_number, 'Withdraw', amount, new_balance))
#             conn.commit()

#             flash(f"Withdrawal of {amount} successful!", "success")
#             return render_template('index.html')  # Proper redirection

        
#         flash(f"No {account_type.capitalize()} account found for this card number!", "error")
#         return render_template('cash_withdraw.html')
#     except mysql.connector.Error as e:
#         flash(f"Error performing withdrawal: {str(e)}", "error")
#         return render_template('menu.html')

#     finally:
#         cur.close()
#         conn.close()

@app.route('/mini_statement', methods=['GET'])
def mini_statement():
    card_number = session.get('card_number')

    if not card_number:
        flash("You are not logged in!", "error")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT t.transaction_date, t.transaction_type, t.amount, t.balance, u.account_type
        FROM transactions t
        JOIN users u ON t.card_number = u.card_number
        WHERE t.card_number = %s
        ORDER BY t.transaction_date DESC
        LIMIT 10
    """
    cursor.execute(query, (card_number,))
    rows = cursor.fetchall()

    # Use cursor.description to pair column names with values
    columns = [column[0] for column in cursor.description]
    transactions = [dict(zip(columns, row)) for row in rows]

    conn.close()

    # Debugging print statement
    print("Transactions fetched:", transactions)

    return render_template('mini_statement.html', transactions=transactions)

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
            conn = get_db_connection()
            cur = conn.cursor()

            # Check if the old PIN is correct
            query = "SELECT pin FROM users WHERE card_number = %s"
            cur.execute(query, (card_number,))
            result = cur.fetchone()

            if result and result[0] == old_pin:
                # Update with the new PIN
                update_query = "UPDATE users SET pin = %s WHERE card_number = %s"
                cur.execute(update_query, (new_pin, card_number))
                conn.commit()
                flash("PIN changed successfully!", "success")
                return render_template('index.html')
            
            flash("Incorrect old PIN!", "error")
            return render_template('change_pin.html')
        except mysql.connector.Error as e:
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