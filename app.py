from flask import Flask, render_template, request, redirect, flash, jsonify
from database import get_db_connection
from datetime import date

app = Flask(__name__)

# Secret key for Flask flash messages
app.secret_key = "attendance-system-secret-key"


# =========================================================
# HOME PAGE
# =========================================================
@app.route("/")
def home():
    return render_template("index.html")


# =========================================================
# TEACHER LOGIN
# =========================================================
@app.route("/teacher-login", methods=["GET", "POST"])
def teacher_login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            "SELECT * FROM teachers WHERE username=%s AND password=%s",
            (username, password)
        )

        teacher = cursor.fetchone()

        cursor.close()
        connection.close()

        if teacher:
            return redirect("/teacher-dashboard")

        flash("Invalid teacher username or password.")

    return render_template("teacher_login.html")


# =========================================================
# TEACHER DASHBOARD
# =========================================================
@app.route("/teacher-dashboard")
def teacher_dashboard():

    connection = get_db_connection()
    cursor = connection.cursor()

    # Total students
    cursor.execute("SELECT COUNT(*) FROM students")
    total_students = cursor.fetchone()[0]

    # Today's attendance
    today = date.today()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM attendance
        WHERE date=%s AND status='Present'
        """,
        (today,)
    )
    present_today = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM attendance
        WHERE date=%s AND status='Absent'
        """,
        (today,)
    )
    absent_today = cursor.fetchone()[0]

    # Overall attendance percentage
    cursor.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) AS present
        FROM attendance
        """
    )

    overall_data = cursor.fetchone()

    total_attendance = overall_data[0] or 0
    total_present = overall_data[1] or 0

    if total_attendance > 0:
        overall_percentage = round(
            (total_present / total_attendance) * 100, 2
        )
    else:
        overall_percentage = 0

    # Student-wise attendance
    cursor.execute(
        """
        SELECT
            s.id,
            s.name,
            s.roll_no,
            COUNT(a.id) AS total_classes,
            SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) AS present_classes,
            SUM(CASE WHEN a.status='Absent' THEN 1 ELSE 0 END) AS absent_classes
        FROM students s
        LEFT JOIN attendance a
            ON s.id = a.student_id
        GROUP BY s.id, s.name, s.roll_no
        ORDER BY s.roll_no
        """
    )

    student_attendance = cursor.fetchall()

    # Students below 75%
    low_attendance_students = []

    for student in student_attendance:

        total_classes = student[3] or 0
        present_classes = student[4] or 0

        if total_classes > 0:

            percentage = (present_classes / total_classes) * 100

            if percentage < 75:
                low_attendance_students.append(student)

    cursor.close()
    connection.close()

    return render_template(
        "teacher_dashboard.html",
        total_students=total_students,
        present_today=present_today,
        absent_today=absent_today,
        overall_percentage=overall_percentage,
        student_attendance=student_attendance,
        low_attendance_students=low_attendance_students
    )


# =========================================================
# MANAGE STUDENTS
# =========================================================
@app.route("/manage-students")
def manage_students():

    search = request.args.get("search", "").strip()

    connection = get_db_connection()
    cursor = connection.cursor()

    if search:

        search_value = f"%{search}%"

        cursor.execute(
            """
            SELECT *
            FROM students
            WHERE name LIKE %s
               OR roll_no LIKE %s
               OR username LIKE %s
            ORDER BY roll_no
            """,
            (search_value, search_value, search_value)
        )

    else:

        cursor.execute(
            """
            SELECT *
            FROM students
            ORDER BY roll_no
            """
        )

    students = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "manage_students.html",
        students=students,
        search=search
    )


# =========================================================
# ADD STUDENT - TEACHER
# =========================================================
@app.route("/add-student", methods=["GET", "POST"])
def add_student():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        roll_no = request.form.get("roll_no", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not name or not roll_no or not username or not password:
            flash("All fields are required.")
            return redirect("/add-student")

        connection = get_db_connection()
        cursor = connection.cursor()

        try:

            cursor.execute(
                """
                SELECT id
                FROM students
                WHERE username=%s OR roll_no=%s
                """,
                (username, roll_no)
            )

            existing_student = cursor.fetchone()

            if existing_student:
                flash("Username or Roll Number already exists.")
                return redirect("/add-student")

            cursor.execute(
                """
                INSERT INTO students
                (username, password, name, roll_no)
                VALUES (%s, %s, %s, %s)
                """,
                (username, password, name, roll_no)
            )

            connection.commit()

            flash("Student added successfully!")

        except Exception as e:

            connection.rollback()
            flash("Error adding student.")

        finally:

            cursor.close()
            connection.close()

        return redirect("/manage-students")

    return render_template("add_student.html")


# =========================================================
# STUDENT SELF REGISTRATION
# =========================================================
@app.route("/student-register", methods=["GET", "POST"])
def student_register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        roll_no = request.form.get("roll_no", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        # Check empty fields
        if not name or not roll_no or not username or not password or not confirm_password:

            flash("Please fill all fields.")
            return redirect("/student-register")

        # Check password matching
        if password != confirm_password:

            flash("Passwords do not match.")
            return redirect("/student-register")

        # Minimum password length
        if len(password) < 4:

            flash("Password must contain at least 4 characters.")
            return redirect("/student-register")

        connection = get_db_connection()
        cursor = connection.cursor()

        try:

            # Check username
            cursor.execute(
                """
                SELECT id
                FROM students
                WHERE username=%s
                """,
                (username,)
            )

            existing_username = cursor.fetchone()

            if existing_username:

                flash("Username already exists. Please choose another username.")
                return redirect("/student-register")

            # Check roll number
            cursor.execute(
                """
                SELECT id
                FROM students
                WHERE roll_no=%s
                """,
                (roll_no,)
            )

            existing_roll = cursor.fetchone()

            if existing_roll:

                flash("Roll Number already exists.")
                return redirect("/student-register")

            # Create student account
            cursor.execute(
                """
                INSERT INTO students
                (username, password, name, roll_no)
                VALUES (%s, %s, %s, %s)
                """,
                (username, password, name, roll_no)
            )

            connection.commit()

            flash(
                "Registration successful! You can now login with your username and password."
            )

            return redirect("/student-login")

        except Exception as e:

            connection.rollback()
            flash("Registration failed. Please try again.")

        finally:

            cursor.close()
            connection.close()

    return render_template("student_register.html")


# =========================================================
# EDIT STUDENT
# =========================================================
@app.route("/edit-student/<int:student_id>", methods=["GET", "POST"])
def edit_student(student_id):

    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        roll_no = request.form.get("roll_no", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not name or not roll_no or not username or not password:

            flash("All fields are required.")

            cursor.close()
            connection.close()

            return redirect(f"/edit-student/{student_id}")

        try:

            cursor.execute(
                """
                SELECT id
                FROM students
                WHERE (username=%s OR roll_no=%s)
                AND id != %s
                """,
                (username, roll_no, student_id)
            )

            existing_student = cursor.fetchone()

            if existing_student:

                flash("Username or Roll Number already exists.")

                cursor.close()
                connection.close()

                return redirect(f"/edit-student/{student_id}")

            cursor.execute(
                """
                UPDATE students
                SET name=%s,
                    roll_no=%s,
                    username=%s,
                    password=%s
                WHERE id=%s
                """,
                (name, roll_no, username, password, student_id)
            )

            connection.commit()

            flash("Student updated successfully!")

            cursor.close()
            connection.close()

            return redirect("/manage-students")

        except Exception as e:

            connection.rollback()

            flash("Error updating student.")

            cursor.close()
            connection.close()

            return redirect(f"/edit-student/{student_id}")

    # GET request
    cursor.execute(
        "SELECT * FROM students WHERE id=%s",
        (student_id,)
    )

    student = cursor.fetchone()

    cursor.close()
    connection.close()

    if not student:

        flash("Student not found.")
        return redirect("/manage-students")

    return render_template(
        "edit_student.html",
        student=student
    )


# =========================================================
# DELETE STUDENT
# =========================================================
@app.route("/delete-student/<int:student_id>")
def delete_student(student_id):

    connection = get_db_connection()
    cursor = connection.cursor()

    try:

        # Delete attendance first because of foreign key
        cursor.execute(
            "DELETE FROM attendance WHERE student_id=%s",
            (student_id,)
        )

        cursor.execute(
            "DELETE FROM students WHERE id=%s",
            (student_id,)
        )

        connection.commit()

        flash("Student deleted successfully!")

    except Exception as e:

        connection.rollback()
        flash("Error deleting student.")

    finally:

        cursor.close()
        connection.close()

    return redirect("/manage-students")


# =========================================================
# MARK ATTENDANCE
# =========================================================
@app.route("/mark-attendance", methods=["GET", "POST"])
def mark_attendance():

    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == "POST":

        selected_date = request.form.get("attendance_date")

        if not selected_date:

            flash("Please select a date.")

            cursor.close()
            connection.close()

            return redirect("/mark-attendance")

        updated_count = 0
        inserted_count = 0

        cursor.execute(
            "SELECT id FROM students ORDER BY roll_no"
        )

        students = cursor.fetchall()

        for student in students:

            student_id = student[0]

            status = request.form.get(
                f"status_{student_id}"
            )

            if not status:
                continue

            # Check whether attendance already exists
            cursor.execute(
                """
                SELECT id
                FROM attendance
                WHERE student_id=%s
                AND date=%s
                """,
                (student_id, selected_date)
            )

            existing_attendance = cursor.fetchone()

            if existing_attendance:

                cursor.execute(
                    """
                    UPDATE attendance
                    SET status=%s
                    WHERE student_id=%s
                    AND date=%s
                    """,
                    (
                        status,
                        student_id,
                        selected_date
                    )
                )

                updated_count += 1

            else:

                cursor.execute(
                    """
                    INSERT INTO attendance
                    (student_id, date, status)
                    VALUES (%s, %s, %s)
                    """,
                    (
                        student_id,
                        selected_date,
                        status
                    )
                )

                inserted_count += 1

        connection.commit()

        if updated_count > 0 and inserted_count > 0:

            flash(
                f"Attendance updated successfully! "
                f"{updated_count} record(s) updated and "
                f"{inserted_count} new record(s) saved."
            )

        elif updated_count > 0:

            flash(
                f"Attendance updated successfully! "
                f"{updated_count} record(s) updated."
            )

        elif inserted_count > 0:

            flash(
                f"Attendance saved successfully! "
                f"{inserted_count} record(s) saved."
            )

        else:

            flash("No attendance records were changed.")

        cursor.close()
        connection.close()

        return redirect(
            f"/mark-attendance?date={selected_date}"
        )

    # GET request
    selected_date = request.args.get(
        "date",
        date.today().isoformat()
    )

    cursor.execute(
        """
        SELECT *
        FROM students
        ORDER BY roll_no
        """
    )

    students = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "mark_attendance.html",
        students=students,
        selected_date=selected_date
    )


# =========================================================
# ATTENDANCE REPORT
# =========================================================
@app.route("/attendance-report")
def attendance_report():

    selected_date = request.args.get("date", "")

    connection = get_db_connection()
    cursor = connection.cursor()

    if selected_date:

        cursor.execute(
            """
            SELECT
                a.id,
                s.name,
                s.roll_no,
                a.date,
                a.status
            FROM attendance a
            JOIN students s
                ON a.student_id = s.id
            WHERE a.date=%s
            ORDER BY s.roll_no
            """,
            (selected_date,)
        )

    else:

        cursor.execute(
            """
            SELECT
                a.id,
                s.name,
                s.roll_no,
                a.date,
                a.status
            FROM attendance a
            JOIN students s
                ON a.student_id = s.id
            ORDER BY a.date DESC, s.roll_no
            """
        )

    attendance_records = cursor.fetchall()

    # Summary
    if selected_date:

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE date=%s
            AND status='Present'
            """,
            (selected_date,)
        )

        present_count = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE date=%s
            AND status='Absent'
            """,
            (selected_date,)
        )

        absent_count = cursor.fetchone()[0]

    else:

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE status='Present'
            """
        )

        present_count = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE status='Absent'
            """
        )

        absent_count = cursor.fetchone()[0]

    cursor.close()
    connection.close()

    return render_template(
        "attendance_report.html",
        attendance_records=attendance_records,
        selected_date=selected_date,
        present_count=present_count,
        absent_count=absent_count
    )


# =========================================================
# STUDENT LOGIN
# =========================================================
@app.route("/student-login", methods=["GET", "POST"])
def student_login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM students
            WHERE username=%s
            AND password=%s
            """,
            (username, password)
        )

        student = cursor.fetchone()

        cursor.close()
        connection.close()

        if student:

            return redirect(
                f"/student-dashboard/{student[0]}"
            )

        flash("Invalid student username or password.")

    return render_template("student_login.html")


# =========================================================
# STUDENT DASHBOARD
# =========================================================
@app.route("/student-dashboard/<int:student_id>")
def student_dashboard(student_id):

    connection = get_db_connection()
    cursor = connection.cursor()

    # Student information
    cursor.execute(
        """
        SELECT *
        FROM students
        WHERE id=%s
        """,
        (student_id,)
    )

    student = cursor.fetchone()

    if not student:

        cursor.close()
        connection.close()

        flash("Student not found.")
        return redirect("/student-login")

    # Attendance history
    cursor.execute(
        """
        SELECT date, status
        FROM attendance
        WHERE student_id=%s
        ORDER BY date DESC
        """,
        (student_id,)
    )

    attendance = cursor.fetchall()

    # Attendance statistics
    cursor.execute(
        """
        SELECT
            COUNT(*),
            SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status='Absent' THEN 1 ELSE 0 END)
        FROM attendance
        WHERE student_id=%s
        """,
        (student_id,)
    )

    attendance_data = cursor.fetchone()

    total_classes = attendance_data[0] or 0
    present = attendance_data[1] or 0
    absent = attendance_data[2] or 0

    if total_classes > 0:

        percentage = round(
            (present / total_classes) * 100,
            2
        )

    else:

        percentage = 0

    cursor.close()
    connection.close()

    return render_template(
        "student_dashboard.html",
        student=student,
        attendance=attendance,
        total_classes=total_classes,
        present=present,
        absent=absent,
        percentage=percentage
    )


# =========================================================
# CHATBOT
# =========================================================
@app.route("/chatbot", methods=["POST"])
def chatbot():

    data = request.get_json()

    if not data:

        return jsonify({
            "reply": "Please type a message."
        })

    message = data.get("message", "").lower().strip()

    if not message:

        return jsonify({
            "reply": "Please type a message."
        })

    # Greeting
    if any(word in message for word in [
        "hello",
        "hi",
        "hey",
        "hii",
        "good morning",
        "good afternoon",
        "good evening"
    ]):

        reply = (
            "Hello! 👋 Welcome to the Student Attendance Management System. "
            "How can I help you today?"
        )

    # Login
    elif "login" in message or "log in" in message:

        reply = (
            "To login, choose either Teacher Login or Student Login "
            "from the home page and enter your username and password."
        )

    # Mark attendance
    elif (
        "mark attendance" in message
        or "take attendance" in message
        or "attendance mark" in message
    ):

        reply = (
            "Teachers can mark attendance from the Mark Attendance page. "
            "Select a date, choose Present or Absent for each student, "
            "and click the save/update button."
        )

    # Check attendance
    elif (
        "check attendance" in message
        or "my attendance" in message
        or "attendance percentage" in message
        or "attendance percent" in message
    ):

        reply = (
            "Students can login through Student Login to view their "
            "attendance history, total classes, present classes, "
            "absent classes, and attendance percentage."
        )

    # Add student
    elif (
        "add student" in message
        or "new student" in message
        or "create student" in message
    ):

        reply = (
            "Teachers can add a student from Manage Students → Add Student. "
            "Enter the student's name, roll number, username and password."
        )

    # Student registration
    elif (
        "register" in message
        or "registration" in message
        or "create account" in message
        or "sign up" in message
        or "signup" in message
    ):

        reply = (
            "Students can now create their own account! 🎓 "
            "Go to Student Login and click 'Register here'. "
            "Enter your name, roll number, username and password."
        )

    # Edit student
    elif (
        "edit student" in message
        or "update student" in message
    ):

        reply = (
            "Teachers can edit student information from "
            "Manage Students → Edit."
        )

    # Delete student
    elif (
        "delete student" in message
        or "remove student" in message
    ):

        reply = (
            "Teachers can delete a student from the Manage Students page. "
            "Please be careful because deleting a student also removes "
            "that student's attendance records."
        )

    # Attendance report
    elif (
        "attendance report" in message
        or "report" in message
    ):

        reply = (
            "Teachers can open Attendance Report to view attendance records. "
            "You can also filter the report by date."
        )

    # Low attendance
    elif (
        "low attendance" in message
        or "below 75" in message
        or "75%" in message
        or "75 percent" in message
    ):

        reply = (
            "Students with attendance below 75% are shown in the "
            "Low Attendance section of the Teacher Dashboard."
        )

    # Password
    elif (
        "password" in message
        or "forgot password" in message
        or "reset password" in message
    ):

        reply = (
            "If you forget your password, please contact your teacher/admin "
            "to update your student account details."
        )

    # Teacher
    elif "teacher" in message:

        reply = (
            "Teachers can login, manage students, mark attendance, "
            "update attendance and view attendance reports."
        )

    # Student
    elif "student" in message:

        reply = (
            "Students can register themselves, login and view their "
            "attendance dashboard and attendance history."
        )

    # Help
    elif (
        "help" in message
        or "support" in message
        or "what can you do" in message
    ):

        reply = (
            "I can help you with Teacher Login, Student Registration, "
            "Student Login, Mark Attendance, Attendance Reports, "
            "Student Management and Attendance Percentage. 🤖"
        )

    # Thanks
    elif any(word in message for word in [
        "thanks",
        "thank you",
        "thankyou"
    ]):

        reply = (
            "You're welcome! 😊 I'm always here to help."
        )

    # Goodbye
    elif any(word in message for word in [
        "bye",
        "goodbye"
    ]):

        reply = (
            "Goodbye! 👋 Have a great day!"
        )

    # Unknown question
    else:

        reply = (
            "I'm not sure about that yet. 🤔 "
            "Try asking me about login, student registration, "
            "marking attendance, attendance reports, or student management."
        )

    return jsonify({
        "reply": reply
    })


# =========================================================
# RUN APPLICATION
# =========================================================
if __name__ == "__main__":
    app.run(debug=True)

