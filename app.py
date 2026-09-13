from flask import (
    Flask,
    render_template,
    request,
    redirect,
    flash,
    jsonify,
    session
)

from database import get_db_connection

from datetime import date

import os
import uuid
import requests

from dotenv import load_dotenv

from werkzeug.utils import secure_filename


# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

load_dotenv()


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

app.secret_key = "attendance-system-secret-key"


# =========================================================
# MESSAGE CENTRAL SETTINGS
# =========================================================

MESSAGE_CENTRAL_BASE_URL = "https://cpaas.messagecentral.com"

MESSAGE_CENTRAL_CUSTOMER_ID = os.getenv(
    "MESSAGE_CENTRAL_CUSTOMER_ID"
)

MESSAGE_CENTRAL_AUTH_TOKEN = os.getenv(
    "MESSAGE_CENTRAL_AUTH_TOKEN"
)


# =========================================================
# FACE IMAGE UPLOAD SETTINGS
# =========================================================

UPLOAD_FOLDER = "static/uploads/faces"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png"
}

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(
            ".",
            1
        )[1].lower()
        in ALLOWED_EXTENSIONS
    )


def normalize_phone(phone):

    phone = str(phone or "").strip()

    if phone.startswith("+91"):
        phone = phone[3:]

    if phone.startswith("91") and len(phone) == 12:
        phone = phone[2:]

    return phone


def delete_face_image(image_path):

    if not image_path:
        return

    try:

        full_path = os.path.join(
            "static",
            image_path
        )

        if os.path.exists(full_path):
            os.remove(full_path)

    except Exception as e:

        print(
            "Could not delete face image:",
            e
        )


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# =========================================================
# TEACHER LOGIN
# =========================================================

@app.route(
    "/teacher-login",
    methods=["GET", "POST"]
)
def teacher_login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        ).strip()

        if not username or not password:

            flash(
                "Username and password are required.",
                "warning"
            )

            return redirect(
                "/teacher-login"
            )

        conn = get_db_connection()

        cursor = conn.cursor()

        try:

            cursor.execute(
                """
                SELECT
                    id,
                    username,
                    password
                FROM teachers
                WHERE username=%s
                AND password=%s
                """,
                (
                    username,
                    password
                )
            )

            teacher = cursor.fetchone()

        finally:

            cursor.close()
            conn.close()

        if teacher:

            session["teacher_id"] = teacher[0]

            session["teacher_username"] = teacher[1]

            flash(
                "Teacher login successful!",
                "success"
            )

            return redirect(
                "/teacher-dashboard"
            )

        flash(
            "Invalid username or password.",
            "danger"
        )

        return redirect(
            "/teacher-login"
        )

    return render_template(
        "teacher_login.html"
    )


# =========================================================
# TEACHER LOGOUT
# =========================================================

@app.route("/teacher-logout")
def teacher_logout():

    session.pop(
        "teacher_id",
        None
    )

    session.pop(
        "teacher_username",
        None
    )

    flash(
        "Teacher logged out successfully.",
        "success"
    )

    return redirect("/")


# =========================================================
# TEACHER DASHBOARD
# =========================================================

@app.route("/teacher-dashboard")
def teacher_dashboard():

    if "teacher_id" not in session:

        flash(
            "Please login as teacher first.",
            "warning"
        )

        return redirect(
            "/teacher-login"
        )

    conn = get_db_connection()

    cursor = conn.cursor()

    try:

        # -------------------------------------------------
        # TOTAL STUDENTS
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM students
            """
        )

        total_students = cursor.fetchone()[0]


        # -------------------------------------------------
        # PRESENT TODAY
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE date=%s
            AND status='Present'
            """,
            (
                date.today(),
            )
        )

        present_today = cursor.fetchone()[0]


        # -------------------------------------------------
        # ABSENT TODAY
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE date=%s
            AND status='Absent'
            """,
            (
                date.today(),
            )
        )

        absent_today = cursor.fetchone()[0]


        # -------------------------------------------------
        # TOTAL ATTENDANCE RECORDS
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            """
        )

        total_attendance = cursor.fetchone()[0]


        # -------------------------------------------------
        # TOTAL PRESENT RECORDS
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE status='Present'
            """
        )

        total_present = cursor.fetchone()[0]


        # -------------------------------------------------
        # OVERALL ATTENDANCE PERCENTAGE
        # -------------------------------------------------

        if total_attendance > 0:

            overall_percentage = round(
                (
                    total_present
                    / total_attendance
                ) * 100,
                2
            )

        else:

            overall_percentage = 0


        # =================================================
        # STUDENT-WISE ATTENDANCE
        # =================================================

        cursor.execute(
            """
            SELECT
                s.id,
                s.name,
                s.roll_no,
                s.face_image,

                COUNT(a.id) AS total_classes,

                COALESCE(
                    SUM(
                        CASE
                            WHEN a.status='Present'
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS present_classes,

                COALESCE(
                    SUM(
                        CASE
                            WHEN a.status='Absent'
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS absent_classes

            FROM students s

            LEFT JOIN attendance a
                ON s.id = a.student_id

            GROUP BY
                s.id,
                s.name,
                s.roll_no,
                s.face_image

            ORDER BY s.name
            """
        )

        student_rows = cursor.fetchall()


        student_summary = []

        low_attendance = []


        # -------------------------------------------------
        # CREATE STUDENT SUMMARY
        # -------------------------------------------------

        for row in student_rows:

            student_id = row[0]

            student_name = row[1]

            roll_no = row[2]

            face_image = row[3]

            total_classes = row[4] or 0

            present_classes = row[5] or 0

            absent_classes = row[6] or 0


            # -------------------------------------------------
            # CALCULATE PERCENTAGE
            # -------------------------------------------------

            if total_classes > 0:

                percentage = round(
                    (
                        present_classes
                        / total_classes
                    ) * 100,
                    2
                )

            else:

                percentage = 0


            # -------------------------------------------------
            # SUMMARY TUPLE
            #
            # 0 = student id
            # 1 = student name
            # 2 = roll number
            # 3 = face image
            # 4 = total classes
            # 5 = present classes
            # 6 = absent classes
            # 7 = percentage
            # -------------------------------------------------

            summary = (
                student_id,
                student_name,
                roll_no,
                face_image,
                total_classes,
                present_classes,
                absent_classes,
                percentage
            )


            student_summary.append(
                summary
            )


            # -------------------------------------------------
            # LOW ATTENDANCE STUDENTS
            # -------------------------------------------------

            if (
                total_classes > 0
                and percentage < 75
            ):

                low_attendance.append(
                    summary
                )


    except Exception as e:

        print(
            "Teacher dashboard error:",
            e
        )

        flash(
            f"Error loading teacher dashboard: {e}",
            "danger"
        )

        student_summary = []

        low_attendance = []

        total_students = 0

        present_today = 0

        absent_today = 0

        total_attendance = 0

        total_present = 0

        overall_percentage = 0


    finally:

        cursor.close()

        conn.close()


    return render_template(
        "teacher_dashboard.html",

        total_students=total_students,

        present_today=present_today,

        absent_today=absent_today,

        total_attendance=total_attendance,

        total_present=total_present,

        overall_percentage=overall_percentage,

        student_summary=student_summary,

        low_attendance=low_attendance
    )


# =========================================================
# MANAGE STUDENTS
# =========================================================

@app.route(
    "/manage-students",
    methods=["GET"]
)
def manage_students():

    if "teacher_id" not in session:

        return redirect(
            "/teacher-login"
        )

    search = request.args.get(
        "search",
        ""
    ).strip()

    conn = get_db_connection()

    cursor = conn.cursor()

    try:

        if search:

            search_value = f"%{search}%"

            cursor.execute(
                """
                SELECT
                    id,
                    name,
                    roll_no,
                    username,
                    phone_number,
                    face_image
                FROM students
                WHERE name LIKE %s
                   OR roll_no LIKE %s
                   OR username LIKE %s
                ORDER BY name
                """,
                (
                    search_value,
                    search_value,
                    search_value
                )
            )

        else:

            cursor.execute(
                """
                SELECT
                    id,
                    name,
                    roll_no,
                    username,
                    phone_number,
                    face_image
                FROM students
                ORDER BY name
                """
            )

        students = cursor.fetchall()

    finally:

        cursor.close()

        conn.close()


    return render_template(
        "manage_students.html",
        students=students,
        search=search
    )


# =========================================================
# ADD STUDENT
# =========================================================

@app.route(
    "/add-student",
    methods=["GET", "POST"]
)
def add_student():

    if "teacher_id" not in session:

        return redirect(
            "/teacher-login"
        )


    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        roll_no = request.form.get(
            "roll_no",
            ""
        ).strip()

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        ).strip()

        phone_number = normalize_phone(
            request.form.get(
                "phone_number",
                ""
            )
        )


        if (
            not name
            or not roll_no
            or not username
            or not password
        ):

            flash(
                "All required fields must be filled.",
                "warning"
            )

            return redirect(
                "/add-student"
            )


        face_image = request.files.get(
            "face_image"
        )

        saved_path = None


        if face_image and face_image.filename:

            if not allowed_file(
                face_image.filename
            ):

                flash(
                    "Only JPG, JPEG and PNG images are allowed.",
                    "warning"
                )

                return redirect(
                    "/add-student"
                )


            extension = secure_filename(
                face_image.filename
            ).rsplit(
                ".",
                1
            )[1].lower()


            filename = (
                str(uuid.uuid4())
                + "."
                + extension
            )


            file_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )


            face_image.save(
                file_path
            )


            saved_path = (
                "uploads/faces/"
                + filename
            )


        conn = get_db_connection()

        cursor = conn.cursor()


        try:

            cursor.execute(
                """
                SELECT id
                FROM students
                WHERE username=%s
                   OR roll_no=%s
                """,
                (
                    username,
                    roll_no
                )
            )

            existing = cursor.fetchone()


            if existing:

                if saved_path:

                    delete_face_image(
                        saved_path
                    )

                flash(
                    "Username or Roll No already exists.",
                    "warning"
                )

                return redirect(
                    "/add-student"
                )


            cursor.execute(
                """
                INSERT INTO students
                (
                    username,
                    password,
                    name,
                    roll_no,
                    phone_number,
                    face_image
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    username,
                    password,
                    name,
                    roll_no,
                    phone_number or None,
                    saved_path
                )
            )


            conn.commit()


            flash(
                "Student added successfully!",
                "success"
            )


            return redirect(
                "/manage-students"
            )


        except Exception as e:

            conn.rollback()


            if saved_path:

                delete_face_image(
                    saved_path
                )


            flash(
                f"Error adding student: {e}",
                "danger"
            )


            return redirect(
                "/add-student"
            )


        finally:

            cursor.close()

            conn.close()


    return render_template(
        "add_student.html"
    )


# =========================================================
# EDIT STUDENT
# =========================================================

@app.route(
    "/edit-student/<int:student_id>",
    methods=["GET", "POST"]
)
def edit_student(student_id):

    if "teacher_id" not in session:

        return redirect(
            "/teacher-login"
        )


    conn = get_db_connection()

    cursor = conn.cursor()


    try:

        if request.method == "POST":

            name = request.form.get(
                "name",
                ""
            ).strip()

            roll_no = request.form.get(
                "roll_no",
                ""
            ).strip()

            username = request.form.get(
                "username",
                ""
            ).strip()

            password = request.form.get(
                "password",
                ""
            ).strip()

            phone_number = normalize_phone(
                request.form.get(
                    "phone_number",
                    ""
                )
            )


            if (
                not name
                or not roll_no
                or not username
            ):

                flash(
                    "Name, Roll No and Username are required.",
                    "warning"
                )

                return redirect(
                    f"/edit-student/{student_id}"
                )


            # -------------------------------------------------
            # CHECK DUPLICATES
            # -------------------------------------------------

            cursor.execute(
                """
                SELECT id
                FROM students
                WHERE
                    (username=%s OR roll_no=%s)
                    AND id!=%s
                """,
                (
                    username,
                    roll_no,
                    student_id
                )
            )

            duplicate = cursor.fetchone()


            if duplicate:

                flash(
                    "Username or Roll No already exists.",
                    "warning"
                )

                return redirect(
                    f"/edit-student/{student_id}"
                )


            # -------------------------------------------------
            # CURRENT PHOTO
            # -------------------------------------------------

            cursor.execute(
                """
                SELECT face_image
                FROM students
                WHERE id=%s
                """,
                (
                    student_id,
                )
            )

            current_student = cursor.fetchone()


            if not current_student:

                flash(
                    "Student not found.",
                    "danger"
                )

                return redirect(
                    "/manage-students"
                )


            old_face_image = current_student[0]


            # -------------------------------------------------
            # NEW PHOTO
            # -------------------------------------------------

            face_image = request.files.get(
                "face_image"
            )

            new_face_path = None


            if face_image and face_image.filename:

                if not allowed_file(
                    face_image.filename
                ):

                    flash(
                        "Only JPG, JPEG and PNG images are allowed.",
                        "warning"
                    )

                    return redirect(
                        f"/edit-student/{student_id}"
                    )


                extension = secure_filename(
                    face_image.filename
                ).rsplit(
                    ".",
                    1
                )[1].lower()


                filename = (
                    str(uuid.uuid4())
                    + "."
                    + extension
                )


                file_path = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )


                face_image.save(
                    file_path
                )


                new_face_path = (
                    "uploads/faces/"
                    + filename
                )


            # -------------------------------------------------
            # UPDATE STUDENT
            # -------------------------------------------------

            if password:

                if new_face_path:

                    cursor.execute(
                        """
                        UPDATE students
                        SET
                            name=%s,
                            roll_no=%s,
                            username=%s,
                            password=%s,
                            phone_number=%s,
                            face_image=%s
                        WHERE id=%s
                        """,
                        (
                            name,
                            roll_no,
                            username,
                            password,
                            phone_number or None,
                            new_face_path,
                            student_id
                        )
                    )

                else:

                    cursor.execute(
                        """
                        UPDATE students
                        SET
                            name=%s,
                            roll_no=%s,
                            username=%s,
                            password=%s
                        WHERE id=%s
                        """,
                        (
                            name,
                            roll_no,
                            username,
                            password,
                            student_id
                        )
                    )

            else:

                if new_face_path:

                    cursor.execute(
                        """
                        UPDATE students
                        SET
                            name=%s,
                            roll_no=%s,
                            username=%s,
                            phone_number=%s,
                            face_image=%s
                        WHERE id=%s
                        """,
                        (
                            name,
                            roll_no,
                            username,
                            phone_number or None,
                            new_face_path,
                            student_id
                        )
                    )

                else:

                    cursor.execute(
                        """
                        UPDATE students
                        SET
                            name=%s,
                            roll_no=%s,
                            username=%s,
                            phone_number=%s
                        WHERE id=%s
                        """,
                        (
                            name,
                            roll_no,
                            username,
                            phone_number or None,
                            student_id
                        )
                    )


            conn.commit()


            # -------------------------------------------------
            # DELETE OLD PHOTO
            # -------------------------------------------------

            if new_face_path and old_face_image:

                delete_face_image(
                    old_face_image
                )


            flash(
                "Student updated successfully!",
                "success"
            )


            return redirect(
                "/manage-students"
            )


        # -----------------------------------------------------
        # GET STUDENT
        # -----------------------------------------------------

        cursor.execute(
            """
            SELECT
                id,
                name,
                roll_no,
                username,
                password,
                phone_number,
                face_image
            FROM students
            WHERE id=%s
            """,
            (
                student_id,
            )
        )

        student = cursor.fetchone()


        if not student:

            flash(
                "Student not found.",
                "danger"
            )

            return redirect(
                "/manage-students"
            )


    finally:

        cursor.close()

        conn.close()


    return render_template(
        "edit_student.html",
        student=student
    )


# =========================================================
# DELETE STUDENT
# =========================================================

@app.route(
    "/delete-student/<int:student_id>",
    methods=["POST", "GET"]
)
def delete_student(student_id):

    if "teacher_id" not in session:

        return redirect(
            "/teacher-login"
        )


    conn = get_db_connection()

    cursor = conn.cursor()


    try:

        cursor.execute(
            """
            SELECT face_image
            FROM students
            WHERE id=%s
            """,
            (
                student_id,
            )
        )

        student = cursor.fetchone()


        if not student:

            flash(
                "Student not found.",
                "warning"
            )

            return redirect(
                "/manage-students"
            )


        face_image = student[0]


        # -------------------------------------------------
        # DELETE ATTENDANCE
        # -------------------------------------------------

        cursor.execute(
            """
            DELETE FROM attendance
            WHERE student_id=%s
            """,
            (
                student_id,
            )
        )


        # -------------------------------------------------
        # DELETE STUDENT
        # -------------------------------------------------

        cursor.execute(
            """
            DELETE FROM students
            WHERE id=%s
            """,
            (
                student_id,
            )
        )


        conn.commit()


        if face_image:

            delete_face_image(
                face_image
            )


        flash(
            "Student deleted successfully!",
            "success"
        )


    except Exception as e:

        conn.rollback()


        flash(
            f"Error deleting student: {e}",
            "danger"
        )


    finally:

        cursor.close()

        conn.close()


    return redirect(
        "/manage-students"
    )


# =========================================================
# MARK ATTENDANCE
# =========================================================

@app.route(
    "/mark-attendance",
    methods=["GET", "POST"]
)
def mark_attendance():

    if "teacher_id" not in session:

        flash(
            "Please login as teacher first.",
            "warning"
        )

        return redirect(
            "/teacher-login"
        )


    # =====================================================
    # POST - SAVE ATTENDANCE
    # =====================================================

    if request.method == "POST":

        attendance_date = request.form.get(
            "attendance_date",
            ""
        ).strip()


        if not attendance_date:

            flash(
                "Please select an attendance date before saving.",
                "warning"
            )

            return redirect(
                "/mark-attendance"
            )


        conn = get_db_connection()

        cursor = conn.cursor()


        try:

            # -------------------------------------------------
            # GET ALL STUDENTS
            # -------------------------------------------------

            cursor.execute(
                """
                SELECT id
                FROM students
                ORDER BY id
                """
            )

            students = cursor.fetchall()


            inserted_count = 0

            updated_count = 0


            # -------------------------------------------------
            # SAVE ATTENDANCE
            # -------------------------------------------------

            for student in students:

                student_id = student[0]

                status = request.form.get(
                    f"status_{student_id}",
                    ""
                ).strip()


                if not status:

                    continue


                if status not in (
                    "Present",
                    "Absent"
                ):

                    continue


                # -------------------------------------------------
                # CHECK EXISTING RECORD
                # -------------------------------------------------

                cursor.execute(
                    """
                    SELECT id
                    FROM attendance
                    WHERE student_id=%s
                    AND date=%s
                    """,
                    (
                        student_id,
                        attendance_date
                    )
                )

                existing = cursor.fetchone()


                # -------------------------------------------------
                # UPDATE
                # -------------------------------------------------

                if existing:

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
                            attendance_date
                        )
                    )

                    updated_count += 1


                # -------------------------------------------------
                # INSERT
                # -------------------------------------------------

                else:

                    cursor.execute(
                        """
                        INSERT INTO attendance
                        (
                            student_id,
                            date,
                            status
                        )
                        VALUES
                        (
                            %s,
                            %s,
                            %s
                        )
                        """,
                        (
                            student_id,
                            attendance_date,
                            status
                        )
                    )

                    inserted_count += 1


            conn.commit()


            flash(
                f"Attendance saved successfully! "
                f"Inserted: {inserted_count}, "
                f"Updated: {updated_count}.",
                "success"
            )


        except Exception as e:

            conn.rollback()


            flash(
                f"Error marking attendance: {e}",
                "danger"
            )


        finally:

            cursor.close()

            conn.close()


        return redirect(
            f"/mark-attendance?date={attendance_date}"
        )


    # =====================================================
    # GET - SHOW STUDENTS
    # =====================================================

    selected_date = request.args.get(
        "date",
        ""
    ).strip()


    if not selected_date:

        selected_date = date.today().isoformat()


    conn = get_db_connection()

    cursor = conn.cursor()


    try:

        cursor.execute(
            """
            SELECT
                s.id,
                s.username,
                s.password,
                s.name,
                s.roll_no,
                s.face_image,
                a.status
            FROM students s
            LEFT JOIN attendance a
                ON s.id=a.student_id
                AND a.date=%s
            ORDER BY s.name
            """,
            (
                selected_date,
            )
        )

        students = cursor.fetchall()


    finally:

        cursor.close()

        conn.close()


    return render_template(
        "mark_attendance.html",
        students=students,
        selected_date=selected_date
    )


# =========================================================
# ATTENDANCE REPORT
# =========================================================

@app.route(
    "/attendance-report",
    methods=["GET"]
)
def attendance_report():

    if "teacher_id" not in session:

        flash(
            "Please login as teacher first.",
            "warning"
        )

        return redirect(
            "/teacher-login"
        )


    selected_date = request.args.get(
        "date",
        ""
    ).strip()


    conn = get_db_connection()

    cursor = conn.cursor()


    try:

        # =====================================================
        # SELECTED DATE
        # =====================================================

        if selected_date:

            cursor.execute(
                """
                SELECT
                    a.id,
                    s.name,
                    s.roll_no,
                    s.face_image,
                    a.date,
                    a.status
                FROM attendance a
                JOIN students s
                    ON a.student_id = s.id
                WHERE a.date = %s
                ORDER BY s.name
                """,
                (
                    selected_date,
                )
            )

            attendance_records = cursor.fetchall()


            # -------------------------------------------------
            # PRESENT COUNT
            # -------------------------------------------------

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM attendance
                WHERE date = %s
                AND status = 'Present'
                """,
                (
                    selected_date,
                )
            )

            present_count = cursor.fetchone()[0]


            # -------------------------------------------------
            # ABSENT COUNT
            # -------------------------------------------------

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM attendance
                WHERE date = %s
                AND status = 'Absent'
                """,
                (
                    selected_date,
                )
            )

            absent_count = cursor.fetchone()[0]


        # =====================================================
        # SHOW ALL RECORDS
        # =====================================================

        else:

            cursor.execute(
                """
                SELECT
                    a.id,
                    s.name,
                    s.roll_no,
                    s.face_image,
                    a.date,
                    a.status
                FROM attendance a
                JOIN students s
                    ON a.student_id = s.id
                ORDER BY
                    a.date DESC,
                    s.name
                """
            )

            attendance_records = cursor.fetchall()


            # -------------------------------------------------
            # TOTAL PRESENT
            # -------------------------------------------------

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM attendance
                WHERE status = 'Present'
                """
            )

            present_count = cursor.fetchone()[0]


            # -------------------------------------------------
            # TOTAL ABSENT
            # -------------------------------------------------

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM attendance
                WHERE status = 'Absent'
                """
            )

            absent_count = cursor.fetchone()[0]


    except Exception as e:

        flash(
            f"Error loading attendance report: {e}",
            "danger"
        )

        attendance_records = []

        present_count = 0

        absent_count = 0


    finally:

        cursor.close()

        conn.close()


    return render_template(
        "attendance_report.html",
        attendance_records=attendance_records,
        selected_date=selected_date,
        present_count=present_count,
        absent_count=absent_count
    )


# =========================================================
# STUDENT LOGOUT
# =========================================================

@app.route("/student-logout")
def student_logout():

    session.pop(
        "student_id",
        None
    )

    session.pop(
        "student_username",
        None
    )

    flash(
        "Student logged out successfully.",
        "success"
    )

    return redirect("/")


# =========================================================
# STUDENT LOGIN
# =========================================================

@app.route(
    "/student-login",
    methods=["GET", "POST"]
)
def student_login():

    # -----------------------------------------------------
    # SHOW STUDENT LOGIN PAGE
    # -----------------------------------------------------

    if request.method == "GET":

        return render_template(
            "student_login.html"
        )


    # -----------------------------------------------------
    # GET LOGIN DETAILS
    # -----------------------------------------------------

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    ).strip()


    # -----------------------------------------------------
    # VALIDATE LOGIN DETAILS
    # -----------------------------------------------------

    if not username or not password:

        flash(
            "Username and password are required.",
            "warning"
        )

        return redirect(
            "/student-login"
        )


    # -----------------------------------------------------
    # DATABASE CONNECTION
    # -----------------------------------------------------

    conn = get_db_connection()

    cursor = conn.cursor()


    try:

        cursor.execute(
            """
            SELECT
                id,
                username,
                password
            FROM students
            WHERE username=%s
            AND password=%s
            """,
            (
                username,
                password
            )
        )

        student = cursor.fetchone()


    finally:

        cursor.close()

        conn.close()


    # -----------------------------------------------------
    # LOGIN SUCCESS
    # -----------------------------------------------------

    if student:

        session["student_id"] = student[0]

        session["student_username"] = student[1]

        flash(
            "Student login successful!",
            "success"
        )

        return redirect(
            "/student-dashboard"
        )


    # -----------------------------------------------------
    # LOGIN FAILED
    # -----------------------------------------------------

    flash(
        "Invalid username or password.",
        "danger"
    )

    return redirect(
        "/student-login"
    )


# =========================================================
# STUDENT DASHBOARD
# =========================================================

@app.route("/student-dashboard")
def student_dashboard():

    if "student_id" not in session:

        flash(
            "Please login as student first.",
            "warning"
        )

        return redirect(
            "/student-login"
        )


    student_id = session["student_id"]


    conn = get_db_connection()

    cursor = conn.cursor()


    try:

        # -------------------------------------------------
        # STUDENT DETAILS
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                id,
                name,
                roll_no,
                username,
                face_image
            FROM students
            WHERE id=%s
            """,
            (
                student_id,
            )
        )

        student = cursor.fetchone()


        if not student:

            session.pop(
                "student_id",
                None
            )

            flash(
                "Student account not found.",
                "danger"
            )

            return redirect(
                "/student-login"
            )


        # -------------------------------------------------
        # ATTENDANCE HISTORY
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                date,
                status
            FROM attendance
            WHERE student_id=%s
            ORDER BY date DESC
            """,
            (
                student_id,
            )
        )

        attendance_history = cursor.fetchall()


        # -------------------------------------------------
        # TOTAL CLASSES
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE student_id=%s
            """,
            (
                student_id,
            )
        )

        total_classes = cursor.fetchone()[0]


        # -------------------------------------------------
        # PRESENT CLASSES
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE student_id=%s
            AND status='Present'
            """,
            (
                student_id,
            )
        )

        present_classes = cursor.fetchone()[0]


        # -------------------------------------------------
        # ABSENT CLASSES
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE student_id=%s
            AND status='Absent'
            """,
            (
                student_id,
            )
        )

        absent_classes = cursor.fetchone()[0]


        # -------------------------------------------------
        # ATTENDANCE PERCENTAGE
        # -------------------------------------------------

        if total_classes > 0:

            attendance_percentage = round(
                (
                    present_classes
                    / total_classes
                ) * 100,
                2
            )

        else:

            attendance_percentage = 0


    finally:

        cursor.close()

        conn.close()


    return render_template(
        "student_dashboard.html",
        student=student,
        attendance_history=attendance_history,
        total_classes=total_classes,
        present_classes=present_classes,
        absent_classes=absent_classes,
        attendance_percentage=attendance_percentage
    )


# =========================================================
# SEND OTP
# =========================================================

@app.route(
    "/send-otp",
    methods=["POST"]
)
def send_otp():

    try:

        data = request.get_json(
            silent=True
        )


        if data is None:

            data = request.form.to_dict()


        print(
            "Received data:",
            data
        )


        phone_number = (
            data.get("phone_number")
            or data.get("mobile_number")
            or ""
        ).strip()


        phone_number = normalize_phone(
            phone_number
        )


        if not phone_number:

            return jsonify(
                {
                    "success": False,
                    "message": "Mobile number is required."
                }
            ), 400


        if (
            not phone_number.isdigit()
            or len(phone_number) != 10
        ):

            return jsonify(
                {
                    "success": False,
                    "message":
                        "Please enter a valid 10-digit mobile number."
                }
            ), 400


        if not MESSAGE_CENTRAL_CUSTOMER_ID:

            return jsonify(
                {
                    "success": False,
                    "message":
                        "Message Central Customer ID is not configured."
                }
            ), 500


        if not MESSAGE_CENTRAL_AUTH_TOKEN:

            return jsonify(
                {
                    "success": False,
                    "message":
                        "Message Central Auth Token is not configured."
                }
            ), 500


        # -------------------------------------------------
        # SEND OTP
        # -------------------------------------------------

        url = (
            MESSAGE_CENTRAL_BASE_URL
            + "/verification/v3/send"
        )


        headers = {
            "authToken":
                MESSAGE_CENTRAL_AUTH_TOKEN
        }


        params = {

            "customerId":
                MESSAGE_CENTRAL_CUSTOMER_ID,

            "countryCode":
                "91",

            "flowType":
                "SMS",

            "mobileNumber":
                phone_number,

            "otpLength":
                "6"
        }


        response = requests.post(
            url,
            headers=headers,
            params=params,
            timeout=30
        )


        print(
            "Send OTP status:",
            response.status_code
        )

        print(
            "Send OTP response:",
            response.text
        )


        if response.status_code != 200:

            return jsonify(
                {
                    "success": False,
                    "message":
                        "Unable to send OTP. "
                        "Please check Message Central credentials."
                }
            ), response.status_code


        try:

            result = response.json()

        except Exception:

            result = {}


        # -------------------------------------------------
        # GET VERIFICATION ID
        # -------------------------------------------------

        verification_id = (
            result.get("verificationId")
            or result.get("data", {}).get(
                "verificationId"
            )
        )


        if not verification_id:

            return jsonify(
                {
                    "success": False,
                    "message":
                        "OTP sent response did not contain verification ID."
                }
            ), 500


        session["verification_id"] = (
            verification_id
        )

        session["otp_phone"] = (
            phone_number
        )

        session["otp_verified"] = False


        return jsonify(
            {
                "success": True,
                "message":
                    "OTP sent successfully.",
                "verificationId":
                    verification_id
            }
        )


    except Exception as e:

        print(
            "Send OTP error:",
            e
        )


        return jsonify(
            {
                "success": False,
                "message":
                    "An unexpected error occurred while sending OTP."
            }
        ), 500


# =========================================================
# VERIFY OTP
# =========================================================

@app.route(
    "/verify-otp",
    methods=["POST"]
)
def verify_otp():

    try:

        data = request.get_json(
            silent=True
        )


        if data is None:

            data = request.form.to_dict()


        phone_number = (
            data.get("phone_number")
            or data.get("mobile_number")
            or session.get("otp_phone")
            or ""
        ).strip()


        phone_number = normalize_phone(
            phone_number
        )


        otp = (
            data.get("otp")
            or data.get("code")
            or ""
        ).strip()


        verification_id = (
            data.get("verificationId")
            or data.get("verification_id")
            or session.get("verification_id")
            or ""
        )


        if not phone_number:

            return jsonify(
                {
                    "success": False,
                    "message":
                        "Mobile number is required."
                }
            ), 400


        if not otp:

            return jsonify(
                {
                    "success": False,
                    "message":
                        "OTP is required."
                }
            ), 400


        if (
            not otp.isdigit()
            or len(otp) != 6
        ):

            return jsonify(
                {
                    "success": False,
                    "message":
                        "Please enter a valid 6-digit OTP."
                }
            ), 400


        if not verification_id:

            return jsonify(
                {
                    "success": False,
                    "message":
                        "Verification ID is missing. Please send OTP again."
                }
            ), 400


        if not MESSAGE_CENTRAL_AUTH_TOKEN:

            return jsonify(
                {
                    "success": False,
                    "message":
                        "Message Central Auth Token is not configured."
                }
            ), 500


        # -------------------------------------------------
        # VALIDATE OTP
        # -------------------------------------------------

        url = (
            MESSAGE_CENTRAL_BASE_URL
            + "/verification/v3/validateOtp"
        )


        headers = {

            "authToken":
                MESSAGE_CENTRAL_AUTH_TOKEN
        }


        params = {

            "verificationId":
                verification_id,

            "code":
                otp,

            "flowType":
                "SMS"
        }


        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=30
        )


        print(
            "Message Central Verify OTP status:",
            response.status_code
        )

        print(
            "Message Central Verify OTP response:",
            response.text
        )


        if response.status_code == 200:

            session["otp_verified"] = True

            session["verified_phone"] = (
                phone_number
            )


            return jsonify(
                {
                    "success": True,
                    "message":
                        "OTP verified successfully."
                }
            )


        if response.status_code == 401:

            return jsonify(
                {
                    "success": False,
                    "message":
                        "Message Central rejected the Auth Token. "
                        "Please check your API credentials."
                }
            ), 401


        return jsonify(
            {
                "success": False,
                "message":
                    "Incorrect or expired OTP."
            }
        ), response.status_code


    except Exception as e:

        print(
            "Verify OTP error:",
            e
        )


        return jsonify(
            {
                "success": False,
                "message":
                    "An unexpected error occurred while verifying OTP."
            }
        ), 500


# =========================================================
# STUDENT REGISTRATION
# =========================================================

@app.route(
    "/student-register",
    methods=["GET", "POST"]
)
def student_register():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        roll_no = request.form.get(
            "roll_no",
            ""
        ).strip()

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        ).strip()

        phone_number = normalize_phone(
            request.form.get(
                "phone_number",
                ""
            )
        )


        # -------------------------------------------------
        # BASIC VALIDATION
        # -------------------------------------------------

        if (
            not name
            or not roll_no
            or not username
            or not password
            or not phone_number
        ):

            flash(
                "Please fill all required fields.",
                "warning"
            )

            return redirect(
                "/student-register"
            )


        # -------------------------------------------------
        # PHONE VALIDATION
        # -------------------------------------------------

        if (
            not phone_number.isdigit()
            or len(phone_number) != 10
        ):

            flash(
                "Please enter a valid 10-digit phone number.",
                "warning"
            )

            return redirect(
                "/student-register"
            )


        # -------------------------------------------------
        # OTP VERIFICATION
        # -------------------------------------------------

        if not session.get(
            "otp_verified"
        ):

            flash(
                "Please verify your phone number using OTP first.",
                "warning"
            )

            return redirect(
                "/student-register"
            )


        if (
            session.get("verified_phone")
            != phone_number
        ):

            flash(
                "Please verify the same phone number used for registration.",
                "warning"
            )

            return redirect(
                "/student-register"
            )


        # -------------------------------------------------
        # FACE IMAGE
        # -------------------------------------------------

        face_image = request.files.get(
            "face_image"
        )


        if not face_image or not face_image.filename:

            flash(
                "Please upload your face photo.",
                "warning"
            )

            return redirect(
                "/student-register"
            )


        if not allowed_file(
            face_image.filename
        ):

            flash(
                "Only JPG, JPEG and PNG images are allowed.",
                "warning"
            )

            return redirect(
                "/student-register"
            )


        # -------------------------------------------------
        # SAVE IMAGE
        # -------------------------------------------------

        extension = secure_filename(
            face_image.filename
        ).rsplit(
            ".",
            1
        )[1].lower()


        filename = (
            str(uuid.uuid4())
            + "."
            + extension
        )


        file_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )


        face_image.save(
            file_path
        )


        saved_path = (
            "uploads/faces/"
            + filename
        )


        conn = get_db_connection()

        cursor = conn.cursor()


        try:

            # -------------------------------------------------
            # CHECK DUPLICATES
            # -------------------------------------------------

            cursor.execute(
                """
                SELECT id
                FROM students
                WHERE
                    username=%s
                    OR roll_no=%s
                    OR phone_number=%s
                """,
                (
                    username,
                    roll_no,
                    phone_number
                )
            )


            existing = cursor.fetchone()


            if existing:

                delete_face_image(
                    saved_path
                )

                flash(
                    "Username, Roll No or phone number already exists.",
                    "warning"
                )

                return redirect(
                    "/student-register"
                )


            # -------------------------------------------------
            # INSERT STUDENT
            # -------------------------------------------------

            cursor.execute(
                """
                INSERT INTO students
                (
                    username,
                    password,
                    name,
                    roll_no,
                    phone_number,
                    face_image
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    username,
                    password,
                    name,
                    roll_no,
                    phone_number,
                    saved_path
                )
            )


            conn.commit()


            # -------------------------------------------------
            # CLEAR OTP SESSION
            # -------------------------------------------------

            session.pop(
                "verification_id",
                None
            )

            session.pop(
                "otp_phone",
                None
            )

            session.pop(
                "otp_verified",
                None
            )

            session.pop(
                "verified_phone",
                None
            )


            flash(
                "Student registration successful! You can now login.",
                "success"
            )


            return redirect(
                "/student-login"
            )


        except Exception as e:

            conn.rollback()

            delete_face_image(
                saved_path
            )

            flash(
                f"Registration error: {e}",
                "danger"
            )

            return redirect(
                "/student-register"
            )


        finally:

            cursor.close()

            conn.close()


    return render_template(
        "student_register.html"
    )


# =========================================================
# STUDENT PROFILE
# =========================================================

@app.route(
    "/student-profile/<int:student_id>",
    methods=["GET", "POST"]
)
def student_profile(student_id):

    if (
        "student_id" not in session
        or session["student_id"] != student_id
    ):

        flash(
            "Unauthorized access.",
            "danger"
        )

        return redirect(
            "/student-login"
        )


    conn = get_db_connection()

    cursor = conn.cursor()


    try:

        # -------------------------------------------------
        # POST - UPDATE PROFILE
        # -------------------------------------------------

        if request.method == "POST":

            name = request.form.get(
                "name",
                ""
            ).strip()

            roll_no = request.form.get(
                "roll_no",
                ""
            ).strip()

            username = request.form.get(
                "username",
                ""
            ).strip()

            password = request.form.get(
                "password",
                ""
            ).strip()

            phone_number = normalize_phone(
                request.form.get(
                    "phone_number",
                    ""
                )
            )


            if (
                not name
                or not roll_no
                or not username
                or not phone_number
            ):

                flash(
                    "Name, Roll No, Username and Phone Number are required.",
                    "warning"
                )

                return redirect(
                    f"/student-profile/{student_id}"
                )


            if (
                not phone_number.isdigit()
                or len(phone_number) != 10
            ):

                flash(
                    "Please enter a valid 10-digit phone number.",
                    "warning"
                )

                return redirect(
                    f"/student-profile/{student_id}"
                )


            # -------------------------------------------------
            # CHECK DUPLICATES
            # -------------------------------------------------

            cursor.execute(
                """
                SELECT id
                FROM students
                WHERE
                    (
                        username=%s
                        OR roll_no=%s
                        OR phone_number=%s
                    )
                    AND id!=%s
                """,
                (
                    username,
                    roll_no,
                    phone_number,
                    student_id
                )
            )


            duplicate = cursor.fetchone()


            if duplicate:

                flash(
                    "Username, Roll No or phone number already exists.",
                    "warning"
                )

                return redirect(
                    f"/student-profile/{student_id}"
                )


            # -------------------------------------------------
            # CURRENT PHOTO
            # -------------------------------------------------

            cursor.execute(
                """
                SELECT face_image
                FROM students
                WHERE id=%s
                """,
                (
                    student_id,
                )
            )


            current_student = cursor.fetchone()


            if not current_student:

                flash(
                    "Student not found.",
                    "danger"
                )

                return redirect(
                    "/student-dashboard"
                )


            old_face_image = current_student[0]


            # -------------------------------------------------
            # NEW PHOTO
            # -------------------------------------------------

            face_image = request.files.get(
                "face_image"
            )

            new_face_path = None


            if face_image and face_image.filename:

                if not allowed_file(
                    face_image.filename
                ):

                    flash(
                        "Only JPG, JPEG and PNG images are allowed.",
                        "warning"
                    )

                    return redirect(
                        f"/student-profile/{student_id}"
                    )


                extension = secure_filename(
                    face_image.filename
                ).rsplit(
                    ".",
                    1
                )[1].lower()


                filename = (
                    str(uuid.uuid4())
                    + "."
                    + extension
                )


                file_path = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )


                face_image.save(
                    file_path
                )


                new_face_path = (
                    "uploads/faces/"
                    + filename
                )


            # -------------------------------------------------
            # UPDATE DATABASE
            # -------------------------------------------------

            if password:

                if new_face_path:

                    cursor.execute(
                        """
                        UPDATE students
                        SET
                            name=%s,
                            roll_no=%s,
                            username=%s,
                            password=%s,
                            phone_number=%s,
                            face_image=%s
                        WHERE id=%s
                        """,
                        (
                            name,
                            roll_no,
                            username,
                            password,
                            phone_number,
                            new_face_path,
                            student_id
                        )
                    )

                else:

                    cursor.execute(
                        """
                        UPDATE students
                        SET
                            name=%s,
                            roll_no=%s,
                            username=%s,
                            password=%s,
                            phone_number=%s
                        WHERE id=%s
                        """,
                        (
                            name,
                            roll_no,
                            username,
                            password,
                            phone_number,
                            student_id
                        )
                    )

            else:

                if new_face_path:

                    cursor.execute(
                        """
                        UPDATE students
                        SET
                            name=%s,
                            roll_no=%s,
                            username=%s,
                            phone_number=%s,
                            face_image=%s
                        WHERE id=%s
                        """,
                        (
                            name,
                            roll_no,
                            username,
                            phone_number,
                            new_face_path,
                            student_id
                        )
                    )

                else:

                    cursor.execute(
                        """
                        UPDATE students
                        SET
                            name=%s,
                            roll_no=%s,
                            username=%s,
                            phone_number=%s
                        WHERE id=%s
                        """,
                        (
                            name,
                            roll_no,
                            username,
                            phone_number,
                            student_id
                        )
                    )


            conn.commit()


            # -------------------------------------------------
            # DELETE OLD PHOTO
            # -------------------------------------------------

            if new_face_path and old_face_image:

                delete_face_image(
                    old_face_image
                )


            session["student_username"] = (
                username
            )


            flash(
                "Profile updated successfully!",
                "success"
            )


            return redirect(
                "/student-dashboard"
            )


        # -------------------------------------------------
        # GET PROFILE
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                id,
                name,
                roll_no,
                username,
                password,
                phone_number,
                face_image
            FROM students
            WHERE id=%s
            """,
            (
                student_id,
            )
        )


        student = cursor.fetchone()


        if not student:

            flash(
                "Student not found.",
                "danger"
            )

            return redirect(
                "/student-dashboard"
            )


    finally:

        cursor.close()

        conn.close()


    return render_template(
        "student_profile.html",
        student=student
    )


# =========================================================
# CHATBOT PAGE
# =========================================================

@app.route("/chatbot")
def chatbot():

    return render_template(
        "chatbot.html"
    )


# =========================================================
# CHATBOT API
# =========================================================

@app.route(
    "/chatbot-api",
    methods=["POST"]
)
def chatbot_api():

    try:

        data = request.get_json(
            silent=True
        )


        if not data:

            return jsonify(
                {
                    "reply":
                        "Please enter a message."
                }
            )


        message = str(
            data.get(
                "message",
                ""
            )
        ).strip().lower()


        if not message:

            return jsonify(
                {
                    "reply":
                        "Please enter a message."
                }
            )


        # -------------------------------------------------
        # SIMPLE PROJECT CHATBOT
        # -------------------------------------------------

        if (
            "hello" in message
            or "hi" in message
            or "hey" in message
        ):

            reply = (
                "Hello! 👋 "
                "How can I help you with the "
                "Student Attendance Management System?"
            )


        elif "attendance" in message:

            reply = (
                "Attendance can be marked by the teacher "
                "from the Mark Attendance section."
            )


        elif (
            "login" in message
            and "student" in message
        ):

            reply = (
                "Students can login using their registered "
                "username and password."
            )


        elif (
            "login" in message
            and "teacher" in message
        ):

            reply = (
                "Teachers can login using their teacher "
                "username and password."
            )


        elif (
            "register" in message
            or "registration" in message
        ):

            reply = (
                "Students can register by providing their "
                "name, Roll No, username, password, phone "
                "number, OTP verification and face photo."
            )


        elif (
            "report" in message
            or "attendance report" in message
        ):

            reply = (
                "Teachers can open Attendance Report to "
                "view attendance by date or view all records."
            )


        elif "password" in message:

            reply = (
                "If you are a student, you can update your "
                "password from Edit Profile after logging in."
            )


        elif (
            "photo" in message
            or "face" in message
        ):

            reply = (
                "A student face photo can be uploaded during "
                "registration or updated from Edit Profile."
            )


        elif "thank" in message:

            reply = (
                "You're welcome! 😊"
            )


        else:

            reply = (
                "I can help with student registration, "
                "login, attendance marking, attendance "
                "reports, profile updates and other features "
                "of this system."
            )


        return jsonify(
            {
                "reply": reply
            }
        )


    except Exception as e:

        print(
            "Chatbot error:",
            e
        )


        return jsonify(
            {
                "reply":
                    "Sorry, something went wrong."
            }
        ), 500


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(404)
def page_not_found(error):

    return (
        render_template(
            "index.html"
        ),
        404
    )


@app.errorhandler(500)
def internal_server_error(error):

    return (
        "Internal Server Error. Please check the terminal for details.",
        500
    )


# =========================================================
# RUN FLASK APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )

