# USask AI Course Planner

A local Flask workspace for tracking Computer Science courses, checking prerequisites, and drafting future terms at the University of Saskatchewan.

## Run locally

Use Python 3.11.5 or later with IANA time-zone data available to Python (system zoneinfo or the Python `tzdata` package). From the project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m app.init_db
python -m flask --app main run
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). The database initialization command creates missing tables and keeps existing records. Saved progress lives in the local SQLite database. The app has no accounts or multi-user isolation.

Paid course summaries are disabled by default. To enable them for local use, set both `OPENAI_SUMMARIES_ENABLED=1` and `OPENAI_API_KEY` in your shell or in an ignored local `.env` file when using the Flask CLI. Only the explicit **Generate summary** action sends the course code and public USask catalogue text to OpenAI. Official lookup, planning recommendations, and document features run without OpenAI. Keep summaries disabled on shared or publicly reachable instances until the endpoint has authentication and per-user limits.

Keep student data local unless the deployment has appropriate access controls. The app uses a single shared workspace and all visitors to a reachable instance can access it. Use synthetic data for a public demo and disable student-data writes and uploads there.

## Features

- **Dashboard** tracks courses and verified credit units for the seven-course starter template. Status reflects the latest saved progress.
- **Course Explorer** searches a dated, 96-entry CMPT index and locally cached courses. Direct code lookup, such as `MATH 110`, retrieves an individual course entry when it is available. It shows the official source, credit units when known, and missing prerequisites or a manual-verification reason.
- **Degree Planner** records completed courses and saves, loads, imports, and exports progress. Existing JSON exports still work. Ordered semester drafts are stored separately in the current browser. Sequence checks use cached prerequisites and assume earlier draft courses will be completed as planned.
- **AI Assistant** shows official text separately from optional generated explanations. Planning status comes from the prerequisite engine.
- **Settings** offers dark, light, and system themes with browser-local preferences.

## Sources and limits

- The [USask course catalogue](https://catalogue.usask.ca/) is effective May 2026 through April 2027. The [CMPT subject index](https://catalogue.usask.ca/?subj_code=CMPT) snapshot contains course codes, titles, and available credit-unit values fetched November 18, 2026. Individual descriptions come from course pages and may be cached.
- The [official BSc Computer Science program page](https://programs.usask.ca/arts-and-science/computer-science/bsc-4-computer-science.php) covers the complete degree and the Artificial Intelligence specialization. The starter template’s course and credit counts cover that template only. The app does not perform a degree audit or determine graduation eligibility.
- **Manual verification needed** flags missing catalogue data, grades, permissions, or conditions the parser cannot interpret. **Prerequisites met** refers to the parsed course prerequisites alone. Confirm other restrictions and enrolment eligibility with USask.
- The planner checks prerequisite order. Class sections and timetable clashes require verified section data from [USask Class Search](https://pawnss.usask.ca/ban/bwckschd.p_disp_dyn_sched).
- Semester drafts are browser-local and are outside the existing saved-progress export. No saved-plan schema migration is required.

## Architecture and testing

Flask handles pages and JSON endpoints in `app/routes.py`. Jinja templates, shared CSS tokens, and browser JavaScript modules live in `app/templates` and `app/static`. The scraper and service layer provide cached catalogue data. `app/planner.py` parses prerequisites and evaluates completed courses. SQLite stores saved progress and cached course descriptions.

```sh
python -m unittest discover -s tests -v
git diff --check
```

The suite uses an in-memory database and mocks external catalogue and AI calls where needed.

## Student workspace

The calendar supports month, week and day views, editable events, course links and in-app reminder times. Timed events store UTC instants and use the selected IANA time zone for display. All-day dates stay the same across time zones. Calendar entries are entered by the student or approved during syllabus import. They are independent of official class availability.

Syllabus import accepts text-based PDF or UTF-8 text. A local parser proposes deadlines and shows the original text and PDF page. Review each candidate, correct uncertain dates and approve only the entries you want to save. Scans without a text layer need a text export, and the parser may miss irregular tables or wording. Uploads are kept local. The syllabus itself is discarded after preview.

My Courses stores notes and materials in the local database. Filename search works for saved files, and supported extracted text is searchable when available. Dashboard deadlines and Assistant agenda views use saved calendar entries. Prioritization is deterministic and read-only. It does not read uploaded documents or send private data to an external model.

### Enable storage after approving the migration

Starting the app does not apply student migrations. The original database initialization command handles the legacy Planner separately.

For a new installation with no database file:

```sh
python -m flask --app main migrate-student
```

For an existing installation, use a new backup path outside the checkout:

```sh
python -m flask --app main migrate-student --backup ~/planner-before-student.sqlite
```

The command uses SQLite's online backup API before changing an existing database and verifies the snapshot with `PRAGMA quick_check`. It stops if student tables already exist without a recorded migration, or if the recorded schema is missing required tables or columns. Schema version 1 adds calendar storage and version 2 adds course workspaces and materials. The migration is additive and leaves saved plans and catalogue records intact. Keep the backup private because it may contain personal notes or uploaded material. The app keeps working as a local planner before the student migrations run.

If the upgrade fails, SQLite rolls back the schema transaction. Keep the original and the backup. To rehearse recovery, verify the backup with `sqlite3 -readonly /path/to/backup.sqlite 'PRAGMA quick_check;'` and test a separate copy. Before restoring to the original path, stop every process using the database and preserve the current DB and any WAL, SHM or journal files together. Restore the verified backup only after confirming that any writes made after the snapshot have been accounted for.

This build is single-user for local use. Public deployment would require authentication, per-user authorization, isolated document storage, retention and deletion controls, rate limits, and operational monitoring.
