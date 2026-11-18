# Expense Tracker

A small learning project using Flask, MySQL 8 and Redis.

## Features
- Add, list and delete expenses
- Show the current month's expense total
- Cache the monthly total in Redis for 60 seconds
- `/health` endpoint checks Flask, MySQL and Redis connectivity

## Application configuration
The application reads these environment variables:

- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DB`
- `REDIS_HOST`
- `REDIS_PORT`
- `FLASK_SECRET_KEY`

The Flask application listens on port `5000`. Redis listens on `6379`; MySQL listens on `3306`.

## Project structure

```text
expense-tracker/
├── app.py
├── requirements.txt
└── templates/
    └── index.html
```

The MySQL `expenses` table is created automatically when `app.py` starts.
