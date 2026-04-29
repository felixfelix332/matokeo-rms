# Roadmap

Matokeo RMS is moving from a practical school result system toward a global, configurable academic reporting platform. This roadmap focuses on stability, international adaptability, and contributor friendliness.

## Phase 1: Open-Source Foundation

- Maintain a clear README, contributing guide, code of conduct, license, and roadmap.
- Add screenshots and a short demo workflow after the UI stabilizes.
- Add sample data that is safe to publish and easy to reset.
- Add continuous integration for Django checks and tests.
- Add issue templates for bugs, feature requests, and good first issues.

## Phase 2: Testing and Reliability

- Add tests for authentication, permissions, school selection, and teacher/student access.
- Add tests for `accounts/services/template_preview.py`.
- Add tests for score calculations, grading, report-card generation, and template rendering.
- Add regression tests for Section 2 and Section 3 combined template behavior.
- Add smoke tests for the main admin, teacher, student, and template-editor pages.

## Phase 3: Configurable Grading Systems

- Replace hardcoded grading logic with named grading profiles.
- Support letter grades, competency bands, points, divisions, descriptors, pass/fail, and custom remarks.
- Store grading thresholds, labels, points, and remarks in JSON or database-backed configuration.
- Allow schools to select a grading profile per school, class level, session, term, or report template.
- Add import/export for grading profiles so communities can share country or school-specific packs.

## Phase 4: Template Editor Architecture

- Keep one authoritative registry for template sections, models, labels, and customization modes.
- Move large template-editor customization constants out of views.
- Introduce schema validation for template section definitions.
- Add preview tests for each section and model.
- Make combined-template behavior explicit so one section does not accidentally override another section.
- Support printable and PDF-friendly layouts.

## Phase 5: Code Structure and Scalability

- Split `accounts/views.py` into smaller school setup, data management, authentication, and shell modules.
- Move direct SQL into selectors/repositories and keep view functions thin.
- Prefer Django ORM models where the schema is stable.
- Add service modules for grading, reports, attendance, comments, attributes, and school setup.
- Add forms for validation instead of validating large POST payloads directly in views.

## Phase 6: Internationalization

- Add Django translation support for UI text.
- Support configurable terminology such as class/form/grade, term/semester, subject/course, and headteacher/principal.
- Support locale-aware dates, names, number formatting, and print labels.
- Avoid country-specific language in core code; place local education-system rules inside named profiles.
- Add documentation for creating local education-system profiles.

## Phase 7: Contributor and Sponsor Readiness

- Publish beginner-friendly issues with clear acceptance criteria.
- Add architecture notes for grading profiles, template sections, and database routing.
- Add maintainership guidelines and release notes.
- Add sponsorship/grant materials describing the education impact, target users, and public-good value.
- Add a public demo deployment once security and sample data are ready.

## Beginner-Friendly Issues

- Add tests for `normalize_selected_models`.
- Add a sample grading-profile JSON file.
- Document how to create a demo school.
- Add issue templates.
- Add screenshots to README.
- Replace hardcoded `current_year` in template-editor context.
- Add labels and aria attributes to template-editor buttons.
- Create a small architecture note for the two-database setup.
