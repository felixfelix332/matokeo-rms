# Matokeo RMS

Matokeo RMS is a Django-based school result management system with a template editor for report sheet layouts.

## Setup

1. Create and activate a virtual environment.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies.

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

3. Create local environment settings.

```powershell
Copy-Item .env.example .env
```

Update `.env` with a secure `DJANGO_SECRET_KEY` before deploying.

4. Apply migrations.

```powershell
python manage.py migrate
python manage.py migrate --database school_data
```

5. Run the development server.

```powershell
python manage.py runserver
```

Open `http://127.0.0.1:8000/` in your browser.

## Notes

Local SQLite databases, media uploads, extracted video frames, and generated artifacts are intentionally ignored so the public repository contains source code and setup files only.
