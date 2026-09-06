from flask import Flask, render_template, request, redirect
from database import get_db_connection
from datetime import date

app = Flask(__name__)


# =========================
# HOME PAGE
# =========================
@app.route("/")
def home():
    return render_template("index.html")


# =========================
# TEACHER LOGIN
# =========================
@app.route("/teacher-login", methods=["GET", "POST"])
def teacher_login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM teachers
            WHERE username = %s
            AND password = %s
            """,
            (username, password)
        )

        teacher = cursor.fetchone()

        cursor.close()
        connection.close()

        if teacher:
            return redirect("/teacher-dashboard")

        return "Invalid username or password!"

    return render_template("teacher_login.html")


# =========================
# TEACHER DASHBOARD
# =========================
@app.route("/teacher-dashboard")
def teacher_dashboard():

    connection = get_db_connection()
    cursor = connection.cursor()

    # ==================================================
    # TOTAL STUDENTS
    # ==================================================

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM students
        """
    )

    total_students = cursor.fetchone()[0]


    # ==================================================
    # PRESENT TODAY
    # ==================================================

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM attendance
        WHERE date = CURDATE()
        AND status = 'Present'
        """
    )

    present_today = cursor.fetchone()[0]


    # ==================================================
    # ABSENT TODAY
    # ==================================================

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM attendance
        WHERE date = CURDATE()
        AND status = 'Absent'
        """
    )

    absent_today = cursor.fetchone()[0]


    # ==================================================
    # TOTAL ATTENDANCE RECORDS
    # ==================================================

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM attendance
        """
    )

    total_attendance = cursor.fetchone()[0]


    # ==================================================
    # TOTAL PRESENT RECORDS
    # ==================================================

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM attendance
        WHERE status = 'Present'
        """
    )

    total_present = cursor.fetchone()[0]


    # ==================================================
    # OVERALL ATTENDANCE %
    # ==================================================

    if total_attendance > 0:

        overall_percentage = round(
            (total_present / total_attendance) * 100,
            2
        )

    else:

        overall_percentage = 0


    # ==================================================
    # STUDENT-WISE ATTENDANCE SUMMARY
    # ==================================================

    cursor.execute(
        """
        SELECT
            students.id,
            students.name,
            students.roll_no,

            COUNT(attendance.id) AS total_classes,

            COALESCE(
                SUM(
                    CASE
                        WHEN attendance.status = 'Present'
                        THEN 1
                        ELSE 0
                    END
                ),
                0
            ) AS present_classes,

            COALESCE(
                SUM(
                    CASE
                        WHEN attendance.status = 'Absent'
                        THEN 1
                        ELSE 0
                    END
                ),
                0
            ) AS absent_classes

        FROM students

        LEFT JOIN attendance
        ON students.id = attendance.student_id

        GROUP BY
            students.id,
            students.name,
            students.roll_no

        ORDER BY students.roll_no
        """
    )

    student_attendance = cursor.fetchall()


    # ==================================================
    # STUDENTS BELOW 75%
    # ==================================================

    cursor.execute(
        """
        SELECT
            students.id,
            students.name,
            students.roll_no,

            COUNT(attendance.id) AS total_classes,

            COALESCE(
                SUM(
                    CASE
                        WHEN attendance.status = 'Present'
                        THEN 1
                        ELSE 0
                    END
                ),
                0
            ) AS present_classes

        FROM students

        LEFT JOIN attendance
        ON students.id = attendance.student_id

        GROUP BY
            students.id,
            students.name,
            students.roll_no

        HAVING
            COUNT(attendance.id) > 0
            AND
            (
                SUM(
                    CASE
                        WHEN attendance.status = 'Present'
                        THEN 1
                        ELSE 0
                    END
                ) / COUNT(attendance.id)
            ) * 100 < 75

        ORDER BY students.roll_no
        """
    )

    low_attendance_students = cursor.fetchall()


    cursor.close()
    connection.close()


    # ==================================================
    # SEND DATA TO TEACHER DASHBOARD
    # ==================================================

    return render_template(
        "teacher_dashboard.html",

        total_students=total_students,

        present_today=present_today,

        absent_today=absent_today,

        overall_percentage=overall_percentage,

        student_attendance=student_attendance,

        low_attendance_students=low_attendance_students
    )


# =========================
# MANAGE STUDENTS
# =========================
@app.route("/manage-students")
def manage_students():

    search = request.args.get("search", "").strip()

    connection = get_db_connection()
    cursor = connection.cursor()

    if search:

        cursor.execute(
            """
            SELECT *
            FROM students
            WHERE name LIKE %s
            OR roll_no LIKE %s
            OR username LIKE %s
            ORDER BY roll_no
            """,
            (
                "%" + search + "%",
                "%" + search + "%",
                "%" + search + "%"
            )
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


# =========================
# ADD STUDENT
# =========================
@app.route("/add-student", methods=["POST"])
def add_student():

    name = request.form["name"]
    roll_no = request.form["roll_no"]
    username = request.form["username"]
    password = request.form["password"]

    connection = get_db_connection()
    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO students
            (username, password, name, roll_no)
            VALUES (%s, %s, %s, %s)
            """,
            (
                username,
                password,
                name,
                roll_no
            )
        )

        connection.commit()

    except Exception:

        connection.rollback()

        cursor.close()
        connection.close()

        return "Error: Username or Roll Number already exists!"

    cursor.close()
    connection.close()

    return redirect("/manage-students")


# =========================
# EDIT STUDENT
# =========================
@app.route("/edit-student/<int:student_id>", methods=["GET", "POST"])
def edit_student(student_id):

    connection = get_db_connection()
    cursor = connection.cursor()

    # UPDATE STUDENT
    if request.method == "POST":

        name = request.form["name"]
        roll_no = request.form["roll_no"]
        username = request.form["username"]
        password = request.form["password"]

        try:

            cursor.execute(
                """
                UPDATE students
                SET
                    name = %s,
                    roll_no = %s,
                    username = %s,
                    password = %s
                WHERE id = %s
                """,
                (
                    name,
                    roll_no,
                    username,
                    password,
                    student_id
                )
            )

            connection.commit()

        except Exception:

            connection.rollback()

            cursor.close()
            connection.close()

            return "Error: Username or Roll Number already exists!"

        cursor.close()
        connection.close()

        return redirect("/manage-students")


    # GET STUDENT
    cursor.execute(
        """
        SELECT *
        FROM students
        WHERE id = %s
        """,
        (student_id,)
    )

    student = cursor.fetchone()

    cursor.close()
    connection.close()

    if not student:

        return "Student not found!"

    return render_template(
        "edit_student.html",
        student=student
    )


# =========================
# DELETE STUDENT
# =========================
@app.route("/delete-student/<int:student_id>")
def delete_student(student_id):

    connection = get_db_connection()
    cursor = connection.cursor()

    try:

        # Delete attendance first
        cursor.execute(
            """
            DELETE FROM attendance
            WHERE student_id = %s
            """,
            (student_id,)
        )

        # Delete student
        cursor.execute(
            """
            DELETE FROM students
            WHERE id = %s
            """,
            (student_id,)
        )

        connection.commit()

    except Exception:

        connection.rollback()

        cursor.close()
        connection.close()

        return "Unable to delete student!"

    cursor.close()
    connection.close()

    return redirect("/manage-students")


# ==================================================
# MARK ATTENDANCE
# ==================================================
@app.route("/mark-attendance", methods=["GET", "POST"])
def mark_attendance():

    connection = get_db_connection()
    cursor = connection.cursor()


    # ==================================================
    # SAVE ATTENDANCE
    # ==================================================

    if request.method == "POST":

        attendance_date = request.form.get("attendance_date")


        # If date is empty, use today's date
        if not attendance_date:

            attendance_date = date.today().strftime("%Y-%m-%d")


        # Process each student's attendance
        for field in request.form:

            if field.startswith("status_"):

                student_id = field.replace("status_", "")

                status = request.form[field]


                # Ignore empty status
                if not status:

                    continue


                # Check whether attendance already exists
                cursor.execute(
                    """
                    SELECT id
                    FROM attendance
                    WHERE student_id = %s
                    AND date = %s
                    """,
                    (
                        student_id,
                        attendance_date
                    )
                )

                existing_record = cursor.fetchone()


                if existing_record:

                    # UPDATE existing attendance
                    cursor.execute(
                        """
                        UPDATE attendance
                        SET status = %s
                        WHERE id = %s
                        """,
                        (
                            status,
                            existing_record[0]
                        )
                    )

                else:

                    # INSERT new attendance
                    cursor.execute(
                        """
                        INSERT INTO attendance
                        (student_id, date, status)
                        VALUES (%s, %s, %s)
                        """,
                        (
                            student_id,
                            attendance_date,
                            status
                        )
                    )


        connection.commit()

        cursor.close()
        connection.close()


        return redirect(
            "/mark-attendance?date=" + attendance_date
        )


    # ==================================================
    # GET SELECTED DATE
    # ==================================================

    selected_date = request.args.get("date")


    # If no date selected, use today's date
    if not selected_date:

        selected_date = date.today().strftime("%Y-%m-%d")


    # ==================================================
    # GET STUDENTS WITH SELECTED DATE ATTENDANCE
    # ==================================================

    cursor.execute(
        """
        SELECT
            students.id,
            students.username,
            students.password,
            students.name,
            students.roll_no,
            attendance.status

        FROM students

        LEFT JOIN attendance

        ON students.id = attendance.student_id

        AND attendance.date = %s

        ORDER BY students.roll_no
        """,
        (selected_date,)
    )

    students = cursor.fetchall()

    cursor.close()
    connection.close()


    return render_template(
        "mark_attendance.html",
        students=students,
        selected_date=selected_date
    )


# ==================================================
# ATTENDANCE REPORT - DATE FILTER
# ==================================================
@app.route("/attendance-report")
def attendance_report():

    selected_date = request.args.get("date", "").strip()

    connection = get_db_connection()
    cursor = connection.cursor()


    # ==================================================
    # SHOW ATTENDANCE FOR SELECTED DATE
    # ==================================================

    if selected_date:

        cursor.execute(
            """
            SELECT
                students.roll_no,
                students.name,
                attendance.date,
                attendance.status

            FROM attendance

            INNER JOIN students

            ON attendance.student_id = students.id

            WHERE attendance.date = %s

            ORDER BY students.roll_no
            """,
            (selected_date,)
        )


    # ==================================================
    # SHOW ALL ATTENDANCE
    # ==================================================

    else:

        cursor.execute(
            """
            SELECT
                students.roll_no,
                students.name,
                attendance.date,
                attendance.status

            FROM attendance

            INNER JOIN students

            ON attendance.student_id = students.id

            ORDER BY
                attendance.date DESC,
                students.roll_no
            """
        )


    attendance = cursor.fetchall()


    # ==================================================
    # SUMMARY FOR SELECTED DATE
    # ==================================================

    if selected_date:

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE date = %s
            AND status = 'Present'
            """,
            (selected_date,)
        )

        present_count = cursor.fetchone()[0]


        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE date = %s
            AND status = 'Absent'
            """,
            (selected_date,)
        )

        absent_count = cursor.fetchone()[0]

    else:

        present_count = 0

        absent_count = 0


    cursor.close()
    connection.close()


    return render_template(
        "attendance_report.html",

        attendance=attendance,

        selected_date=selected_date,

        present_count=present_count,

        absent_count=absent_count
    )


# =========================
# STUDENT LOGIN
# =========================
@app.route("/student-login", methods=["GET", "POST"])
def student_login():

    if request.method == "POST":

        username = request.form["username"]

        password = request.form["password"]


        connection = get_db_connection()

        cursor = connection.cursor()


        cursor.execute(
            """
            SELECT *
            FROM students
            WHERE username = %s
            AND password = %s
            """,
            (
                username,
                password
            )
        )


        student = cursor.fetchone()


        if not student:

            cursor.close()

            connection.close()

            return "Invalid username or password!"


        student_id = student[0]


        # ==================================================
        # ATTENDANCE HISTORY
        # ==================================================

        cursor.execute(
            """
            SELECT date, status
            FROM attendance
            WHERE student_id = %s
            ORDER BY date DESC
            """,
            (student_id,)
        )

        attendance = cursor.fetchall()


        # ==================================================
        # TOTAL CLASSES
        # ==================================================

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE student_id = %s
            """,
            (student_id,)
        )

        total_classes = cursor.fetchone()[0]


        # ==================================================
        # PRESENT
        # ==================================================

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE student_id = %s
            AND status = 'Present'
            """,
            (student_id,)
        )

        present = cursor.fetchone()[0]


        # ==================================================
        # ABSENT
        # ==================================================

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE student_id = %s
            AND status = 'Absent'
            """,
            (student_id,)
        )

        absent = cursor.fetchone()[0]


        # ==================================================
        # ATTENDANCE PERCENTAGE
        # ==================================================

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


    return render_template("student_login.html")


# =========================
# RUN FLASK APPLICATION
# =========================
if __name__ == "__main__":

    app.run(debug=True)