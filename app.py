from flask import Flask, render_template, request, redirect, url_for, flash
import mysql.connector

app = Flask(__name__)
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

@app.route('/login', methods=['POST'])
def login():
    card_number = request.form.get('card_number')
    pin_hash = request.form.get('pin')

    # Database query
    query = "SELECT * FROM users WHERE card_number=%s AND pin=%s"
    cur.execute("SELECT * FROM users WHERE card_number=%s AND pin_hash=%s", (card_number, pin_hash))
    user = cur.fetchone()

    if user:
        flash('Login successful!', 'success')
        return redirect('/dashboard')
    else:
        flash('Invalid card number or PIN!', 'danger')
        return redirect('/')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if request.method == 'POST':
        transaction = request.form.get('dashboard')

        if transaction == 'balance':
            return redirect(url_for('balance_inquiry'))
        elif transaction == 'withdraw':
            return redirect(url_for('withdraw'))
        elif transaction == 'deposit':
            return redirect(url_for('deposit'))
        elif transaction == 'statement':
            return redirect(url_for('mini_statement'))
        elif transaction == 'change_pin':
            return redirect(url_for('change_pin'))
        elif transaction == 'exit':
            return redirect(url_for('logout'))

    return render_template('dashboard.html')

@app.route('/balance_inquiry')
def balance_inquiry():
    # Fetch balance from the database and display
    return "Balance Inquiry Page (Coming Soon!)"

@app.route('/withdraw')
def withdraw():
    # Cash withdrawal logic
    return "Cash Withdrawal Page (Coming Soon!)"

@app.route('/deposit')
def deposit():
    # Cash deposit logic
    return "Cash Deposit Page (Coming Soon!)"

@app.route('/mini_statement')
def mini_statement():
    # Display the recent transactions
    return "Mini Statement Page (Coming Soon!)"

@app.route('/change_pin')
def change_pin():
    # Change PIN logic
    return "Change PIN Page (Coming Soon!)"



@app.route('/logout')
def logout():
    return redirect('index.html')


if __name__ == "__main__":
    app.run(debug=True)

