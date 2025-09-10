from flask import Blueprint, render_template

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