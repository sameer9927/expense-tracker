import os
from datetime import date
from decimal import Decimal, InvalidOperation

import pymysql
import redis
from flask import Flask, flash, redirect, render_template, request, url_for

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-later")

# MySQL connection settings come from Docker environment variables.
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "expenseuser")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "expensepass")
MYSQL_DB = os.getenv("MYSQL_DB", "expense_tracker")

# Redis connection settings.
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_connect_timeout=2,
)


def get_db_connection():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def initialize_database():
    """Create the expenses table if it does not already exist."""
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS expenses (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    amount DECIMAL(10, 2) NOT NULL,
                    category VARCHAR(100) NOT NULL,
                    description VARCHAR(255),
                    expense_date DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
    finally:
        connection.close()


def get_monthly_total():
    """Return this month's expense total, using Redis as a 60-second cache."""
    cache_key = f"monthly_total:{date.today().strftime('%Y-%m')}"

    try:
        cached_total = redis_client.get(cache_key)
        if cached_total is not None:
            return Decimal(cached_total), "Redis cache"
    except redis.RedisError:
        # If Redis is unavailable, the app can still get the total from MySQL.
        pass

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM expenses
                WHERE YEAR(expense_date) = YEAR(CURDATE())
                  AND MONTH(expense_date) = MONTH(CURDATE())
                """
            )
            total = cursor.fetchone()["total"]
    finally:
        connection.close()

    try:
        redis_client.setex(cache_key, 60, str(total))
    except redis.RedisError:
        pass

    return total, "MySQL (cached for next request)"


def clear_monthly_cache():
    cache_key = f"monthly_total:{date.today().strftime('%Y-%m')}"
    try:
        redis_client.delete(cache_key)
    except redis.RedisError:
        pass


@app.route("/")
def index():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM expenses ORDER BY expense_date DESC, id DESC")
            expenses = cursor.fetchall()
    finally:
        connection.close()

    monthly_total, total_source = get_monthly_total()
    return render_template(
        "index.html",
        expenses=expenses,
        monthly_total=monthly_total,
        total_source=total_source,
    )


@app.route("/add", methods=["POST"])
def add_expense():
    try:
        amount = Decimal(request.form["amount"])
        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")
    except (KeyError, ValueError, InvalidOperation):
        flash("Please enter a valid amount greater than zero.", "error")
        return redirect(url_for("index"))

    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    expense_date = request.form.get("expense_date", "")

    if not category or not expense_date:
        flash("Please provide a category and date.", "error")
        return redirect(url_for("index"))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO expenses (amount, category, description, expense_date) VALUES (%s, %s, %s, %s)",
                (amount, category, description, expense_date),
            )
    finally:
        connection.close()

    clear_monthly_cache()
    flash("Expense added successfully.", "success")
    return redirect(url_for("index"))


@app.route("/delete/<int:expense_id>", methods=["POST"])
def delete_expense(expense_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM expenses WHERE id = %s", (expense_id,))
    finally:
        connection.close()

    clear_monthly_cache()
    flash("Expense deleted.", "success")
    return redirect(url_for("index"))


@app.route("/health")
def health():
    status = {"flask": "ok", "mysql": "ok", "redis": "ok"}
    http_status = 200

    try:
        connection = get_db_connection()
        connection.close()
    except Exception as error:
        status["mysql"] = f"error: {error.__class__.__name__}"
        http_status = 503

    try:
        redis_client.ping()
    except redis.RedisError as error:
        status["redis"] = f"error: {error.__class__.__name__}"
        http_status = 503

    return status, http_status


# Create the table when the application starts (including when Gunicorn imports it).
initialize_database()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
