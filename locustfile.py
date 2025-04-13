from locust import HttpUser, task, between

class ATMUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        # This runs before every test starts and logs in the user
        response = self.client.post("/login", data={
            "card_number": "1234567890",  # Use a valid test card_number from DB
            "pin": "1234"                 # Use matching valid pin_hash from DB
        }, allow_redirects=True)

        if "Login successful!" not in response.text:
            print("Login failed in on_start")

    @task
    def check_balance(self):
        self.client.get("/balance_inquiry")

    @task
    def view_menu(self):
        self.client.get("/menu")

    @task
    def withdraw_cash(self):
        # Step 1: select account
        self.client.post("/withdraw", data={"account_type": "savings"})

        # Step 2: perform withdrawal (only if step 1 succeeded)
        self.client.post("/perform_withdraw", data={
            "account_type": "savings",
            "amount": 100
        })

    @task
    def get_mini_statement(self):
        self.client.get("/mini_statement")

