# USask AI Course Planner

A local Flask workspace for tracking Computer Science courses, checking prerequisites, and drafting future terms at the University of Saskatchewan.

## Run locally

Use Python 3.10 or later. From the project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m app.init_db
python -m flask --app main run
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). The database initialization command creates missing tables and keeps existing records. Saved progress lives in the local SQLite database. The app has no accounts or multi-user isolation.

The dashboard, planner, Course Explorer, and official course lookup work without an OpenAI key. To enable generated course summaries, set `OPENAI_API_KEY` in your environment or local `.env` file. With a key configured, **Generate summary** sends public course text to OpenAI and can incur usage charges.

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
