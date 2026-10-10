import base64
import binascii
import hashlib
import hmac
from datetime import date, datetime, timedelta
import os
import re
import tempfile
import uuid
import secrets
from functools import lru_cache
from decimal import Decimal, InvalidOperation
from collections import Counter
import base64
import uuid
import cv2
import numpy as np
import face_recognition

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.utils import timezone
from django.core.files.base import ContentFile
from django.core import signing

from .models import Register, Subject, Attendance, RoomInventory
import cv2
import face_recognition
import numpy as np


@lru_cache(maxsize=4096)
def _cached_student_face_encoding(image_path, modified_at_ns):
    try:
        image = face_recognition.load_image_file(image_path)
        encodings = face_recognition.face_encodings(image)
        return encodings[0] if encodings else None
    except Exception:
        return None
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
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
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from .upload_validation import validate_homework_upload, validate_image_bytes

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
    LoginAttempt,
    AdminMFAProfile,
    AdminLoginChallenge,
    TeacherProfile,
)
from .models import Attendance, Register, Subject


AUTH_FAILURE_WINDOW = timedelta(minutes=15)
AUTH_ACCOUNT_FAILURE_LIMIT = 5
AUTH_IP_FAILURE_LIMIT = 25


def _auth_attempt_keys(request, identifier):
    """Return privacy-preserving account and source-IP throttle keys."""
    secret = settings.SECRET_KEY.encode("utf-8")
    normalized_identifier = str(identifier or "").strip().casefold()
    ip_address = request.META.get("REMOTE_ADDR", "unknown")
    account_digest = hmac.new(
        secret,
        f"account:{normalized_identifier}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    ip_digest = hmac.new(
        secret,
        f"ip:{ip_address}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return (
        (account_digest, AUTH_ACCOUNT_FAILURE_LIMIT),
        (ip_digest, AUTH_IP_FAILURE_LIMIT),
    )


def _auth_throttled_until(request, identifier):
    now = timezone.now()
    keys = [key for key, _ in _auth_attempt_keys(request, identifier)]
    return LoginAttempt.objects.filter(
        key__in=keys,
        locked_until__gt=now,
    ).order_by("-locked_until").values_list("locked_until", flat=True).first()


def _record_auth_failure(request, identifier):
    now = timezone.now()
    LoginAttempt.objects.filter(
        window_started__lt=now - timedelta(days=1),
    ).delete()
    for key, limit in _auth_attempt_keys(request, identifier):
        with transaction.atomic():
            LoginAttempt.objects.get_or_create(
                key=key,
                defaults={"window_started": now},
            )
            attempt = LoginAttempt.objects.select_for_update().get(key=key)
            if now - attempt.window_started >= AUTH_FAILURE_WINDOW:
                attempt.failures = 0
                attempt.window_started = now
                attempt.locked_until = None
            attempt.failures = min(attempt.failures + 1, 32767)
            if attempt.failures >= limit:
                attempt.locked_until = now + AUTH_FAILURE_WINDOW
            attempt.save(update_fields=["failures", "window_started", "locked_until"])


def _clear_auth_failures(request, identifier):
    keys = [key for key, _ in _auth_attempt_keys(request, identifier)]
    LoginAttempt.objects.filter(key__in=keys).delete()


def _issue_admin_mfa_code(request, user):
    identifier = f"admin-mfa:{user.pk}"
    if _auth_throttled_until(request, identifier) or not user.email:
        return False
    code = f"{secrets.randbelow(1_000_000):06d}"
    AdminLoginChallenge.objects.filter(
        user=user,
        created_at__lt=timezone.now() - timedelta(days=1),
    ).delete()
    challenge = AdminLoginChallenge.objects.create(
        user=user,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    try:
        send_mail(
            "Your administrator sign-in code",
            f"Your one-time administrator sign-in code is {code}. It expires in 5 minutes.",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except Exception:
        challenge.used_at = timezone.now()
        challenge.save(update_fields=["used_at"])
        return False
    _record_auth_failure(request, identifier)
    request.session["pending_admin_mfa_challenge"] = challenge.pk
    request.session["pending_admin_mfa_user"] = user.pk
    return True


def _complete_admin_mfa(request, code):
    challenge_id = request.session.get("pending_admin_mfa_challenge")
    user_id = request.session.get("pending_admin_mfa_user")
    if not challenge_id or not user_id:
        return None
    with transaction.atomic():
        challenge = AdminLoginChallenge.objects.select_for_update().filter(
            pk=challenge_id,
            user_id=user_id,
            used_at__isnull=True,
            expires_at__gt=timezone.now(),
            attempts__lt=5,
            user__is_active=True,
            user__is_staff=True,
            user__admin_mfa__enabled=True,
        ).select_related("user").first()
        if not challenge:
            return None
        if not check_password(code, challenge.code_hash):
            challenge.attempts += 1
            if challenge.attempts >= 5:
                challenge.used_at = timezone.now()
            challenge.save(update_fields=["attempts", "used_at"])
            return None
        challenge.used_at = timezone.now()
        challenge.save(update_fields=["used_at"])
        user = challenge.user
    request.session.pop("pending_admin_mfa_challenge", None)
    request.session.pop("pending_admin_mfa_user", None)
    auth_login(request, user)
    request.session["admin_mfa_verified_user"] = user.pk
    _clear_auth_failures(request, f"admin-mfa:{user.pk}")
    return user


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
        image_bytes = base64.b64decode(payload, validate=True)
        validate_image_bytes(image_bytes, f".{extension}")
        return image_bytes, extension
    except (AttributeError, ValueError, binascii.Error, ValidationError) as exc:
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


def _single_face_encoding(image_bytes, extension):
    """Return an encoding only when the capture contains exactly one face."""
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}") as temp_file:
            temp_file.write(image_bytes)
            temp_path = temp_file.name
        image = face_recognition.load_image_file(temp_path)
        locations = face_recognition.face_locations(image)
        if len(locations) != 1:
            return None
        encodings = face_recognition.face_encodings(image, known_face_locations=locations)
        return encodings[0] if len(encodings) == 1 else None
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

    if (
        len(student_name) > 100
        or len(roll_no) > 20
        or semester not in dict(Subject.SEMESTER_CHOICES)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .&/-]{0,49}", branch)
        or len(face_image_data) > 8_000_000
    ):
        messages.error(request, "Some registration fields are invalid or too long.")
        return render(request, "register.html")

    if password != confirm_password:
        messages.error(
            request,
            "Passwords do not match."
        )
        return render(request, "register.html")

    try:
        validate_password(password, User(username=roll_no, first_name=student_name))
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
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


@never_cache
def login(request):

    if request.method == "POST":
        username = request.POST.get("roll_no", "").strip()
        if _auth_throttled_until(request, username):
            messages.error(request, "Too many login attempts. Try again in 15 minutes.")
            return render(request, "login.html")

        user = authenticate(
            request,
            username=username,
            password=request.POST.get("password", ""),
        )

        if user is not None:
            _clear_auth_failures(request, username)

            # Admin login
            if user.is_staff:
                if AdminMFAProfile.objects.filter(user=user, enabled=True).exists():
                    if not _issue_admin_mfa_code(request, user):
                        messages.error(request, "Unable to send a sign-in code. Check the administrator email settings or try again later.")
                        return render(request, "adminlogin.html")
                    messages.success(request, "A one-time sign-in code was sent to the administrator email address.")
                    return redirect("adminlogin")
                auth_login(request, user)
                return redirect("adminpanel")

            auth_login(request, user)

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

                if ParentProfile.objects.filter(user=user).exists():
                    return redirect("parent_dashboard")

                return redirect("userpanel")

        _record_auth_failure(request, username)
        messages.error(
            request,
            "Invalid roll number or password."
        )

    return render(
        request,
        "login.html"
    )


@never_cache
def student_forgot_password(request):
    """Reset a student's password after matching a fresh webcam capture."""
    stage = "verify"
    reset_token = ""

    if request.method == "POST":
        action = request.POST.get("action", "verify_face")

        if action == "set_password":
            token = request.POST.get("reset_token", "")
            password = request.POST.get("password", "")
            confirm_password = request.POST.get("confirm_password", "")
            try:
                token_data = signing.loads(
                    token,
                    salt="student-password-reset",
                    max_age=300,
                )
                expected_nonce = request.session.get("student_password_reset_nonce")
                if not expected_nonce or token_data.get("nonce") != expected_nonce:
                    raise signing.BadSignature("Reset confirmation expired")
                with transaction.atomic():
                    student = Register.objects.select_for_update().select_related("user").get(
                        roll_no=token_data["roll_no"],
                        user_id=token_data["user_id"],
                    )
                    if not student.user_id:
                        raise signing.BadSignature("Student account missing")
                    if password != confirm_password:
                        raise ValidationError("Passwords do not match.")
                    validate_password(password, student.user)
                    student.user.set_password(password)
                    student.user.save(update_fields=["password"])
                request.session.pop("student_password_reset_nonce", None)
                request.session.pop("student_password_reset_failures", None)
                messages.success(request, "Password updated. Please log in with your new password.")
                return redirect("login")
            except signing.SignatureExpired:
                messages.error(request, "Face verification expired. Please verify your face again.")
            except (signing.BadSignature, Register.DoesNotExist, KeyError):
                messages.error(request, "Password reset session is invalid. Please verify your face again.")
            except ValidationError as error:
                messages.error(request, " ".join(error.messages))

        else:
            now = timezone.now().timestamp()
            window_started = request.session.get("student_reset_window_started", now)
            failures = request.session.get("student_password_reset_failures", 0)
            if now - window_started > 600:
                failures = 0
                window_started = now

            roll_no = request.POST.get("roll_no", "").strip()
            face_image_data = request.POST.get("face_image_data", "")
            auth_locked = bool(_auth_throttled_until(request, roll_no))
            student = Register.objects.select_related("user").filter(
                roll_no__iexact=roll_no,
            ).first() if roll_no and not auth_locked else None
            matched = False
            if (
                failures < 5
                and not auth_locked
                and student
                and student.user_id
                and student.face_image
                and len(face_image_data) <= 8_000_000
            ):
                try:
                    image_bytes, extension = _decode_data_url(face_image_data)
                    captured_encoding = _single_face_encoding(image_bytes, extension)
                    registered_encodings = face_recognition.face_encodings(
                        face_recognition.load_image_file(student.face_image.path)
                    )
                    if captured_encoding is not None and len(registered_encodings) == 1:
                        distance = face_recognition.face_distance(
                            [registered_encodings[0]],
                            captured_encoding,
                        )[0]
                        matched = bool(distance <= 0.45)
                except (ValueError, OSError, RuntimeError):
                    matched = False
                except Exception:
                    matched = False

            if matched:
                _clear_auth_failures(request, roll_no)
                nonce = secrets.token_urlsafe(24)
                request.session["student_password_reset_nonce"] = nonce
                request.session.pop("student_password_reset_failures", None)
                reset_token = signing.dumps(
                    {
                        "user_id": student.user_id,
                        "roll_no": student.roll_no,
                        "nonce": nonce,
                    },
                    salt="student-password-reset",
                )
                stage = "password"
            else:
                if not auth_locked:
                    _record_auth_failure(request, roll_no)
                failures += 1
                request.session["student_password_reset_failures"] = failures
                request.session["student_reset_window_started"] = window_started
                if failures >= 5:
                    messages.error(request, "Too many attempts. Please try again in 10 minutes.")
                else:
                    messages.error(request, "Roll number or live face did not match. Please try again.")

    return render(request, "student_forgot_password.html", {
        "stage": stage,
        "reset_token": reset_token,
    })


def adminlogin(request):
    if request.user.is_authenticated and request.user.is_staff:
        if not AdminMFAProfile.objects.filter(user=request.user, enabled=True).exists():
            return redirect("adminpanel")
        if request.session.get("admin_mfa_verified_user") == request.user.pk:
            return redirect("adminpanel")
        if not request.session.get("pending_admin_mfa_challenge"):
            if not _issue_admin_mfa_code(request, request.user):
                messages.error(request, "Unable to send a sign-in code. Check the administrator email settings or try again later.")
                return render(request, "adminlogin.html")
            messages.success(request, "A one-time sign-in code was sent to the administrator email address.")
    if request.method == "POST":
        mfa_code = request.POST.get("mfa_code", "").strip()
        if mfa_code:
            user = _complete_admin_mfa(request, mfa_code)
            if user:
                return redirect("adminpanel")
            messages.error(request, "The sign-in code is invalid or expired.")
            return render(request, "adminlogin.html", {"mfa_pending": True})

        username = request.POST.get("username", "").strip()
        if _auth_throttled_until(request, username):
            messages.error(request, "Too many login attempts. Try again in 15 minutes.")
            return render(request, "adminlogin.html")
        user = authenticate(request, username=username, password=request.POST.get("password", ""))
        if user is not None and user.is_staff:
            _clear_auth_failures(request, username)
            if AdminMFAProfile.objects.filter(user=user, enabled=True).exists():
                if not _issue_admin_mfa_code(request, user):
                    messages.error(request, "Unable to send a sign-in code. Check the administrator email settings or try again later.")
                    return render(request, "adminlogin.html")
                messages.success(request, "A one-time sign-in code was sent to the administrator email address.")
                return render(request, "adminlogin.html", {"mfa_pending": True})
            auth_login(request, user)
            return redirect("adminpanel")
        _record_auth_failure(request, username)
        messages.error(request, "Invalid username or password.")
    return render(request, "adminlogin.html", {
        "mfa_pending": bool(request.session.get("pending_admin_mfa_challenge")),
    })

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
    
    
from .models import TimetableSlot

from datetime import date

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
    attendance_summary, _, _, _, _ = get_attendance_summary(request.user)
    attendance_summary = [
        {**record, "subject_name": record["name"]}
        for record in attendance_summary
    ]

    # Student's published timetable
    timetable = TimetableSlot.objects.none()
    today_timetable = []
    today = date.today()
    student_adjustments = []
    unread_dashboard_notices = []

    if profile:
        timetable = (
            TimetableSlot.objects
            .filter(
                configuration__branch=profile.branch,
                configuration__semester=profile.semester,
                status=TimetableSlot.Status.PUBLISHED,
            )
            .select_related(
                "subject",
                "teacher__user",
                "configuration",
            )
            .order_by("day", "start_time")
        )

        # Today's published timetable
        today_timetable = list(timetable.filter(
            day=today.weekday()
        ).order_by("start_time"))
        student_adjustments = list(TeacherLeaveAdjustment.objects.filter(
            subject__branch__iexact=profile.branch,
            subject__semester=profile.semester,
            class_date__gte=today,
            timetable_slot__isnull=False,
        ).select_related(
            "subject",
            "original_teacher__user",
            "substitute_teacher__user",
        ).order_by("class_date", "start_time"))

    announcements = Announcement.objects.none()
    if profile:
        announcements = Announcement.objects.filter(
            audience=Announcement.Audience.STUDENTS,
        ).filter(
            Q(branch__isnull=True) | Q(branch__iexact=profile.branch),
            Q(semester__isnull=True) | Q(semester=profile.semester),
        ).select_related("teacher__user", "created_by")
        print("STUDENT PROFILE:", profile)
        print("TIMETABLE COUNT:", timetable.count())
        print("TODAY TIMETABLE COUNT:", len(today_timetable))

    unread_announcements = announcements.exclude(
        reads__user=request.user
    ).distinct()[:20]
    announcements = announcements[:30]

    student_tests = ClassTest.objects.none()
    if profile:
        student_tests = list(
            ClassTest.objects.filter(
                subject__branch__iexact=profile.branch,
                subject__semester=profile.semester,
            ).select_related("subject", "teacher__user")[:30]
        )
        results_by_test = {
            result.test_id: result
            for result in TestResult.objects.filter(
                student=profile,
                test_id__in=[class_test.pk for class_test in student_tests],
            )
        }
        for class_test in student_tests:
            class_test.student_result = results_by_test.get(class_test.pk)

        read_states = {
            (row.notice_type, row.object_id): row.seen_updated_at
            for row in DashboardNoticeRead.objects.filter(user=request.user)
        }
        for class_test in student_tests:
            notice_version = class_test.created_at
            if (
                class_test.student_result
                and class_test.student_result.updated_at > notice_version
            ):
                notice_version = class_test.student_result.updated_at
            seen_at = read_states.get((DashboardNoticeRead.NoticeType.TEST, class_test.pk))
            if seen_at is None or notice_version > seen_at:
                test_detail = (
                    f"{class_test.subject.name} · {class_test.test_date:%b %d, %Y} · {class_test.max_marks} marks"
                )
                if class_test.student_result:
                    test_detail += f" · Your result: {class_test.student_result.marks_obtained}/{class_test.max_marks}"
                unread_dashboard_notices.append({
                    "key": f"TEST:{class_test.pk}",
                    "type": "Test or result updated",
                    "title": class_test.title,
                    "detail": test_detail,
                })
        for adjustment in student_adjustments:
            seen_at = read_states.get((DashboardNoticeRead.NoticeType.ADJUSTMENT, adjustment.pk))
            if seen_at is None or adjustment.updated_at > seen_at:
                plan = (
                    adjustment.substitute_teacher.user.get_full_name()
                    or adjustment.substitute_teacher.user.username
                    if adjustment.adjustment_type == TeacherLeaveAdjustment.AdjustmentType.SUBSTITUTE
                    and adjustment.substitute_teacher_id
                    else "Library period"
                    if adjustment.adjustment_type == TeacherLeaveAdjustment.AdjustmentType.LIBRARY
                    else adjustment.custom_activity or "Schedule updated"
                )
                unread_dashboard_notices.append({
                    "key": f"ADJUSTMENT:{adjustment.pk}",
                    "type": "Timetable changed",
                    "title": adjustment.subject.name,
                    "detail": f"{adjustment.class_date:%b %d, %Y} · {adjustment.start_time:%I:%M %p}–{adjustment.end_time:%I:%M %p} · {plan}",
                })

    context = {
        "user": request.user,
        "profile": profile,
        "attendance_records": attendance_records,
        "total_attended": total_attended,
        "attendance_summary": attendance_summary,
        "timetable": timetable,
        "today_timetable": today_timetable,
        "student_adjustments": student_adjustments,
        "unread_dashboard_notices": unread_dashboard_notices,
        "announcements": announcements,
        "unread_announcements": unread_announcements,
        "student_tests": student_tests,
    }

    return render(
        request,
        "userpanel.html",
        context
    )


@login_required
def leave_portal(request):
    profile = Register.objects.filter(user=request.user).first()
    if profile is None:
        messages.error(request, "Student profile not found.")
        return redirect("userpanel")

    subjects = Subject.objects.filter(
        is_active=True,
        branch__iexact=profile.branch,
        semester=profile.semester,
        assigned_teachers__is_active=True,
    ).distinct().order_by("name")
    teachers = TeacherProfile.objects.filter(
        is_active=True,
        subjects__in=subjects,
    ).select_related("user").distinct().order_by("user__first_name", "user__username")
    teacher_choices = [
        {
            "teacher": teacher,
            "subject_ids": list(
                teacher.subjects.filter(pk__in=subjects).values_list("pk", flat=True)
            ),
        }
        for teacher in teachers
    ]

    if request.method == "POST":
        subject_ids = request.POST.getlist("subjects")
        teacher_ids = request.POST.getlist("teachers")
        reason = request.POST.get("reason", "").strip()

        try:
            start_date = date.fromisoformat(request.POST.get("start_date", ""))
            end_date = date.fromisoformat(request.POST.get("end_date", ""))
        except ValueError:
            messages.error(request, "Enter valid leave dates.")
        else:
            selected_subjects = list(subjects.filter(pk__in=subject_ids))
            selected_teachers = list(teachers.filter(pk__in=teacher_ids))
            subject_teachers = []
            for subject in selected_subjects:
                matches = [teacher for teacher in selected_teachers if teacher.subjects.filter(pk=subject.pk).exists()]
                if len(matches) == 1:
                    subject_teachers.append((subject, matches[0]))

            if (
                not selected_subjects
                or len(selected_subjects) != len(set(subject_ids))
                or len(selected_teachers) != len(set(teacher_ids))
                or len(subject_teachers) != len(selected_subjects)
                or {teacher.pk for _, teacher in subject_teachers} != {teacher.pk for teacher in selected_teachers}
                or not reason
                or len(reason) > 4000
            ):
                messages.error(request, "Choose subjects and assigned teachers so each subject matches exactly one selected teacher, then provide a reason.")
            elif end_date < start_date:
                messages.error(request, "The end date cannot be earlier than the start date.")
            elif (end_date - start_date).days > 365:
                messages.error(request, "A single leave request cannot be longer than one year.")
            elif any(
                LeaveApplication.objects.filter(
                    student=profile,
                    subject=subject,
                    status__in=[LeaveApplication.Status.PENDING, LeaveApplication.Status.APPROVED],
                    start_date__lte=end_date,
                    end_date__gte=start_date,
                ).exists()
                for subject, _ in subject_teachers
            ):
                messages.error(request, "At least one selected subject already has a pending or approved leave request for these dates.")
            else:
                with transaction.atomic():
                    LeaveApplication.objects.bulk_create([
                        LeaveApplication(
                            student=profile,
                            subject=subject,
                            teacher=teacher,
                            start_date=start_date,
                            end_date=end_date,
                            reason=reason,
                        )
                        for subject, teacher in subject_teachers
                    ])
                messages.success(request, f"Leave request sent to the assigned teacher for {len(subject_teachers)} subject(s).")
                return redirect("leave_portal")

    applications = LeaveApplication.objects.filter(
        student=profile,
    ).select_related("subject", "teacher__user")
    return render(request, "leave_portal.html", {
        "profile": profile,
        "subjects": subjects,
        "teachers": teachers,
        "teacher_choices": teacher_choices,
        "applications": applications,
    })


    
    
    
@staff_required
def adminpanel(request):
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "issue_parent_code":
            student_id = request.POST.get("student_id", "")
            code_request_key = f"parent-code-admin:{request.user.pk}"
            student = (
                Register.objects.select_related("user").filter(pk=student_id).first()
                if student_id.isdigit()
                else None
            )
            if not student or not student.user_id:
                messages.error(request, "Choose a valid student account.")
            elif _auth_throttled_until(request, code_request_key):
                messages.error(request, "Too many verification-code requests. Try again in 15 minutes.")
            else:
                code = secrets.token_urlsafe(9).upper()
                ParentVerificationCode.objects.filter(
                    student=student,
                    is_active=True,
                    used_at__isnull=True,
                ).update(is_active=False)
                ParentVerificationCode.objects.create(
                    student=student,
                    code_hash=make_password(code),
                    issued_by=request.user,
                    expires_at=timezone.now() + timedelta(minutes=15),
                )
                _record_auth_failure(request, code_request_key)
                messages.success(
                    request,
                    f"One-time parent code for {student.student_name} "
                    f"({student.roll_no}): {code}. Give it directly to the parent; "
                    "it expires in 15 minutes.",
                )
            return redirect("/adminpanel/?section=parent-access")
        elif action == "add_room":
            room_number = request.POST.get("room_number", "").strip()
            room_type = request.POST.get("room_type", "").strip()
            purpose = request.POST.get("other_purpose", "").strip()
            other_label = request.POST.get("other_label", "").strip()
            valid_type = room_type in RoomInventory.RoomType.values
            valid_purpose = purpose in RoomInventory.OtherPurpose.values
            if not room_number or len(room_number) > 50 or not valid_type:
                messages.error(request, "Enter a room number and choose Theory, Lab, or Other.")
            elif room_type == RoomInventory.RoomType.OTHER and not valid_purpose:
                messages.error(request, "Choose Library, Sports, or Other for this facility.")
            elif (
                room_type == RoomInventory.RoomType.OTHER
                and purpose == RoomInventory.OtherPurpose.OTHER
                and not other_label
            ):
                messages.error(request, "Enter a name for this other facility.")
            elif len(other_label) > 50:
                messages.error(request, "Facility names cannot exceed 50 characters.")
            elif RoomInventory.objects.filter(room_number__iexact=room_number).exists():
                messages.error(request, "That room number is already in the room inventory.")
            else:
                room = RoomInventory(
                    room_number=room_number,
                    room_type=room_type,
                    other_purpose=purpose if room_type == RoomInventory.RoomType.OTHER else "",
                    other_label=other_label if purpose == RoomInventory.OtherPurpose.OTHER else "",
                )
                room.full_clean()
                room.save()
                if (
                    room.room_type == RoomInventory.RoomType.OTHER
                    and room.other_purpose == RoomInventory.OtherPurpose.LIBRARY
                ):
                    refresh_library_adjustment_rooms()
                messages.success(request, f"Room {room} was added to the inventory.")
            return redirect("/adminpanel/?section=rooms")
        elif action == "toggle_room":
            room_id = request.POST.get("room_id", "").strip()
            room = RoomInventory.objects.filter(pk=room_id).first() if room_id.isdigit() else None
            if not room:
                messages.error(request, "Choose a valid room.")
            else:
                room.is_active = not room.is_active
                room.save(update_fields=["is_active"])
                if (
                    room.room_type == RoomInventory.RoomType.OTHER
                    and room.other_purpose == RoomInventory.OtherPurpose.LIBRARY
                ):
                    refresh_library_adjustment_rooms()
                status = "active" if room.is_active else "inactive"
                messages.success(request, f"Room {room.room_number} is now {status}.")
            return redirect("/adminpanel/?section=rooms")
        else:
            title = request.POST.get("title", "").strip()
            body = request.POST.get("message", "").strip()
            audience = request.POST.get("audience", "").strip()

            if (
                not title or len(title) > 150
                or not body or len(body) > 10000
                or audience not in Announcement.Audience.values
            ):
                messages.error(request, "Enter a title, message, and valid audience.")
            else:
                Announcement.objects.create(
                    created_by=request.user,
                    title=title,
                    message=body,
                    audience=audience,
                )
                messages.success(request, "Announcement posted successfully.")
                return redirect("/adminpanel/?section=announcements")

    return render(request, "adminpanel.html", {
        "announcements": Announcement.objects.filter(
            created_by=request.user,
        ).select_related("created_by").order_by("-created_at")[:30],
        "show_announcements": (
            request.GET.get("section") == "announcements"
            or request.method == "POST"
        ),
        "show_parent_access": request.GET.get("section") == "parent-access",
        "show_rooms": request.GET.get("section") == "rooms",
        "room_inventory": RoomInventory.objects.all(),
        "parent_code_students": Register.objects.select_related("user").filter(
            user__isnull=False
        ).order_by("student_name"),
        "parent_verification_codes": ParentVerificationCode.objects.select_related(
            "student", "issued_by"
        )[:30],
    })


@login_required
@require_POST
def mark_announcements_read(request):
    announcement_ids = request.POST.getlist("announcement_ids")
    notice_keys = request.POST.getlist("notice_keys")
    marked = 0

    if hasattr(request.user, "teacher_profile"):
        available = Announcement.objects.filter(
            audience=Announcement.Audience.TEACHERS,
        )
    else:
        profile = Register.objects.filter(user=request.user).first()
        available = Announcement.objects.none()
        parent = ParentProfile.objects.filter(user=request.user).first()
        if parent:
            children = Register.objects.filter(parent_links__parent=parent)
            for child in children:
                available = available | Announcement.objects.filter(
                    audience=Announcement.Audience.STUDENTS,
                ).filter(
                    Q(branch__isnull=True) | Q(branch__iexact=child.branch),
                    Q(semester__isnull=True) | Q(semester=child.semester),
                )
        elif profile:
            available = Announcement.objects.filter(
                audience=Announcement.Audience.STUDENTS,
            ).filter(
                Q(branch__isnull=True) | Q(branch__iexact=profile.branch),
                Q(semester__isnull=True) | Q(semester=profile.semester),
            )

    if announcement_ids:
        rows = [
            AnnouncementRead(announcement_id=announcement_id, user=request.user)
            for announcement_id in available.filter(pk__in=announcement_ids)
            .exclude(reads__user=request.user)
            .values_list("pk", flat=True)
        ]
        AnnouncementRead.objects.bulk_create(rows, ignore_conflicts=True)
        marked += len(rows)

    if hasattr(request.user, "teacher_profile"):
        teacher = request.user.teacher_profile
        allowed_adjustments = TeacherLeaveAdjustment.objects.filter(
            Q(original_teacher=teacher) | Q(substitute_teacher=teacher),
            class_date__gte=date.today(),
        )
        allowed_tests = ClassTest.objects.none()
        allowed_homework = Homework.objects.none()
    else:
        profile = Register.objects.filter(user=request.user).first()
        allowed_adjustments = TeacherLeaveAdjustment.objects.none()
        allowed_tests = ClassTest.objects.none()
        allowed_homework = Homework.objects.none()
        parent = ParentProfile.objects.filter(user=request.user).first()
        if parent:
            student_scope = Q(pk__in=[])
            for child in Register.objects.filter(parent_links__parent=parent):
                student_scope |= Q(
                    subject__branch__iexact=child.branch,
                    subject__semester=child.semester,
                )
            allowed_adjustments = TeacherLeaveAdjustment.objects.filter(
                student_scope,
                class_date__gte=date.today(),
            )
            allowed_tests = ClassTest.objects.filter(student_scope)
            allowed_homework = Homework.objects.filter(student_scope)
        elif profile:
            allowed_adjustments = TeacherLeaveAdjustment.objects.filter(
                subject__branch__iexact=profile.branch,
                subject__semester=profile.semester,
                class_date__gte=date.today(),
            )
            allowed_tests = ClassTest.objects.filter(
                subject__branch__iexact=profile.branch,
                subject__semester=profile.semester,
            )

    for key in notice_keys:
        try:
            notice_type, raw_id = key.split(":", 1)
            object_id = int(raw_id)
        except (ValueError, AttributeError):
            continue
        if notice_type == DashboardNoticeRead.NoticeType.TEST:
            notice = allowed_tests.filter(pk=object_id).first()
            version = notice.created_at if notice else None
            if notice and not hasattr(request.user, "teacher_profile"):
                if profile:
                    results = TestResult.objects.filter(test=notice, student=profile)
                else:
                    parent = ParentProfile.objects.filter(user=request.user).first()
                    student_ids = Register.objects.filter(
                        parent_links__parent=parent,
                    ).values_list("pk", flat=True) if parent else []
                    results = TestResult.objects.filter(
                        test=notice,
                        student_id__in=student_ids,
                    )
                latest_result = results.order_by("-updated_at").first()
                if latest_result and latest_result.updated_at > version:
                    version = latest_result.updated_at
        elif notice_type == DashboardNoticeRead.NoticeType.ADJUSTMENT:
            notice = allowed_adjustments.filter(pk=object_id).first()
            version = notice.updated_at if notice else None
        elif notice_type == DashboardNoticeRead.NoticeType.HOMEWORK:
            notice = allowed_homework.filter(pk=object_id).first()
            version = notice.updated_at if notice else None
        else:
            continue
        if version is None:
            continue
        DashboardNoticeRead.objects.update_or_create(
            user=request.user,
            notice_type=notice_type,
            object_id=object_id,
            defaults={"seen_updated_at": version},
        )
        marked += 1

    return JsonResponse({"marked": marked})


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
    branch_names = request.POST.getlist("branches")
    branch_names = [b.strip() for b in branch_names if b.strip()]
    subject_ids = request.POST.getlist("subjects")

    if not all([name, username, password, employee_id, branch_names]):
        messages.error(
            request,
            "Name, username, password, employee ID and at least one branch are required."
        )
        return redirect("manage_teachers")

    try:
        if (
            len(name) > 150 or len(username) > 150 or len(employee_id) > 30
            or len(email) > 254 or len(phone) > 15
            or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .&/-]{0,49}", branch) for branch in branch_names)
        ):
            raise ValidationError("Some teacher fields are invalid or too long.")
        if email:
            validate_email(email)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("manage_teachers")

    try:
        validate_password(password, User(username=username, first_name=name))
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("manage_teachers")

    if User.objects.filter(username=username).exists():
        messages.error(request, "This username already exists.")
        return redirect("manage_teachers")

    if TeacherProfile.objects.filter(employee_id=employee_id).exists():
        messages.error(request, "This employee ID already exists.")
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
                branch=branch_names[0]
            )

            selected_branches = []
            for branch_name in branch_names:
                branch_obj, _ = Branch.objects.get_or_create(name=branch_name)
                selected_branches.append(branch_obj)

            teacher.branches.set(selected_branches)

            valid_subjects = Subject.objects.filter(
                id__in=subject_ids,
                branch__in=branch_names,
                is_active=True
            )
            teacher.subjects.set(valid_subjects)

        messages.success(request, f"Teacher {name} added successfully.")

    except IntegrityError:
        messages.error(request, "Unable to create teacher.")

    return redirect("manage_teachers")
from .models import TeacherProfile, Subject, Branch

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
    branch_names = request.POST.getlist("branches")
    branch_names = [b.strip() for b in branch_names if b.strip()]
    password = request.POST.get("password", "")
    is_active = request.POST.get("is_active") == "on"
    subject_ids = request.POST.getlist("subjects")

    if not all([name, username, employee_id, branch_names]):
        messages.error(
            request,
            "Name, username, employee ID and at least one branch are required."
        )
        return redirect("manage_teachers")

    try:
        if (
            len(name) > 150 or len(username) > 150 or len(employee_id) > 30
            or len(email) > 254 or len(phone) > 15
            or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .&/-]{0,49}", branch) for branch in branch_names)
        ):
            raise ValidationError("Some teacher fields are invalid or too long.")
        if email:
            validate_email(email)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("manage_teachers")

    if User.objects.filter(username=username).exclude(id=teacher.user.id).exists():
        messages.error(request, "This username is already being used.")
        return redirect("manage_teachers")

    if TeacherProfile.objects.filter(employee_id=employee_id).exclude(id=teacher.id).exists():
        messages.error(request, "This employee ID is already being used.")
        return redirect("manage_teachers")

    if password:
        try:
            validate_password(password, User(username=username, first_name=name))
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
            return redirect("manage_teachers")

    try:
        with transaction.atomic():
            teacher.user.first_name = name
            teacher.user.username = username
            teacher.user.email = email

            if password:
                teacher.user.set_password(password)

            teacher.user.save()

            teacher.employee_id = employee_id
            teacher.phone = phone
            teacher.branch = branch_names[0]
            teacher.is_active = is_active
            teacher.save()

            selected_branches = []
            for branch_name in branch_names:
                branch_obj, _ = Branch.objects.get_or_create(name=branch_name)
                selected_branches.append(branch_obj)

            teacher.branches.set(selected_branches)

            valid_subjects = Subject.objects.filter(
                id__in=subject_ids,
                branch__in=branch_names,
                is_active=True
            )
            teacher.subjects.set(valid_subjects)

        messages.success(
            request,
            f"{name}'s details updated successfully."
        )

    except IntegrityError:
        messages.error(request, "Unable to update teacher.")

    return redirect("manage_teachers")


@staff_required
@require_POST
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

def _record_attendance_once(student_user, subject, jpeg_bytes, attendance_date):
    attendance = Attendance(
        student=student_user,
        subject=subject,
        attendance_date=attendance_date,
    )
    try:
        with transaction.atomic():
            attendance.face_image.save(
                f"{uuid.uuid4().hex}.jpg",
                ContentFile(jpeg_bytes),
                save=True,
            )
    except IntegrityError:
        if attendance.face_image.name:
            attendance.face_image.storage.delete(attendance.face_image.name)
        return None
    return attendance


@staff_or_teacher_required
def liveattendance(request, teacher=None):

    # =====================================================
    # TEACHER
    # =====================================================

    if teacher is not None:

        assigned_subjects = list(
            teacher.subjects.filter(is_active=True).order_by(
                "branch", "semester", "name"
            )
        )
        teacher_branches = list(
            teacher.branches.order_by("name").values_list("name", flat=True)
        )
        for branch_name in [teacher.branch] + [
            subject.branch for subject in assigned_subjects
        ]:
            if branch_name and branch_name.casefold() not in {
                branch.casefold() for branch in teacher_branches
            }:
                teacher_branches.append(branch_name)
        valid_branches = {branch.casefold() for branch in teacher_branches}
        assigned_subjects = [
            subject for subject in assigned_subjects
            if subject.branch.casefold() in valid_branches
        ]
        branches_with_subjects = {
            subject.branch.casefold() for subject in assigned_subjects
        }
        default_teacher_branch = next(
            (
                branch for branch in teacher_branches
                if branch.casefold() == teacher.branch.casefold()
                and branch.casefold() in branches_with_subjects
            ),
            next(
                (
                    branch for branch in teacher_branches
                    if branch.casefold() in branches_with_subjects
                ),
                teacher_branches[0] if teacher_branches else "",
            ),
        )
        assigned_semesters = sorted(
            {(subject.branch, subject.semester) for subject in assigned_subjects},
            key=lambda item: (item[0].casefold(), int(item[1])),
        )

        return render(
            request,
            "liveattendance.html",
            {
                "teacher": teacher,
                "teacher_mode": True,

                # Teacher ka branch automatic
                "teacher_branch": default_teacher_branch,
                "teacher_branches": teacher_branches,

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
    today = local_attendance_date()
    if Attendance.objects.filter(student=matched_student.user, subject=subject, attendance_date=today).exists():
        context["error"] = "Attendance has already been marked for this student and subject today."
        return render(request, "liveattendance.html", context)
    _, jpeg = cv2.imencode(".jpg", frame)
    attendance = _record_attendance_once(
        matched_student.user,
        subject,
        jpeg.tobytes(),
        today,
    )
    if attendance is None:
        context["error"] = "Attendance has already been marked for this student and subject today."
        return render(request, "liveattendance.html", context)
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
    (
        summary,
        total_attended,
        overall_total_classes,
        overall_percentage,
        last_attendance,
    ) = get_attendance_summary(request.user)

    return render(request, "attendance_summary.html", {
        "summary": summary,
        "total_attended": total_attended,
        "overall_total_classes": overall_total_classes,
        "overall_percentage": overall_percentage,
        "total_leave_credit": sum(item["leave_credited"] for item in summary),
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

@staff_required
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
        student_name = request.POST.get("student_name", "").strip()
        semester = request.POST.get("semester", "").strip()
        branch = request.POST.get("branch", "").strip()
        if (
            not student_name or len(student_name) > 100
            or not roll_no or len(roll_no) > 20
            or semester not in dict(Subject.SEMESTER_CHOICES)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .&/-]{0,49}", branch)
        ):
            messages.error(request, "Enter valid student details within the allowed field lengths.")
            return render(request, "edit_student.html", {"student": student})
        if Register.objects.exclude(id=student.id).filter(roll_no=roll_no).exists() or (student.user and User.objects.exclude(id=student.user_id).filter(username=roll_no).exists()):
            messages.error(request, "Roll number already exists.")
            return render(request, "edit_student.html", {"student": student})
        with transaction.atomic():
            student.student_name = student_name
            student.roll_no = roll_no
            student.semester = semester
            student.branch = branch
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

def approved_leave_credit(profile, subject, total_classes, attended_dates):
    """Return approved missed sessions; the overall cap is applied later."""
    if not profile or total_classes <= 0:
        return Decimal("0")

    scheduled_weekdays = set(
        TimetableSlot.objects.filter(
            subject=subject,
            status=TimetableSlot.Status.PUBLISHED,
        ).values_list("day", flat=True)
    )
    if not scheduled_weekdays:
        return Decimal("0")

    recorded_class_dates = set(
        Attendance.objects.filter(subject=subject).dates("timestamp", "day")
    )
    approved_dates = set()
    applications = LeaveApplication.objects.filter(
        student=profile,
        subject=subject,
        status=LeaveApplication.Status.APPROVED,
    )
    for application in applications:
        day = application.start_date
        while day <= application.end_date:
            if (
                day.weekday() in scheduled_weekdays
                and day in recorded_class_dates
                and day not in attended_dates
            ):
                approved_dates.add(day)
            day += timedelta(days=1)

    return Decimal(len(approved_dates))


def get_attendance_summary(user):
    attendance_records = Attendance.objects.filter(student=user)
    profile = Register.objects.filter(user=user).first()
    subjects = Subject.objects.all()
    if profile:
        subjects = subjects.filter(
            branch__iexact=profile.branch,
            semester=profile.semester,
        )

    summary = []
    total_attended = 0
    overall_total_classes = 0
    total_leave_credit = Decimal("0")

    for subject in subjects:
        total_classes = Attendance.objects.filter(subject=subject).dates(
            "timestamp", "day"
        ).count()
        attended_dates = set(
            attendance_records.filter(subject=subject).dates("timestamp", "day")
        )
        attended = len(attended_dates)
        leave_credit = approved_leave_credit(
            profile,
            subject,
            total_classes,
            attended_dates,
        )
        raw_percentage = (
            (Decimal(attended) / Decimal(total_classes) * Decimal("100"))
            if total_classes else Decimal("0")
        )
        if attended > 0 or leave_credit > 0:
            summary.append({
                "name": subject.name,
                "attended": attended,
                "total": total_classes,
                "leave_credited": leave_credit,
                "raw_percentage": round(raw_percentage, 2),
                "percentage": round(raw_percentage, 2),
            })

        total_attended += attended
        overall_total_classes += total_classes
        total_leave_credit += leave_credit

    raw_overall_percentage = (
        Decimal(total_attended) / Decimal(overall_total_classes) * Decimal("100")
        if overall_total_classes else Decimal("0")
    )
    eligible_for_leave_credit = raw_overall_percentage >= Decimal("75")
    maximum_leave_credit = (
        Decimal(overall_total_classes) * Decimal("0.05")
        if eligible_for_leave_credit else Decimal("0")
    )
    total_leave_credit = min(total_leave_credit, maximum_leave_credit)

    # Allocate the single overall allowance across subjects for the detail table.
    remaining_credit = total_leave_credit
    for item in summary:
        credited = min(Decimal(item["leave_credited"]), remaining_credit)
        item["leave_credited"] = credited
        item["percentage"] = round(
            min(
                Decimal("100"),
                (Decimal(item["attended"]) + credited) / Decimal(item["total"]) * Decimal("100"),
            ) if item["total"] else Decimal("0"),
            2,
        )
        remaining_credit -= credited

    overall_percentage = (
        round(
            min(
                Decimal("100"),
                (Decimal(total_attended) + total_leave_credit)
                / Decimal(overall_total_classes) * Decimal("100"),
            ),
            2,
        )
        if overall_total_classes else 0
    )

    last_attendance = attendance_records.order_by("-timestamp").first()

    return (
        summary,
        total_attended,
        overall_total_classes,
        overall_percentage,
        last_attendance,
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

            teacher_branches = list(
                teacher.branches.values_list("name", flat=True)
            )
            if teacher.branch:
                teacher_branches.append(teacher.branch)
            if (
                not teacher.is_active
                or branch.casefold() not in {item.casefold() for item in teacher_branches}
            ):

                return JsonResponse({
                    "success": False,
                    "error": "Invalid branch for this teacher."
                }, status=400)

            # Teacher ke assigned subject ko database se check
            try:

                subject = teacher.subjects.get(
                    name=subject_name,
                    semester=semester,
                    branch__iexact=branch,
                    is_active=True
                )

            except (Subject.DoesNotExist, Subject.MultipleObjectsReturned):

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

        known_students = []
        known_encodings = []
        for student in students:
            if not student.face_image:
                continue
            image_path = student.face_image.path
            try:
                modified_at_ns = os.stat(image_path).st_mtime_ns
            except (OSError, ValueError):
                continue
            registered_encoding = _cached_student_face_encoding(image_path, modified_at_ns)
            if registered_encoding is not None:
                known_students.append(student)
                known_encodings.append(registered_encoding)

        tolerance = 0.50
        match_candidates = []
        for face_index, captured_encoding in enumerate(captured_encodings):
            if not known_encodings:
                break
            distances = face_recognition.face_distance(known_encodings, captured_encoding)
            for student_index, distance in enumerate(distances):
                if distance <= tolerance:
                    match_candidates.append((float(distance), face_index, student_index))

        # Assign every detected face and every student at most once per frame.
        matched_students = []
        assigned_faces = set()
        assigned_students = set()
        for distance, face_index, student_index in sorted(match_candidates):
            if face_index in assigned_faces or student_index in assigned_students:
                continue
            assigned_faces.add(face_index)
            assigned_students.add(student_index)
            matched_students.append((known_students[student_index], distance))

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

        today = local_attendance_date()

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
                    attendance_date=today,
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

            # =================================================
            # CREATE ATTENDANCE
            # =================================================

            attendance = _record_attendance_once(
                matched_student.user,
                subject,
                jpeg.tobytes(),
                today,
            )
            if attendance is None:
                already_marked_students.append({
                    "student_name": matched_student.student_name,
                    "roll_no": matched_student.roll_no,
                    "face_distance": round(float(best_distance), 4),
                })
                continue


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
@staff_required
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
    
@staff_required
@require_POST
def add_subject(request):

    if request.method == "POST":

        name = request.POST.get("name", "").strip()
        semester = request.POST.get("semester", "").strip()
        branch = request.POST.get("branch", "").strip()

        if (
            not name or len(name) > 100
            or semester not in dict(Subject.SEMESTER_CHOICES)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .&/-]{0,49}", branch)
        ):
            messages.error(request, "Enter valid subject details within the allowed field lengths.")
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


@staff_required
@require_POST
def edit_subject(request, subject_id):

    subject = get_object_or_404(Subject, id=subject_id)

    if request.method == "POST":

        name = request.POST.get("name", "").strip()
        semester = request.POST.get("semester", "").strip()
        branch = request.POST.get("branch", "").strip()

        is_active = request.POST.get("is_active") == "on"

        if (
            not name or len(name) > 100
            or semester not in dict(Subject.SEMESTER_CHOICES)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .&/-]{0,49}", branch)
        ):
            messages.error(request, "Enter valid subject details within the allowed field lengths.")
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

@staff_required
@require_POST
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

        



from .models import Register, Subject, Attendance, TeacherProfile


from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Count, Q
from django.utils import timezone

from .models import (
    Announcement,
    AnnouncementRead,
    Attendance,
    ClassTest,
    CollegeHoliday,
    DashboardNoticeRead,
    Homework,
    LeaveApplication,
    local_attendance_date,
    ParentProfile,
    ParentStudentLink,
    ParentTeacherMessage,
    ParentVerificationCode,
    Register,
    RoomInventory,
    Subject,
    TeacherLeaveApplication,
    TeacherLeaveAdjustment,
    TestResult,
    TeacherProfile,
)


class ParentPasswordResetForm(PasswordResetForm):
    def get_users(self, email):
        matching_users = User.objects.filter(
            email__iexact=email,
            is_active=True,
            parent_profile__isnull=False,
        )
        return (
            user for user in matching_users
            if user.has_usable_password()
        )

    def save(self, *, request=None, **kwargs):
        email = self.cleaned_data.get("email", "").strip().casefold()
        request_key = f"parent-password-reset:{email}"
        if request and _auth_throttled_until(request, request_key):
            # Keep the normal success response to avoid account enumeration.
            return None
        if request:
            _record_auth_failure(request, request_key)
        return super().save(request=request, **kwargs)


@never_cache
def parent_register(request):
    if request.user.is_authenticated and ParentProfile.objects.filter(user=request.user).exists():
        return redirect("parent_dashboard")
    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        email = request.POST.get("email", "").strip().casefold()
        roll_no = request.POST.get("roll_no", "").strip()
        relationship = request.POST.get("relationship", "").strip()
        code = request.POST.get("verification_code", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        validation_error = None
        if (
            not full_name or len(full_name) > 150
            or not email or len(email) > 150
            or not roll_no or len(roll_no) > 20
            or not relationship or not code or len(code) > 128
        ):
            validation_error = "Complete every field to create the parent account."
        try:
            validate_email(email)
        except ValidationError:
            validation_error = "Enter a valid email address."
        if relationship not in ParentStudentLink.Relationship.values:
            validation_error = "Choose Father, Mother, or Guardian."
        if password != confirm_password:
            validation_error = "Passwords do not match."
        if not validation_error:
            try:
                validate_password(
                    password,
                    User(username=email, email=email, first_name=full_name),
                )
            except ValidationError as error:
                validation_error = " ".join(error.messages)
        if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists():
            validation_error = "An account already uses this email address."

        student = None
        code_record = None
        if validation_error is None:
            student = Register.objects.select_related("user").filter(
                roll_no__iexact=roll_no,
            ).first()
            now = timezone.now()
            if student and student.user_id:
                code_record = ParentVerificationCode.objects.filter(
                    student=student,
                    is_active=True,
                    used_at__isnull=True,
                    expires_at__gt=now,
                    attempts__lt=5,
                ).order_by("-issued_at").first()
            if not code_record or not check_password(code, code_record.code_hash):
                if code_record:
                    code_record.attempts += 1
                    if code_record.attempts >= 5:
                        code_record.is_active = False
                    code_record.save(update_fields=["attempts", "is_active"])
                validation_error = "Student ID or verification code is invalid."

        if validation_error:
            messages.error(request, validation_error)
        else:
            try:
                with transaction.atomic():
                    locked_code = ParentVerificationCode.objects.select_for_update().get(
                        pk=code_record.pk,
                        is_active=True,
                        used_at__isnull=True,
                        expires_at__gt=timezone.now(),
                        attempts__lt=5,
                    )
                    if not check_password(code, locked_code.code_hash):
                        raise ValueError("The verification code is no longer valid.")
                    user = User.objects.create_user(
                        username=email,
                        email=email,
                        password=password,
                        first_name=full_name,
                    )
                    parent = ParentProfile.objects.create(user=user)
                    ParentStudentLink.objects.create(
                        parent=parent,
                        student=student,
                        relationship=relationship,
                    )
                    locked_code.used_at = timezone.now()
                    locked_code.is_active = False
                    locked_code.save(update_fields=["used_at", "is_active"])
                messages.success(request, "Parent account verified. You can now log in.")
                return redirect("parent_login")
            except (IntegrityError, ParentVerificationCode.DoesNotExist, ValueError):
                messages.error(request, "That code was already used or is no longer valid. Ask the school for a new code.")
    return render(request, "parent_register.html")


@never_cache
def parent_login(request):
    if request.user.is_authenticated and ParentProfile.objects.filter(user=request.user).exists():
        return redirect("parent_dashboard")
    if request.method == "POST":
        email = request.POST.get("email", "").strip().casefold()
        if _auth_throttled_until(request, email):
            messages.error(request, "Too many login attempts. Try again in 15 minutes.")
            return render(request, "parent_login.html")
        user = authenticate(
            request,
            username=email,
            password=request.POST.get("password", ""),
        )
        if user and ParentProfile.objects.filter(user=user).exists():
            _clear_auth_failures(request, email)
            auth_login(request, user)
            return redirect("parent_dashboard")
        _record_auth_failure(request, email)
        messages.error(request, "Invalid parent email or password.")
    return render(request, "parent_login.html")


@login_required
@never_cache
@require_POST
def parent_logout(request):
    if not ParentProfile.objects.filter(user=request.user).exists():
        return redirect("login")
    auth_logout(request)
    return redirect("parent_login")


@login_required
@never_cache
def parent_report_card(request, student_link_id):
    parent = ParentProfile.objects.filter(user=request.user).first()
    student_link = ParentStudentLink.objects.filter(
        pk=student_link_id,
        parent=parent,
    ).select_related("student").first() if parent else None
    if not student_link:
        return HttpResponse("Student link not found.", status=404)

    student = student_link.student
    tests = ClassTest.objects.filter(
        subject__branch__iexact=student.branch,
        subject__semester=student.semester,
    ).select_related("subject").order_by("test_date", "subject__name")
    results = {
        result.test_id: result
        for result in TestResult.objects.filter(
            student=student,
            test__in=tests,
        )
    }
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="report-card-{student.pk}.pdf"'
    )
    report = canvas.Canvas(response, pagesize=letter)
    _page_width, page_height = letter
    y = page_height - 56
    report.setFont("Helvetica-Bold", 18)
    report.drawString(48, y, "Student Test Report")
    y -= 32
    report.setFont("Helvetica", 11)
    for label in (
        f"Student: {student.student_name}",
        f"Roll number: {student.roll_no}",
        f"Branch: {student.branch}    Semester: {student.semester}",
        f"Parent: {request.user.get_full_name() or request.user.email}",
    ):
        report.drawString(48, y, label[:105])
        y -= 19
    y -= 12
    report.setFont("Helvetica-Bold", 10)
    report.drawString(48, y, "Date")
    report.drawString(130, y, "Subject / Test")
    report.drawString(430, y, "Marks")
    y -= 10
    report.line(48, y, _page_width - 48, y)
    y -= 18
    report.setFont("Helvetica", 10)
    if not tests:
        report.drawString(48, y, "No tests have been published for this class.")
    else:
        for class_test in tests:
            if y < 60:
                report.showPage()
                y = page_height - 56
                report.setFont("Helvetica", 10)
            result = results.get(class_test.pk)
            marks = (
                f"{result.marks_obtained} / {class_test.max_marks}"
                if result else "Not published"
            )
            report.drawString(48, y, class_test.test_date.strftime("%d %b %Y"))
            report.drawString(
                130,
                y,
                f"{class_test.subject.name} - {class_test.title}"[:48],
            )
            report.drawString(430, y, marks)
            y -= 18
    report.save()
    return response


@login_required
@never_cache
def parent_dashboard(request):
    parent = ParentProfile.objects.filter(user=request.user).first()
    if not parent:
        messages.error(request, "This account is not registered as a parent.")
        return redirect("parent_login")

    student_links = list(
        ParentStudentLink.objects.filter(parent=parent)
        .select_related("student", "student__user")
        .order_by("student__student_name")
    )
    if not student_links:
        messages.error(request, "No student is linked to this parent account.")
        return redirect("parent_login")

    selected_link = next(
        (
            link for link in student_links
            if str(link.pk) == request.GET.get("child")
        ),
        student_links[0],
    )
    student = selected_link.student
    subjects = Subject.objects.filter(
        is_active=True,
        branch__iexact=student.branch,
        semester=student.semester,
    )
    teachers = TeacherProfile.objects.filter(
        is_active=True,
        subjects__in=subjects,
    ).select_related("user").distinct().order_by("user__first_name", "user__username")

    if request.method == "POST" and request.POST.get("action") == "send_parent_message":
        requested_link = ParentStudentLink.objects.filter(
            pk=request.POST.get("student_link_id") if request.POST.get("student_link_id", "").isdigit() else None,
            parent=parent,
        ).select_related("student").first()
        requested_subjects = Subject.objects.filter(
            is_active=True,
            branch__iexact=requested_link.student.branch,
            semester=requested_link.student.semester,
        ) if requested_link else Subject.objects.none()
        permitted_teachers = TeacherProfile.objects.filter(
            is_active=True,
            subjects__in=requested_subjects,
        ).distinct()
        teacher_id = request.POST.get("teacher_id", "")
        selected_teacher = (
            permitted_teachers.filter(pk=teacher_id).first()
            if teacher_id.isdigit()
            else None
        )
        body = request.POST.get("message", "").strip()
        if not requested_link or not selected_teacher or not body or len(body) > 4000:
            messages.error(request, "Choose your child's teacher and enter a message (up to 4,000 characters).")
        else:
            ParentTeacherMessage.objects.create(
                student_link=requested_link,
                teacher=selected_teacher,
                sender=request.user,
                message=body,
            )
            messages.success(request, "Your message was sent to the teacher.")
            return redirect(f"{reverse('parent_dashboard')}?child={requested_link.pk}&section=messages")

    student_user = student.user
    attendance_summary, total_attended, total_classes, overall_percentage, last_attendance = (
        get_attendance_summary(student_user)
    ) if student_user else ([], 0, 0, 0, None)
    timetable = list(
        TimetableSlot.objects.filter(
            configuration__branch__iexact=student.branch,
            configuration__semester=student.semester,
            status=TimetableSlot.Status.PUBLISHED,
        ).select_related("subject", "teacher__user").order_by("day", "start_time")
    )
    today = date.today()
    student_attendance = Attendance.objects.filter(
        student=student_user,
        timestamp__date__gte=today.replace(day=1),
        timestamp__date__lte=today,
    ) if student_user else Attendance.objects.none()
    present_by_day = set(student_attendance.values_list("subject_id", "timestamp__date"))
    calendar_holidays = CollegeHoliday.objects.filter(
        approval_status=CollegeHoliday.ApprovalStatus.APPROVED,
        applies_to_all=True,
        start_date__lte=today,
        end_date__gte=today.replace(day=1),
    )
    holiday_dates = set()
    for holiday in calendar_holidays:
        holiday_day = max(holiday.start_date, today.replace(day=1))
        holiday_end = min(holiday.end_date, today)
        while holiday_day <= holiday_end:
            holiday_dates.add(holiday_day)
            holiday_day += timedelta(days=1)
    attendance_calendar = []
    day = today.replace(day=1)
    while day <= today:
        if day in holiday_dates:
            day += timedelta(days=1)
            continue
        day_slots = [slot for slot in timetable if slot.day == day.weekday()]
        for slot in day_slots:
            if day < today:
                status = "Present" if (slot.subject_id, day) in present_by_day else "Absent"
            elif (slot.subject_id, day) in present_by_day:
                status = "Present"
            else:
                status = "Not marked yet"
            attendance_calendar.append({
                "date": day,
                "subject": slot.subject.name,
                "time": slot.start_time,
                "status": status,
            })
        day += timedelta(days=1)
    today_slots = [slot for slot in timetable if slot.day == today.weekday()]
    today_marked = student_attendance.filter(timestamp__date=today).exists()
    today_status = (
        "School holiday"
        if today in holiday_dates
        else "No classes scheduled"
        if not today_slots
        else "Attendance recorded"
        if today_marked
        else "Not marked yet"
    )

    results_by_test = {
        result.test_id: result
        for result in TestResult.objects.filter(
            student=student,
            test__subject__in=subjects,
        ).select_related("test")
    }
    class_tests = list(
        ClassTest.objects.filter(subject__in=subjects)
        .select_related("subject", "teacher__user")
        .order_by("-test_date", "subject__name")
    )
    for class_test in class_tests:
        class_test.student_result = results_by_test.get(class_test.pk)

    homework = list(
        Homework.objects.filter(subject__in=subjects)
        .select_related("subject", "teacher__user")
        .order_by("due_date", "-created_at")[:50]
    )
    announcements = Announcement.objects.filter(
        audience=Announcement.Audience.STUDENTS,
    ).filter(
        Q(branch__isnull=True) | Q(branch__iexact=student.branch),
        Q(semester__isnull=True) | Q(semester=student.semester),
    ).select_related("teacher__user", "created_by").order_by("-created_at")
    adjustments = list(
        TeacherLeaveAdjustment.objects.filter(
            subject__branch__iexact=student.branch,
            subject__semester=student.semester,
            class_date__gte=today,
            timetable_slot__isnull=False,
        ).select_related(
            "subject", "original_teacher__user", "substitute_teacher__user"
        ).order_by("class_date", "start_time")
    )
    parent_messages = ParentTeacherMessage.objects.filter(
        student_link=selected_link,
    ).select_related("teacher__user", "sender").order_by("created_at")

    unread_announcements = list(
        announcements.exclude(reads__user=request.user).distinct()[:20]
    )
    parent_notice_reads = {
        (row.notice_type, row.object_id): row.seen_updated_at
        for row in DashboardNoticeRead.objects.filter(user=request.user)
    }
    unread_parent_updates = []
    for class_test in class_tests:
        result = class_test.student_result
        version = max(
            class_test.created_at,
            result.updated_at if result else class_test.created_at,
        )
        seen_at = parent_notice_reads.get((DashboardNoticeRead.NoticeType.TEST, class_test.pk))
        if (
            class_test.test_date >= today or (result and result.updated_at > class_test.created_at)
        ) and (seen_at is None or version > seen_at):
            unread_parent_updates.append({
                "key": f"TEST:{class_test.pk}",
                "type": "Test or result",
                "title": class_test.title,
                "detail": f"{class_test.subject.name} · {class_test.test_date:%b %d, %Y} · {class_test.max_marks} marks"
                + (f" · Result: {result.marks_obtained}/{class_test.max_marks}" if result else ""),
            })
    for item in homework:
        seen_at = parent_notice_reads.get((DashboardNoticeRead.NoticeType.HOMEWORK, item.pk))
        if item.due_date >= today and (seen_at is None or item.updated_at > seen_at):
            unread_parent_updates.append({
                "key": f"HOMEWORK:{item.pk}",
                "type": "Homework",
                "title": item.title,
                "detail": f"{item.subject.name} · Due {item.due_date:%b %d, %Y}",
            })
    for item in adjustments:
        seen_at = parent_notice_reads.get((DashboardNoticeRead.NoticeType.ADJUSTMENT, item.pk))
        if seen_at is None or item.updated_at > seen_at:
            unread_parent_updates.append({
                "key": f"ADJUSTMENT:{item.pk}",
                "type": "Timetable change",
                "title": item.subject.name,
                "detail": f"{item.class_date:%b %d, %Y} · {item.start_time:%I:%M %p}–{item.end_time:%I:%M %p}",
            })
    school_holidays = list(
        CollegeHoliday.objects.filter(
            approval_status=CollegeHoliday.ApprovalStatus.APPROVED,
            applies_to_all=True,
            end_date__gte=today,
        ).order_by("start_date")[:20]
    )
    notifications = (
        [{"type": "Announcement", "title": item.title, "date": item.created_at, "text": item.message}
         for item in unread_announcements]
        + [{"type": "Test", "title": item.title, "date": item.test_date, "text": f"{item.subject.name} · {item.max_marks} marks"}
           for item in class_tests if item.test_date >= today]
        + [{"type": "Homework", "title": item.title, "date": item.due_date, "text": item.subject.name}
           for item in homework if item.due_date >= today]
        + [{"type": "Timetable change", "title": item.subject.name, "date": item.class_date, "text": f"{item.start_time}–{item.end_time}"}
           for item in adjustments]
    )
    notifications.extend(
        {
            "type": "School holiday",
            "title": holiday.name,
            "date": holiday.start_date,
            "text": f"{holiday.start_date:%b %d, %Y} – {holiday.end_date:%b %d, %Y}",
        }
        for holiday in school_holidays
    )
    if overall_percentage < 75 and total_classes:
        notifications.append({
            "type": "Attendance alert",
            "title": "Attendance below 75%",
            "date": today,
            "text": f"Current overall attendance is {overall_percentage}%.",
        })

    return render(request, "parent_dashboard.html", {
        "parent": parent,
        "student_links": student_links,
        "student_link": selected_link,
        "student": student,
        "today_status": today_status,
        "today_classes": today_slots,
        "attendance_summary": attendance_summary,
        "total_attended": total_attended,
        "total_classes": total_classes,
        "overall_percentage": overall_percentage,
        "attendance_calendar": attendance_calendar,
        "class_tests": class_tests,
        "upcoming_tests": [item for item in class_tests if item.test_date >= today],
        "homework": homework,
        "pending_homework_count": sum(item.due_date >= today for item in homework),
        "timetable": timetable,
        "adjustments": adjustments,
        "school_holidays": school_holidays,
        "announcements": announcements[:30],
        "notifications": notifications,
        "unread_announcements": unread_announcements,
        "unread_parent_updates": unread_parent_updates,
        "teachers": teachers,
        "parent_messages": parent_messages,
    })


@login_required
@require_POST
def teacher_homework(request, teacher):
    subject_id = request.POST.get("subject_id", "")
    subject = (
        teacher.subjects.filter(pk=subject_id, is_active=True).first()
        if subject_id.isdigit()
        else None
    )
    title = request.POST.get("title", "").strip()
    instructions = request.POST.get("instructions", "").strip()
    try:
        due_date = date.fromisoformat(request.POST.get("due_date", ""))
    except ValueError:
        due_date = None
    attachment = request.FILES.get("attachment")
    invalid_upload = False
    if attachment:
        try:
            validate_homework_upload(attachment)
        except ValidationError:
            invalid_upload = True

    if not subject or not title or len(title) > 180 or not instructions or len(instructions) > 10000 or not due_date or invalid_upload:
        messages.error(request, "Enter valid homework details and attach a PDF, document, text, or image file up to 10 MB.")
    else:
        if attachment:
            extension = os.path.splitext(attachment.name)[1].lower()
            attachment.name = f"{uuid.uuid4().hex}{extension}"
        Homework.objects.create(
            teacher=teacher,
            subject=subject,
            title=title,
            instructions=instructions,
            due_date=due_date,
            attachment=attachment,
        )
        messages.success(request, "Homework posted for the students in that subject.")
    return redirect("/teacher/?section=homework")


@login_required
def private_file(request, file_kind, object_id):
    """Deliver face images and homework only to users allowed to see the record."""
    from django.http import FileResponse, Http404
    import mimetypes

    file_field = None
    allowed = request.user.is_staff

    if file_kind == "homework":
        item = Homework.objects.select_related("subject", "teacher__user").filter(pk=object_id).first()
        if item and item.attachment:
            teacher = TeacherProfile.objects.filter(user=request.user).first()
            profile = Register.objects.filter(user=request.user).first()
            parent_access = ParentStudentLink.objects.filter(
                parent__user=request.user,
                student__branch__iexact=item.subject.branch,
                student__semester=item.subject.semester,
            ).exists()
            student_access = bool(
                profile
                and profile.branch.casefold() == item.subject.branch.casefold()
                and profile.semester == item.subject.semester
            )
            teacher_access = bool(
                teacher
                and teacher.subjects.filter(pk=item.subject_id, is_active=True).exists()
            )
            allowed = allowed or parent_access or student_access or teacher_access
            file_field = item.attachment
            as_attachment = True
        else:
            raise Http404
    elif file_kind == "student-face":
        item = Register.objects.filter(pk=object_id).first()
        if item and item.face_image:
            parent_access = ParentStudentLink.objects.filter(
                parent__user=request.user, student=item,
            ).exists()
            teacher = TeacherProfile.objects.filter(user=request.user).first()
            teacher_access = bool(
                teacher and teacher.subjects.filter(
                    branch__iexact=item.branch,
                    semester=item.semester,
                    is_active=True,
                ).exists()
            )
            allowed = allowed or item.user_id == request.user.pk or parent_access or teacher_access
            file_field = item.face_image
            as_attachment = False
        else:
            raise Http404
    elif file_kind == "attendance-face":
        item = Attendance.objects.select_related("student", "subject").filter(pk=object_id).first()
        if item and item.face_image:
            parent_access = Register.objects.filter(
                user_id=item.student_id,
                parent_links__parent__user=request.user,
            ).exists()
            teacher = TeacherProfile.objects.filter(user=request.user).first()
            teacher_access = bool(
                teacher and teacher.subjects.filter(pk=item.subject_id, is_active=True).exists()
            )
            allowed = allowed or item.student_id == request.user.pk or parent_access or teacher_access
            file_field = item.face_image
            as_attachment = False
        else:
            raise Http404
    else:
        raise Http404

    if not allowed:
        raise Http404

    filename = os.path.basename(str(file_field.name).replace("\\", "/"))
    filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:120] or "download"
    content_type = "application/octet-stream" if as_attachment else (
        mimetypes.guess_type(filename)[0] or "application/octet-stream"
    )
    response = FileResponse(
        file_field.open("rb"),
        as_attachment=as_attachment,
        filename=filename,
        content_type=content_type,
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store, no-cache, max-age=0, must-revalidate"
    return response


def block_public_media(request, file_path):
    """Keep MEDIA_ROOT from becoming a public file server, including in DEBUG."""
    from django.http import Http404
    raise Http404


@login_required
@require_POST
def teacher_parent_message_reply(request, teacher):
    message_id = request.POST.get("message_id", "")
    parent_message = (
        ParentTeacherMessage.objects.filter(
            pk=message_id,
            teacher=teacher,
        ).select_related("student_link").first()
        if message_id.isdigit()
        else None
    )
    body = request.POST.get("message", "").strip()
    if not parent_message or not body or len(body) > 4000:
        messages.error(request, "Enter a reply of up to 4,000 characters.")
    else:
        ParentTeacherMessage.objects.create(
            student_link=parent_message.student_link,
            teacher=teacher,
            sender=request.user,
            message=body,
        )
        messages.success(request, "Reply sent to the parent.")
    return redirect("/teacher/?section=parent-messages")


def teacher_required(view):

    @login_required
    def wrapped(request, *args, **kwargs):
        try:
            teacher = request.user.teacher_profile

        except TeacherProfile.DoesNotExist:
            if request.user.is_staff:
                messages.info(
                    request,
                    "This browser is signed in as an administrator. Chrome shares one login across tabs; use a separate Chrome profile or Incognito window to keep the teacher and admin accounts signed in at the same time.",
                )
                return redirect("adminpanel")

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

    subjects = teacher.subjects.filter(
        is_active=True
    ).order_by("semester", "name")
    announcement_semesters = sorted(
        set(subjects.values_list("semester", flat=True))
    )

    if request.method == "POST":

        action = request.POST.get("action")

        if action in {"create_test", "save_marks"}:
            return teacher_tests(request)
        if action == "create_homework":
            return teacher_homework(request, teacher)
        if action == "reply_parent_message":
            return teacher_parent_message_reply(request, teacher)
        if action == "review_student_leave":
            return teacher_leaves(request)
        if action == "submit_teacher_leave":
            return teacher_leave_portal(request)

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

        elif action == "create_announcement":
            title = request.POST.get("title", "").strip()
            body = request.POST.get("message", "").strip()
            semester = request.POST.get("semester", "").strip()

            if not title or len(title) > 150 or not body or len(body) > 10000 or semester not in announcement_semesters:
                messages.error(request, "Enter a title, message, and a semester you teach.")
            else:
                Announcement.objects.create(
                    teacher=teacher,
                    title=title,
                    message=body,
                    audience=Announcement.Audience.STUDENTS,
                    branch=teacher.branch,
                    semester=semester,
                )
                messages.success(request, "Announcement posted for students.")
                return redirect("teacherpanel")

    subject_ids = subjects.values_list(
        "id",
        flat=True
    )

    taught_classes = Q(pk__in=[])
    for taught_subject in subjects:
        taught_classes |= Q(
            branch__iexact=taught_subject.branch,
            semester=taught_subject.semester,
        )
    students = Register.objects.filter(taught_classes).order_by(
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

    tests = list(
        ClassTest.objects.filter(teacher=teacher)
        .select_related("subject")
        .prefetch_related("results")
    )
    for test in tests:
        roster = Register.objects.filter(
            branch__iexact=test.subject.branch,
            semester=test.subject.semester,
        ).order_by("roll_no")
        results_by_student = {result.student_id: result for result in test.results.all()}
        test.student_rows = [
            {"student": student, "result": results_by_student.get(student.pk)}
            for student in roster
        ]

    student_leave_applications = LeaveApplication.objects.filter(
        teacher=teacher,
    ).select_related("student", "subject").order_by(
        "status", "start_date", "-requested_at"
    )
    own_leave_applications = TeacherLeaveApplication.objects.filter(teacher=teacher)
    teacher_adjustments = TeacherLeaveAdjustment.objects.filter(
        Q(leave_application__teacher=teacher)
        | Q(original_teacher=teacher)
        | Q(substitute_teacher=teacher)
    ).select_related(
        "leave_application__teacher__user",
        "subject",
        "original_teacher__user",
        "substitute_teacher__user",
    ).order_by("class_date", "start_time")

    teacher_read_states = {
        row.object_id: row.seen_updated_at
        for row in DashboardNoticeRead.objects.filter(
            user=request.user,
            notice_type=DashboardNoticeRead.NoticeType.ADJUSTMENT,
        )
    }
    unread_dashboard_notices = []
    for adjustment in teacher_adjustments.filter(class_date__gte=date.today()):
        seen_at = teacher_read_states.get(adjustment.pk)
        if seen_at is None or adjustment.updated_at > seen_at:
            plan = (
                adjustment.substitute_teacher.user.get_full_name()
                or adjustment.substitute_teacher.user.username
                if adjustment.adjustment_type == TeacherLeaveAdjustment.AdjustmentType.SUBSTITUTE
                and adjustment.substitute_teacher_id
                else "Library period"
                if adjustment.adjustment_type == TeacherLeaveAdjustment.AdjustmentType.LIBRARY
                else adjustment.custom_activity or "Schedule updated"
            )
            unread_dashboard_notices.append({
                "key": f"ADJUSTMENT:{adjustment.pk}",
                "type": "Timetable changed",
                "title": adjustment.subject.name,
                "detail": (
                    f"{adjustment.class_date:%b %d, %Y} · "
                    f"{adjustment.start_time:%I:%M %p}–{adjustment.end_time:%I:%M %p} · {plan}"
                    + (
                        f" · Room {adjustment.room}"
                        if adjustment.adjustment_type == TeacherLeaveAdjustment.AdjustmentType.LIBRARY
                        and adjustment.room
                        else ""
                    )
                ),
            })

    return render(
        request,
        "teacherpanel.html",
        {
            "teacher": teacher,
            "announcement_semesters": announcement_semesters,
            "announcements": Announcement.objects.filter(
                audience=Announcement.Audience.TEACHERS
            ).select_related("created_by")[:30],
            "unread_announcements": Announcement.objects.filter(
                audience=Announcement.Audience.TEACHERS
            ).exclude(reads__user=request.user).distinct().select_related(
                "created_by"
            )[:20],
            "unread_dashboard_notices": unread_dashboard_notices,
            "subjects": subjects,
            "students": students,
            "attendance_records": attendance_records,
            "subject_count": subjects.count(),
            "students_count": students.count(),
            "today_attendance": today_attendance,
            "total_attendance": total_attendance,
            "tests": tests,
            "student_leave_applications": student_leave_applications,
            "own_leave_applications": own_leave_applications,
            "teacher_adjustments": teacher_adjustments,
            "teacher_homework": Homework.objects.filter(
                teacher=teacher,
            ).select_related("subject").order_by("-created_at")[:50],
            "parent_messages": ParentTeacherMessage.objects.filter(
                teacher=teacher,
            ).select_related(
                "student_link__student",
                "student_link__parent__user",
                "sender",
            ).order_by("-created_at")[:100],
        }
    )
@teacher_required
def teacher_tests(request, teacher):
    if request.method != "POST":
        return redirect("/teacher/?section=tests")

    assigned_subjects = teacher.subjects.filter(is_active=True).order_by(
        "semester", "name"
    )

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "create_test":
            title = request.POST.get("title", "").strip()
            topics = request.POST.get("units_topics", "").strip()
            subject_id = request.POST.get("subject", "").strip()
            subject = (
                assigned_subjects.filter(pk=subject_id).first()
                if subject_id.isdigit()
                else None
            )

            try:
                test_date = date.fromisoformat(request.POST.get("test_date", ""))
                max_marks = Decimal(request.POST.get("max_marks", ""))
                if (
                    not max_marks.is_finite()
                    or max_marks <= 0
                    or max_marks > Decimal("99999.99")
                    or max_marks.as_tuple().exponent < -2
                ):
                    raise InvalidOperation
            except (ValueError, InvalidOperation):
                messages.error(request, "Enter a valid test date and maximum marks greater than zero.")
            else:
                if not title or not topics or subject is None:
                    messages.error(request, "Enter all test details and select one of your assigned subjects.")
                else:
                    ClassTest.objects.create(
                        teacher=teacher,
                        subject=subject,
                        title=title,
                        test_date=test_date,
                        max_marks=max_marks,
                        units_topics=topics,
                    )
                    messages.success(request, "Test details are now visible to matching students.")
                    return redirect("/teacher/?section=tests")

        elif action == "save_marks":
            test_id = request.POST.get("test_id", "").strip()
            if not test_id.isdigit():
                messages.error(request, "Select a valid test before saving marks.")
                return redirect("/teacher/?section=tests")
            test = get_object_or_404(
                ClassTest.objects.select_related("subject"),
                pk=test_id,
                teacher=teacher,
            )
            roster = Register.objects.filter(
                branch__iexact=test.subject.branch,
                semester=test.subject.semester,
            ).order_by("roll_no")
            entries = []
            errors = []

            for student in roster:
                raw_marks = request.POST.get(f"marks_{student.pk}", "").strip()
                if not raw_marks:
                    continue
                try:
                    marks = Decimal(raw_marks)
                    if (
                        not marks.is_finite()
                        or marks < 0
                        or marks > test.max_marks
                        or marks.as_tuple().exponent < -2
                    ):
                        raise InvalidOperation
                    entries.append((student, marks))
                except InvalidOperation:
                    errors.append(f"{student.student_name}: enter marks from 0 to {test.max_marks}.")

            if errors:
                for error in errors:
                    messages.error(request, error)
            else:
                with transaction.atomic():
                    for student, marks in entries:
                        TestResult.objects.update_or_create(
                            test=test,
                            student=student,
                            defaults={"marks_obtained": marks},
                        )
                messages.success(request, f"Marks saved for {len(entries)} student(s).")
                return redirect("/teacher/?section=tests")

    return redirect("/teacher/?section=tests")


@teacher_required
def teacher_leaves(request, teacher):
    if request.method != "POST":
        return redirect("/teacher/?section=student-leaves")
    if request.method == "POST":
        application_id = request.POST.get("application_id", "").strip()
        decision = request.POST.get("decision", "").strip()
        application = get_object_or_404(
            LeaveApplication.objects.select_related("subject", "student"),
            pk=application_id if application_id.isdigit() else None,
            teacher=teacher,
            status=LeaveApplication.Status.PENDING,
        )

        if decision not in {LeaveApplication.Status.APPROVED, LeaveApplication.Status.REJECTED}:
            messages.error(request, "Choose approve or reject for this leave request.")
        else:
            application.status = decision
            application.teacher_note = request.POST.get("teacher_note", "").strip()
            application.reviewed_at = timezone.now()
            application.save(update_fields=["status", "teacher_note", "reviewed_at"])
            messages.success(request, f"Leave request {application.get_status_display().lower()}.")
            return redirect("/teacher/?section=student-leaves")

    return redirect("/teacher/?section=student-leaves")


@teacher_required
def teacher_leave_portal(request, teacher):
    if request.method != "POST":
        return redirect("/teacher/?section=my-leave")
    if request.method == "POST":
        try:
            start_date = date.fromisoformat(request.POST.get("start_date", ""))
            end_date = date.fromisoformat(request.POST.get("end_date", ""))
        except ValueError:
            messages.error(request, "Enter valid leave dates.")
        else:
            reason = request.POST.get("reason", "").strip()
            if not reason or len(reason) > 4000:
                messages.error(request, "Enter a reason for your leave request (up to 4,000 characters).")
            elif end_date < start_date:
                messages.error(request, "The end date cannot be earlier than the start date.")
            elif (end_date - start_date).days > 365:
                messages.error(request, "A single leave request cannot be longer than one year.")
            elif TeacherLeaveApplication.objects.filter(
                teacher=teacher,
                status__in=[TeacherLeaveApplication.Status.PENDING, TeacherLeaveApplication.Status.APPROVED],
                start_date__lte=end_date,
                end_date__gte=start_date,
            ).exists():
                messages.error(request, "You already have a pending or approved leave request for these dates.")
            else:
                TeacherLeaveApplication.objects.create(
                    teacher=teacher,
                    start_date=start_date,
                    end_date=end_date,
                    reason=reason,
                )
                messages.success(request, "Your leave request was sent to the admin.")
                return redirect("/teacher/?section=my-leave")

    return redirect("/teacher/?section=my-leave")


def teacher_is_free_for_adjustment(teacher, timetable_slot, class_date, exclude_adjustment=None):
    if not teacher.is_active or not teacher.subjects.filter(pk=timetable_slot.subject_id).exists():
        return False
    if not teacher.branches.filter(name__iexact=timetable_slot.subject.branch).exists():
        return False
    if TeacherLeaveApplication.objects.filter(
        teacher=teacher,
        status=TeacherLeaveApplication.Status.APPROVED,
        start_date__lte=class_date,
        end_date__gte=class_date,
    ).exists():
        return False

    occupied_slots = TimetableSlot.objects.filter(
        teacher=teacher,
        status=TimetableSlot.Status.PUBLISHED,
        day=class_date.weekday(),
    ).exclude(pk=timetable_slot.pk).select_related("subject")
    for occupied_slot in occupied_slots:
        if not (
            timetable_slot.start_time < occupied_slot.end_time
            and timetable_slot.end_time > occupied_slot.start_time
        ):
            continue
        existing_change = TeacherLeaveAdjustment.objects.filter(
            timetable_slot=occupied_slot,
            class_date=class_date,
        ).first()
        if existing_change is None:
            return False
        if (
            existing_change.adjustment_type == TeacherLeaveAdjustment.AdjustmentType.SUBSTITUTE
            and existing_change.substitute_teacher_id == teacher.pk
        ):
            return False

    active_substitutions = TeacherLeaveAdjustment.objects.filter(
        substitute_teacher=teacher,
        class_date=class_date,
        adjustment_type=TeacherLeaveAdjustment.AdjustmentType.SUBSTITUTE,
        timetable_slot__isnull=False,
    ).select_related("timetable_slot")
    if exclude_adjustment:
        active_substitutions = active_substitutions.exclude(pk=exclude_adjustment.pk)
    if any(
        timetable_slot.start_time < item.timetable_slot.end_time
        and timetable_slot.end_time > item.timetable_slot.start_time
        for item in active_substitutions
    ):
        return False
    return True


def create_teacher_leave_adjustments(application):
    slots = TimetableSlot.objects.filter(
        teacher=application.teacher,
        status=TimetableSlot.Status.PUBLISHED,
    ).select_related("subject", "configuration").order_by("day", "start_time")
    class_date = application.start_date
    while class_date <= application.end_date:
        for slot in slots:
            if slot.day != class_date.weekday():
                continue
            existing = TeacherLeaveAdjustment.objects.filter(
                timetable_slot=slot,
                class_date=class_date,
            ).first()
            if existing:
                continue
            substitutes = TeacherProfile.objects.filter(
                is_active=True,
                subjects=slot.subject,
                branches__name__iexact=slot.subject.branch,
            ).exclude(pk=application.teacher_id).select_related("user").distinct().order_by(
                "user__first_name", "user__username"
            )
            substitute = next(
                (
                    candidate for candidate in substitutes
                    if teacher_is_free_for_adjustment(candidate, slot, class_date)
                ),
                None,
            )
            TeacherLeaveAdjustment.objects.create(
                leave_application=application,
                timetable_slot=slot,
                subject=slot.subject,
                original_teacher=slot.teacher,
                class_date=class_date,
                start_time=slot.start_time,
                end_time=slot.end_time,
                room=(
                    slot.room
                    if substitute
                    else available_library_room(slot, class_date)
                ),
                adjustment_type=(
                    TeacherLeaveAdjustment.AdjustmentType.SUBSTITUTE
                    if substitute
                    else TeacherLeaveAdjustment.AdjustmentType.LIBRARY
                ),
                substitute_teacher=substitute,
            )
        class_date += timedelta(days=1)


@staff_required
def admin_teacher_leaves(request):
    if request.method == "POST":
        action = request.POST.get("action", "review_leave")
        if action == "update_adjustment":
            adjustment_id = request.POST.get("adjustment_id", "").strip()
            adjustment = get_object_or_404(
                TeacherLeaveAdjustment.objects.select_related("timetable_slot__subject"),
                pk=adjustment_id if adjustment_id.isdigit() else None,
            )
            selected_type = request.POST.get("adjustment_type", "").strip()
            note = request.POST.get("admin_note", "").strip()
            if selected_type not in TeacherLeaveAdjustment.AdjustmentType.values:
                messages.error(request, "Choose a valid class adjustment.")
            elif selected_type == TeacherLeaveAdjustment.AdjustmentType.SUBSTITUTE:
                substitute_id = request.POST.get("substitute_teacher", "").strip()
                substitute = TeacherProfile.objects.filter(
                    pk=substitute_id,
                    is_active=True,
                    subjects=adjustment.subject,
                    branches__name__iexact=adjustment.subject.branch,
                ).first() if substitute_id.isdigit() else None
                if substitute is None:
                    messages.error(request, "Choose an active teacher assigned to this subject and branch.")
                elif adjustment.timetable_slot is None:
                    messages.error(request, "This class was removed from the timetable; its historical adjustment cannot be reassigned.")
                elif not teacher_is_free_for_adjustment(
                    substitute,
                    adjustment.timetable_slot,
                    adjustment.class_date,
                    exclude_adjustment=adjustment,
                ):
                    messages.error(request, "That teacher has another class at this time or is already covering a class.")
                else:
                    adjustment.adjustment_type = selected_type
                    adjustment.substitute_teacher = substitute
                    adjustment.custom_activity = ""
                    adjustment.room = adjustment.timetable_slot.room
                    adjustment.admin_note = note
                    adjustment.save(update_fields=[
                        "adjustment_type", "substitute_teacher", "custom_activity",
                        "room", "admin_note", "updated_at",
                    ])
                    messages.success(request, "Class adjustment updated.")
                    return redirect("admin_teacher_leaves")
            elif selected_type == TeacherLeaveAdjustment.AdjustmentType.CUSTOM:
                custom_activity = request.POST.get("custom_activity", "").strip()
                if not custom_activity:
                    messages.error(request, "Enter the name of the replacement activity.")
                else:
                    adjustment.adjustment_type = selected_type
                    adjustment.substitute_teacher = None
                    adjustment.custom_activity = custom_activity
                    adjustment.room = adjustment.timetable_slot.room if adjustment.timetable_slot_id else ""
                    adjustment.admin_note = note
                    adjustment.save(update_fields=[
                        "adjustment_type", "substitute_teacher", "custom_activity",
                        "room", "admin_note", "updated_at",
                    ])
                    messages.success(request, "Class adjustment updated.")
                    return redirect("admin_teacher_leaves")
            else:
                library_room = available_library_room(
                    adjustment.timetable_slot,
                    adjustment.class_date,
                    exclude_adjustment=adjustment,
                ) if adjustment.timetable_slot_id else ""
                if not library_room:
                    messages.error(request, "No configured library room is free for this class time. Add or free a Library room first.")
                else:
                    adjustment.adjustment_type = selected_type
                    adjustment.substitute_teacher = None
                    adjustment.custom_activity = ""
                    adjustment.room = library_room
                    adjustment.admin_note = note
                    adjustment.save(update_fields=[
                        "adjustment_type", "substitute_teacher", "custom_activity",
                        "room", "admin_note", "updated_at",
                    ])
                    messages.success(request, f"Class adjustment updated. Library room {library_room} is assigned.")
                    return redirect("admin_teacher_leaves")

        if action == "update_adjustment":
            return redirect("admin_teacher_leaves")

        application_id = request.POST.get("application_id", "").strip()
        decision = request.POST.get("decision", "").strip()
        application = get_object_or_404(
            TeacherLeaveApplication.objects.select_related("teacher", "teacher__user"),
            pk=application_id if application_id.isdigit() else None,
            status=TeacherLeaveApplication.Status.PENDING,
        )
        if decision not in {TeacherLeaveApplication.Status.APPROVED, TeacherLeaveApplication.Status.REJECTED}:
            messages.error(request, "Choose approve or reject for this teacher leave request.")
        else:
            with transaction.atomic():
                application.status = decision
                application.admin_note = request.POST.get("admin_note", "").strip()
                application.reviewed_at = timezone.now()
                application.save(update_fields=["status", "admin_note", "reviewed_at"])
                if decision == TeacherLeaveApplication.Status.APPROVED:
                    create_teacher_leave_adjustments(application)
            messages.success(request, f"Teacher leave request {application.get_status_display().lower()}.")
            return redirect("admin_teacher_leaves")

    adjustments = TeacherLeaveAdjustment.objects.select_related(
        "leave_application__teacher__user",
        "subject",
        "original_teacher__user",
        "timetable_slot",
        "substitute_teacher__user",
    ).order_by("class_date", "start_time")
    available_teachers = TeacherProfile.objects.filter(is_active=True).select_related(
        "user"
    ).prefetch_related("subjects", "branches").order_by("user__first_name", "user__username")

    applications = TeacherLeaveApplication.objects.select_related(
        "teacher", "teacher__user"
    ).order_by("status", "start_date", "-requested_at")
    return render(request, "admin_teacher_leaves.html", {
        "applications": applications,
        "adjustments": adjustments,
        "available_teachers": available_teachers,
    })


@teacher_required
def teacher_students(request, teacher):

    subjects = teacher.subjects.filter(
        is_active=True
    )

    taught_classes = Q(pk__in=[])
    for taught_subject in subjects:
        taught_classes |= Q(
            branch__iexact=taught_subject.branch,
            semester=taught_subject.semester,
        )
    students = Register.objects.filter(taught_classes).select_related("user")

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
@require_POST
def teacher_logout(request):

    auth_logout(request)

    return redirect("login")



from datetime import datetime, timedelta
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import render
from .models import (
    Subject,
    TeacherProfile,
    TimetableConfiguration,
    SubjectScheduleRequirement,
    TimetableSlot,
)






def normalize_room_name(room):
    return " ".join((room or "").casefold().split())


def available_library_room(timetable_slot, class_date, exclude_adjustment=None):
    """Choose a configured library room that is free at this date and time."""
    library_rooms = RoomInventory.objects.filter(
        room_type=RoomInventory.RoomType.OTHER,
        other_purpose=RoomInventory.OtherPurpose.LIBRARY,
        is_active=True,
    ).order_by("room_number")
    for room in library_rooms:
        occupied_classes = TimetableSlot.objects.filter(
            status=TimetableSlot.Status.PUBLISHED,
            day=class_date.weekday(),
            start_time__lt=timetable_slot.end_time,
            end_time__gt=timetable_slot.start_time,
        ).exclude(pk=timetable_slot.pk).values_list("room", flat=True)
        occupied_by_class = any(
            normalize_room_name(existing_room) == normalize_room_name(room.room_number)
            for existing_room in occupied_classes
        )
        occupied_adjustments = TeacherLeaveAdjustment.objects.filter(
            class_date=class_date,
            start_time__lt=timetable_slot.end_time,
            end_time__gt=timetable_slot.start_time,
        ).values_list("room", flat=True)
        if exclude_adjustment:
            occupied_adjustments = TeacherLeaveAdjustment.objects.filter(
                class_date=class_date,
                start_time__lt=timetable_slot.end_time,
                end_time__gt=timetable_slot.start_time,
            ).exclude(
                pk=exclude_adjustment.pk,
            ).values_list("room", flat=True)
        occupied_by_adjustment = any(
            normalize_room_name(existing_room) == normalize_room_name(room.room_number)
            for existing_room in occupied_adjustments
        )
        if not occupied_by_class and not occupied_by_adjustment:
            return room.room_number
    return ""


def refresh_library_adjustment_rooms():
    """Reassign upcoming library periods after the library inventory changes."""
    pending_adjustments = list(TeacherLeaveAdjustment.objects.filter(
        adjustment_type=TeacherLeaveAdjustment.AdjustmentType.LIBRARY,
        class_date__gte=date.today(),
        timetable_slot__isnull=False,
    ).select_related("timetable_slot").order_by("class_date", "start_time", "pk"))
    if not pending_adjustments:
        return
    with transaction.atomic():
        TeacherLeaveAdjustment.objects.filter(
            pk__in=[item.pk for item in pending_adjustments],
        ).update(room="")
        for adjustment in pending_adjustments:
            adjustment.room = available_library_room(
                adjustment.timetable_slot,
                adjustment.class_date,
                exclude_adjustment=adjustment,
            )
            adjustment.save(update_fields=["room", "updated_at"])


def validate_timetable_slots(configuration, candidate_slots):
    """Check candidate sessions against each other and every other timetable."""
    conflicts = []
    candidate_bookings = []
    other_slots = list(
        TimetableSlot.objects.exclude(configuration=configuration).select_related(
            "teacher", "subject", "configuration"
        )
    )

    def overlaps(start_a, end_a, start_b, end_b):
        return start_a < end_b and end_a > start_b

    for slot in candidate_slots:
        if slot.end_time <= slot.start_time:
            conflicts.append(f"{slot.subject.name}: end time must be later than start time.")
            continue
        if slot.day >= configuration.working_days:
            conflicts.append(f"{slot.subject.name}: scheduled outside configured working days.")
        if (
            slot.start_time < configuration.college_start
            or slot.end_time > configuration.college_end
            or (slot.start_time < configuration.lunch_end and slot.end_time > configuration.lunch_start)
        ):
            conflicts.append(f"{slot.subject.name}: scheduled outside college hours or across lunch.")

        for other in other_slots:
            if other.day != slot.day or not overlaps(
                slot.start_time, slot.end_time, other.start_time, other.end_time
            ):
                continue

            same_class = (
                other.configuration.academic_year == configuration.academic_year
                and other.configuration.branch.casefold() == configuration.branch.casefold()
                and other.configuration.semester == configuration.semester
            )
            if same_class:
                conflicts.append(
                    f"Class clash: {slot.subject.name} overlaps {other.subject.name} "
                    f"for {configuration.branch}, semester {configuration.semester}."
                )
            if other.teacher_id == slot.teacher_id:
                conflicts.append(
                    f"Teacher clash: {slot.teacher.user.get_full_name() or slot.teacher.user.username} "
                    f"is assigned to overlapping classes ({slot.subject.name} / {other.subject.name})."
                )
            room = normalize_room_name(slot.room)
            if room and room == normalize_room_name(other.room):
                conflicts.append(
                    f"Room clash: {slot.room} is assigned to overlapping classes "
                    f"({slot.subject.name} / {other.subject.name})."
                )

        for other in candidate_bookings:
            if other.day != slot.day or not overlaps(
                slot.start_time, slot.end_time, other.start_time, other.end_time
            ):
                continue
            conflicts.append(
                f"Generated class clash: {slot.subject.name} overlaps {other.subject.name}."
            )
            if other.teacher_id == slot.teacher_id:
                conflicts.append(
                    f"Generated teacher clash: {slot.teacher.username} has overlapping classes."
                )
            room = normalize_room_name(slot.room)
            if room and room == normalize_room_name(other.room):
                conflicts.append(f"Generated room clash: {slot.room} is double-booked.")
        candidate_bookings.append(slot)

    return list(dict.fromkeys(conflicts))


def generate_timetable_draft(configuration, subject_rows):
    """
    Generate a draft timetable for one branch and semester.
    Check teacher and room availability across all other configurations.
    """

    conflicts = []
    slots = []

    today = datetime.today().date()
    college_start = datetime.combine(today, configuration.college_start)
    college_end = datetime.combine(today, configuration.college_end)
    lunch_start = datetime.combine(today, configuration.lunch_start)
    lunch_end = datetime.combine(today, configuration.lunch_end)

    # Validate college timing.
    if college_end <= college_start:
        return [], ["College end time must be after college start time."]

    if lunch_end <= lunch_start:
        return [], ["Lunch end time must be after lunch start time."]

    if lunch_start < college_start or lunch_end > college_end:
        return [], ["Lunch must fall within college working hours."]

    if not 1 <= configuration.working_days <= 7:
        return [], ["Working days must be between 1 and 7."]

    period_minutes = configuration.default_theory_duration
    if not 1 <= period_minutes <= 600:
        return [], ["Theory period duration must be between 1 and 600 minutes."]

    registered_theory_rooms = list(RoomInventory.objects.filter(
        room_type=RoomInventory.RoomType.THEORY,
        is_active=True,
    ).values_list("room_number", flat=True))
    registered_lab_rooms = list(RoomInventory.objects.filter(
        room_type=RoomInventory.RoomType.LAB,
        is_active=True,
    ).values_list("room_number", flat=True))
    theory_rooms = registered_theory_rooms or list(dict.fromkeys(
        room.strip()
        for room in configuration.theory_rooms.split(",")
        if room.strip()
    ))
    lab_rooms = registered_lab_rooms or list(dict.fromkeys(
        room.strip()
        for room in configuration.lab_rooms.split(",")
        if room.strip()
    ))

    if not theory_rooms:
        return [], ["Please configure at least one theory classroom."]

    if not lab_rooms:
        return [], ["Please configure at least one lab room."]

    # Every required session becomes an individual scheduling task.
    sessions = []

    for row in subject_rows:
        subject = row["subject"]
        requirement = row.get("requirement")

        if not requirement:
            continue

        if requirement.theory_classes_per_week:
            for _ in range(requirement.theory_classes_per_week):
                sessions.append({
                    "subject": subject,
                    "teacher": requirement.teacher,
                    "type": TimetableSlot.SessionType.THEORY,
                    "duration": requirement.theory_duration_minutes,
                })

        if requirement.lab_classes_per_week:
            for _ in range(requirement.lab_classes_per_week):
                sessions.append({
                    "subject": subject,
                    "teacher": requirement.teacher,
                    "type": TimetableSlot.SessionType.LAB,
                    "duration": requirement.lab_duration_minutes,
                })

    if not sessions:
        return [], ["Set at least one theory or lab session per week."]

    for session in sessions:
        subject = session["subject"]
        teacher = session["teacher"]

        if session["duration"] <= 0:
            return [], [f"{subject.name}: duration must be positive."]

        if not teacher.is_active:
            return [], [f"{subject.name}: the selected teacher is inactive."]

        if not teacher.subjects.filter(pk=subject.pk).exists():
            return [], [
                f"{teacher.user.username} is not assigned to {subject.name}."
            ]
        if not teacher.branches.filter(name__iexact=subject.branch).exists():
            return [], [
                f"{teacher.user.username} is not assigned to branch {subject.branch}."
            ]

    # Schedule long labs first.
    sessions.sort(
        key=lambda item: (
            -item["duration"],
            item["subject"].name.casefold(),
        )
    )

    # All saved slots belonging to other configurations count as occupied,
    # irrespective of branch, semester, academic year, or draft/published status.
    # Exclude only the current configuration because its old draft is replaced.
    other_slots = list(
        TimetableSlot.objects.exclude(
            configuration=configuration
        ).select_related(
            "teacher",
            "subject",
            "configuration",
        )
    )

    def overlaps(start_a, end_a, start_b, end_b):
        return start_a < end_b and end_a > start_b

    # Local bookings created while generating this timetable.
    class_bookings = {
        day: [] for day in range(configuration.working_days)
    }
    planned_bookings = []

    subject_day_count = {}
    daily_load = {day: 0 for day in range(configuration.working_days)}
    daily_count = {day: 0 for day in range(configuration.working_days)}

    def get_candidate_times(duration):
        """Generate possible starts on the regular period grid."""
        result = []
        current = college_start

        while current < college_end:
            slot_end = current + timedelta(minutes=duration)

            if lunch_start <= current < lunch_end:
                current = lunch_end
                continue

            # A class or lab must never cross the lunch break.
            if current < lunch_start and slot_end > lunch_start:
                current = lunch_end
                continue

            if lunch_start < current < lunch_end:
                current = lunch_end
                continue

            if slot_end <= college_end:
                result.append((current, slot_end))

            current += timedelta(minutes=period_minutes)

        return result

    for session in sessions:
        subject = session["subject"]
        teacher = session["teacher"]
        duration = session["duration"]
        session_type = session["type"]

        rooms = (
            theory_rooms
            if session_type == TimetableSlot.SessionType.THEORY
            else lab_rooms
        )

        candidates = []

        for day in range(configuration.working_days):
            for start, end in get_candidate_times(duration):

                # 1. Same class/semester cannot have overlapping sessions.
                if any(
                    overlaps(start, end, item["start"], item["end"])
                    for item in class_bookings[day]
                ):
                    continue

                class_busy_elsewhere = any(
                    other.day == day
                    and other.configuration.academic_year == configuration.academic_year
                    and other.configuration.branch.casefold() == configuration.branch.casefold()
                    and other.configuration.semester == configuration.semester
                    and overlaps(
                        start.time(), end.time(), other.start_time, other.end_time
                    )
                    for other in other_slots
                )
                if class_busy_elsewhere:
                    continue

                # 2. Teacher cannot be teaching another class at that time.
                teacher_busy_elsewhere = any(
                    other.day == day
                    and other.teacher_id == teacher.pk
                    and overlaps(
                        start.time(),
                        end.time(),
                        other.start_time,
                        other.end_time,
                    )
                    for other in other_slots
                )

                teacher_busy_here = any(
                    item["day"] == day
                    and item["teacher"].pk == teacher.pk
                    and overlaps(start, end, item["start"], item["end"])
                    for item in planned_bookings
                )

                if teacher_busy_elsewhere or teacher_busy_here:
                    continue

                # 3. Find a room that remains free for the FULL session.
                for room in rooms:
                    room_busy_elsewhere = any(
                        other.day == day
                        and normalize_room_name(other.room) == normalize_room_name(room)
                        and overlaps(
                            start.time(),
                            end.time(),
                            other.start_time,
                            other.end_time,
                        )
                        for other in other_slots
                    )

                    room_busy_here = any(
                        item["day"] == day
                        and normalize_room_name(item["room"]) == normalize_room_name(room)
                        and overlaps(start, end, item["start"], item["end"])
                        for item in planned_bookings
                    )

                    if room_busy_elsewhere or room_busy_here:
                        continue

                    # Prefer less-loaded days and avoid repeating a subject
                    # on the same day when other options are available.
                    repeats = subject_day_count.get((subject.pk, day), 0)

                    score = (
                        repeats * 100000
                        + daily_load[day] * 20
                        + daily_count[day] * 500
                        + start.hour * 60
                        + start.minute
                    )

                    candidates.append({
                        "score": score,
                        "day": day,
                        "start": start,
                        "end": end,
                        "room": room,
                    })

        if not candidates:
            conflicts.append(
                f"{subject.name} ({session_type}, {duration} min): "
                "no available time, teacher, and room combination found."
            )
            continue

        chosen = min(
            candidates,
            key=lambda item: (
                item["score"],
                item["day"],
                item["start"],
                item["room"].casefold(),
            ),
        )

        day = chosen["day"]
        start = chosen["start"]
        end = chosen["end"]
        room = chosen["room"]

        class_bookings[day].append({
            "start": start,
            "end": end,
        })

        planned_bookings.append({
            "day": day,
            "start": start,
            "end": end,
            "teacher": teacher,
            "room": room,
        })

        key = (subject.pk, day)
        subject_day_count[key] = subject_day_count.get(key, 0) + 1

        daily_load[day] += duration
        daily_count[day] += 1

        slots.append(
            TimetableSlot(
                configuration=configuration,
                subject=subject,
                teacher=teacher,
                day=day,
                start_time=start.time(),
                end_time=end.time(),
                session_type=session_type,
                room=room,
                status=TimetableSlot.Status.DRAFT,
            )
        )

    # Never save a partial timetable.
    if conflicts:
        return [], conflicts

    conflicts = validate_timetable_slots(configuration, slots)
    if conflicts:
        return [], conflicts

    return slots, []






@staff_required
def timetable(request):
    error_message = ""
    success_message = ""
    generation_done = False
    generation_conflicts = []
    generated_slots = []
    published_timetable = False

    semester_choices = Subject.SEMESTER_CHOICES

    branches = list(
        Subject.objects.filter(is_active=True)
        .values_list("branch", flat=True)
        .distinct()
        .order_by("branch")
    )

    academic_year = request.GET.get(
        "academic_year",
        request.POST.get("academic_year", "2026-2027"),
    )
    branch = request.GET.get(
        "branch",
        request.POST.get("branch", branches[0] if branches else "IT"),
    )
    semester = request.GET.get(
        "semester",
        request.POST.get("semester", "1"),
    )

    valid_semesters = [value for value, _label in semester_choices]
    if semester not in valid_semesters:
        semester = "1"

    existing_configuration = TimetableConfiguration.objects.filter(
        academic_year=academic_year,
        branch=branch,
        semester=semester,
    ).first()
    inventory_theory_rooms = list(RoomInventory.objects.filter(
        room_type=RoomInventory.RoomType.THEORY,
        is_active=True,
    ).values_list("room_number", flat=True))
    inventory_lab_rooms = list(RoomInventory.objects.filter(
        room_type=RoomInventory.RoomType.LAB,
        is_active=True,
    ).values_list("room_number", flat=True))
    has_theory_inventory = RoomInventory.objects.filter(
        room_type=RoomInventory.RoomType.THEORY,
    ).exists()
    has_lab_inventory = RoomInventory.objects.filter(
        room_type=RoomInventory.RoomType.LAB,
    ).exists()
    theory_rooms_for_form = ", ".join(inventory_theory_rooms) if has_theory_inventory else (
        existing_configuration.theory_rooms if existing_configuration else "204,205,208"
    )
    lab_rooms_for_form = ", ".join(inventory_lab_rooms) if has_lab_inventory else (
        existing_configuration.lab_rooms if existing_configuration else "Lab 1,Lab 2"
    )
    stored_theory_rooms = (
        theory_rooms_for_form
        if not has_theory_inventory
        else existing_configuration.theory_rooms if existing_configuration else "204,205,208"
    )
    stored_lab_rooms = (
        lab_rooms_for_form
        if not has_lab_inventory
        else existing_configuration.lab_rooms if existing_configuration else "Lab 1,Lab 2"
    )

    # Always initialize action so it is available throughout the function.
    action = (
        request.POST.get("action", "save")
        if request.method == "POST"
        else "save"
    )

    # Publish the draft timetable separately from saving settings.
    if request.method == "POST" and action == "publish":
        configuration = TimetableConfiguration.objects.filter(
            academic_year=academic_year,
            branch=branch,
            semester=semester,
        ).first()

        if configuration is None:
            error_message = "Timetable configuration not found."
        else:
            draft_slots = list(TimetableSlot.objects.filter(
                configuration=configuration,
                status=TimetableSlot.Status.DRAFT,
            ).select_related("teacher", "teacher__user", "subject", "configuration"))

            if not draft_slots:
                error_message = (
                    "No draft timetable slots available to publish."
                )
            else:
                conflicts = validate_timetable_slots(configuration, draft_slots)
                if conflicts:
                    generation_conflicts = conflicts
                    error_message = "Timetable was not published because conflicts were found."
                else:
                    with transaction.atomic():
                        TimetableSlot.objects.filter(
                            configuration=configuration,
                            status=TimetableSlot.Status.PUBLISHED,
                        ).delete()
                        TimetableSlot.objects.filter(
                            pk__in=[slot.pk for slot in draft_slots]
                        ).update(status=TimetableSlot.Status.PUBLISHED)
                    success_message = "Timetable published successfully! No timetable conflicts were found."
                    published_timetable = True

    elif request.method == "POST":
        try:
            with transaction.atomic():

                def read_time(name, default):
                    return datetime.strptime(
                        request.POST.get(name, default),
                        "%H:%M",
                    ).time()

                start_time = read_time("college_start", "09:00")
                end_time = read_time("college_end", "16:00")
                lunch_start = read_time("lunch_start", "13:00")
                lunch_end = read_time("lunch_end", "13:30")

                working_days = int(
                    request.POST.get("working_days", "6")
                )
                period_minutes = int(
                    request.POST.get("default_theory_duration", "50")
                )

                theory_rooms = theory_rooms_for_form
                lab_rooms = lab_rooms_for_form

                if end_time <= start_time:
                    raise ValueError(
                        "College end time must be after college start time."
                    )

                if lunch_end <= lunch_start:
                    raise ValueError(
                        "Lunch end time must be after lunch start time."
                    )

                if lunch_start < start_time or lunch_end > end_time:
                    raise ValueError(
                        "Lunch must be within college working hours."
                    )

                if not 1 <= working_days <= 7:
                    raise ValueError(
                        "Working days must be between 1 and 7."
                    )

                if not 1 <= period_minutes <= 600:
                    raise ValueError(
                        "Theory period duration must be between 1 and 600."
                    )

                theory_room_list = [
                    room.strip()
                    for room in theory_rooms.split(",")
                    if room.strip()
                ]
                lab_room_list = [
                    room.strip()
                    for room in lab_rooms.split(",")
                    if room.strip()
                ]

                if not theory_room_list or not lab_room_list:
                    raise ValueError(
                        "Enter at least one classroom and one lab room."
                    )

                if len({
                    normalize_room_name(room) for room in theory_room_list
                }) != len(theory_room_list):
                    raise ValueError("Duplicate theory room names found.")

                if len({
                    normalize_room_name(room) for room in lab_room_list
                }) != len(lab_room_list):
                    raise ValueError("Duplicate lab room names found.")

                configuration, _ = (
                    TimetableConfiguration.objects.get_or_create(
                        academic_year=academic_year,
                        branch=branch,
                        semester=semester,
                        defaults={
                            "college_start": start_time,
                            "college_end": end_time,
                            "lunch_start": lunch_start,
                            "lunch_end": lunch_end,
                            "working_days": working_days,
                            "default_theory_duration": period_minutes,
                            "theory_rooms": stored_theory_rooms,
                            "lab_rooms": stored_lab_rooms,
                        },
                    )
                )

                configuration.college_start = start_time
                configuration.college_end = end_time
                configuration.lunch_start = lunch_start
                configuration.lunch_end = lunch_end
                configuration.working_days = working_days
                configuration.default_theory_duration = period_minutes
                configuration.theory_rooms = stored_theory_rooms
                configuration.lab_rooms = stored_lab_rooms
                configuration.full_clean()
                configuration.save()

                subjects = list(
                    Subject.objects.filter(
                        is_active=True,
                        branch=branch,
                        semester=semester,
                    ).order_by("name")
                )

                if not subjects:
                    raise ValueError(
                        "No active subjects found for this branch and semester."
                    )

                # Validate all submitted requirements before generating.
                for subject in subjects:
                    teacher_id = request.POST.get(
                        f"teacher_{subject.pk}", ""
                    ).strip()

                    theory_count = int(
                        request.POST.get(
                            f"theory_count_{subject.pk}", "0"
                        )
                    )
                    theory_duration = int(
                        request.POST.get(
                            f"theory_duration_{subject.pk}", "50"
                        )
                    )
                    lab_count = int(
                        request.POST.get(
                            f"lab_count_{subject.pk}", "0"
                        )
                    )
                    lab_duration = int(
                        request.POST.get(
                            f"lab_duration_{subject.pk}", "120"
                        )
                    )

                    if not (
                        0 <= theory_count <= 30
                        and 0 <= lab_count <= 30
                        and 1 <= theory_duration <= 600
                        and 1 <= lab_duration <= 600
                    ):
                        raise ValueError(
                            f"{subject.name}: invalid weekly count or duration."
                        )

                    if theory_count == 0 and lab_count == 0:
                        SubjectScheduleRequirement.objects.filter(
                            subject=subject
                        ).delete()
                        continue

                    # Validate teacher ID before querying the database.
                    if not teacher_id.isdigit():
                        raise ValueError(
                            f"Select an active teacher assigned to "
                            f"{subject.name}."
                        )

                    teacher = TeacherProfile.objects.filter(
                        pk=teacher_id,
                        is_active=True,
                        branches__name=subject.branch,
                        subjects=subject,
                    ).first()

                    if teacher is None:
                        raise ValueError(
                            f"Select an active teacher assigned to "
                            f"{subject.name}."
                        )

                    requirement, _ = (
                        SubjectScheduleRequirement.objects.get_or_create(
                            subject=subject,
                            defaults={
                                "teacher": teacher,
                                "theory_classes_per_week": theory_count,
                                "theory_duration_minutes": theory_duration,
                                "lab_classes_per_week": lab_count,
                                "lab_duration_minutes": lab_duration,
                            },
                        )
                    )

                    requirement.teacher = teacher
                    requirement.theory_classes_per_week = theory_count
                    requirement.theory_duration_minutes = theory_duration
                    requirement.lab_classes_per_week = lab_count
                    requirement.lab_duration_minutes = lab_duration

                    requirement.full_clean()
                    requirement.save()

                if action == "generate":
                    subject_rows = []

                    for subject in subjects:
                        requirement = (
                            SubjectScheduleRequirement.objects
                            .filter(subject=subject)
                            .select_related("teacher")
                            .first()
                        )

                        if requirement:
                            subject_rows.append({
                                "subject": subject,
                                "requirement": requirement,
                            })

                    new_slots, generation_conflicts = (
                        generate_timetable_draft(
                            configuration,
                            subject_rows,
                        )
                    )

                    generation_done = True

                    if generation_conflicts:
                        raise ValueError(
                            "Timetable could not be generated: "
                            + " | ".join(generation_conflicts)
                        )

                    # Replace this configuration's drafts only.
                    TimetableSlot.objects.filter(
                        configuration=configuration,
                        status=TimetableSlot.Status.DRAFT,
                    ).delete()

                    TimetableSlot.objects.bulk_create(new_slots)

                    success_message = (
                        f"Timetable generated successfully: "
                        f"{len(new_slots)} sessions."
                    )

                else:
                    success_message = (
                        "Timetable settings saved successfully."
                    )

        except (ValueError, ValidationError) as exc:
            error_message = str(exc)

            if " | " in error_message:
                generation_conflicts = error_message.split(" | ")

            generated_slots = []

    configuration = TimetableConfiguration.objects.filter(
        academic_year=academic_year,
        branch=branch,
        semester=semester,
    ).first()

    subjects = Subject.objects.filter(
        is_active=True,
        branch=branch,
        semester=semester,
    ).order_by("name")

    subject_rows = []

    for subject in subjects:
        requirement = (
            SubjectScheduleRequirement.objects
            .filter(subject=subject)
            .select_related("teacher", "teacher__user")
            .first()
        )

        teachers = TeacherProfile.objects.filter(
            is_active=True,
            branches__name=subject.branch,
            subjects=subject,
        ).select_related("user").distinct().order_by("user__username")

        subject_rows.append({
            "subject": subject,
            "requirement": requirement,
            "teachers": teachers,
        })

    if configuration:
        generated_slots = list(
            TimetableSlot.objects.filter(
                configuration=configuration,
                status=TimetableSlot.Status.DRAFT,
            ).select_related(
                "subject", "teacher", "teacher__user"
            ).order_by("day", "start_time")
        )
        if not generated_slots:
            generated_slots = list(
                TimetableSlot.objects.filter(
                    configuration=configuration,
                    status=TimetableSlot.Status.PUBLISHED,
                ).select_related(
                    "subject", "teacher", "teacher__user"
                ).order_by("day", "start_time")
            )
            published_timetable = bool(generated_slots)

    day_choices = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    timetable_headers = []
    timetable_rows = []

    if configuration:
        today = datetime.today().date()
        start = datetime.combine(today, configuration.college_start)
        end = datetime.combine(today, configuration.college_end)
        lunch_start = datetime.combine(today, configuration.lunch_start)
        lunch_end = datetime.combine(today, configuration.lunch_end)
        period_minutes = configuration.default_theory_duration

        current = start

        while current < end:
            if lunch_start <= current < lunch_end:
                timetable_headers.append({
                    "is_lunch": True,
                    "label": "Lunch",
                    "start": None,
                    "end": None,
                })
                current = lunch_end
                continue

            period_end = min(
                current + timedelta(minutes=period_minutes),
                end,
            )

            if current < lunch_start < period_end:
                period_end = lunch_start

            if period_end <= current:
                current = lunch_end
                continue

            timetable_headers.append({
                "is_lunch": False,
                "label": (
                    f"{current.strftime('%H:%M')} - "
                    f"{period_end.strftime('%H:%M')}"
                ),
                "start": current,
                "end": period_end,
            })

            current = period_end

        # Show only the configured number of working days.
        for day_number, day_name in day_choices[:configuration.working_days]:
            cells = []
            index = 0

            while index < len(timetable_headers):
                header = timetable_headers[index]

                if header["is_lunch"]:
                    cells.append({
                        "is_lunch": True,
                        "slot": None,
                        "colspan": 1,
                    })
                    index += 1
                    continue

                matching_slot = next(
                    (
                        slot for slot in generated_slots
                        if slot.day == day_number
                        and slot.start_time < header["end"].time()
                        and slot.end_time > header["start"].time()
                    ),
                    None,
                )

                if matching_slot is None:
                    cells.append({
                        "is_lunch": False,
                        "slot": None,
                        "colspan": 1,
                    })
                    index += 1
                    continue

                # Merge consecutive periods only when the session fully
                # covers those periods; partial periods remain separate.
                colspan = 0
                scan = index

                while scan < len(timetable_headers):
                    next_header = timetable_headers[scan]

                    if next_header["is_lunch"]:
                        break

                    if not (
                        matching_slot.start_time
                        <= next_header["start"].time()
                        and matching_slot.end_time
                        >= next_header["end"].time()
                    ):
                        break

                    colspan += 1
                    scan += 1

                if colspan == 0:
                    colspan = 1

                cells.append({
                    "is_lunch": False,
                    "slot": matching_slot,
                    "colspan": colspan,
                })
                index += colspan

            timetable_rows.append({
                "day": day_number,
                "day_name": day_name,
                "cells": cells,
            })

    context = {
        "branches": branches,
        "semester_choices": semester_choices,
        "academic_year": academic_year,
        "branch": branch,
        "semester": semester,
        "configuration": configuration,
        "theory_rooms_for_form": theory_rooms_for_form,
        "lab_rooms_for_form": lab_rooms_for_form,
        "subject_rows": subject_rows,
        "error_message": error_message,
        "success_message": success_message,
        "generation_done": generation_done,
        "generated_slots": generated_slots,
        "generation_conflicts": generation_conflicts,
        "published_timetable": published_timetable,
        "day_choices": day_choices,
        "timetable_headers": timetable_headers,
        "timetable_rows": timetable_rows,
    }

    return render(request, "timetable.html", context)
