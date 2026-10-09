import base64
import binascii
from datetime import date, datetime
import os
import tempfile
import uuid
from collections import Counter
import base64
import uuid
import cv2
import numpy as np
import face_recognition

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.files.base import ContentFile

from .models import Register, Subject, Attendance
import cv2
import face_recognition
import numpy as np
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import base64
import binascii
import os
import tempfile
import uuid

from collections import Counter
from datetime import date, datetime

import cv2
import numpy as np
import face_recognition

from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth import update_session_auth_hash

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Count, Q

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .models import (
    Register,
    Subject,
    Attendance,
    TeacherProfile,
)
from .models import Attendance, Register, Subject


def staff_required(view):
    return user_passes_test(lambda user: user.is_active and user.is_staff, login_url="adminlogin")(view)

def staff_or_teacher_required(view):
    @login_required
    def wrapped(request, *args, **kwargs):

        # ==============================
        # ADMIN
        # ==============================

        if request.user.is_staff:
            return view(
                request,
                teacher=None,
                *args,
                **kwargs
            )

        # ==============================
        # TEACHER
        # ==============================

        try:
            teacher = request.user.teacher_profile

        except TeacherProfile.DoesNotExist:

            messages.error(
                request,
                "You are not authorized to access attendance."
            )

            return redirect("login")

        if not teacher.is_active:

            auth_logout(request)

            messages.error(
                request,
                "Your teacher account is inactive."
            )

            return redirect("login")

        return view(
            request,
            teacher=teacher,
            *args,
            **kwargs
        )

    return wrapped

def index(request):
    return render(request, "index.html")


def _decode_data_url(data_url):
    """Return the image bytes and extension from a base64 image data URL."""
    try:
        header, payload = data_url.split(";base64,", 1)
        if not header.startswith("data:image/"):
            raise ValueError
        extension = header.removeprefix("data:image/").lower()
        if extension not in {"png", "jpeg", "jpg", "webp"}:
            raise ValueError
        return base64.b64decode(payload, validate=True), extension
    except (AttributeError, ValueError, binascii.Error) as exc:
        raise ValueError("Invalid image data.") from exc


def _face_encoding(image_bytes, extension):
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}") as temp_file:
            temp_file.write(image_bytes)
            temp_path = temp_file.name
        encodings = face_recognition.face_encodings(face_recognition.load_image_file(temp_path))
        return encodings[0] if encodings else None
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def register(request):

    if request.method != "POST":
        return render(request, "register.html")

    student_name = request.POST.get("student_name", "").strip()
    roll_no = request.POST.get("roll_no", "").strip()
    semester = request.POST.get("semester", "").strip()
    branch = request.POST.get("branch", "").strip()
    password = request.POST.get("password", "")
    confirm_password = request.POST.get("confirm_password", "")
    face_image_data = request.POST.get("face_image_data", "")

    # =====================================================
    # VALIDATION
    # =====================================================

    if not all([
        student_name,
        roll_no,
        semester,
        branch,
        password,
        face_image_data
    ]):
        messages.error(
            request,
            "Please complete all required fields."
        )
        return render(request, "register.html")

    if password != confirm_password:
        messages.error(
            request,
            "Passwords do not match."
        )
        return render(request, "register.html")

    # =====================================================
    # CHECK ROLL NUMBER
    # =====================================================

    if User.objects.filter(username=roll_no).exists():
        messages.error(
            request,
            "Roll number already exists."
        )
        return render(request, "register.html")

    if Register.objects.filter(roll_no=roll_no).exists():
        messages.error(
            request,
            "Roll number already exists."
        )
        return render(request, "register.html")

    # =====================================================
    # DECODE IMAGE
    # =====================================================

    try:
        image_bytes, extension = _decode_data_url(
            face_image_data
        )

    except ValueError:
        messages.error(
            request,
            "Please capture a valid face image."
        )
        return render(request, "register.html")

    # =====================================================
    # CHECK FACE
    # =====================================================

    try:
        new_encoding = _face_encoding(
            image_bytes,
            extension
        )

    except Exception as e:

        print(
            "Face processing error:",
            repr(e)
        )

        messages.error(
            request,
            "Unable to process the face image."
        )

        return render(request, "register.html")

    if new_encoding is None:

        messages.error(
            request,
            "No face was detected. Please capture a clear face image."
        )

        return render(request, "register.html")

    # =====================================================
    # CHECK DUPLICATE FACE
    # =====================================================

    for student in Register.objects.all():

        if not student.face_image:
            continue

        try:

            existing_image = (
                face_recognition.load_image_file(
                    student.face_image.path
                )
            )

            existing_encodings = (
                face_recognition.face_encodings(
                    existing_image
                )
            )

            if not existing_encodings:
                continue

            distance = face_recognition.face_distance(
                [existing_encodings[0]],
                new_encoding
            )[0]

            print(
                f"{student.roll_no} "
                f"distance = {distance:.4f}"
            )

            if distance <= 0.50:

                messages.error(
                    request,
                    "This face is already registered."
                )

                return render(
                    request,
                    "register.html"
                )

        except Exception as e:

            print(
                f"Face check failed for "
                f"{student.roll_no}:",
                repr(e)
            )

            continue

    # =====================================================
    # CREATE USER + STUDENT
    # =====================================================

    try:

        with transaction.atomic():

            user = User.objects.create_user(
                username=roll_no,
                password=password
            )

            Register.objects.create(
                user=user,
                student_name=student_name,
                roll_no=roll_no,
                semester=semester,
                branch=branch,
                face_image=ContentFile(
                    image_bytes,
                    name=f"{uuid.uuid4()}.{extension}"
                )
            )

    except IntegrityError:

        messages.error(
            request,
            "Roll number already exists."
        )

        return render(
            request,
            "register.html"
        )

    # =====================================================
    # SUCCESS
    # =====================================================

    messages.success(
        request,
        "Registration successful. Please log in."
    )

    return redirect("login")


def login(request):

    if request.method == "POST":

        user = authenticate(
            request,
            username=request.POST.get("roll_no", "").strip(),
            password=request.POST.get("password", ""),
        )

        if user is not None:

            auth_login(request, user)

            # Admin login
            if user.is_staff:
                return redirect("adminpanel")

            # Teacher login
            try:

                teacher = user.teacher_profile

                if not teacher.is_active:

                    auth_logout(request)

                    messages.error(
                        request,
                        "Your teacher account is inactive."
                    )

                    return redirect("login")

                # First login - compulsory password change
                if teacher.must_change_password:

                    return redirect(
                        "teacherpanel"
                    )

                return redirect(
                    "teacherpanel"
                )

            except TeacherProfile.DoesNotExist:

                # Normal student
                return redirect("userpanel")

        messages.error(
            request,
            "Invalid roll number or password."
        )

    return render(
        request,
        "login.html"
    )


def adminlogin(request):
    if request.method == "POST":
        user = authenticate(request, username=request.POST.get("username", ""), password=request.POST.get("password", ""))
        if user is not None and user.is_staff:
            auth_login(request, user)
            return redirect("adminpanel")
        messages.error(request, "Invalid credentials or insufficient permissions.")
    return render(request, "adminlogin.html")

@login_required
def userprofile(request):

    profile = Register.objects.filter(
        user=request.user
    ).first()

    return render(
        request,
        "userprofile.html",
        {
            "user": request.user,
            "profile": profile,
        }
    )
@login_required
def userpanel(request):

    # Logged-in user's Register profile
    profile = Register.objects.filter(
        user=request.user
    ).first()

    # Attendance of logged-in user
    attendance_records = (
        Attendance.objects
        .filter(student=request.user)
        .select_related("subject")
        .order_by("-timestamp")
    )

    # Total attendance
    total_attended = attendance_records.count()

    context = {
        "user": request.user,
        "profile": profile,
        "attendance_records": attendance_records,
        "total_attended": total_attended,
    }

    return render(
        request,
        "userpanel.html",
        context
    )
@staff_required
def adminpanel(request):
    return render(request, "adminpanel.html")


BRANCH_SUBJECTS = {
    "IT": {
        "First": ["Computer Basics", "Maths-I", "Physics-I"],
        "Second": ["Programming Fundamentals", "Maths-II", "Digital Logic"],
        "Third": ["Data Structures", "Operating Systems", "Database Management"],
        "Fourth": ["Computer Networks", "Software Engineering", "Web Development"],
        "Fifth": ["Python", "Java", "Artificial Intelligence"],
        "Sixth": ["Machine Learning", "DNT", "Cloud Computing"],
    },

    "CSE": {
        "First": ["Maths-I", "Physics-I", "Introduction to Computers"],
        "Second": ["Maths-II", "Programming Basics", "Digital Logic"],
        "Third": ["Data Structures", "Operating Systems", "DBMS"],
        "Fourth": ["Computer Networks", "Algorithms", "Software Engg"],
        "Fifth": ["Java", "Python", "Compiler Design"],
        "Sixth": ["AI", "DNT", "Cloud Computing"],
    },

    "ECE": {
        "First": ["Maths-I", "Physics-I", "Basic Electronics"],
        "Second": ["Maths-II", "Circuit Theory", "Digital Electronics"],
        "Third": ["Signals & Systems", "Electromagnetics", "Microprocessors"],
        "Fourth": ["Communication Systems", "Analog Circuits", "Digital Communication"],
        "Fifth": ["VLSI Design", "Python", "Embedded Systems"],
        "Sixth": ["Computer Networks", "DNT", "Control Systems"],
    },

    "EE": {
        "First": ["Maths-I", "Physics-I", "Electrical Basics"],
        "Second": ["Maths-II", "Circuit Theory", "Electrical Machines-I"],
        "Third": ["Electronics", "Control Systems", "Power Systems-I"],
        "Fourth": ["Power Systems-II", "Electrical Machines-II", "Digital Systems"],
        "Fifth": ["Python", "DNT", "Renewable Energy"],
        "Sixth": ["Microgrids", "AI", "Communication Systems"],
    },

    "CE": {
        "First": ["Maths-I", "Physics-I", "Engineering Drawing"],
        "Second": ["Maths-II", "Mechanics", "Materials Science"],
        "Third": ["Surveying", "Building Materials", "Structural Analysis"],
        "Fourth": ["Design of Concrete Structures", "Fluid Mechanics", "Soil Mechanics"],
        "Fifth": ["Python", "Transportation Engineering", "DNT"],
        "Sixth": ["Environmental Engg", "Construction Management", "Computer Networks"],
    },
}


@staff_required
def manage_teachers(request):
    teachers = (
        TeacherProfile.objects
        .select_related("user")
        .prefetch_related("subjects")
        .order_by("user__first_name")
    )

    subjects = (
        Subject.objects
        .filter(is_active=True)
        .order_by("branch", "semester", "name")
    )

    branches = (
        Subject.objects
        .filter(is_active=True)
        .values_list("branch", flat=True)
        .distinct()
        .order_by("branch")
    )

    return render(
        request,
        "manage_teachers.html",
        {
            "teachers": teachers,
            "subjects": subjects,
            "branches": branches,
        }
    )

@staff_required
def add_teacher(request):
    if request.method != "POST":
        return redirect("manage_teachers")

    name = request.POST.get("name", "").strip()
    username = request.POST.get("username", "").strip()
    password = request.POST.get("password", "")
    employee_id = request.POST.get("employee_id", "").strip()
    email = request.POST.get("email", "").strip()
    phone = request.POST.get("phone", "").strip()
    branch = request.POST.get("branch", "").strip()
    subject_ids = request.POST.getlist("subjects")

    if not all([
        name,
        username,
        password,
        employee_id,
        branch
    ]):
        messages.error(
            request,
            "Name, username, password, employee ID and branch are required."
        )
        return redirect("manage_teachers")

    if User.objects.filter(username=username).exists():
        messages.error(
            request,
            "This username already exists."
        )
        return redirect("manage_teachers")

    if TeacherProfile.objects.filter(
        employee_id=employee_id
    ).exists():
        messages.error(
            request,
            "This employee ID already exists."
        )
        return redirect("manage_teachers")

    try:
        with transaction.atomic():

            user = User.objects.create_user(
                username=username,
                password=password,
                email=email,
                first_name=name
            )

            teacher = TeacherProfile.objects.create(
                user=user,
                employee_id=employee_id,
                phone=phone,
                branch=branch
            )

            valid_subjects = Subject.objects.filter(
                id__in=subject_ids,
                branch__iexact=branch,
                is_active=True
            )

            teacher.subjects.set(valid_subjects)

        messages.success(
            request,
            f"Teacher {name} added successfully."
        )

    except IntegrityError:
        messages.error(
            request,
            "Unable to create teacher."
        )

    return redirect("manage_teachers")


@staff_required
def update_teacher(request, teacher_id):
    teacher = get_object_or_404(
        TeacherProfile.objects.select_related("user"),
        id=teacher_id
    )

    if request.method != "POST":
        return redirect("manage_teachers")

    name = request.POST.get("name", "").strip()
    username = request.POST.get("username", "").strip()
    email = request.POST.get("email", "").strip()
    phone = request.POST.get("phone", "").strip()
    employee_id = request.POST.get("employee_id", "").strip()
    branch = request.POST.get("branch", "").strip()
    password = request.POST.get("password", "")
    is_active = request.POST.get("is_active") == "on"
    subject_ids = request.POST.getlist("subjects")

    if not all([
        name,
        username,
        employee_id,
        branch
    ]):
        messages.error(
            request,
            "Name, username, employee ID and branch are required."
        )
        return redirect("manage_teachers")

    if User.objects.filter(
        username=username
    ).exclude(
        id=teacher.user.id
    ).exists():
        messages.error(
            request,
            "This username is already being used."
        )
        return redirect("manage_teachers")

    if TeacherProfile.objects.filter(
        employee_id=employee_id
    ).exclude(
        id=teacher.id
    ).exists():
        messages.error(
            request,
            "This employee ID is already being used."
        )
        return redirect("manage_teachers")

    teacher.user.first_name = name
    teacher.user.username = username
    teacher.user.email = email

    if password:
        teacher.user.set_password(password)

    teacher.user.save()

    teacher.employee_id = employee_id
    teacher.phone = phone
    teacher.branch = branch
    teacher.is_active = is_active
    teacher.save()

    valid_subjects = Subject.objects.filter(
        id__in=subject_ids,
        branch__iexact=branch,
        is_active=True
    )

    teacher.subjects.set(valid_subjects)

    messages.success(
        request,
        f"{name}'s details updated successfully."
    )

    return redirect("manage_teachers")


@staff_required
def delete_teacher(request, teacher_id):
    teacher = get_object_or_404(
        TeacherProfile.objects.select_related("user"),
        id=teacher_id
    )

    if request.method == "POST":
        teacher_name = teacher.user.get_full_name() or teacher.user.username

        teacher.user.delete()

        messages.success(
            request,
            f"Teacher {teacher_name} deleted successfully."
        )

    return redirect("manage_teachers")


from django.http import HttpResponse, JsonResponse

@staff_or_teacher_required
def liveattendance(request, teacher=None):

    # =====================================================
    # TEACHER
    # =====================================================

    if teacher is not None:

        # Teacher ko admin ne jo subjects allot kiye hain
        assigned_subjects = (
            teacher.subjects
            .filter(
                is_active=True,
                branch__iexact=teacher.branch
            )
            .order_by("semester", "name")
        )

        # Teacher ke assigned subjects ke semesters
        assigned_semesters = sorted(
            set(
                assigned_subjects.values_list(
                    "semester",
                    flat=True
                )
            ),
            key=lambda x: int(x)
        )

        return render(
            request,
            "liveattendance.html",
            {
                "teacher": teacher,
                "teacher_mode": True,

                # Teacher ka branch automatic
                "teacher_branch": teacher.branch,

                # Sirf teacher ke allotted subjects
                "assigned_subjects": assigned_subjects,

                # Sirf teacher ke subjects ke semesters
                "assigned_semesters": assigned_semesters,

                # Admin ke fields teacher ko nahi chahiye
                "branches": [],
                "semester_subjects": {},
            }
        )

    # =====================================================
    # ADMIN
    # =====================================================

    return render(
        request,
        "liveattendance.html",
        {
            "teacher": None,
            "teacher_mode": False,

            "teacher_branch": "",

            "assigned_subjects": [],
            "assigned_semesters": [],

            "branches": list(BRANCH_SUBJECTS),
            "semester_subjects": BRANCH_SUBJECTS,
        }
    )

    branch = request.POST.get("branch")
    semester = request.POST.get("semester")
    subject_name = request.POST.get("subject")
    if subject_name not in BRANCH_SUBJECTS.get(branch, {}).get(semester, []):
        context["error"] = "Please select a valid branch, semester, and subject."
        return render(request, "liveattendance.html", context)
    try:
        image_bytes, _ = _decode_data_url(request.POST.get("face_image_data", ""))
        frame = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError
        encodings = face_recognition.face_encodings(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if not encodings:
            context["error"] = "No face was detected. Please capture a clear image."
            return render(request, "liveattendance.html", context)
    except Exception:
        context["error"] = "Failed to decode the captured image."
        return render(request, "liveattendance.html", context)

    captured_encoding = encodings[0]
    matched_student = None
    for student in Register.objects.filter(branch=branch, semester=semester).select_related("user"):
        if not student.user or not student.face_image:
            continue
        try:
            reference = face_recognition.face_encodings(face_recognition.load_image_file(student.face_image.path))
            if reference and face_recognition.compare_faces([reference[0]], captured_encoding, tolerance=0.45)[0]:
                matched_student = student
                break
        except Exception:
            continue
    if not matched_student:
        context["error"] = "No matching face was found."
        return render(request, "liveattendance.html", context)

    subject, _ = Subject.objects.get_or_create(name=subject_name)
    if Attendance.objects.filter(student=matched_student.user, subject=subject, timestamp__date=timezone.now().date()).exists():
        context["error"] = "Attendance has already been marked for this student and subject today."
        return render(request, "liveattendance.html", context)
    _, jpeg = cv2.imencode(".jpg", frame)
    attendance = Attendance(student=matched_student.user, subject=subject)
    attendance.face_image.save(f"{matched_student.roll_no}_{timezone.now():%Y%m%d%H%M%S}.jpg", ContentFile(jpeg.tobytes()), save=True)
    context.update(success="Attendance marked successfully!", student=matched_student, subject=subject)
    return render(request, "liveattendance.html", context)


# myattendance view
from collections import Counter
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Attendance

@login_required
def myattendance(request):
    # All attendance records for this student (most recent first)
    attendance_records = Attendance.objects.filter(student=request.user).order_by('-timestamp')

    # Build a dictionary { "Math": 5, "Science": 3, ... }
    subject_counts = dict(Counter(str(record.subject) for record in attendance_records))

    return render(request, 'myattendance.html', {
        'attendance_records': attendance_records,
        'subject_counts': subject_counts
    })





#attendance summary

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from collections import Counter
from .models import Attendance, Subject, Register

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Attendance, Subject, Register

@login_required
def attendance_summary(request):
    # Get student profile
    student_profile = Register.objects.get(user=request.user)

    # Get all attendance records of this student
    attendance_records = Attendance.objects.filter(student=request.user)

    # Group by subject
    summary = []
    total_attended = 0
    overall_total_classes = 0

    for subject in Subject.objects.all():
        # total classes conducted for this subject (all students)
        total_classes = Attendance.objects.filter(subject=subject).count()

        # classes attended by this student
        attended = attendance_records.filter(subject=subject).count()

        if total_classes > 0:
            percentage = round((attended / total_classes) * 100, 2)
        else:
            percentage = 0

        # Add only if student has at least 1 attendance in this subject
        if attended > 0:
            summary.append({
                "name": subject.name,
                "attended": attended,
                "total": total_classes,
                "percentage": percentage
            })

        total_attended += attended
        overall_total_classes += total_classes

    # Overall percentage
    overall_percentage = round((total_attended / overall_total_classes) * 100, 2) if overall_total_classes > 0 else 0

    # Last attendance
    last_attendance = attendance_records.order_by("-timestamp").first()

    return render(request, "attendance_summary.html", {
        "summary": summary,
        "total_attended": total_attended,
        "overall_total_classes": overall_total_classes,
        "overall_percentage": overall_percentage,
        "last_attendance": last_attendance.timestamp if last_attendance else None,
    })







#pdf download

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from .models import Attendance

@login_required
def download_attendance_pdf(request):
    records = Attendance.objects.filter(student=request.user).order_by('-timestamp')
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="my_attendance.pdf"'

    p = canvas.Canvas(response, pagesize=letter)
    width, height = letter
    y = height - 50

    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, y, "Attendance Report")
    y -= 30

    p.setFont("Helvetica", 12)
    p.drawString(50, y, "Date & Time")
    p.drawString(200, y, "Subject")
    y -= 20

    for record in records:
        p.drawString(50, y, record.timestamp.strftime("%Y-%m-%d %H:%M:%S"))
        p.drawString(200, y, str(record.subject))
        y -= 20
        if y < 50:
            p.showPage()
            y = height - 50

    p.save()
    return response



#manage user
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from .models import Register   # ✅ use Register, not Student

def manage_students(request):
    students = Register.objects.all()   # ✅ corrected
    return render(request, "manage_students.html", {"students": students})

    # =====================================================
    # STUDENT PROFILE
    # =====================================================

    profile = Register.objects.filter(
        user=request.user
    ).first()

    # =====================================================
    # TITLE
    # =====================================================

    y = height - 50

    pdf.setFont(
        "Helvetica-Bold",
        18
    )

    pdf.drawString(
        50,
        y,
        "Attendance Report"
    )

    y -= 35

    # =====================================================
    # STUDENT DETAILS
    # =====================================================

    pdf.setFont(
        "Helvetica",
        11
    )

    if profile:

        pdf.drawString(
            50,
            y,
            f"Name: {profile.student_name}"
        )

        y -= 18

        pdf.drawString(
            50,
            y,
            f"Roll No: {profile.roll_no}"
        )

        y -= 18

        pdf.drawString(
            50,
            y,
            f"Branch: {profile.branch}"
        )

        y -= 18

        pdf.drawString(
            50,
            y,
            f"Semester: {profile.semester}"
        )

        y -= 30

    # =====================================================
    # ATTENDANCE
    # =====================================================

    records = (
        Attendance.objects
        .filter(student=request.user)
        .select_related("subject")
        .order_by("-timestamp")
    )

    pdf.setFont(
        "Helvetica-Bold",
        11
    )

    pdf.drawString(
        50,
        y,
        "Date"
    )

    pdf.drawString(
        150,
        y,
        "Time"
    )

    pdf.drawString(
        230,
        y,
        "Subject"
    )

    y -= 20

    pdf.setFont(
        "Helvetica",
        10
    )

    # =====================================================
    # RECORDS
    # =====================================================

    for record in records:

        if y < 50:

            pdf.showPage()

            y = height - 50

            pdf.setFont(
                "Helvetica",
                10
            )

        pdf.drawString(
            50,
            y,
            record.timestamp.strftime(
                "%d-%m-%Y"
            )
        )

        pdf.drawString(
            150,
            y,
            record.timestamp.strftime(
                "%I:%M %p"
            )
        )

        pdf.drawString(
            230,
            y,
            record.subject.name
        )

        y -= 18

    # =====================================================
    # NO RECORDS
    # =====================================================

    if not records.exists():

        pdf.drawString(
            50,
            y,
            "No attendance records found."
        )

    # =====================================================
    # SAVE PDF
    # =====================================================

    pdf.save()

    return response
@staff_required
def manage_students(request):
    return render(request, "manage_students.html", {"students": Register.objects.select_related("user").all()})


@staff_required
def edit_student(request, student_id):
    student = get_object_or_404(Register, id=student_id)
    if request.method == "POST":
        roll_no = request.POST.get("roll_no", "").strip()
        if not roll_no:
            messages.error(request, "Roll number is required.")
            return render(request, "edit_student.html", {"student": student})
        if Register.objects.exclude(id=student.id).filter(roll_no=roll_no).exists() or (student.user and User.objects.exclude(id=student.user_id).filter(username=roll_no).exists()):
            messages.error(request, "Roll number already exists.")
            return render(request, "edit_student.html", {"student": student})
        with transaction.atomic():
            student.student_name = request.POST.get("student_name", "").strip()
            student.roll_no = roll_no
            student.semester = request.POST.get("semester", "").strip()
            student.branch = request.POST.get("branch", "").strip()
            if student.user:
                student.user.username = roll_no
                student.user.save(update_fields=["username"])
            student.save()
        messages.success(request, "Student updated successfully.")
        return redirect("manage_students")
    return render(request, "edit_student.html", {"student": student})


@staff_required
@require_POST
def delete_student(request, student_id):
    student = get_object_or_404(Register, id=student_id)
    user = student.user
    with transaction.atomic():
        student.delete()
        if user:
            user.delete()
    messages.success(request, "Student deleted successfully.")
    return redirect("manage_students")

def get_attendance_summary(user):
    attendance_records = Attendance.objects.filter(student=user)

    summary = []
    total_attended = 0
    overall_total_classes = 0

    for subject in Subject.objects.all():

        total_classes = Attendance.objects.filter(subject=subject).count()

        attended = attendance_records.filter(subject=subject).count()

        percentage = round((attended / total_classes) * 100, 2) if total_classes > 0 else 0

        if attended > 0:
            summary.append({
                "name": subject.name,
                "attended": attended,
                "total": total_classes,
                "percentage": percentage
            })

        total_attended += attended
        overall_total_classes += total_classes

    overall_percentage = (
        round((total_attended / overall_total_classes) * 100, 2)
        if overall_total_classes > 0 else 0
    )

    last_attendance = attendance_records.order_by("-timestamp").first()

    return (
        summary,
        total_attended,
        overall_total_classes,
        overall_percentage,
        last_attendance
    )

@staff_required
def student_search(request):

    context = {
        "student_data": None,
        "summary": [],
        "overall_percentage": 0,
        "total_attended": 0,
        "overall_total_classes": 0,
        "last_attendance": None,
        "error": None
    }

    if request.method == "POST":

        student = Register.objects.filter(
            roll_no=request.POST.get("roll_no", "").strip()
        ).select_related("user").first()

        if not student or not student.user:
            context["error"] = "Student with this roll number does not exist."

        else:
            (
                summary,
                attended,
                classes,
                percentage,
                last
            ) = get_attendance_summary(student.user)

            context.update(
                student_data=student,
                summary=summary,
                total_attended=attended,
                overall_total_classes=classes,
                overall_percentage=percentage,
                last_attendance=last.timestamp if last else None
            )

    return render(request, "student_search.html", context)

@login_required
@require_POST
def recognize_attendance(request):

    try:

        # =====================================================
        # GET DATA
        # =====================================================

        face_image_data = request.POST.get(
            "face_image_data",
            ""
        ).strip()

        branch = request.POST.get(
            "branch",
            ""
        ).strip()

        semester = request.POST.get(
            "semester",
            ""
        ).strip()

        subject_name = request.POST.get(
            "subject",
            ""
        ).strip()


        # =====================================================
        # BASIC VALIDATION
        # =====================================================

        if not face_image_data:
            return JsonResponse({
                "success": False,
                "error": "Face image is required."
            }, status=400)

        if not branch:
            return JsonResponse({
                "success": False,
                "error": "Branch is required."
            }, status=400)

        if not semester:
            return JsonResponse({
                "success": False,
                "error": "Semester is required."
            }, status=400)

        if not subject_name:
            return JsonResponse({
                "success": False,
                "error": "Subject is required."
            }, status=400)


        # =====================================================
        # CHECK BRANCH / SEMESTER / SUBJECT
        # =====================================================

        if request.user.is_staff:

            # ==============================
            # ADMIN FLOW - SAME AS BEFORE
            # ==============================

            if branch not in BRANCH_SUBJECTS:

                return JsonResponse({
                    "success": False,
                    "error": "Selected branch does not exist."
                }, status=400)

            if semester not in BRANCH_SUBJECTS[branch]:

                return JsonResponse({
                    "success": False,
                    "error": "Selected semester does not exist."
                }, status=400)

            available_subjects = BRANCH_SUBJECTS[branch][semester]

            if subject_name not in available_subjects:

                return JsonResponse({
                    "success": False,
                    "error": (
                        f"Selected subject does not exist: "
                        f"{subject_name}"
                    )
                }, status=400)

        else:

            # ==============================
            # TEACHER FLOW
            # ==============================

            try:
                teacher = request.user.teacher_profile

            except TeacherProfile.DoesNotExist:

                return JsonResponse({
                    "success": False,
                    "error": "Teacher profile not found."
                }, status=403)

            # Teacher ka branch automatically verify
            if branch != teacher.branch:

                return JsonResponse({
                    "success": False,
                    "error": "Invalid branch for this teacher."
                }, status=400)

            # Teacher ke assigned subject ko database se check
            try:

                subject = teacher.subjects.get(
                    name=subject_name,
                    semester=semester,
                    is_active=True
                )

            except Subject.DoesNotExist:

                return JsonResponse({
                    "success": False,
                    "error": (
                        "This subject is not assigned "
                        "to this teacher."
                    )
                }, status=400)


        # =====================================================
        # DECODE CAMERA IMAGE
        # =====================================================

        try:

            image_bytes, extension = (
                _decode_data_url(
                    face_image_data
                )
            )

        except ValueError as e:

            return JsonResponse({
                "success": False,
                "error": str(e)
            }, status=400)


        # =====================================================
        # CONVERT IMAGE
        # =====================================================

        image_array = np.frombuffer(
            image_bytes,
            dtype=np.uint8
        )

        frame = cv2.imdecode(
            image_array,
            cv2.IMREAD_COLOR
        )

        if frame is None:

            return JsonResponse({
                "success": False,
                "error": "Unable to read captured image."
            }, status=400)


        # =====================================================
        # BGR -> RGB
        # =====================================================

        rgb_frame = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )


        # =====================================================
        # DETECT FACE
        # =====================================================

        face_locations = face_recognition.face_locations(
            rgb_frame,
            model="hog"
        )

        print(
            "Camera faces detected:",
            len(face_locations)
        )


        if len(face_locations) == 0:

            return JsonResponse({
                "success": False,
                "error": (
                    "No face detected. "
                    "Please look directly at the camera."
                )
            }, status=404)


        # =====================================================
        # CAMERA FACE ENCODING
        # =====================================================

        captured_encodings = (
            face_recognition.face_encodings(
                rgb_frame,
                known_face_locations=face_locations
            )
        )


        if not captured_encodings:

            return JsonResponse({
                "success": False,
                "error": (
                    "Could not create face encoding."
                )
            }, status=404)


        # =====================================================
        # GET STUDENTS OF SAME BRANCH + SEMESTER
        # =====================================================

        students = Register.objects.filter(
            branch=branch,
            semester=semester
        ).select_related("user")


        print(
            "Students found:",
            students.count()
        )


        if not students.exists():

            return JsonResponse({
                "success": False,
                "error": (
                    f"No students found for "
                    f"{branch} - {semester}."
                )
            }, status=404)


        # =====================================================
        # FACE MATCHING - MULTIPLE FACES
        # =====================================================

        matched_students = []

        tolerance = 0.50

        for face_index, captured_encoding in enumerate(
            captured_encodings
        ):

            matched_student = None
            best_distance = 1.0

            print(
                f"Checking camera face {face_index + 1}"
            )

            for student in students:

                if not student.face_image:

                    print(
                        f"{student.roll_no}: "
                        "No registered face image"
                    )

                    continue

                try:

                    registered_image = (
                        face_recognition.load_image_file(
                            student.face_image.path
                        )
                    )

                    registered_encodings = (
                        face_recognition.face_encodings(
                            registered_image
                        )
                    )

                    if not registered_encodings:

                        print(
                            f"{student.roll_no}: "
                            "No face in registered image"
                        )

                        continue

                    registered_encoding = (
                        registered_encodings[0]
                    )

                    distance = (
                        face_recognition.face_distance(
                            [registered_encoding],
                            captured_encoding
                        )[0]
                    )

                    print(
                        f"Camera face {face_index + 1} - "
                        f"{student.roll_no}: "
                        f"distance = {distance:.4f}"
                    )

                    if distance < best_distance:

                        best_distance = distance
                        matched_student = student

                except Exception as e:

                    print(
                        f"Recognition error for "
                        f"{student.roll_no}:",
                        repr(e)
                    )

                    continue

            print(
                f"Camera face {face_index + 1} "
                f"best distance:",
                best_distance
            )

            if (
                matched_student is not None
                and best_distance <= tolerance
            ):

                # Same student ko ek frame me dobara add na karein
                if matched_student.id not in [
                    student.id
                    for student, distance in matched_students
                ]:

                    matched_students.append(
                        (
                            matched_student,
                            best_distance
                        )
                    )


        # =====================================================
        # CHECK MATCH
        # =====================================================

        if not matched_students:

            return JsonResponse({
                "success": False,
                "error": "No recognized student found."
            }, status=404)


        # =====================================================
        # GET SUBJECT
        # =====================================================

        if request.user.is_staff:

            subject, created = Subject.objects.get_or_create(
                name=subject_name
            )


        # =====================================================
        # CHECK TODAY'S ATTENDANCE
        # =====================================================

        today = timezone.now().date()

        marked_students = []
        already_marked_students = []


        # =====================================================
        # ENCODE CAPTURED IMAGE
        # =====================================================

        success, jpeg = cv2.imencode(
            ".jpg",
            frame
        )

        if not success:

            return JsonResponse({
                "success": False,
                "error": "Failed to encode captured image."
            }, status=500)


        # =====================================================
        # MARK ATTENDANCE FOR ALL MATCHED STUDENTS
        # =====================================================

        for matched_student, best_distance in matched_students:

            already_marked = (
                Attendance.objects.filter(
                    student=matched_student.user,
                    subject=subject,
                    timestamp__date=today
                ).exists()
            )

            if already_marked:

                already_marked_students.append({
                    "student_name":
                        matched_student.student_name,

                    "roll_no":
                        matched_student.roll_no,

                    "face_distance":
                        round(
                            float(best_distance),
                            4
                        )
                })

                continue


            # =================================================
            # FILE NAME
            # =================================================

            filename = (
                f"{matched_student.roll_no}_"
                f"{subject.id}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
            )


            # =================================================
            # CREATE ATTENDANCE
            # =================================================

            attendance = Attendance(
                student=matched_student.user,
                subject=subject
            )

            attendance.face_image.save(
                filename,
                ContentFile(
                    jpeg.tobytes()
                ),
                save=True
            )


            marked_students.append({
                "student_name":
                    matched_student.student_name,

                "roll_no":
                    matched_student.roll_no,

                "branch":
                    matched_student.branch,

                "semester":
                    matched_student.semester,

                "subject":
                    subject.name,

                "face_distance":
                    round(
                        float(best_distance),
                        4
                    ),

                "attendance_id":
                    attendance.id
            })


            print(
                "ATTENDANCE SUCCESS:",
                matched_student.student_name,
                matched_student.roll_no,
                subject_name,
                best_distance
            )


        # =====================================================
        # FINAL RESPONSE
        # =====================================================

        if not marked_students and not already_marked_students:

            return JsonResponse({
                "success": False,
                "error": "No new attendance was marked."
            }, status=404)


        return JsonResponse({
            "success": True,
            "message": "Attendance processed successfully.",
            "marked_students": marked_students,
            "already_marked_students": already_marked_students,
            "total_marked": len(marked_students),
            "total_already_marked": len(already_marked_students)
        })


    except Exception as e:

        print(
            "Recognition Error:",
            repr(e)
        )

        return JsonResponse({

            "success": False,

            "error":
                f"Recognition Error: {str(e)}"

        }, status=500)
        
        
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from .models import Subject, Attendance     
@login_required
def subjects(request):

    search = request.GET.get("search", "").strip()
    semester = request.GET.get("semester", "").strip()
    branch = request.GET.get("branch", "").strip()

    subjects = Subject.objects.annotate(
        attendance_count=Count("attendance")
    )

    if search:
        subjects = subjects.filter(
            Q(name__icontains=search) |
            Q(branch__icontains=search)
        )

    if semester:
        subjects = subjects.filter(semester=semester)

    if branch:
        subjects = subjects.filter(branch__iexact=branch)

    branches = (
        Subject.objects
        .values_list("branch", flat=True)
        .distinct()
        .order_by("branch")
    )

    return render(request, "subjects.html", {
    "subjects": subjects,
    "branches": branches,
    "selected_semester": semester,
    "selected_branch": branch,
    "search": search,
    "semester_choices": Subject.SEMESTER_CHOICES,
})
    
@login_required
def add_subject(request):

    if request.method == "POST":

        name = request.POST.get("name", "").strip()
        semester = request.POST.get("semester", "").strip()
        branch = request.POST.get("branch", "").strip()

        if not name or not semester or not branch:
            messages.error(request, "All fields are required.")
            return redirect("subjects")

        if Subject.objects.filter(
            name__iexact=name,
            semester=semester,
            branch__iexact=branch
        ).exists():

            messages.error(
                request,
                "This subject already exists for this semester and branch."
            )

            return redirect("subjects")

        Subject.objects.create(
            name=name,
            semester=semester,
            branch=branch
        )

        messages.success(
            request,
            f"{name} added successfully."
        )

    return redirect("subjects")


@login_required
def edit_subject(request, subject_id):

    subject = get_object_or_404(Subject, id=subject_id)

    if request.method == "POST":

        name = request.POST.get("name", "").strip()
        semester = request.POST.get("semester", "").strip()
        branch = request.POST.get("branch", "").strip()

        is_active = request.POST.get("is_active") == "on"

        if not name or not semester or not branch:
            messages.error(request, "All fields are required.")
            return redirect("subjects")

        duplicate = Subject.objects.filter(
            name__iexact=name,
            semester=semester,
            branch__iexact=branch
        ).exclude(
            id=subject.id
        ).exists()

        if duplicate:
            messages.error(
                request,
                "Another subject with the same details already exists."
            )
            return redirect("subjects")

        subject.name = name
        subject.semester = semester
        subject.branch = branch
        subject.is_active = is_active

        subject.save()

        messages.success(
            request,
            "Subject updated successfully."
        )

    return redirect("subjects")

@login_required
def delete_subject(request, subject_id):

    subject = get_object_or_404(
        Subject,
        id=subject_id
    )

    attendance_count = Attendance.objects.filter(
        subject=subject
    ).count()

    if attendance_count > 0:

        messages.error(
            request,
            f"Cannot delete {subject.name}. "
            f"It has {attendance_count} attendance records. "
            f"Deactivate it instead."
        )

    else:

        subject.delete()

        messages.success(
            request,
            "Subject deleted successfully."
        )

    return redirect("subjects")

        

@login_required
def timetable(request):
    # timetable page
    pass

from .models import Register, Subject, Attendance, TeacherProfile


from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Count, Q
from django.utils import timezone

from .models import (
    Attendance,
    Register,
    Subject,
    TeacherProfile,
)
def teacher_required(view):

    @login_required
    def wrapped(request, *args, **kwargs):

        if request.user.is_staff:
            return redirect("adminpanel")

        try:
            teacher = request.user.teacher_profile

        except TeacherProfile.DoesNotExist:
            messages.error(
                request,
                "Teacher profile not found."
            )
            return redirect("login")

        if not teacher.is_active:
            auth_logout(request)

            messages.error(
                request,
                "Your teacher account is inactive."
            )
            return redirect("login")

        # First login → force password change
        if (
            teacher.must_change_password
            and request.resolver_match.url_name != "teacher_change_password"
        ):
            return redirect("teacher_change_password")

        return view(
            request,
            teacher=teacher,
            *args,
            **kwargs
        )

    return wrapped


def teacher_change_password(request):

    if not request.user.is_authenticated:
        return redirect("login")

    try:
        teacher = request.user.teacher_profile
    except TeacherProfile.DoesNotExist:
        return redirect("login")

    if request.method == "POST":

        form = PasswordChangeForm(
            request.user,
            request.POST
        )

        if form.is_valid():

            user = form.save()

            update_session_auth_hash(
                request,
                user
            )

            teacher.must_change_password = False

            teacher.save(
                update_fields=[
                    "must_change_password"
                ]
            )

            messages.success(
                request,
                "Password changed successfully."
            )

            return redirect("teacherpanel")

    else:

        form = PasswordChangeForm(
            request.user
        )

    return render(
        request,
        "teacher_change_password.html",
        {
            "form": form,
            "teacher": teacher
        }
    )
    
@teacher_required
def teacherpanel(request, teacher):

    if request.method == "POST":

        action = request.POST.get("action")

        if action == "change_password":

            form = PasswordChangeForm(
                request.user,
                request.POST
            )

            if form.is_valid():

                user = form.save()

                update_session_auth_hash(
                    request,
                    user
                )

                teacher.must_change_password = False
                teacher.save(
                    update_fields=["must_change_password"]
                )

                messages.success(
                    request,
                    "Password changed successfully."
                )

                return redirect("teacherpanel")

            else:

                for error in form.errors.values():

                    messages.error(
                        request,
                        error.as_text()
                    )

    subjects = teacher.subjects.filter(
        is_active=True
    ).order_by(
        "semester",
        "name"
    )

    subject_ids = subjects.values_list(
        "id",
        flat=True
    )

    semesters = subjects.values_list(
        "semester",
        flat=True
    )

    students = Register.objects.filter(
        branch__iexact=teacher.branch,
        semester__in=semesters
    ).order_by(
        "semester",
        "roll_no"
    )

    
    today = date.today()

    attendance_records = Attendance.objects.filter(
        subject_id__in=subject_ids
    ).select_related(
        "student",
        "subject"
    ).order_by(
        "-timestamp"
    )[:100]

    today_attendance = Attendance.objects.filter(
        subject_id__in=subject_ids,
        timestamp__date=today
    ).count()

    total_attendance = Attendance.objects.filter(
        subject_id__in=subject_ids
    ).count()

    return render(
        request,
        "teacherpanel.html",
        {
            "teacher": teacher,
            "subjects": subjects,
            "students": students,
            "attendance_records": attendance_records,
            "subject_count": subjects.count(),
            "students_count": students.count(),
            "today_attendance": today_attendance,
            "total_attendance": total_attendance,
        }
    )
@teacher_required
def teacher_students(request, teacher):

    subjects = teacher.subjects.filter(
        is_active=True
    )

    semesters = subjects.values_list(
        "semester",
        flat=True
    )

    students = Register.objects.filter(
        branch__iexact=teacher.branch,
        semester__in=semesters
    ).select_related("user")

    search = request.GET.get(
        "search",
        ""
    ).strip()

    semester = request.GET.get(
        "semester",
        ""
    ).strip()

    if search:

        students = students.filter(
            Q(student_name__icontains=search)
            |
            Q(roll_no__icontains=search)
        )

    if semester:

        students = students.filter(
            semester=semester
        )

    return render(
        request,
        "teacher_students.html",
        {
            "teacher": teacher,
            "students": students,
            "subjects": subjects,
            "semesters": sorted(
                set(
                    subjects.values_list(
                        "semester",
                        flat=True
                    )
                )
            ),
            "search": search,
            "selected_semester": semester,
        }
    )
    
@teacher_required
def teacher_subjects(request, teacher):
    subjects = teacher.subjects.filter(
        is_active=True
    ).order_by(
        "semester",
        "name"
    )

    return render(
        request,
        "teacherpanel.html",
        {
            "teacher": teacher,
            "subjects": subjects,
            "active_section": "subjects",
        }
    )
    
@teacher_required
def teacher_attendance(request, teacher):

    subjects = (
        teacher.subjects
        .filter(is_active=True)
        .order_by("semester", "name")
    )

    selected_subject = request.GET.get(
        "subject",
        ""
    ).strip()

    selected_date = request.GET.get(
        "date",
        ""
    ).strip()

    attendance = Attendance.objects.filter(
        subject__in=subjects
    ).select_related(
        "student",
        "subject"
    ).order_by(
        "-timestamp"
    )

    if selected_subject:

        attendance = attendance.filter(
            subject_id=selected_subject
        )

    if selected_date:

        attendance = attendance.filter(
            timestamp__date=selected_date
        )

    return render(
        request,
        "teacher_attendance.html",
        {
            "teacher": teacher,
            "subjects": subjects,
            "attendance": attendance,
            "selected_subject": selected_subject,
            "selected_date": selected_date,
        }
    )
    
@teacher_required
def teacher_profile(request, teacher):

    return render(
        request,
        "teacher_profile.html",
        {
            "teacher": teacher,
        }
    )
from django.contrib.auth import logout as auth_logout
@login_required
def teacher_logout(request):

    auth_logout(request)

    return redirect("login")