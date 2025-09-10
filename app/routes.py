from flask import Blueprint, render_template, request
from app.gpt_helper import summarize_course


# Defined to access the main 'Blueprint' function
bp = Blueprint("main", __name__)


# Observing the site address and taking actions accordingly
# and expanding the site templates accordingly

@bp.route("/")
def home():
    # If the site address has a dash
    # it returns the template to the 'index.html' template
    return render_template("index.html")

@bp.route("/about")
def about():
    # If the site address has a dash with an 'about'
    # it returns the template to the 'about.html' template
    return render_template("about.html")

# If user reaches the summary template, it updates the method to POST and the url name to summarize_course
@bp.route("/summarize", methods=["POST"], endpoint="summarize_course")

# It is importing users data inputs from the HTML files to create a summary post
def summarize_course_route():
    # Looks for the 'course_code' in the HTML file to ensure it is not an empty string
    code = request.form.get("course_code", "").strip()
    # The variable holds the output data from the gpt_helper file
    summary = summarize_course(code) \
        if code else "No course code provided." # The function gets called if the variable 'code' is not an empty string
    return render_template("index.html", summary=summary)