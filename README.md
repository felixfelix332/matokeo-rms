# Matokeo RMS

Matokeo RMS is an open-source academic report management system for schools that need flexible report cards, marks entry, attendance, student records, teacher workflows, and printable result layouts.

The project started from practical school report workflows and is being shaped into a global academic reporting platform. The long-term goal is to support different countries, grading styles, school levels, languages, calendars, assessment structures, and report-card templates without forcing every school into one education system.

## Project Status

Matokeo RMS is currently an early-stage Django application. Core workflows exist, including school setup, student records, teacher portals, marks entry, report-card previews, template sections, and local SQLite-backed development data. The next major engineering focus is to move hardcoded report logic into configuration-driven modules so contributors can add new grading systems and layouts safely.

## Features

- School setup with branding, sessions, terms, classes, subjects, teachers, and students.
- Admin login, teacher login, and student portal entry points.
- Teacher workflows for marks entry, attendance, comments, attributes, class lists, broadsheets, and report cards.
- Template editor for report-card sections such as school details, student details, academic performance, grading/rating keys, skills/attributes, and comments.
- Multiple academic performance layouts for different assessment styles.
- Component-based score storage using JSON-backed component scores.
- Local development with SQLite databases for fast setup and experimentation.
- Public-repository hygiene through ignored local databases, media, generated frames, and artifacts.

## Vision

Matokeo RMS aims to become a globally adaptable academic reporting engine. Instead of hardcoding one country's report-card format, the project should support:

- Configurable grading scales such as letters, points, divisions, descriptors, competency bands, percentages, and pass/fail schemes.
- Configurable assessment components such as CA, exams, projects, attendance, skills, behavior, and custom school-defined components.
- Configurable report-card sections and layouts that can be reused across schools and education systems.
- International terminology, date formats, academic calendars, languages, and school structures.
- Safe extension points for community-contributed grading packs and report templates.

## Installation

### Requirements

- Python 3.12 or newer is recommended.
- Git.
- A virtual environment tool such as `venv`.

### Setup

Clone the repository:

```powershell
git clone https://github.com/felixfelix332/matokeo-rms.git
cd matokeo-rms
```

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create local environment settings:

```powershell
Copy-Item .env.example .env
```

On macOS or Linux:

```bash
cp .env.example .env
```

Update `.env` with a secure `DJANGO_SECRET_KEY` before deployment.

Apply migrations:

```powershell
python manage.py migrate
python manage.py migrate --database school_data
```

Create an admin user:

```powershell
python manage.py createsuperuser
```

Run the development server:

```powershell
python manage.py runserver
```

Open `http://127.0.0.1:8000/` in your browser.

## Usage

1. Log in as an administrator.
2. Create or select a school.
3. Add sessions, terms, classes, subjects, teachers, and students.
4. Use the teacher portal to enter marks, attendance, attributes, and comments.
5. Generate result views, broadsheets, and report cards.
6. Use the template editor to preview report-card section layouts.

Local SQLite databases are intentionally ignored by Git. Each developer should create their own local data or import a safe sample dataset when one becomes available.

## Project Structure

```text
accounts/                         Authentication, school-entry flows, template-editor registry and preview services
config/                           Django settings, URLs, WSGI/ASGI, and database routing
portal/                           Student, teacher, report-card, marks, attendance, and school-management workflows
portal/templates/accounts/        Admin/school-entry pages and template-editor screens
portal/templates/portal/          Portal dashboards and teacher/student pages
static/                           CSS, images, and static UI assets
```

Important extension points:

- `accounts/template_registry.py` defines available report-card template sections and models.
- `accounts/services/template_preview.py` normalizes model selections and builds preview state.
- `accounts/views_template_editor.py` currently holds template-editor customization data and should be split as the system grows.
- `portal/marks_helpers.py` contains score-component helpers and the current hardcoded grading function.
- `portal/teacher_views.py` contains many teacher workflows and should be modularized over time.

## Contributing

Contributions are welcome. Good first contributions include documentation cleanup, tests, small template fixes, extraction of hardcoded configuration, and accessibility improvements.

Before opening a pull request:

1. Create a feature branch from `main`.
2. Keep changes focused and easy to review.
3. Run Django checks and tests:

```powershell
python manage.py check
python manage.py test
```

4. Avoid committing local SQLite databases, media uploads, generated artifacts, or secrets.
5. Explain the user-facing impact of your change in the pull request.

Read [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor guide.

## Roadmap

The short version:

- Stabilize tests and development setup.
- Extract grading systems into configuration.
- Split large Django views into services, selectors, forms, and view modules.
- Make report templates data-driven and internationally adaptable.
- Add sample data and contributor-friendly demo flows.
- Improve accessibility, responsiveness, and print/PDF output.

Read [ROADMAP.md](ROADMAP.md) for the detailed roadmap.

## Known Technical Debt

This project is useful, but it is not yet architecturally finished. Current weak points include:

- Some grading logic is hardcoded to specific systems, especially CBC-style grading.
- Several view files are very large and mix SQL, business rules, validation, and rendering.
- Template-editor configuration is split between registry data, view context, templates, and JavaScript.
- Many database operations use direct SQLite queries, which makes portability to PostgreSQL/MySQL harder.
- Automated tests are minimal.
- Internationalization and localization are not yet implemented.

These are strong areas for contributors who want to help the project become globally useful.

## License

Matokeo RMS is released under the MIT License. See [LICENSE](LICENSE).
