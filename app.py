from flask import Flask, render_template, request, redirect, url_for, flash
import mysql.connector

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # For flash messages

# Database connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="shreyapk",
    database="atm_db"
)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    card_number = request.form['card_number']
    pin = request.form['pin']

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE card_number = %s AND pin = %s", (card_number, pin))
    user = cursor.fetchone()

    if user:
        flash('Login successful!', 'success')
        return redirect(url_for('dashboard'))
    else:
        flash('Invalid card number or PIN.', 'danger')
        return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

if __name__ == "__main__":
    app.run(debug=True)
