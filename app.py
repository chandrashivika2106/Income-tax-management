import os
import re
import logging
from decimal import Decimal, InvalidOperation

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from database import get_connection
from tax_calculator import calculate_new_regime_tax


app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "development-secret-change-before-deployment"
)

app.logger.setLevel(logging.INFO)


VALID_FINANCIAL_YEARS = {
    "2025-2026",
    "2026-2027",
    "2027-2028"
}

PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")

MAX_AMOUNT = Decimal("9999999999.99")
ZERO = Decimal("0.00")


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_logged_in_user_id():
    return session.get("user_id")


def parse_amount(value, field_name):
    try:
        amount = Decimal(str(value).strip())

    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field_name} must be a valid number.")

    if not amount.is_finite():
        raise ValueError(f"{field_name} must be a valid number.")

    if amount < ZERO:
        raise ValueError(f"{field_name} cannot be negative.")

    if amount > MAX_AMOUNT:
        raise ValueError(f"{field_name} is too large.")

    if amount.as_tuple().exponent < -2:
        raise ValueError(
            f"{field_name} cannot have more than two decimal places."
        )

    return amount.quantize(Decimal("0.01"))


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    table_counts = {}

    tables = [
        "USERS",
        "TAXPAYERS",
        "INCOME_DETAILS",
        "TAX_RECORDS"
    ]

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            table_counts[table] = cursor.fetchone()[0]

    except Exception:
        app.logger.exception("Unable to fetch database statistics.")
        table_counts = {}

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

    return render_template(
        "index.html",
        table_counts=table_counts
    )


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Please enter username and password.", "error")
            return render_template("register.html")

        if len(username) > 100:
            flash("Username cannot exceed 100 characters.", "error")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
            return render_template("register.html")

        connection = None
        cursor = None

        try:
            connection = get_connection()
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT USER_ID
                FROM USERS
                WHERE LOWER(USERNAME) = LOWER(:username)
                """,
                {"username": username}
            )

            if cursor.fetchone():
                flash("Username already exists.", "error")
                return render_template("register.html")

            password_hash = generate_password_hash(password)

            cursor.execute(
                """
                INSERT INTO USERS (USERNAME, PASSWORD_HASH)
                VALUES (:username, :password_hash)
                """,
                {
                    "username": username,
                    "password_hash": password_hash
                }
            )

            connection.commit()

            flash("Registration successful! Please log in.", "success")

            return redirect(url_for("login"))

        except Exception:
            if connection:
                connection.rollback()

            app.logger.exception("Registration failed.")
            flash("Registration failed. Please try again.", "error")

        finally:
            if cursor:
                cursor.close()

            if connection:
                connection.close()

    return render_template("register.html")


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Enter your username and password.", "error")
            return render_template("login.html")

        connection = None
        cursor = None

        try:
            connection = get_connection()
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT USER_ID, PASSWORD_HASH
                FROM USERS
                WHERE LOWER(USERNAME) = LOWER(:username)
                """,
                {"username": username}
            )

            user = cursor.fetchone()

            if user and check_password_hash(user[1], password):

                session.clear()

                session["user_id"] = user[0]
                session["username"] = username

                flash("Login successful!", "success")

                return redirect(url_for("dashboard"))

            flash("Invalid username or password.", "error")

        except Exception:
            app.logger.exception("Login failed.")
            flash("Unable to log in right now.", "error")

        finally:
            if cursor:
                cursor.close()

            if connection:
                connection.close()

    return render_template("login.html")


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    user_id = get_logged_in_user_id()

    if not user_id:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    connection = None
    cursor = None

    taxpayer = None
    income = None
    latest_tax_record = None
    tax_record_count = 0

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT TAXPAYER_ID, FULL_NAME, PAN, FINANCIAL_YEAR
            FROM TAXPAYERS
            WHERE USER_ID = :user_id
            """,
            {"user_id": user_id}
        )

        taxpayer = cursor.fetchone()

        if taxpayer:

            taxpayer_id = taxpayer[0]

            cursor.execute(
                """
                SELECT SALARY_INCOME,
                       HOUSE_PROPERTY_INCOME,
                       OTHER_INCOME,
                       ELIGIBLE_DEDUCTIONS,
                       TDS_AMOUNT
                FROM INCOME_DETAILS
                WHERE TAXPAYER_ID = :taxpayer_id
                """,
                {"taxpayer_id": taxpayer_id}
            )

            income = cursor.fetchone()

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM TAX_RECORDS
                WHERE TAXPAYER_ID = :taxpayer_id
                """,
                {"taxpayer_id": taxpayer_id}
            )

            tax_record_count = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT RECORD_ID,
                       GROSS_TOTAL_INCOME,
                       TAXABLE_INCOME,
                       TOTAL_TAX_LIABILITY,
                       TAX_PAYABLE,
                       CALCULATION_DATE
                FROM TAX_RECORDS
                WHERE TAXPAYER_ID = :taxpayer_id
                ORDER BY CALCULATION_DATE DESC, RECORD_ID DESC
                FETCH FIRST 1 ROW ONLY
                """,
                {"taxpayer_id": taxpayer_id}
            )

            latest_tax_record = cursor.fetchone()

    except Exception:
        app.logger.exception("Dashboard loading failed.")
        flash("Unable to load all dashboard information.", "error")

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

    return render_template(
        "dashboard.html",
        username=session.get("username"),
        taxpayer=taxpayer,
        income=income,
        latest_tax_record=latest_tax_record,
        tax_record_count=tax_record_count
    )


# ============================================================
# TAXPAYER PROFILE
# ============================================================

@app.route("/profile", methods=["GET", "POST"])
def profile():

    user_id = get_logged_in_user_id()

    if not user_id:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        if request.method == "POST":

            full_name = request.form.get("full_name", "").strip()
            pan = request.form.get("pan", "").strip().upper()
            financial_year = request.form.get(
                "financial_year", ""
            ).strip()

            if not full_name or len(full_name) > 200:
                flash("Enter a valid full name.", "error")

            elif not PAN_PATTERN.fullmatch(pan):
                flash("Enter a valid PAN format.", "error")

            elif financial_year not in VALID_FINANCIAL_YEARS:
                flash("Select a valid financial year.", "error")

            else:

                cursor.execute(
                    """
                    SELECT TAXPAYER_ID
                    FROM TAXPAYERS
                    WHERE PAN = :pan
                      AND USER_ID <> :user_id
                    """,
                    {
                        "pan": pan,
                        "user_id": user_id
                    }
                )

                if cursor.fetchone():

                    flash(
                        "This PAN is already associated with another account.",
                        "error"
                    )

                else:

                    cursor.execute(
                        """
                        SELECT TAXPAYER_ID
                        FROM TAXPAYERS
                        WHERE USER_ID = :user_id
                        """,
                        {"user_id": user_id}
                    )

                    existing = cursor.fetchone()

                    if existing:

                        cursor.execute(
                            """
                            UPDATE TAXPAYERS
                            SET FULL_NAME = :full_name,
                                PAN = :pan,
                                FINANCIAL_YEAR = :financial_year
                            WHERE USER_ID = :user_id
                            """,
                            {
                                "full_name": full_name,
                                "pan": pan,
                                "financial_year": financial_year,
                                "user_id": user_id
                            }
                        )

                    else:

                        cursor.execute(
                            """
                            INSERT INTO TAXPAYERS
                            (
                                USER_ID,
                                FULL_NAME,
                                PAN,
                                FINANCIAL_YEAR
                            )
                            VALUES
                            (
                                :user_id,
                                :full_name,
                                :pan,
                                :financial_year
                            )
                            """,
                            {
                                "user_id": user_id,
                                "full_name": full_name,
                                "pan": pan,
                                "financial_year": financial_year
                            }
                        )

                    connection.commit()

                    flash("Taxpayer profile saved successfully!", "success")

                    return redirect(url_for("profile"))

        cursor.execute(
            """
            SELECT TAXPAYER_ID, FULL_NAME, PAN, FINANCIAL_YEAR
            FROM TAXPAYERS
            WHERE USER_ID = :user_id
            """,
            {"user_id": user_id}
        )

        taxpayer = cursor.fetchone()

        return render_template(
            "profile.html",
            taxpayer=taxpayer,
            financial_years=sorted(VALID_FINANCIAL_YEARS)
        )

    except Exception:
        if connection:
            connection.rollback()

        app.logger.exception("Profile operation failed.")
        flash("Unable to save or load your profile.", "error")

        return redirect(url_for("dashboard"))

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()


# ============================================================
# INCOME DETAILS
# ============================================================

@app.route("/income", methods=["GET", "POST"])
def income():

    user_id = get_logged_in_user_id()

    if not user_id:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT TAXPAYER_ID
            FROM TAXPAYERS
            WHERE USER_ID = :user_id
            """,
            {"user_id": user_id}
        )

        taxpayer = cursor.fetchone()

        if not taxpayer:
            flash("Please create your profile first.", "error")
            return redirect(url_for("profile"))

        taxpayer_id = taxpayer[0]

        cursor.execute(
            """
            SELECT INCOME_ID,
                   SALARY_INCOME,
                   HOUSE_PROPERTY_INCOME,
                   OTHER_INCOME,
                   ELIGIBLE_DEDUCTIONS,
                   TDS_AMOUNT
            FROM INCOME_DETAILS
            WHERE TAXPAYER_ID = :taxpayer_id
            """,
            {"taxpayer_id": taxpayer_id}
        )

        existing_income = cursor.fetchone()

        if request.method == "POST":

            try:
                salary = parse_amount(
                    request.form.get("salary_income", ""),
                    "Salary income"
                )

                house = parse_amount(
                    request.form.get("house_property_income", "0"),
                    "House property income"
                )

                other = parse_amount(
                    request.form.get("other_income", "0"),
                    "Other income"
                )

                deductions = parse_amount(
                    request.form.get("eligible_deductions", "0"),
                    "Eligible deductions"
                )

                tds = parse_amount(
                    request.form.get("tds_amount", "0"),
                    "TDS amount"
                )

            except ValueError as error:
                flash(str(error), "error")

                return render_template(
                    "income.html",
                    income=existing_income
                )

            if existing_income:

                cursor.execute(
                    """
                    UPDATE INCOME_DETAILS
                    SET SALARY_INCOME = :salary,
                        HOUSE_PROPERTY_INCOME = :house,
                        OTHER_INCOME = :other,
                        ELIGIBLE_DEDUCTIONS = :deductions,
                        TDS_AMOUNT = :tds
                    WHERE TAXPAYER_ID = :taxpayer_id
                    """,
                    {
                        "salary": salary,
                        "house": house,
                        "other": other,
                        "deductions": deductions,
                        "tds": tds,
                        "taxpayer_id": taxpayer_id
                    }
                )

            else:

                cursor.execute(
                    """
                    INSERT INTO INCOME_DETAILS
                    (
                        TAXPAYER_ID,
                        SALARY_INCOME,
                        HOUSE_PROPERTY_INCOME,
                        OTHER_INCOME,
                        ELIGIBLE_DEDUCTIONS,
                        TDS_AMOUNT
                    )
                    VALUES
                    (
                        :taxpayer_id,
                        :salary,
                        :house,
                        :other,
                        :deductions,
                        :tds
                    )
                    """,
                    {
                        "taxpayer_id": taxpayer_id,
                        "salary": salary,
                        "house": house,
                        "other": other,
                        "deductions": deductions,
                        "tds": tds
                    }
                )

            connection.commit()

            flash("Income details saved successfully!", "success")

            return redirect(url_for("income"))

        cursor.execute(
            """
            SELECT INCOME_ID,
                   SALARY_INCOME,
                   HOUSE_PROPERTY_INCOME,
                   OTHER_INCOME,
                   ELIGIBLE_DEDUCTIONS,
                   TDS_AMOUNT
            FROM INCOME_DETAILS
            WHERE TAXPAYER_ID = :taxpayer_id
            """,
            {"taxpayer_id": taxpayer_id}
        )

        saved_income = cursor.fetchone()

        return render_template(
            "income.html",
            income=saved_income
        )

    except Exception:
        if connection:
            connection.rollback()

        app.logger.exception("Income operation failed.")
        flash("Unable to save or load income details.", "error")

        return redirect(url_for("dashboard"))

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()


# ============================================================
# TAX CALCULATOR
# ============================================================

@app.route("/calculate-tax", methods=["GET", "POST"])
def calculate_tax():

    user_id = get_logged_in_user_id()

    if not user_id:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT TAXPAYER_ID, FINANCIAL_YEAR
            FROM TAXPAYERS
            WHERE USER_ID = :user_id
            """,
            {"user_id": user_id}
        )

        taxpayer = cursor.fetchone()

        if not taxpayer:
            flash("Please create your taxpayer profile first.", "error")
            return redirect(url_for("profile"))

        taxpayer_id = taxpayer[0]
        financial_year = taxpayer[1]

        if financial_year != "2026-2027":

            flash(
                "The current calculator supports FY 2026-2027 only.",
                "error"
            )

            return render_template(
                "tax_calculator.html",
                financial_year=financial_year
            )

        cursor.execute(
            """
            SELECT SALARY_INCOME,
                   HOUSE_PROPERTY_INCOME,
                   OTHER_INCOME,
                   ELIGIBLE_DEDUCTIONS,
                   TDS_AMOUNT
            FROM INCOME_DETAILS
            WHERE TAXPAYER_ID = :taxpayer_id
            """,
            {"taxpayer_id": taxpayer_id}
        )

        income_data = cursor.fetchone()

        if not income_data:
            flash("Please save your income details first.", "error")
            return redirect(url_for("income"))

        if request.method == "POST":

            result = calculate_new_regime_tax(*income_data)

            cursor.execute(
                """
                INSERT INTO TAX_RECORDS
                (
                    TAXPAYER_ID,
                    GROSS_TOTAL_INCOME,
                    TAXABLE_INCOME,
                    INCOME_TAX,
                    CESS,
                    TOTAL_TAX_LIABILITY,
                    TAX_PAYABLE
                )
                VALUES
                (
                    :taxpayer_id,
                    :gross_total_income,
                    :taxable_income,
                    :income_tax,
                    :cess,
                    :total_tax_liability,
                    :tax_payable
                )
                """,
                {
                    "taxpayer_id": taxpayer_id,
                    "gross_total_income": result["gross_total_income"],
                    "taxable_income": result["taxable_income"],
                    "income_tax": result["income_tax"],
                    "cess": result["cess"],
                    "total_tax_liability": result["total_tax_liability"],
                    "tax_payable": result["tax_payable"]
                }
            )

            connection.commit()

            flash("Tax calculated and saved successfully!", "success")

            return render_template(
                "tax_result.html",
                result=result,
                financial_year=financial_year
            )

        return render_template(
            "tax_calculator.html",
            financial_year=financial_year
        )

    except ValueError as error:
        if connection:
            connection.rollback()

        flash(str(error), "error")
        return redirect(url_for("calculate_tax"))

    except Exception:
        if connection:
            connection.rollback()

        app.logger.exception("Tax calculation failed.")
        flash("Tax calculation failed. Please try again.", "error")

        return redirect(url_for("dashboard"))

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()


# ============================================================
# TAX HISTORY
# ============================================================

@app.route("/tax-history")
def tax_history():

    user_id = get_logged_in_user_id()

    if not user_id:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT TAXPAYER_ID
            FROM TAXPAYERS
            WHERE USER_ID = :user_id
            """,
            {"user_id": user_id}
        )

        taxpayer = cursor.fetchone()

        if not taxpayer:
            flash("Please create your profile first.", "error")
            return redirect(url_for("profile"))

        taxpayer_id = taxpayer[0]

        cursor.execute(
            """
            SELECT RECORD_ID,
                   GROSS_TOTAL_INCOME,
                   TAXABLE_INCOME,
                   INCOME_TAX,
                   CESS,
                   TOTAL_TAX_LIABILITY,
                   TAX_PAYABLE,
                   CALCULATION_DATE
            FROM TAX_RECORDS
            WHERE TAXPAYER_ID = :taxpayer_id
            ORDER BY CALCULATION_DATE DESC, RECORD_ID DESC
            """,
            {"taxpayer_id": taxpayer_id}
        )

        records = cursor.fetchall()

        return render_template(
            "tax_history.html",
            records=records
        )

    except Exception:
        app.logger.exception("Tax history loading failed.")
        flash("Unable to load tax history.", "error")
        return redirect(url_for("dashboard"))

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    flash("You have been logged out successfully.", "success")

    return redirect(url_for("login"))


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":
    app.run(debug=True)