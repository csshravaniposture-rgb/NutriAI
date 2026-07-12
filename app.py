from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "nutriai_secret_key"

# ---------------- DATABASE CONFIG ---------------- #

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///nutriai.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ---------------- DATABASE TABLE ---------------- #

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    age = db.Column(db.Integer)
    height = db.Column(db.Integer)
    weight = db.Column(db.Integer)
    diet = db.Column(db.String(50))
    goal = db.Column(db.String(50))

# Create Database
with app.app_context():
    db.create_all()

# ---------------- HOME ---------------- #

@app.route("/")
def home():
    return render_template("index.html")

# ---------------- REGISTER ---------------- #

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        email = request.form["email"]

        # Check duplicate email
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            return "Email already registered. Please Login."

        user = User(
            name=request.form["name"],
            email=email,
            password=generate_password_hash(request.form["password"]),
            age=request.form["age"],
            height=request.form["height"],
            weight=request.form["weight"],
            diet=request.form["diet"],
            goal=request.form["goal"]
        )

        db.session.add(user)
        db.session.commit()

        return redirect(url_for("login"))

    return render_template("register.html")

# ---------------- LOGIN ---------------- #

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            return redirect(url_for("dashboard"))

        return "Invalid Email or Password"

    return render_template("login.html")

# ---------------- DASHBOARD ---------------- #

from flask import session

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])

    return render_template("dashboard.html", user=user)

# ---------------- MEAL PLANNER ---------------- #

@app.route("/mealplanner")
def mealplanner():
    return render_template("mealplanner.html")

# ---------------- NUTRITION ---------------- #

@app.route("/nutrition")
def nutrition():
    return render_template("nutrition.html")

# ---------------- RECIPE ---------------- #

@app.route("/recipe")
def recipe():
    return render_template("recipe.html")

# ---------------- GROCERY ---------------- #

@app.route("/grocery")
def grocery():
    return render_template("grocery.html")

# ---------------- REPORT ---------------- #

@app.route("/report")
def report():
    return render_template("report.html")

# ---------------- PROFILE ---------------- #

@app.route("/profile")
def profile():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])

    return render_template("profile.html", user=user)

# ---------------- RUN APP ---------------- #

if __name__ == "__main__":
    app.run(debug=True)