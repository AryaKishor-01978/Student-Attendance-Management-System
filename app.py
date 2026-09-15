from flask import (
    Flask,
    render_template,
    request,
    redirect,
    flash,
    jsonify,
    session,
    url_for
)

from database import get_db_connection

from datetime import date, datetime, timedelta

import os
import uuid
import secrets
import base64
from io import BytesIO

import qrcode

from werkzeug.utils import secure_filename


# =========================================================
# FLASK APP
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)

app.secret_key = "attendance-system-secret-key"


# =========================================================
# FACE IMAGE UPLOAD SETTINGS
# =========================================================

UPLOAD_FOLDER = os.path.join(
    BASE_DIR,
    "static",
    "uploads",
    "faces"
)

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
# QR SETTINGS
# =========================================================

QR_EXPIRY_MINUTES = 2


# =========================================================
# HELPER - ALLOWED IMAGE
# =========================================================

def allowed_file(filename):

    return (
        "." in filename
        and
        filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
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

        connection = get_db_connection()
        cursor = connection.cursor()

        try:

            cursor.execute(
                """
                SELECT *
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
            connection.close()

        if teacher:

            # Save teacher login in session
            session.clear()

            session["teacher_id"] = teacher[0]

            session["teacher_username"] = username

            return redirect(
                "/teacher-dashboard"
            )

        flash(
            "Invalid teacher username or password."
        )

    return render_template(
        "teacher_login.html"
    )


# =========================================================
# TEACHER DASHBOARD
# =========================================================

@app.route("/teacher-dashboard")
def teacher_dashboard():

    if "teacher_id" not in session:

        flash(
            "Please login as teacher first."
        )

        return redirect(
            "/teacher-login"
        )

    connection = get_db_connection()
    cursor = connection.cursor()

    # Default values
    total_students = 0
    present_today = 0
    absent_today = 0
    overall_percentage = 0

    student_summary = []
    low_attendance_students = []

    try:

        # =================================================
        # TOTAL STUDENTS
        # =================================================

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM students
            """
        )

        total_students = cursor.fetchone()[0]


        # =================================================
        # TODAY'S ATTENDANCE
        # =================================================

        today = date.today()


        # Today's Present

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE date = %s
            AND status = 'Present'
            """,
            (today,)
        )

        present_today = cursor.fetchone()[0]


        # Today's Absent

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE date = %s
            AND status = 'Absent'
            """,
            (today,)
        )

        absent_today = cursor.fetchone()[0]


        # =================================================
        # OVERALL ATTENDANCE PERCENTAGE
        # =================================================

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(
                    SUM(
                        CASE
                            WHEN status = 'Present'
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS present
            FROM attendance
            """
        )

        overall_data = cursor.fetchone()

        total_attendance = (
            overall_data[0]
            or 0
        )

        total_present = (
            overall_data[1]
            or 0
        )


        if total_attendance > 0:

            overall_percentage = round(
                (
                    total_present
                    /
                    total_attendance
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
                            WHEN a.status = 'Present'
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS present_classes,

                COALESCE(
                    SUM(
                        CASE
                            WHEN a.status = 'Absent'
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

            ORDER BY
                s.roll_no
            """
        )

        student_attendance = cursor.fetchall()


        # =================================================
        # CREATE STUDENT SUMMARY
        # =================================================

        for student in student_attendance:

            student_id = student[0]

            student_name = student[1]

            roll_no = student[2]

            face_image = student[3]

            total_classes = (
                student[4]
                or 0
            )

            present_classes = (
                student[5]
                or 0
            )

            absent_classes = (
                student[6]
                or 0
            )


            # ---------------------------------------------
            # ATTENDANCE PERCENTAGE
            # ---------------------------------------------

            if total_classes > 0:

                percentage = round(
                    (
                        present_classes
                        /
                        total_classes
                    ) * 100,
                    2
                )

            else:

                percentage = 0


            # ---------------------------------------------
            # COMPLETE STUDENT RECORD
            # ---------------------------------------------

            student_data = (
                student_id,
                student_name,
                roll_no,
                face_image,
                total_classes,
                present_classes,
                absent_classes,
                percentage
            )


            # Add to Student-wise Summary

            student_summary.append(
                student_data
            )


            # ---------------------------------------------
            # BELOW 75%
            # ---------------------------------------------

            if percentage < 75:

                low_attendance_students.append(
                    student_data
                )


    except Exception as e:

        print(
            "Teacher dashboard error:",
            e
        )

        flash(
            "Unable to load teacher dashboard. Please check the terminal."
        )


    finally:

        cursor.close()
        connection.close()


    # =================================================
    # SEND DATA TO TEMPLATE
    # =================================================

    return render_template(
        "teacher_dashboard.html",

        total_students=total_students,

        present_today=present_today,

        absent_today=absent_today,

        overall_percentage=overall_percentage,

        student_attendance=student_attendance,

        student_summary=student_summary,

        low_attendance_students=
            low_attendance_students
    )


# =========================================================
# QR ATTENDANCE - GENERATE QR
# =========================================================

@app.route(
    "/generate-qr",
    methods=["GET", "POST"]
)
def generate_qr():

    # -----------------------------------------------------
    # Teacher authentication
    # -----------------------------------------------------

    if "teacher_id" not in session:

        flash(
            "Please login as teacher first."
        )

        return redirect(
            "/teacher-login"
        )


    teacher_id = session["teacher_id"]


    # -----------------------------------------------------
    # Attendance date
    # -----------------------------------------------------

    attendance_date = request.form.get(
        "attendance_date"
    )

    if not attendance_date:

        attendance_date = date.today().isoformat()


    # -----------------------------------------------------
    # Generate secure temporary token
    # -----------------------------------------------------

    session_token = secrets.token_urlsafe(
        32
    )


    created_at = datetime.now()

    expires_at = (
        created_at
        +
        timedelta(
            minutes=QR_EXPIRY_MINUTES
        )
    )


    connection = get_db_connection()
    cursor = connection.cursor()

    try:

        # -------------------------------------------------
        # Deactivate previous QR sessions
        # -------------------------------------------------

        cursor.execute(
            """
            UPDATE attendance_qr_sessions
            SET is_active=FALSE
            WHERE teacher_id=%s
            AND attendance_date=%s
            AND is_active=TRUE
            """,
            (
                teacher_id,
                attendance_date
            )
        )


        # -------------------------------------------------
        # Insert new QR session
        # -------------------------------------------------

        cursor.execute(
            """
            INSERT INTO attendance_qr_sessions
            (
                teacher_id,
                attendance_date,
                session_token,
                created_at,
                expires_at,
                is_active
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                TRUE
            )
            """,
            (
                teacher_id,
                attendance_date,
                session_token,
                created_at,
                expires_at
            )
        )

        connection.commit()


        # -------------------------------------------------
        # QR URL
        # -------------------------------------------------

        qr_url = (
            request.host_url.rstrip("/")
            +
            url_for(
                "qr_attendance",
                token=session_token
            )
        )


        # -------------------------------------------------
        # Create QR image
        # -------------------------------------------------

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4
        )

        qr.add_data(qr_url)

        qr.make(
            fit=True
        )

        qr_image = qr.make_image(
            fill_color="black",
            back_color="white"
        )


        # -------------------------------------------------
        # Convert QR image to Base64
        # -------------------------------------------------

        image_buffer = BytesIO()

        qr_image.save(
            image_buffer,
            format="PNG"
        )

        image_buffer.seek(0)

        qr_base64 = base64.b64encode(
            image_buffer.getvalue()
        ).decode(
            "utf-8"
        )


    except Exception as e:

        connection.rollback()

        print(
            "QR generation error:",
            e
        )

        flash(
            "Error generating QR code."
        )

        return redirect(
            "/teacher-dashboard"
        )

    finally:

        cursor.close()
        connection.close()


    return render_template(
        "teacher_qr.html",

        qr_image=qr_base64,

        qr_url=qr_url,

        attendance_date=attendance_date,

        expires_at=expires_at.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        expiry_minutes=
            QR_EXPIRY_MINUTES
    )


# =========================================================
# QR ATTENDANCE - STUDENT SCANS QR
# =========================================================

@app.route(
    "/qr-attendance/<token>"
)
def qr_attendance(token):

    # -----------------------------------------------------
    # Student must be logged in
    # -----------------------------------------------------

    if "student_id" not in session:

        flash(
            "Please login as student before scanning the QR."
        )

        return redirect(
            "/student-login"
        )


    student_id = session["student_id"]


    connection = get_db_connection()
    cursor = connection.cursor()

    try:

        # -------------------------------------------------
        # Find active QR
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                id,
                teacher_id,
                attendance_date,
                expires_at,
                is_active

            FROM attendance_qr_sessions

            WHERE session_token=%s

            LIMIT 1
            """,
            (token,)
        )

        qr_session = cursor.fetchone()


        # -------------------------------------------------
        # Invalid QR
        # -------------------------------------------------

        if not qr_session:

            flash(
                "Invalid QR code."
            )

            return redirect(
                f"/student-dashboard/{student_id}"
            )


        qr_session_id = qr_session[0]

        attendance_date = qr_session[2]

        expires_at = qr_session[3]

        is_active = qr_session[4]


        # -------------------------------------------------
        # Check active status
        # -------------------------------------------------

        if not is_active:

            flash(
                "This QR code is no longer active."
            )

            return redirect(
                f"/student-dashboard/{student_id}"
            )


        # -------------------------------------------------
        # Check expiry
        # -------------------------------------------------

        if datetime.now() > expires_at:

            cursor.execute(
                """
                UPDATE attendance_qr_sessions
                SET is_active=FALSE
                WHERE id=%s
                """,
                (qr_session_id,)
            )

            connection.commit()

            flash(
                "This QR code has expired."
            )

            return redirect(
                f"/student-dashboard/{student_id}"
            )


        # -------------------------------------------------
        # Check whether attendance already exists
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT id, status
            FROM attendance
            WHERE student_id=%s
            AND date=%s
            LIMIT 1
            """,
            (
                student_id,
                attendance_date
            )
        )

        existing_attendance = cursor.fetchone()


        # -------------------------------------------------
        # Existing attendance
        # -------------------------------------------------

        if existing_attendance:

            attendance_id = (
                existing_attendance[0]
            )

            cursor.execute(
                """
                UPDATE attendance
                SET status='Present'
                WHERE id=%s
                """,
                (attendance_id,)
            )

            connection.commit()

            flash(
                "Attendance already existed. "
                "Status has been updated to Present."
            )

        else:

            # -------------------------------------------------
            # Insert attendance
            # -------------------------------------------------

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
                    'Present'
                )
                """,
                (
                    student_id,
                    attendance_date
                )
            )

            connection.commit()

            flash(
                "Attendance marked Present successfully!"
            )


    except Exception as e:

        connection.rollback()

        print(
            "QR attendance error:",
            e
        )

        flash(
            "Unable to mark attendance."
        )

    finally:

        cursor.close()
        connection.close()


    return redirect(
        f"/student-dashboard/{student_id}"
    )


# =========================================================
# QR SESSION STATUS
# =========================================================

@app.route(
    "/qr-status/<token>"
)
def qr_status(token):

    connection = get_db_connection()
    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            SELECT
                expires_at,
                is_active

            FROM attendance_qr_sessions

            WHERE session_token=%s

            LIMIT 1
            """,
            (token,)
        )

        qr_session = cursor.fetchone()


        if not qr_session:

            return jsonify(
                {
                    "valid": False,
                    "message":
                        "QR session not found."
                }
            )


        expires_at = qr_session[0]

        is_active = qr_session[1]


        if (
            not is_active
            or datetime.now() > expires_at
        ):

            return jsonify(
                {
                    "valid": False,
                    "message":
                        "QR code expired."
                }
            )


        remaining_seconds = int(
            (
                expires_at
                -
                datetime.now()
            ).total_seconds()
        )


        return jsonify(
            {
                "valid": True,
                "remaining_seconds":
                    max(
                        remaining_seconds,
                        0
                    )
            }
        )

    finally:

        cursor.close()
        connection.close()


# =========================================================
# MANAGE STUDENTS
# =========================================================

@app.route(
    "/manage-students"
)
def manage_students():

    if "teacher_id" not in session:

        flash(
            "Please login as teacher first."
        )

        return redirect(
            "/teacher-login"
        )

    search = request.args.get(
        "search",
        ""
    ).strip()

    connection = get_db_connection()
    cursor = connection.cursor()

    try:

        if search:

            search_value = (
                f"%{search}%"
            )

            cursor.execute(
                """
                SELECT
                    id,
                    username,
                    password,
                    name,
                    roll_no,
                    face_image,
                    phone_number
                FROM students

                WHERE name LIKE %s
                OR roll_no LIKE %s
                OR username LIKE %s

                ORDER BY roll_no
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
                    username,
                    password,
                    name,
                    roll_no,
                    face_image,
                    phone_number
                FROM students

                ORDER BY roll_no
                """
            )

        students = cursor.fetchall()

    except Exception as e:

        print(
            "Manage students error:",
            e
        )

        flash(
            "Unable to load students. Please check the terminal."
        )

        students = []

    finally:

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

@app.route(
    "/add-student",
    methods=["GET", "POST"]
)
def add_student():

    if "teacher_id" not in session:

        flash(
            "Please login as teacher first."
        )

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


        if (
            not name
            or not roll_no
            or not username
            or not password
        ):

            flash(
                "All fields are required."
            )

            return redirect(
                "/add-student"
            )


        connection = get_db_connection()
        cursor = connection.cursor()

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

            existing_student = (
                cursor.fetchone()
            )


            if existing_student:

                flash(
                    "Username or Roll Number already exists."
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
                    roll_no
                )
                VALUES
                (
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
                    roll_no
                )
            )

            connection.commit()

            flash(
                "Student added successfully!"
            )


        except Exception as e:

            connection.rollback()

            print(
                "Add student error:",
                e
            )

            flash(
                "Error adding student."
            )

        finally:

            cursor.close()
            connection.close()


        return redirect(
            "/manage-students"
        )


    return render_template(
        "add_student.html"
    )


# =========================================================
# STUDENT SELF REGISTRATION
# WITH FACE PHOTO
# =========================================================

@app.route(
    "/student-register",
    methods=["GET", "POST"]
)
def student_register():

    if request.method == "POST":

        # -------------------------------------------------
        # Get form data
        # -------------------------------------------------

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

        confirm_password = request.form.get(
            "confirm_password",
            ""
        ).strip()


        # -------------------------------------------------
        # Get face image
        # -------------------------------------------------

        face_image = request.files.get(
            "face_image"
        )


        # -------------------------------------------------
        # Empty fields
        # -------------------------------------------------

        if (
            not name
            or not roll_no
            or not username
            or not password
            or not confirm_password
        ):

            flash(
                "Please fill all fields."
            )

            return redirect(
                "/student-register"
            )


        # -------------------------------------------------
        # Password check
        # -------------------------------------------------

        if password != confirm_password:

            flash(
                "Passwords do not match."
            )

            return redirect(
                "/student-register"
            )


        # -------------------------------------------------
        # Minimum password length
        # -------------------------------------------------

        if len(password) < 4:

            flash(
                "Password must contain at least 4 characters."
            )

            return redirect(
                "/student-register"
            )


        # -------------------------------------------------
        # Face image check
        # -------------------------------------------------

        if (
            not face_image
            or face_image.filename == ""
        ):

            flash(
                "Please upload a face photo."
            )

            return redirect(
                "/student-register"
            )


        # -------------------------------------------------
        # Image extension
        # -------------------------------------------------

        if not allowed_file(
            face_image.filename
        ):

            flash(
                "Only JPG, JPEG and PNG images are allowed."
            )

            return redirect(
                "/student-register"
            )


        connection = get_db_connection()
        cursor = connection.cursor()

        image_path = None

        try:

            # -------------------------------------------------
            # Check username
            # -------------------------------------------------

            cursor.execute(
                """
                SELECT id
                FROM students
                WHERE username=%s
                """,
                (username,)
            )

            existing_username = (
                cursor.fetchone()
            )


            if existing_username:

                flash(
                    "Username already exists. "
                    "Please choose another username."
                )

                return redirect(
                    "/student-register"
                )


            # -------------------------------------------------
            # Check roll number
            # -------------------------------------------------

            cursor.execute(
                """
                SELECT id
                FROM students
                WHERE roll_no=%s
                """,
                (roll_no,)
            )

            existing_roll = (
                cursor.fetchone()
            )


            if existing_roll:

                flash(
                    "Roll Number already exists. "
                    "Please use another roll number."
                )

                return redirect(
                    "/student-register"
                )


            # -------------------------------------------------
            # Save face image
            # -------------------------------------------------

            original_filename = secure_filename(
                face_image.filename
            )

            file_extension = (
                original_filename
                .rsplit(
                    ".",
                    1
                )[1]
                .lower()
            )


            unique_filename = (
                str(uuid.uuid4())
                +
                "."
                +
                file_extension
            )


            image_full_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                unique_filename
            )


            face_image.save(
                image_full_path
            )


            image_path = (
                "uploads/faces/"
                +
                unique_filename
            )


            # -------------------------------------------------
            # Insert student
            # -------------------------------------------------

            cursor.execute(
                """
                INSERT INTO students
                (
                    username,
                    password,
                    name,
                    roll_no,
                    face_image
                )
                VALUES
                (
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
                    image_path
                )
            )


            connection.commit()


            flash(
                "Registration successful! "
                "You can now login."
            )


        except Exception as e:

            connection.rollback()


            # -------------------------------------------------
            # Remove image if database fails
            # -------------------------------------------------

            if image_path:

                full_saved_path = os.path.join(
                    BASE_DIR,
                    "static",
                    image_path
                )


                if os.path.exists(
                    full_saved_path
                ):

                    os.remove(
                        full_saved_path
                    )


            print(
                "Student registration error:",
                e
            )


            flash(
                "Error during student registration."
            )


        finally:

            cursor.close()
            connection.close()


        return redirect(
            "/student-login"
        )


    return render_template(
        "student_register.html"
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

        flash(
            "Please login as teacher first."
        )

        return redirect(
            "/teacher-login"
        )


    connection = get_db_connection()
    cursor = connection.cursor()


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


        if (
            not name
            or not roll_no
            or not username
        ):

            flash(
                "Name, Roll Number and Username are required."
            )

            cursor.close()
            connection.close()

            return redirect(
                f"/edit-student/{student_id}"
            )


        try:

            if password:

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

                cursor.execute(
                    """
                    UPDATE students
                    SET
                        name=%s,
                        roll_no=%s,
                        username=%s
                    WHERE id=%s
                    """,
                    (
                        name,
                        roll_no,
                        username,
                        student_id
                    )
                )


            connection.commit()


            flash(
                "Student updated successfully!"
            )


        except Exception as e:

            connection.rollback()

            print(
                "Edit student error:",
                e
            )

            flash(
                "Error updating student."
            )


        finally:

            cursor.close()
            connection.close()


        return redirect(
            "/manage-students"
        )


    cursor.execute(
        """
        SELECT *
        FROM students
        WHERE id=%s
        """,
        (student_id,)
    )


    student = cursor.fetchone()


    cursor.close()
    connection.close()


    if not student:

        flash(
            "Student not found."
        )

        return redirect(
            "/manage-students"
        )


    return render_template(
        "edit_student.html",
        student=student
    )


# =========================================================
# DELETE STUDENT
# =========================================================

@app.route(
    "/delete-student/<int:student_id>"
)
def delete_student(student_id):

    if "teacher_id" not in session:

        flash(
            "Please login as teacher first."
        )

        return redirect(
            "/teacher-login"
        )


    connection = get_db_connection()
    cursor = connection.cursor()

    face_image = None


    try:

        # -------------------------------------------------
        # Get face image
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT face_image
            FROM students
            WHERE id=%s
            """,
            (student_id,)
        )

        student = cursor.fetchone()


        if student:

            face_image = student[0]


        # -------------------------------------------------
        # Delete attendance
        # -------------------------------------------------

        cursor.execute(
            """
            DELETE FROM attendance
            WHERE student_id=%s
            """,
            (student_id,)
        )


        # -------------------------------------------------
        # Delete student
        # -------------------------------------------------

        cursor.execute(
            """
            DELETE FROM students
            WHERE id=%s
            """,
            (student_id,)
        )


        connection.commit()


        # -------------------------------------------------
        # Delete image
        # -------------------------------------------------

        if face_image:

            image_file = os.path.join(
                BASE_DIR,
                "static",
                face_image
            )


            if os.path.exists(
                image_file
            ):

                os.remove(
                    image_file
                )


        flash(
            "Student deleted successfully!"
        )


    except Exception as e:

        connection.rollback()

        print(
            "Delete student error:",
            e
        )

        flash(
            "Error deleting student."
        )


    finally:

        cursor.close()
        connection.close()


    return redirect(
        "/manage-students"
    )


# =========================================================
# MARK ATTENDANCE - MANUAL
# =========================================================

@app.route(
    "/mark-attendance",
    methods=["GET", "POST"]
)
def mark_attendance():

    if "teacher_id" not in session:

        flash(
            "Please login as teacher first."
        )

        return redirect(
            "/teacher-login"
        )

    connection = get_db_connection()
    cursor = connection.cursor()

    # =========================================================
    # POST - SAVE ATTENDANCE
    # =========================================================

    if request.method == "POST":

        attendance_date = request.form.get(
            "attendance_date"
        )

        # Check attendance date
        if not attendance_date:

            cursor.close()
            connection.close()

            flash(
                "Please select an attendance date before saving."
            )

            return redirect(
                "/mark-attendance"
            )

        inserted_count = 0
        updated_count = 0

        try:

            # Get all students
            cursor.execute(
                """
                SELECT id
                FROM students
                ORDER BY roll_no
                """
            )

            students = cursor.fetchall()

            # Process attendance
            for student in students:

                student_id = student[0]

                status = request.form.get(
                    f"status_{student_id}"
                )

                if not status:
                    continue

                # Check if attendance already exists
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

                existing = cursor.fetchone()

                # =================================================
                # UPDATE EXISTING ATTENDANCE
                # =================================================

                if existing:

                    cursor.execute(
                        """
                        UPDATE attendance
                        SET status = %s
                        WHERE student_id = %s
                        AND date = %s
                        """,
                        (
                            status,
                            student_id,
                            attendance_date
                        )
                    )

                    updated_count += 1

                # =================================================
                # INSERT NEW ATTENDANCE
                # =================================================

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

            connection.commit()

            flash(
                f"Attendance updated successfully! "
                f"Inserted: {inserted_count}, "
                f"Updated: {updated_count}"
            )

        except Exception as e:

            connection.rollback()

            print(
                "Attendance error:",
                e
            )

            flash(
                "Error saving attendance."
            )

        finally:

            cursor.close()
            connection.close()

        # Keep the selected date after saving
        return redirect(
            f"/mark-attendance?date={attendance_date}"
        )

    # =========================================================
    # GET - SHOW STUDENTS FOR SELECTED DATE
    # =========================================================

    selected_date = request.args.get(
        "date",
        ""
    ).strip()

    # If no date selected, use today's date
    if not selected_date:

        selected_date = date.today().isoformat()

    try:

        cursor.execute(
            """
            SELECT
                students.id,
                students.username,
                students.password,
                students.name,
                students.roll_no,
                students.face_image,
                attendance.status
            FROM students

            LEFT JOIN attendance
                ON students.id = attendance.student_id
                AND attendance.date = %s

            ORDER BY students.roll_no
            """,
            (
                selected_date,
            )
        )

        students = cursor.fetchall()

    except Exception as e:

        print(
            "Mark attendance error:",
            e
        )

        students = []

        flash(
            "Unable to load students."
        )

    finally:

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

    if "teacher_id" not in session:
        flash("Please login as teacher first.")
        return redirect("/teacher-login")

    selected_date = request.args.get("date", "").strip()

    connection = get_db_connection()
    cursor = connection.cursor()

    attendance_records = []
    present_count = 0
    absent_count = 0

    try:

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
                ORDER BY a.date DESC, s.roll_no
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
                    s.face_image,
                    a.date,
                    a.status
                FROM attendance a
                JOIN students s
                    ON a.student_id = s.id
                ORDER BY a.date DESC, s.roll_no
                """
            )

        attendance_records = cursor.fetchall()

        # =========================
        # CALCULATE SUMMARY
        # =========================

        if selected_date:

            for record in attendance_records:

                if record[5] == "Present":
                    present_count += 1

                elif record[5] == "Absent":
                    absent_count += 1

    except Exception as e:

        print("Attendance report error:", e)

        flash(
            "Unable to load attendance report. Please check the terminal."
        )

        attendance_records = []
        present_count = 0
        absent_count = 0

    finally:

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

@app.route(
    "/student-login",
    methods=["GET", "POST"]
)
def student_login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        ).strip()


        connection = get_db_connection()
        cursor = connection.cursor()


        try:

            cursor.execute(
                """
                SELECT id
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
            connection.close()


        if student:

            session.clear()

            session["student_id"] = (
                student[0]
            )

            session["student_username"] = (
                username
            )


            return redirect(
                f"/student-dashboard/{student[0]}"
            )


        flash(
            "Invalid student username or password."
        )


    return render_template(
        "student_login.html"
    )



# =========================================================
# STUDENT DASHBOARD
# =========================================================

@app.route(
    "/student-dashboard/<int:student_id>"
)
def student_dashboard(student_id):

    # -----------------------------------------------------
    # Student session protection
    # -----------------------------------------------------

    if "student_id" not in session:

        flash(
            "Please login as student first."
        )

        return redirect(
            "/student-login"
        )


    # -----------------------------------------------------
    # Prevent one student opening another student's page
    # -----------------------------------------------------

    if session["student_id"] != student_id:

        flash(
            "Unauthorized access."
        )

        return redirect(
            f"/student-dashboard/{session['student_id']}"
        )


    connection = get_db_connection()
    cursor = connection.cursor()


    try:

        # -------------------------------------------------
        # Student details
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
            (student_id,)
        )

        student = cursor.fetchone()


        if not student:

            flash(
                "Student not found."
            )

            return redirect(
                "/student-login"
            )


        # -------------------------------------------------
        # Attendance summary
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total,

                SUM(
                    CASE
                        WHEN status='Present'
                        THEN 1
                        ELSE 0
                    END
                ) AS present,

                SUM(
                    CASE
                        WHEN status='Absent'
                        THEN 1
                        ELSE 0
                    END
                ) AS absent

            FROM attendance

            WHERE student_id=%s
            """,
            (student_id,)
        )

        attendance_data = cursor.fetchone()


        # -------------------------------------------------
        # Attendance history
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
            (student_id,)
        )

        attendance_history = cursor.fetchall()


    finally:

        cursor.close()
        connection.close()


    # -----------------------------------------------------
    # Attendance calculations
    # -----------------------------------------------------

    total_classes = (
        attendance_data[0]
        or 0
    )

    present_classes = (
        attendance_data[1]
        or 0
    )

    absent_classes = (
        attendance_data[2]
        or 0
    )


    attendance_percentage = 0


    if total_classes > 0:

        attendance_percentage = round(
            (
                present_classes
                /
                total_classes
            ) * 100,
            2
        )


    # -----------------------------------------------------
    # Student dashboard
    # -----------------------------------------------------

    return render_template(
        "student_dashboard.html",

        student=student,

        total_classes=total_classes,

        present_classes=present_classes,

        absent_classes=absent_classes,

        attendance_percentage=attendance_percentage,

        attendance_history=attendance_history
    )



# =========================================================
# STUDENT QR SCAN PAGE
# =========================================================

@app.route(
    "/student-qr-scan"
)
def student_qr_scan():

    # -----------------------------------------------------
    # Student authentication
    # -----------------------------------------------------

    if "student_id" not in session:

        flash(
            "Please login as student first."
        )

        return redirect(
            "/student-login"
        )


    # -----------------------------------------------------
    # Open QR scanner page
    # -----------------------------------------------------

    return render_template(
        "student_qr_scan.html"
    )


# =========================================================
# STUDENT LOGOUT
# =========================================================

@app.route(
    "/student-logout"
)
def student_logout():

    session.clear()

    flash(
        "Student logged out successfully."
    )

    return redirect(
        "/student-login"
    )


# =========================================================
# TEACHER LOGOUT
# =========================================================

@app.route(
    "/teacher-logout"
)
def teacher_logout():

    session.clear()

    flash(
        "Teacher logged out successfully."
    )

    return redirect(
        "/teacher-login"
    )


# =========================================================
# CHATBOT
# =========================================================

@app.route(
    "/chatbot",
    methods=["POST"]
)
def chatbot():

    data = request.get_json(
        silent=True
    ) or {}


    message = data.get(
        "message",
        ""
    ).lower().strip()


    response = (
        "Sorry, I did not understand that. "
        "You can ask about student registration, "
        "login, attendance, reports or low attendance."
    )


    if any(
        word in message
        for word in [
            "hello",
            "hi",
            "hey"
        ]
    ):

        response = (
            "Hello! How can I help you with "
            "the Student Attendance Management System?"
        )


    elif (
        "register" in message
        or
        "registration" in message
    ):

        response = (
            "For student registration, open Student Registration "
            "and enter your name, roll number, username, password "
            "and upload your face photo."
        )


    elif (
        "login" in message
        or
        "sign in" in message
    ):

        response = (
            "Students can login using their registered username "
            "and password. Teachers can use the Teacher Login page."
        )


    elif (
        "qr" in message
        or
        "scan" in message
    ):

        response = (
            "For QR attendance, the teacher generates a temporary "
            "QR code. A logged-in student scans it and attendance "
            "is automatically marked Present."
        )


    elif (
        "attendance" in message
        and
        (
            "mark" in message
            or
            "take" in message
        )
    ):

        response = (
            "Teachers can open Mark Attendance, select the date, "
            "mark students Present or Absent, and save the attendance."
        )


    elif (
        "report" in message
        or
        "reports" in message
    ):

        response = (
            "Teachers can open Attendance Report and filter "
            "attendance by date or view all records."
        )


    elif (
        "low attendance" in message
        or
        "75" in message
    ):

        response = (
            "The Teacher Dashboard shows students whose attendance "
            "is below 75%."
        )


    return jsonify(
    {
        "reply": response
    }
)


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        ssl_context=(
            os.path.join(BASE_DIR, "cert", "cert.pem"),
            os.path.join(BASE_DIR, "cert", "key.pem")
        )
    )