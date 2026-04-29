# Contributing to Matokeo RMS

Thank you for helping improve Matokeo RMS. This project is being built toward a global, school-friendly academic report system, so clear communication and small, reviewable changes matter a lot.

## Ways to Contribute

- Improve documentation, setup instructions, screenshots, and examples.
- Add tests around grading, template selection, report-card output, and permissions.
- Convert hardcoded grading rules into configurable grading profiles.
- Improve accessibility, keyboard navigation, responsive layout, and print styles.
- Add safe template-editor layouts without breaking existing sections.
- Refactor large view files into smaller services, selectors, forms, and views.
- Report bugs with steps to reproduce and expected behavior.

## Development Setup

```powershell
git clone https://github.com/felixfelix332/matokeo-rms.git
cd matokeo-rms
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py migrate --database school_data
python manage.py createsuperuser
python manage.py runserver
```

On macOS or Linux, replace the activation and copy commands with:

```bash
source .venv/bin/activate
cp .env.example .env
```

## Before You Submit a Pull Request

- Run `python manage.py check`.
- Run `python manage.py test`.
- Keep pull requests focused on one problem.
- Do not commit local SQLite databases, uploaded media, secrets, generated frames, or local artifacts.
- Add or update tests when changing scoring, grading, permissions, or template selection.
- Update documentation when changing setup, workflows, or extension points.

## Code Style

- Prefer clear names over clever abbreviations.
- Keep business rules out of templates when possible.
- Prefer configuration-driven behavior for grading systems and report layouts.
- Keep country-specific rules isolated behind named profiles instead of scattering them across views/templates.
- Use Django ORM where practical; if raw SQL is necessary, keep it isolated in selectors/repositories.
- Add comments only when they explain intent, extension points, or non-obvious constraints.

## Suggested Architecture Direction

The current code works, but contributors should gradually move toward this structure:

```text
accounts/
  services/
  selectors/
  forms/
  views/

matokeo/
  grading/
  reports/
  templates/
  services/
  selectors/
  forms/
  views/
```

Recommended extraction targets:

- Move repeated grading and score helpers from large views into focused service modules.
- Split `accounts/views.py` by workflow such as school setup, class data, reports, settings, users, and classes.
- Move template-editor customization constants from `accounts/views_template_editor.py` into configuration modules or database-backed settings.
- Add tests for `accounts/services/template_preview.py` because it controls active template behavior.

## Internationalization Principles

When adding features, avoid assuming:

- Three terms only.
- One grading scale.
- One language.
- One report-card layout.
- One country-specific interpretation of CA, exams, divisions, descriptors, points, or competency bands.

Prefer named configuration profiles such as:

```text
grading_profiles/
  nigeria_basic.json
  uganda_division.json
  cameroon_bilingual.json
  competency_based.json
```

Each profile should define score ranges, labels, points, remarks, visible columns, and calculation behavior.

## Good First Issues

- Add tests for `normalize_selected_models`.
- Add tests for the Section 2 + Section 3 combined template behavior.
- Document how to create a local demo school.
- Replace hardcoded year values in template-editor context.
- Create a sample grading-profile JSON format.
- Improve `.env.example` with optional deployment settings.
- Add accessibility labels to template-editor controls.
- Add screenshots to the README after the UI stabilizes.

## Code of Conduct

All contributors are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
