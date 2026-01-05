from flask import Blueprint, render_template, request
from app.gpt_helper import summarize_course
from app.scraper import get_course_raw_info

bp = Blueprint("main", __name__)

DEBUG_SCRAPE = True  # set to False later


@bp.route("/", methods=["GET"])
def home():
    return render_template("index.html", summary=None)


@bp.route("/about", methods=["GET"])
def about():
    return render_template("about.html")


@bp.route("/summarize", methods=["POST"], endpoint="summarize_course")
def summarize_course_route():
    code = (request.form.get("course_code") or "").strip()

    if not code:
        return render_template("index.html", summary="No course code provided.")

    # 1) Scrape official info (cached)
    raw = get_course_raw_info(code)

    official_text = (raw.get("raw_text") or "").strip()
    source_url = raw.get("source_url")
    from_cache = raw.get("from_cache", False)
    not_found = raw.get("not_found", False)

    if DEBUG_SCRAPE:
        print("\n================ SCRAPE DEBUG ================")
        print("Input:", code)
        print("Normalized:", raw.get("course_code"))
        print("URL:", source_url)
        print("From cache:", from_cache)
        print("Not found:", not_found)
        print("Official text preview:\n", official_text[:1200])
        print("=============================================\n")

    # 2) If we don't have official text, DON'T call GPT (saves $ + follows your rule)
    if not_found or not official_text:
        summary = "I couldn't find official details for this course on the page I scraped."
        return render_template(
            "index.html",
            summary=summary,
            source_url=source_url,
            from_cache=from_cache,
        )

    # 3) Feed official text into GPT (desc is official catalogue text)
    summary = summarize_course(raw.get("course_code", code), desc=official_text)

    return render_template(
        "index.html",
        summary=summary,
        source_url=source_url,
        from_cache=from_cache,
    )