from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date
import re
import os
import json

from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types


app = Flask(__name__)

# =========================================================
# APP CONFIGURATION
# =========================================================

app.secret_key = os.environ.get(
    "NUTRIAI_SECRET_KEY",
    "nutriai-secret-key"
)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///nutriai.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# =========================================================
# GEMINI AI CONFIGURATION
# =========================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

gemini_client = None

if GEMINI_API_KEY:
    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )
else:
    print("WARNING: GEMINI_API_KEY is not set.")


# =========================================================
# DATABASE MODELS
# =========================================================

class User(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    age = db.Column(db.Integer)
    height = db.Column(db.Float)
    weight = db.Column(db.Float)
    diet = db.Column(db.String(50))
    goal = db.Column(db.String(50))


class GroceryItem(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


class MealProgress(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    meal_type = db.Column(db.String(50), nullable=False)
    food = db.Column(db.String(255), nullable=False)
    cost = db.Column(db.Float, default=0)
    completed = db.Column(db.Boolean, default=False)
    date = db.Column(db.Date, nullable=False)


class GeneratedMeal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    meal_type = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    ingredients = db.Column(db.Text, nullable=False)
    instructions = db.Column(db.Text, nullable=False)
    calories = db.Column(db.Float, default=0)
    protein = db.Column(db.Float, default=0)
    carbs = db.Column(db.Float, default=0)
    fat = db.Column(db.Float, default=0)
    cost = db.Column(db.Float, default=0)
    date = db.Column(db.Date, nullable=False)


class NutritionIntake(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    food = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Float, default=100)
    calories = db.Column(db.Float, default=0)
    protein = db.Column(db.Float, default=0)
    carbs = db.Column(db.Float, default=0)
    fat = db.Column(db.Float, default=0)
    fiber = db.Column(db.Float, default=0)
    source = db.Column(db.String(50), default="manual")
    meal_type = db.Column(db.String(50), nullable=True)
    date = db.Column(db.Date, nullable=False)


class WaterIntake(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False)


# =========================================================
# CREATE DATABASE
# =========================================================

with app.app_context():
    db.create_all()


def get_daily_nutrition(user_id, target_date=None):

    if target_date is None:
        target_date = date.today()

    intake = NutritionIntake.query.filter_by(
        user_id=user_id,
        date=target_date
    ).all()

    calories = sum(float(item.calories or 0) for item in intake)
    protein = sum(float(item.protein or 0) for item in intake)
    carbs = sum(float(item.carbs or 0) for item in intake)
    fat = sum(float(item.fat or 0) for item in intake)
    fiber = sum(float(item.fiber or 0) for item in intake)

    return {
        "calories": round(calories, 1),
        "protein": round(protein, 1),
        "carbs": round(carbs, 1),
        "fat": round(fat, 1),
        "fiber": round(fiber, 1)
    }


def get_daily_targets(user):

    calorie_target = 2000
    protein_target = 60

    if user.weight and user.height and user.age:

        weight = float(user.weight)
        height = float(user.height)
        age = int(user.age)

        gender = getattr(user, "gender", None)

        if gender == "Male":
            bmr = 10 * weight + 6.25 * height - 5 * age + 5

        elif gender == "Female":
            bmr = 10 * weight + 6.25 * height - 5 * age - 161

        else:
            bmr = 10 * weight + 6.25 * height - 5 * age - 78

        calorie_target = round(bmr * 1.375)

        if user.goal == "Weight Loss":
            calorie_target -= 300

        elif user.goal == "Weight Gain":
            calorie_target += 300

        elif user.goal == "Muscle Gain":
            calorie_target += 250

        calorie_target = max(calorie_target, 1200)

        protein_target = round(weight)

        if user.goal == "Muscle Gain":
            protein_target = round(weight * 1.6)

        elif user.goal == "Weight Loss":
            protein_target = round(weight * 1.2)

    return {
        "calories": calorie_target,
        "protein": protein_target
    }

# =========================================================
# SIMPLE INDIAN MEAL DATABASE
# =========================================================

vegetarian = [
    {"type": "Breakfast", "food": "Vegetable Poha + Tea", "cost": 25},
    {"type": "Breakfast", "food": "2 Idli + Sambar", "cost": 30},
    {"type": "Breakfast", "food": "Vegetable Upma", "cost": 25},
    {"type": "Breakfast", "food": "2 Roti + Curd", "cost": 30},
    {"type": "Breakfast", "food": "Besan Chilla + Curd", "cost": 35},
    {"type": "Lunch", "food": "Dal + Rice + Cucumber", "cost": 45},
    {"type": "Lunch", "food": "2 Roti + Dal + Sabzi", "cost": 50},
    {"type": "Lunch", "food": "Rajma Rice", "cost": 50},
    {"type": "Lunch", "food": "Vegetable Khichdi + Curd", "cost": 45},
    {"type": "Lunch", "food": "2 Roti + Chana Masala", "cost": 50},
    {"type": "Snack", "food": "Banana + Roasted Chana", "cost": 20},
    {"type": "Snack", "food": "Sprouts Chaat", "cost": 25},
    {"type": "Snack", "food": "Roasted Makhana", "cost": 30},
    {"type": "Snack", "food": "Fruit Bowl", "cost": 30},
    {"type": "Snack", "food": "Peanuts + Tea", "cost": 20},
    {"type": "Dinner", "food": "2 Roti + Dal + Sabzi", "cost": 50},
    {"type": "Dinner", "food": "Moong Dal Khichdi + Curd", "cost": 45},
    {"type": "Dinner", "food": "Vegetable Pulao + Raita", "cost": 50},
    {"type": "Dinner", "food": "2 Roti + Paneer Bhurji", "cost": 65},
    {"type": "Dinner", "food": "Dal + Rice + Salad", "cost": 45}
]


non_vegetarian = [
    {"type": "Breakfast", "food": "2 Boiled Eggs + 2 Roti", "cost": 35},
    {"type": "Breakfast", "food": "Egg Bhurji + 2 Roti", "cost": 40},
    {"type": "Breakfast", "food": "2 Egg Omelette + Toast", "cost": 40},
    {"type": "Lunch", "food": "Chicken Curry + Rice", "cost": 80},
    {"type": "Lunch", "food": "Chicken Curry + 2 Roti", "cost": 85},
    {"type": "Lunch", "food": "Egg Curry + Rice", "cost": 55},
    {"type": "Lunch", "food": "Chicken Pulao + Raita", "cost": 75},
    {"type": "Snack", "food": "Boiled Eggs + Fruit", "cost": 35},
    {"type": "Snack", "food": "Egg Sandwich", "cost": 40},
    {"type": "Snack", "food": "Roasted Chana + Banana", "cost": 20},
    {"type": "Dinner", "food": "Chicken Curry + 2 Roti", "cost": 85},
    {"type": "Dinner", "food": "Egg Curry + 2 Roti", "cost": 60},
    {"type": "Dinner", "food": "Chicken Rice Bowl", "cost": 75},
    {"type": "Dinner", "food": "Egg Bhurji + 2 Roti + Salad", "cost": 55}
]


vegan = [
    {"type": "Breakfast", "food": "Vegetable Poha", "cost": 25},
    {"type": "Breakfast", "food": "Vegetable Upma", "cost": 25},
    {"type": "Breakfast", "food": "Besan Chilla + Green Chutney", "cost": 30},
    {"type": "Breakfast", "food": "2 Roti + Vegetable Sabzi", "cost": 35},
    {"type": "Lunch", "food": "Dal + Rice + Salad", "cost": 45},
    {"type": "Lunch", "food": "Rajma Rice", "cost": 50},
    {"type": "Lunch", "food": "Chana Masala + 2 Roti", "cost": 50},
    {"type": "Lunch", "food": "Vegetable Khichdi", "cost": 40},
    {"type": "Snack", "food": "Banana + Peanuts", "cost": 20},
    {"type": "Snack", "food": "Sprouts Chaat", "cost": 25},
    {"type": "Snack", "food": "Roasted Chana", "cost": 15},
    {"type": "Snack", "food": "Seasonal Fruit", "cost": 25},
    {"type": "Dinner", "food": "Dal + 2 Roti + Sabzi", "cost": 50},
    {"type": "Dinner", "food": "Rajma Rice", "cost": 50},
    {"type": "Dinner", "food": "Vegetable Pulao", "cost": 45},
    {"type": "Dinner", "food": "Chana Masala + 2 Roti", "cost": 50}
]


eggetarian = [
    {"type": "Breakfast", "food": "2 Boiled Eggs + Poha", "cost": 40},
    {"type": "Breakfast", "food": "Egg Omelette + 2 Roti", "cost": 40},
    {"type": "Breakfast", "food": "Egg Bhurji + Toast", "cost": 40},
    {"type": "Breakfast", "food": "2 Idli + Sambar + Egg", "cost": 40},
    {"type": "Lunch", "food": "Dal + Rice + Boiled Egg", "cost": 50},
    {"type": "Lunch", "food": "Egg Curry + Rice", "cost": 55},
    {"type": "Lunch", "food": "2 Roti + Dal + Egg Bhurji", "cost": 55},
    {"type": "Lunch", "food": "Rajma Rice + Boiled Egg", "cost": 55},
    {"type": "Snack", "food": "Boiled Eggs + Banana", "cost": 35},
    {"type": "Snack", "food": "Egg Sandwich", "cost": 40},
    {"type": "Snack", "food": "Roasted Chana + Fruit", "cost": 25},
    {"type": "Dinner", "food": "Egg Curry + 2 Roti", "cost": 60},
    {"type": "Dinner", "food": "Egg Bhurji + 2 Roti + Salad", "cost": 55},
    {"type": "Dinner", "food": "Dal Rice + Boiled Eggs", "cost": 55},
    {"type": "Dinner", "food": "Vegetable Pulao + Egg", "cost": 55}
]


# =========================================================
# MEALS DATABASE
# =========================================================

meals_database = {
    "Vegetarian": vegetarian,
    "Non-Vegetarian": non_vegetarian,
    "Vegan": vegan,
    "Eggetarian": eggetarian
}


# =========================================================
# ESTIMATED MEAL PRICES
# =========================================================

meal_costs = {
    "Breakfast": 55,
    "Lunch": 95,
    "Snack": 35,
    "Dinner": 110,
    "Extra": 40
}


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    return render_template("index.html")


# =========================================================
# EMAIL VALIDATION
# =========================================================

def is_valid_email(email):

    email_pattern = (
        r"^[A-Za-z0-9._%+-]+"
        r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
    )

    return re.fullmatch(email_pattern, email) is not None


# =========================================================
# PASSWORD VALIDATION
# =========================================================

def is_strong_password(password):

    if len(password) < 8:
        return False

    if len(password) > 128:
        return False

    if not re.search(r"[A-Z]", password):
        return False

    if not re.search(r"[a-z]", password):
        return False

    if not re.search(r"\d", password):
        return False

    if not re.search(r"[^A-Za-z0-9]", password):
        return False

    return True


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        age = request.form.get("age", "")
        height = request.form.get("height", "")
        weight = request.form.get("weight", "")
        diet = request.form.get("diet", "").strip()
        goal = request.form.get("goal", "").strip()

        # NAME
        if not name:
            flash("Please enter your full name.")
            return redirect(url_for("register"))

        if len(name) < 2:
            flash("Name must contain at least 2 characters.")
            return redirect(url_for("register"))

        if len(name) > 100:
            flash("Name is too long.")
            return redirect(url_for("register"))

        if not re.fullmatch(r"[A-Za-zÀ-ÿ\s.'-]+", name):
            flash("Please enter a valid name.")
            return redirect(url_for("register"))

        # EMAIL
        if not email:
            flash("Please enter your email address.")
            return redirect(url_for("register"))

        if len(email) > 120:
            flash("Email address is too long.")
            return redirect(url_for("register"))

        if not is_valid_email(email):
            flash("Please enter a valid email address.")
            return redirect(url_for("register"))

        # PASSWORD
        if not password:
            flash("Please create a password.")
            return redirect(url_for("register"))

        if not is_strong_password(password):
            flash(
                "Password must contain at least 8 characters, "
                "one uppercase letter, one lowercase letter, "
                "one number and one special character."
            )
            return redirect(url_for("register"))

        # CONFIRM PASSWORD
        if password != confirm_password:
            flash("Passwords do not match.")
            return redirect(url_for("register"))

        # DUPLICATE EMAIL
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash("An account with this email already exists. Please login.")
            return redirect(url_for("login"))

        # AGE / HEIGHT / WEIGHT
        try:
            age = int(age)
            height = float(height)
            weight = float(weight)
        except (ValueError, TypeError):
            flash("Please enter valid age, height and weight.")
            return redirect(url_for("register"))

        # HEALTH VALUES
        if age < 13 or age > 120:
            flash("Age must be between 13 and 120.")
            return redirect(url_for("register"))

        if height < 50 or height > 250:
            flash("Height must be between 50 and 250 cm.")
            return redirect(url_for("register"))

        if weight < 20 or weight > 300:
            flash("Weight must be between 20 and 300 kg.")
            return redirect(url_for("register"))

        # DIET
        allowed_diets = ["Vegetarian", "Non-Vegetarian", "Vegan", "Eggetarian"]

        if diet not in allowed_diets:
            flash("Please select a valid diet preference.")
            return redirect(url_for("register"))

        # GOAL
        allowed_goals = ["Weight Loss", "Weight Gain", "Muscle Gain", "Maintain Weight"]

        if goal not in allowed_goals:
            flash("Please select a valid fitness goal.")
            return redirect(url_for("register"))

        # CREATE USER
        hashed_password = generate_password_hash(password, method="scrypt")

        user = User(
            name=name,
            email=email,
            password=hashed_password,
            age=age,
            height=height,
            weight=weight,
            diet=diet,
            goal=goal
        )

        try:
            db.session.add(user)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Something went wrong while creating your account. Please try again.")
            return redirect(url_for("register"))

        flash("Account created successfully! Please login.")
        return redirect(url_for("login"))

    return render_template("register.html")


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter your email and password.")
            return redirect(url_for("login"))

        if not is_valid_email(email):
            flash("Please enter a valid email address.")
            return redirect(url_for("login"))

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):

            session.clear()
            session["user_id"] = user.id
            session.permanent = True
            session["login_success"] = True

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")
        return redirect(url_for("login"))

    return render_template("login.html")


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    today = date.today()

    meals = MealProgress.query.filter_by(
        user_id=session["user_id"],
        date=today
    ).all()

    meal_status = {}

    for meal in meals:
        meal_status[meal.meal_type] = meal.completed

    completed_meals = sum(
        1
        for meal in meals
        if meal.completed
        and meal.meal_type in ["Breakfast", "Lunch", "Snack", "Dinner"]
    )

    meal_percentage = int((completed_meals / 4) * 100)

    if meal_percentage > 100:
        meal_percentage = 100

    completed_cost = round(
        sum(meal.cost or 0 for meal in meals if meal.completed),
        2
    )

    show_welcome = session.pop("login_success", False)

    return render_template(
        "dashboard.html",
        user=user,
        meals=meals,
        meal_status=meal_status,
        completed_meals=completed_meals,
        meal_percentage=meal_percentage,
        completed_cost=completed_cost,
        show_welcome=show_welcome,
        today=today
    )


# =========================================================
# COMPLETE / UNCOMPLETE MEAL
# =========================================================

@app.route("/complete-meal/<meal_type>", methods=["POST", "GET"])
def complete_meal(meal_type):

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    today = date.today()

    meal = MealProgress.query.filter_by(
        user_id=user_id,
        meal_type=meal_type,
        date=today
    ).first()

    if meal is None:
        flash("Meal not found.", "error")
        return redirect(url_for("dashboard"))

    # =====================================================
    # COMPLETE MEAL
    # =====================================================

    if not meal.completed:

        meal.completed = True

        generated_meal = GeneratedMeal.query.filter_by(
            user_id=user_id,
            meal_type=meal_type,
            date=today
        ).first()

        if generated_meal:

            existing_intake = NutritionIntake.query.filter_by(
                user_id=user_id,
                meal_type=meal_type,
                date=today,
                source="meal"
            ).first()

            if existing_intake is None:

                intake = NutritionIntake(
                    user_id=user_id,
                    food=generated_meal.name,
                    quantity=1,
                    calories=generated_meal.calories or 0,
                    protein=generated_meal.protein or 0,
                    carbs=generated_meal.carbs or 0,
                    fat=generated_meal.fat or 0,
                    fiber=0,
                    source="meal",
                    meal_type=meal_type,
                    date=today
                )

                db.session.add(intake)

    # =====================================================
    # UN-COMPLETE MEAL
    # =====================================================

    else:

        meal.completed = False

        existing_intake = NutritionIntake.query.filter_by(
            user_id=user_id,
            meal_type=meal_type,
            date=today,
            source="meal"
        ).first()

        if existing_intake:
            db.session.delete(existing_intake)

    db.session.commit()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":

        daily = get_daily_nutrition(user_id)

        return {
            "success": True,
            "completed": meal.completed,
            "nutrition": daily
        }

    return redirect(url_for("dashboard"))


# =========================================================
# GEMINI AI MEAL PLANNER
# Generates MEAL + RECIPE + NUTRITION together
# =========================================================

def generate_ai_meal_plan(goal, diet, budget, meals_per_day):

    if not gemini_client:
        print("Gemini Error: Gemini client is not initialized.")
        return None

    # -----------------------------------------------------
    # MEAL TYPES
    # -----------------------------------------------------

    if meals_per_day == 3:
        meal_types = ["Breakfast", "Lunch", "Dinner"]

    elif meals_per_day == 4:
        meal_types = ["Breakfast", "Lunch", "Snack", "Dinner"]

    elif meals_per_day == 5:
        meal_types = [
            "Breakfast",
            "Mid-Morning Snack",
            "Lunch",
            "Evening Snack",
            "Dinner"
        ]

    else:
        return None

    # -----------------------------------------------------
    # GEMINI PROMPT
    # -----------------------------------------------------

    prompt = f"""
You are NutriAI, an AI Indian meal planning assistant.

Create a complete one-day Indian meal plan for the user.

USER INFORMATION

Fitness Goal:
{goal}

Diet Preference:
{diet}

Daily Food Budget:
₹{budget}

Number of Meals:
{meals_per_day}

MEAL TYPES:

{", ".join(meal_types)}

IMPORTANT RULES:

1. Generate exactly {meals_per_day} meals.

2. Use exactly these meal types:
{", ".join(meal_types)}

3. Every meal MUST include a complete recipe.

4. Recipes must be simple Indian recipes.

5. Recipes should be suitable for a student.

6. Use affordable ingredients.

7. Use ingredients easily available in India.

8. Use approximately 3 to 8 ingredients per recipe.

9. Cooking time should normally be between 10 and 30 minutes.

10. Give simple beginner-friendly cooking instructions.

11. Respect the user's diet preference.

12. Consider the user's fitness goal.

13. Keep the complete day's meals within or close to the given budget.

14. Give realistic approximate cost in Indian Rupees.

15. Give realistic approximate nutrition values for the stated serving.

16. Do not make medical claims.

17. Do not suggest supplements.

18. Do not return markdown.

19. Do not return explanations outside JSON.

20. Return ONLY valid JSON.

RETURN EXACTLY THIS STRUCTURE:

[
    {{
        "type": "Breakfast",
        "food": "Vegetable Poha with Curd",
        "cost": 30,

        "ingredients": [
            "Poha - 1 cup",
            "Onion - 1 small",
            "Carrot - 1 small",
            "Green peas - 1/4 cup",
            "Oil - 1 teaspoon",
            "Curd - 1/2 cup"
        ],

        "instructions": [
            "Wash the poha and drain the water.",
            "Heat oil in a pan.",
            "Add onion and vegetables and sauté.",
            "Add poha and mix well.",
            "Cook for 3 to 5 minutes.",
            "Serve with curd."
        ],

        "nutrition": {{
            "calories": 320,
            "protein": 9,
            "carbs": 48,
            "fat": 10
        }}
    }}
]

JSON RULES:

- type must be one of the requested meal types.
- food must be the actual meal name.
- cost must be a number only.
- ingredients must be an array.
- instructions must be an array.
- nutrition must contain calories, protein, carbs and fat.
- All nutrition values must be numbers.
- Do not put ₹ inside cost.
- Do not use markdown.
- Do not add explanations.
- Return ONLY valid JSON.
"""

    # -----------------------------------------------------
    # CALL GEMINI
    # -----------------------------------------------------

    try:

        print("Sending request to Gemini...")

        response = gemini_client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        response_text = response.text.strip()

        print("Gemini response received.")

        ai_plan = json.loads(response_text)

        if not isinstance(ai_plan, list):
            print("Gemini Error: Response is not a list.")
            return None

        # -------------------------------------------------
        # CLEAN PLAN
        # -------------------------------------------------

        cleaned_plan = []

        for meal in ai_plan:

            if not isinstance(meal, dict):
                continue

            meal_type = str(meal.get("type", "")).strip()
            food = str(meal.get("food", "")).strip()

            # ---------------------------------------------
            # COST
            # ---------------------------------------------

            try:
                cost = float(meal.get("cost", 0))
            except (ValueError, TypeError):
                cost = 0

            # ---------------------------------------------
            # INGREDIENTS
            # ---------------------------------------------

            ingredients = meal.get("ingredients", [])

            if not isinstance(ingredients, list):
                ingredients = [str(ingredients)]

            ingredients = [
                str(item).strip()
                for item in ingredients
                if str(item).strip()
            ]

            # ---------------------------------------------
            # INSTRUCTIONS
            # ---------------------------------------------

            instructions = meal.get("instructions", [])

            if not isinstance(instructions, list):
                instructions = [str(instructions)]

            instructions = [
                str(step).strip()
                for step in instructions
                if str(step).strip()
            ]

            # ---------------------------------------------
            # NUTRITION
            # ---------------------------------------------

            nutrition = meal.get("nutrition", {})

            if not isinstance(nutrition, dict):
                nutrition = {}

            try:
                calories = float(nutrition.get("calories", 0))
            except (ValueError, TypeError):
                calories = 0

            try:
                protein = float(nutrition.get("protein", 0))
            except (ValueError, TypeError):
                protein = 0

            try:
                carbs = float(nutrition.get("carbs", 0))
            except (ValueError, TypeError):
                carbs = 0

            try:
                fat = float(nutrition.get("fat", 0))
            except (ValueError, TypeError):
                fat = 0

            # ---------------------------------------------
            # VALID MEAL
            # ---------------------------------------------

            if meal_type and food and meal_type in meal_types:

                cleaned_plan.append({
                    "type": meal_type,
                    "food": food,
                    "cost": round(cost, 2),
                    "ingredients": ingredients,
                    "instructions": instructions,
                    "nutrition": {
                        "calories": round(calories, 1),
                        "protein": round(protein, 1),
                        "carbs": round(carbs, 1),
                        "fat": round(fat, 1)
                    }
                })

        # -------------------------------------------------
        # VALIDATE NUMBER OF MEALS
        # -------------------------------------------------

        if len(cleaned_plan) != meals_per_day:
            print(
                f"Gemini returned {len(cleaned_plan)} meals "
                f"instead of {meals_per_day}."
            )
            return None

        print("Complete AI meal plan generated successfully.")

        return cleaned_plan

    # -----------------------------------------------------
    # ERROR
    # -----------------------------------------------------

    except json.JSONDecodeError as e:
        print("Gemini JSON Error:", repr(e))
        return None

    except Exception as e:
        print("Gemini Meal Planner Error:", repr(e))
        return None


# =========================================================
# MEAL PLANNER
# =========================================================

@app.route("/mealplanner", methods=["GET", "POST"])
def mealplanner():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    # -----------------------------------------
    # DEFAULT VALUES
    # -----------------------------------------

    selected_goal = user.goal or "Weight Loss"
    selected_diet = user.diet or "Vegetarian"
    selected_budget = 300.0
    selected_meals = 4
    meal_plan = []
    error = None

    # -----------------------------------------
    # POST
    # -----------------------------------------

    if request.method == "POST":

        selected_goal = request.form.get("goal", selected_goal).strip()
        selected_diet = request.form.get("diet", selected_diet).strip()

        allowed_goals = ["Weight Loss", "Weight Gain", "Muscle Gain", "Maintain Weight"]

        if selected_goal not in allowed_goals:
            error = "Please select a valid fitness goal."

        allowed_diets = ["Vegetarian", "Non-Vegetarian", "Vegan", "Eggetarian"]

        if error is None and selected_diet not in allowed_diets:
            error = "Please select a valid diet preference."

        try:
            selected_budget = float(request.form.get("budget", 300))
        except (ValueError, TypeError):
            error = "Please enter a valid budget."

        try:
            selected_meals = int(request.form.get("meals", 4))
        except (ValueError, TypeError):
            error = "Please select a valid number of meals."

        if error is None and selected_budget <= 0:
            error = "Daily budget must be greater than ₹0."

        if error is None and (selected_meals < 3 or selected_meals > 5):
            error = "Meals per day must be between 3 and 5."

        if error is None:

            print("\nGenerating AI meal plan...")

            meal_plan = generate_ai_meal_plan(
                selected_goal,
                selected_diet,
                selected_budget,
                selected_meals
            )

            if not meal_plan:
                error = (
                    "AI meal generation is currently "
                    "unavailable. Please check your "
                    "Gemini API key and try again."
                )

            else:

                print("AI meal plan generated successfully.")

                today = date.today()

                MealProgress.query.filter_by(
                    user_id=session["user_id"],
                    date=today
                ).delete()

                GeneratedMeal.query.filter_by(
                    user_id=session["user_id"],
                    date=today
                ).delete()

                for meal in meal_plan:

                    nutrition = meal.get("nutrition", {})

                    generated_meal = GeneratedMeal(
                        user_id=session["user_id"],
                        meal_type=meal.get("type", "Meal"),
                        name=meal.get("food", "AI Generated Meal"),
                        ingredients=json.dumps(meal.get("ingredients", [])),
                        instructions=json.dumps(meal.get("instructions", [])),
                        calories=float(nutrition.get("calories", 0)),
                        protein=float(nutrition.get("protein", 0)),
                        carbs=float(nutrition.get("carbs", 0)),
                        fat=float(nutrition.get("fat", 0)),
                        cost=float(meal.get("cost", 0)),
                        date=today
                    )

                    db.session.add(generated_meal)

                for meal in meal_plan:

                    meal_type = meal.get("type", "").strip()
                    food = meal.get("food", "").strip()
                    cost = float(meal.get("cost", 0))

                    if meal_type in ["Breakfast", "Lunch", "Snack", "Dinner"]:

                        new_meal = MealProgress(
                            user_id=session["user_id"],
                            meal_type=meal_type,
                            food=food,
                            cost=cost,
                            completed=False,
                            date=today
                        )

                        db.session.add(new_meal)

                db.session.commit()

    # -----------------------------------------
    # CALCULATE TOTAL
    # -----------------------------------------

    if meal_plan is None:
        meal_plan = []

    total_cost = round(
        sum(float(item.get("cost", 0)) for item in meal_plan),
        2
    )

    remaining_budget = round(selected_budget - total_cost, 2)

    budget_status = "within" if remaining_budget >= 0 else "over"

    return render_template(
        "mealplanner.html",
        user=user,
        meal_plan=meal_plan,
        selected_goal=selected_goal,
        selected_diet=selected_diet,
        selected_budget=selected_budget,
        selected_meals=selected_meals,
        total_cost=total_cost,
        remaining_budget=remaining_budget,
        budget_status=budget_status,
        error=error
    )


# =========================================================
# NUTRITION SCORE CALCULATOR
# =========================================================
def calculate_nutrition_score(calories, protein, carbs, fat):
    score = 50

    if protein >= 20:
        score += 20
    elif protein >= 10:
        score += 12
    elif protein >= 5:
        score += 6

    if calories <= 100:
        score += 15
    elif calories <= 200:
        score += 10
    elif calories <= 300:
        score += 5

    if fat <= 5:
        score += 10
    elif fat <= 15:
        score += 5

    if carbs <= 30:
        score += 5

    score = max(0, min(score, 100))

    if score >= 85:
        message = (
            "Excellent nutritional profile. "
            "This food can fit well into a balanced diet."
        )

    elif score >= 70:
        message = (
            "Good nutritional profile. "
            "Pair it with other nutrient-rich foods "
            "for a balanced meal."
        )

    elif score >= 50:
        message = (
            "Moderate nutritional profile. "
            "Portion size and the rest of your meal matter."
        )

    else:
        message = (
            "This food is more calorie-dense or "
            "less protein-rich, so consider portion size."
        )

    return score, message


# =========================================================
# ADD MEAL INGREDIENTS TO GROCERY
# =========================================================
@app.route("/add-meal-ingredients", methods=["POST"])
def add_meal_ingredients():

    if "user_id" not in session:
        return redirect(url_for("login"))

    ingredients = request.form.getlist("ingredients")

    if not ingredients:
        flash("No ingredients found.", "error")
        return redirect(url_for("mealplanner"))

    added_count = 0

    for ingredient in ingredients:

        ingredient = ingredient.strip()

        if not ingredient:
            continue

        existing_item = GroceryItem.query.filter_by(
            user_id=session["user_id"],
            item=ingredient
        ).first()

        if existing_item:
            continue

        grocery_item = GroceryItem(
            item=ingredient,
            quantity="As needed",
            price=0,
            user_id=session["user_id"]
        )

        db.session.add(grocery_item)

        added_count += 1

    db.session.commit()

    flash(
        f"🛒 {added_count} ingredient(s) added to your grocery list!",
        "success"
    )

    return redirect(url_for("grocery"))


# =========================================================
# LOG FOOD (manual nutrition logging via Gemini)
# =========================================================
@app.route("/log-food", methods=["POST"])
def log_food():

    if "user_id" not in session:
        return {
            "success": False,
            "error": "Please login first."
        }, 401

    user_id = session["user_id"]

    food = request.form.get("food", "").strip()
    quantity_text = request.form.get("quantity", "100").strip()

    if not food:
        return {
            "success": False,
            "error": "Please enter a food name."
        }, 400

    try:
        quantity = float(quantity_text)

        if quantity <= 0:
            raise ValueError

    except (ValueError, TypeError):

        return {
            "success": False,
            "error": "Please enter a valid quantity."
        }, 400

    if gemini_client is None:

        return {
            "success": False,
            "error": "Gemini API is not configured."
        }, 500

    # =====================================================
    # ASK GEMINI FOR NUTRITION INFORMATION
    # =====================================================

    prompt = f"""
You are a nutrition calculator.

Calculate the approximate nutrition for:

Food: {food}
Quantity: {quantity} grams

Return ONLY valid JSON.

Do not include markdown.
Do not include ```json.
Do not include explanations.

Use exactly this format:

{{
    "calories": 0,
    "protein": 0,
    "carbs": 0,
    "fat": 0,
    "fiber": 0
}}

All values must be numbers.

Calories should be kcal.
Protein, carbs, fat and fiber should be grams.
"""

    try:

        response = gemini_client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt
        )

        response_text = response.text.strip()

        response_text = response_text.replace("```json", "").replace("```", "").strip()

        nutrition = json.loads(response_text)

        calories = float(nutrition.get("calories", 0))
        protein = float(nutrition.get("protein", 0))
        carbs = float(nutrition.get("carbs", 0))
        fat = float(nutrition.get("fat", 0))
        fiber = float(nutrition.get("fiber", 0))

        # =================================================
        # SAVE FOOD INTO DATABASE
        # =================================================

        intake = NutritionIntake(
            user_id=user_id,
            food=food,
            quantity=quantity,
            calories=calories,
            protein=protein,
            carbs=carbs,
            fat=fat,
            fiber=fiber,
            source="manual",
            meal_type=None,
            date=date.today()
        )

        db.session.add(intake)
        db.session.commit()

        daily = get_daily_nutrition(user_id)

        return {
            "success": True,
            "message": f"{food.title()} added successfully.",
            "food": {
                "name": food,
                "quantity": quantity,
                "calories": calories,
                "protein": protein,
                "carbs": carbs,
                "fat": fat,
                "fiber": fiber
            },
            "nutrition": daily
        }

    except json.JSONDecodeError:

        return {
            "success": False,
            "error": "AI returned invalid nutrition data. Please try again."
        }, 500

    except Exception as e:

        print("Food logging error:", e)

        return {
            "success": False,
            "error": "Unable to calculate nutrition. Please try again."
        }, 500


# =========================================================
# LOG WATER
# =========================================================
@app.route("/log-water", methods=["POST"])
def log_water():

    if "user_id" not in session:
        return {
            "success": False,
            "error": "Please login first."
        }, 401

    user_id = session["user_id"]

    amount_text = request.form.get("amount", "250").strip()

    try:
        amount = float(amount_text)

        if amount <= 0:
            raise ValueError

    except (ValueError, TypeError):

        return {
            "success": False,
            "error": "Enter a valid water amount."
        }, 400

    water = WaterIntake(
        user_id=user_id,
        amount=amount,
        date=date.today()
    )

    db.session.add(water)
    db.session.commit()

    total_water = db.session.query(
        db.func.sum(WaterIntake.amount)
    ).filter_by(
        user_id=user_id,
        date=date.today()
    ).scalar() or 0

    return {
        "success": True,
        "water": round(float(total_water), 2)
    }


# =========================================================
# DAILY PROGRESS (JSON API)
# =========================================================
@app.route("/api/daily-progress", methods=["GET"])
def daily_progress():

    if "user_id" not in session:
        return {
            "success": False,
            "error": "Please login first."
        }, 401

    user_id = session["user_id"]

    user = db.session.get(User, user_id)

    if user is None:
        return {
            "success": False,
            "error": "User not found."
        }, 404

    today = date.today()

    nutrition = get_daily_nutrition(user_id, today)

    targets = get_daily_targets(user)

    calorie_target = max(float(targets["calories"]), 1)
    protein_target = max(float(targets["protein"]), 1)

    meals = MealProgress.query.filter_by(
        user_id=user_id,
        date=today
    ).all()

    total_meals = len(meals)

    completed_meals = sum(1 for meal in meals if meal.completed)

    if total_meals > 0:
        meal_progress = round((completed_meals / total_meals) * 100, 1)
    else:
        meal_progress = 0

    total_water = db.session.query(
        db.func.sum(WaterIntake.amount)
    ).filter_by(
        user_id=user_id,
        date=today
    ).scalar() or 0

    total_water = float(total_water)

    water_target = 2500

    water_progress = round(min((total_water / water_target) * 100, 100), 1)

    calorie_progress = round(
        min((nutrition["calories"] / calorie_target) * 100, 100),
        1
    )

    protein_progress = round(
        min((nutrition["protein"] / protein_target) * 100, 100),
        1
    )

    return {
        "success": True,

        "date": today.isoformat(),

        "nutrition": {
            "calories": nutrition["calories"],
            "protein": nutrition["protein"],
            "carbs": nutrition["carbs"],
            "fat": nutrition["fat"],
            "fiber": nutrition["fiber"]
        },

        "targets": {
            "calories": calorie_target,
            "protein": protein_target
        },

        "meals": {
            "total": total_meals,
            "completed": completed_meals,
            "progress": meal_progress
        },

        "water": {
            "amount": round(total_water, 2),
            "target": water_target,
            "progress": water_progress
        },

        "progress": {
            "calories": calorie_progress,
            "protein": protein_progress,
            "water": water_progress,
            "meals": meal_progress
        }
    }


# =========================================================
# AI NUTRITION ANALYZER
# =========================================================

@app.route("/nutrition", methods=["GET", "POST"])
def nutrition():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user = db.session.get(User, session["user_id"])

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    nutrition_data = None
    error = None

    food = ""
    quantity = 100

    if request.method == "POST":

        food = request.form.get("food", "").strip()
        quantity_text = request.form.get("quantity", "100").strip()

        if not food:
            error = "Please enter a food item."

        elif len(food) > 150:
            error = (
                "Food name is too long. "
                "Please enter a shorter food name."
            )

        if error is None:

            try:
                quantity = float(quantity_text)

                if quantity <= 0:
                    raise ValueError

                if quantity > 5000:
                    error = "Please enter a quantity between 1g and 5000g."

            except (ValueError, TypeError):
                error = "Please enter a valid quantity."

        if error is None and not gemini_client:
            error = (
                "Nutrition AI is currently unavailable. "
                "Please check your Gemini API key."
            )

        if error is None:

            prompt = f"""
You are NutriAI, an AI nutrition analysis assistant.

Analyze the food entered by the user.

FOOD:
{food}

QUANTITY:
{quantity} grams

Your task is to provide approximate nutritional information
for EXACTLY the quantity requested by the user.

IMPORTANT RULES:

1. Analyze ANY food entered by the user.
2. Do not depend on a predefined food database.
3. Recognize Indian foods.
4. Recognize international foods.
5. Recognize fruits.
6. Recognize vegetables.
7. Recognize grains.
8. Recognize dairy products.
9. Recognize eggs.
10. Recognize meat and seafood.
11. Recognize snacks.
12. Recognize beverages.
13. Recognize cooked dishes.
14. If the food name has a minor spelling mistake, try to understand it.
15. Give realistic APPROXIMATE nutrition values.
16. Values must correspond to {quantity} grams.
17. Do NOT give values automatically for 100 grams.
18. Calories must be in kcal.
19. Protein must be in grams.
20. Carbohydrates must be in grams.
21. Fat must be in grams.
22. Fiber must be in grams.
23. Give a nutrition score between 0 and 100.
24. Give a short explanation of the score.
25. Give a short easy-to-understand summary.
26. Do not make medical claims.
27. Do not diagnose diseases.
28. Do not recommend supplements.
29. Do not return markdown.
30. Do not return explanations outside JSON.
31. Return ONLY valid JSON.

RETURN EXACTLY THIS STRUCTURE:

{{
    "food": "{food}",
    "quantity": {quantity},
    "calories": 250,
    "protein": 8.5,
    "carbs": 35.0,
    "fat": 8.0,
    "fiber": 3.5,
    "score": 78,
    "score_message": "Good nutritional profile. Pair it with other nutritious foods for a balanced meal.",
    "summary": "This food provides approximately 250 kcal for {quantity}g, with 8.5g protein, 35g carbohydrates, 8g fat and 3.5g fiber."
}}

JSON RULES:

- food must be the food entered by the user.
- quantity must be exactly {quantity}.
- calories must be a number.
- protein must be a number.
- carbs must be a number.
- fat must be a number.
- fiber must be a number.
- score must be an integer between 0 and 100.
- Do not put units inside numeric values.
- Do not use ₹.
- Do not use markdown.
- Do not use code fences.
- Do not add extra fields.
- Return ONLY JSON.
"""

            try:

                print()
                print("=========================================")
                print("NUTRITION ANALYZER")
                print("=========================================")
                print(f"Food: {food}")
                print(f"Quantity: {quantity}g")
                print("Sending nutrition request to Gemini...")

                response = gemini_client.models.generate_content(
                    model="gemini-3.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )

                if not response:
                    raise ValueError("Gemini returned no response.")

                if not response.text:
                    raise ValueError("Gemini returned an empty response.")

                response_text = response.text.strip()

                print("Gemini nutrition response:")
                print(response_text)

                if response_text.startswith("```json"):
                    response_text = response_text.replace("```json", "", 1).strip()

                if response_text.endswith("```"):
                    response_text = response_text[:-3].strip()

                try:
                    ai_data = json.loads(response_text)

                except json.JSONDecodeError:

                    print("Could not directly parse JSON.")

                    start = response_text.find("{")
                    end = response_text.rfind("}")

                    if start != -1 and end != -1 and end > start:
                        json_text = response_text[start:end + 1]
                        ai_data = json.loads(json_text)

                    else:
                        raise

                if not isinstance(ai_data, dict):
                    raise ValueError("Gemini returned invalid nutrition data.")

                def safe_float(value, default=0.0):

                    try:
                        number = float(value)

                        if number < 0:
                            return default

                        return number

                    except (ValueError, TypeError):
                        return default

                calories = round(safe_float(ai_data.get("calories", 0)), 1)
                protein = round(safe_float(ai_data.get("protein", 0)), 1)
                carbs = round(safe_float(ai_data.get("carbs", 0)), 1)
                fat = round(safe_float(ai_data.get("fat", 0)), 1)
                fiber = round(safe_float(ai_data.get("fiber", 0)), 1)

                try:
                    score = int(float(ai_data.get("score", 50)))
                except (ValueError, TypeError):
                    score = 50

                score = max(0, min(score, 100))

                score_message = str(ai_data.get("score_message", "")).strip()

                if not score_message:

                    if score >= 85:
                        score_message = (
                            "Excellent nutritional profile. "
                            "This food can fit well into a balanced diet."
                        )

                    elif score >= 70:
                        score_message = (
                            "Good nutritional profile. "
                            "Pair it with other nutritious foods "
                            "for a balanced meal."
                        )

                    elif score >= 50:
                        score_message = (
                            "Moderate nutritional profile. "
                            "Portion size and overall meal balance matter."
                        )

                    else:
                        score_message = (
                            "Consider the portion size and balance "
                            "this food with other nutritious foods."
                        )

                summary = str(ai_data.get("summary", "")).strip()

                if not summary:
                    summary = (
                        f"{food.title()} provides approximately "
                        f"{calories} kcal for {quantity}g. "
                        f"It contains {protein}g protein, "
                        f"{carbs}g carbohydrates, "
                        f"{fat}g fat and "
                        f"{fiber}g fiber."
                    )

                nutrition_data = {
                    "food": str(ai_data.get("food", food)).strip().title(),
                    "quantity": quantity,
                    "calories": calories,
                    "protein": protein,
                    "carbs": carbs,
                    "fat": fat,
                    "fiber": fiber,
                    "score": score,
                    "score_message": score_message,
                    "summary": summary
                }

                print("Nutrition analysis successful.")
                print(nutrition_data)
                print("=========================================")

            except json.JSONDecodeError as e:

                print("Nutrition JSON Error:")
                print(repr(e))

                error = (
                    "NutriAI could not understand the AI response. "
                    "Please try the food again."
                )

            except Exception as e:

                print("Nutrition AI Error:")
                print(repr(e))

                error = (
                    "Nutrition analysis failed. "
                    f"DEBUG: {repr(e)}"
                )

    return render_template(
        "nutrition.html",
        user=user,
        food=food,
        quantity=quantity,
        nutrition_data=nutrition_data,
        error=error
    )


# =========================================================
# AI RECIPE GENERATOR
# =========================================================

def generate_ai_recipe(ingredients):
    """
    Generate a simple Indian recipe using Gemini.
    """

    if not gemini_client:
        print("Gemini Error: API key is not configured.")
        return None

    prompt = f"""
You are NutriAI, an AI recipe assistant.

The user has these ingredients:

{ingredients}

Create ONE simple, tasty and affordable Indian recipe using these ingredients.

IMPORTANT RULES:

1. Use the user's ingredients as the main ingredients.
2. You may add a few common ingredients such as salt, oil, spices,
   onion, garlic or water if needed.
3. If chicken is provided, the recipe can be non-vegetarian.
4. If only vegetarian ingredients are provided, keep the recipe vegetarian.
5. Keep the recipe suitable for a college student.
6. Keep the recipe simple and beginner-friendly.
7. Cooking time should normally be between 10 and 30 minutes.
8. Give realistic approximate nutrition values.
9. Give approximate cost in Indian Rupees.
10. Do not make medical claims.
11. Do not recommend supplements.
12. Return ONLY valid JSON.
13. Do not use markdown.
14. Do not add explanations outside JSON.

RETURN EXACTLY THIS JSON STRUCTURE:

{{
    "name": "Chicken Rice Bowl",
    "description": "A simple and affordable Indian-style chicken rice bowl.",
    "ingredients": [
        "Rice - 1 cup",
        "Chicken - 150 g",
        "Onion - 1 small",
        "Oil - 1 teaspoon",
        "Salt - as required",
        "Turmeric - 1/4 teaspoon",
        "Chilli powder - 1/2 teaspoon"
    ],
    "instructions": [
        "Wash and cook the rice.",
        "Heat oil in a pan.",
        "Add onion and sauté until soft.",
        "Add chicken and spices.",
        "Cook until the chicken is completely cooked.",
        "Add the cooked rice and mix well.",
        "Cook for another 2 to 3 minutes and serve hot."
    ],
    "cooking_time": "25 minutes",
    "servings": 1,
    "nutrition": {{
        "calories": 520,
        "protein": 32,
        "carbs": 58,
        "fat": 15
    }},
    "cost": 90
}}
"""

    try:
        print("Sending recipe request to Gemini...")

        response = gemini_client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        if not response or not response.text:
            print("Gemini returned an empty response.")
            return None

        response_text = response.text.strip()

        print("Gemini recipe response received:")
        print(response_text)

        recipe_data = json.loads(response_text)

        if not isinstance(recipe_data, dict):
            print("Gemini recipe response is not an object.")
            return None

        recipe_data.setdefault("name", "AI Generated Recipe")
        recipe_data.setdefault("description", "")
        recipe_data.setdefault("ingredients", [])
        recipe_data.setdefault("instructions", [])
        recipe_data.setdefault("cooking_time", "20 minutes")
        recipe_data.setdefault("servings", 1)
        recipe_data.setdefault("cost", 0)

        nutrition = recipe_data.get("nutrition", {})

        if not isinstance(nutrition, dict):
            nutrition = {}

        recipe_data["nutrition"] = {
            "calories": float(nutrition.get("calories", 0)),
            "protein": float(nutrition.get("protein", 0)),
            "carbs": float(nutrition.get("carbs", 0)),
            "fat": float(nutrition.get("fat", 0))
        }

        try:
            recipe_data["cost"] = float(recipe_data.get("cost", 0))
        except (ValueError, TypeError):
            recipe_data["cost"] = 0

        return recipe_data

    except json.JSONDecodeError as e:
        print("Recipe JSON Error:", repr(e))
        return None

    except Exception as e:
        print("Gemini Recipe Error:", repr(e))
        return None


# =========================================================
# RECIPE GENERATOR
# =========================================================

@app.route("/recipe", methods=["GET", "POST"])
def recipe():

    if "user_id" not in session:
        return redirect(url_for("login"))

    recipe_data = None
    error = None
    ingredients = ""

    if request.method == "POST":

        ingredients = request.form.get("ingredients", "").strip()

        if not ingredients:
            error = "Please enter at least one ingredient."
            return render_template(
                "recipe.html",
                recipe_data=None,
                ingredients=ingredients,
                error=error
            )

        if len(ingredients) > 500:
            error = "Please enter a shorter list of ingredients."
            return render_template(
                "recipe.html",
                recipe_data=None,
                ingredients=ingredients,
                error=error
            )

        print(f"\nGenerating recipe for: {ingredients}")

        recipe_data = generate_ai_recipe(ingredients)

        if not recipe_data:
            error = (
                "Recipe generation failed. "
                "Please check your Gemini API key "
                "and try again."
            )
            print("❌ Recipe generation failed.")

        else:

            print("✅ Recipe generated successfully.")

            nutrition = recipe_data.get("nutrition", {})

            recipe_data["time"] = recipe_data.get("cooking_time", "20 minutes")
            recipe_data["calories"] = nutrition.get("calories", 0)
            recipe_data["difficulty"] = recipe_data.get("difficulty", "Easy")
            recipe_data["servings"] = recipe_data.get("servings", 1)

            if not isinstance(recipe_data.get("ingredients"), list):
                recipe_data["ingredients"] = []

            if not isinstance(recipe_data.get("instructions"), list):
                recipe_data["instructions"] = []

            print("✅ Recipe data prepared for HTML.")

    return render_template(
        "recipe.html",
        recipe_data=recipe_data,
        ingredients=ingredients,
        error=error
    )


# =========================================================
# GROCERY ASSISTANT
# =========================================================

@app.route("/grocery", methods=["GET", "POST"])
def grocery():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    if request.method == "POST":

        item = request.form.get("item", "").strip()
        quantity = request.form.get("quantity", "").strip()
        price_text = request.form.get("price", "").strip()

        if not item or not quantity or not price_text:
            return redirect(url_for("grocery"))

        try:
            price = float(price_text)

            if price < 0:
                raise ValueError

        except ValueError:
            return redirect(url_for("grocery"))

        new_item = GroceryItem(
            item=item,
            quantity=quantity,
            price=price,
            user_id=user.id
        )

        db.session.add(new_item)
        db.session.commit()

        return redirect(url_for("grocery"))

    grocery_items = GroceryItem.query.filter_by(
        user_id=user.id
    ).order_by(
        GroceryItem.id.desc()
    ).all()

    total = round(sum(item.price for item in grocery_items), 2)

    return render_template(
        "grocery.html",
        user=user,
        grocery_items=grocery_items,
        total=total
    )





# =========================================================
# DELETE GROCERY ITEM
# =========================================================

@app.route("/delete-grocery/<int:item_id>")
def delete_grocery(item_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    item = GroceryItem.query.get_or_404(item_id)

    if item.user_id != session["user_id"]:
        return redirect(url_for("grocery"))

    db.session.delete(item)
    db.session.commit()

    return redirect(url_for("grocery"))


# =========================================================
# REPORT
# =========================================================

# =========================================================
# REPORT
# =========================================================

@app.route("/report")
def report():
    """Display the user's daily nutrition, meal, water and budget report."""

    if "user_id" not in session:
        return redirect(url_for("login"))

    user = db.session.get(User, session["user_id"])

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    today = date.today()

    # -----------------------------------------------------
    # MEAL PROGRESS
    # -----------------------------------------------------

    today_meals = MealProgress.query.filter_by(
        user_id=user.id,
        date=today
    ).all()

    total_meals = len(today_meals)

    completed_meals = sum(
        1 for meal in today_meals if meal.completed
    )

    meal_progress = (
        round((completed_meals / total_meals) * 100)
        if total_meals else 0
    )

    meal_progress = min(max(meal_progress, 0), 100)

    completed_meal_types = [
        meal.meal_type
        for meal in today_meals
        if meal.completed
    ]

    completed_cost = round(
        sum(
            float(meal.cost or 0)
            for meal in today_meals
            if meal.completed
        ),
        2
    )

    # -----------------------------------------------------
    # NUTRITION
    # -----------------------------------------------------

    generated_meals = GeneratedMeal.query.filter_by(
        user_id=user.id,
        date=today
    ).all()

    completed_generated_meals = [
        meal for meal in generated_meals
        if meal.meal_type in completed_meal_types
    ]

    calories_consumed = sum(
        float(meal.calories or 0)
        for meal in completed_generated_meals
    )

    protein_consumed = sum(
        float(meal.protein or 0)
        for meal in completed_generated_meals
    )

    carbs_consumed = sum(
        float(meal.carbs or 0)
        for meal in completed_generated_meals
    )

    fat_consumed = sum(
        float(meal.fat or 0)
        for meal in completed_generated_meals
    )

    daily_intake = get_daily_nutrition(user.id, today)

    nutrition = {
        "calories": round(calories_consumed, 1),
        "protein": round(protein_consumed, 1),
        "carbs": round(carbs_consumed, 1),
        "fat": round(fat_consumed, 1),
        "fiber": round(
            float(daily_intake.get("fiber", 0) or 0), 1
        )
    }

    # -----------------------------------------------------
    # DAILY TARGETS
    # -----------------------------------------------------

    targets = get_daily_targets(user)

    calorie_target = max(
        float(targets.get("calories", 2000) or 2000), 1
    )

    protein_target = max(
        float(targets.get("protein", 60) or 60), 1
    )

    calorie_progress = round(
        min((calories_consumed / calorie_target) * 100, 100)
    )

    protein_progress = round(
        min((protein_consumed / protein_target) * 100, 100)
    )

    # -----------------------------------------------------
    # WEIGHT AND BMI
    # -----------------------------------------------------

    weight = float(user.weight or 0)
    bmi = 0

    if user.height and weight > 0:
        height_m = float(user.height) / 100

        if height_m > 0:
            bmi = round(weight / (height_m * height_m), 1)

    # -----------------------------------------------------
    # WATER INTAKE
    # -----------------------------------------------------

    water_amount = db.session.query(
        db.func.sum(WaterIntake.amount)
    ).filter_by(
        user_id=user.id,
        date=today
    ).scalar() or 0

    water_amount = float(water_amount)

    water_target = 2500

    water_percentage = round(
        min((water_amount / water_target) * 100, 100),
        1
    )

    # -----------------------------------------------------
    # DAILY BUDGET
    # -----------------------------------------------------

    daily_budget = float(
        getattr(user, "grocery_budget", 0) or 0
    )

    if daily_budget <= 0:
        daily_budget = sum(
            float(meal.cost or 0)
            for meal in generated_meals
        )

    remaining_budget = max(
        daily_budget - completed_cost, 0
    )

    budget_progress = (
        round(
            min((completed_cost / daily_budget) * 100, 100)
        )
        if daily_budget > 0 else 0
    )

    # -----------------------------------------------------
    # DAILY STATUS
    # -----------------------------------------------------

    if total_meals == 0:
        daily_status = (
            "Your meal plan has not been generated yet. "
            "Generate today's meal plan to start tracking your progress."
        )

    elif completed_meals == total_meals:
        daily_status = (
            "Excellent! You completed all your planned meals today. "
            "Keep maintaining this consistency."
        )

    elif meal_progress >= 50:
        daily_status = (
            f"Good progress! You completed {completed_meals} out of "
            f"{total_meals} meals today. Keep going and complete "
            "the remaining meals."
        )

    else:
        daily_status = (
            f"You have completed {completed_meals} out of "
            f"{total_meals} planned meals today. "
            "Try to complete your remaining meals."
        )

    # -----------------------------------------------------
    # TEMPLATE VARIABLE COMPATIBILITY
    # -----------------------------------------------------

    meal_percentage = meal_progress
    calorie_percentage = calorie_progress
    protein_percentage = protein_progress
    daily_cost = completed_cost
    budget_percentage = budget_progress
    health_status = daily_status

    # -----------------------------------------------------
    # RENDER REPORT PAGE
    # -----------------------------------------------------

    return render_template(
        "report.html",

        user=user,

        total_meals=total_meals,
        completed_meals=completed_meals,
        meal_progress=meal_progress,
        meal_percentage=meal_percentage,

        calories_consumed=round(calories_consumed),
        calorie_target=round(calorie_target),
        calorie_progress=calorie_progress,
        calorie_percentage=calorie_percentage,

        protein_consumed=round(protein_consumed, 1),
        protein_target=round(protein_target, 1),
        protein_progress=protein_progress,
        protein_percentage=protein_percentage,

        carbs_consumed=round(carbs_consumed, 1),
        fat_consumed=round(fat_consumed, 1),
        nutrition=nutrition,

        weight=weight,
        bmi=bmi,

        water_amount=round(water_amount, 1),
        water_target=water_target,
        water_percentage=water_percentage,

        completed_cost=completed_cost,
        daily_cost=daily_cost,
        daily_budget=round(daily_budget, 2),
        remaining_budget=round(remaining_budget, 2),
        budget_progress=budget_progress,
        budget_percentage=budget_percentage,

        daily_status=daily_status,
        health_status=health_status,

        today_meals=today_meals
    )

# =========================================================
# PROFILE
# =========================================================

@app.route("/profile", methods=["GET", "POST"])
def profile():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    if request.method == "POST":

        name = request.form.get("name", "").strip()

        if name:
            user.name = name

        try:
            age = request.form.get("age")
            height = request.form.get("height")
            weight = request.form.get("weight")

            user.age = int(age) if age else None
            user.height = float(height) if height else None
            user.weight = float(weight) if weight else None

        except ValueError:
            return "Please enter valid numbers."

        user.diet = request.form.get("diet", user.diet)
        user.goal = request.form.get("goal", user.goal)

        db.session.commit()

        return redirect(url_for("profile"))

    edit = request.args.get("edit") == "true"

    return render_template(
        "profile.html",
        user=user,
        edit=edit
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(debug=True)