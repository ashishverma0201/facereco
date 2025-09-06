import uuid
from django.shortcuts import render,HttpResponse
import facereco

def index(request):
   return render(request, 'index.html')


import base64
import uuid
from django.core.files.base import ContentFile
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Register

def register(request):
    if request.method == 'POST':
        student_name = request.POST.get('student_name')
        roll_no = request.POST.get('roll_no')
        semester = request.POST.get('semester')
        branch = request.POST.get('branch')
        password = request.POST.get('password')
        face_image_data = request.POST.get('face_image_data')

        # Check if user with roll_no exists
        if User.objects.filter(username=roll_no).exists():
            messages.error(request, "User with this Roll Number already exists.")
            return redirect('register')  # or render with error

        # Create user
        user = User.objects.create_user(username=roll_no, password=password)
        user.save()

        # Decode base64 image
        format, imgstr = face_image_data.split(';base64,')  # e.g. data:image/png;base64,...
        ext = format.split('/')[-1]  # file extension like png, jpeg
        img_data = base64.b64decode(imgstr)

        # Create a ContentFile from decoded image data
        file_name = f"{uuid.uuid4()}.{ext}"
        face_image_file = ContentFile(img_data, name=file_name)

        # Save registration data
        reg = Register.objects.create(
            user=user,
            student_name=student_name,
            roll_no=roll_no,
            semester=semester,
            branch=branch,
            face_image=face_image_file
        )
        reg.save()

        #messages.success(request, "Registration successful! Please login.")
        return redirect('login')  # Change 'login' to your login url name

    return render(request, 'register.html')



from django.contrib.auth import authenticate, login as auth_login
def login(request):
    if request.method == 'POST':
        roll_no = request.POST.get('roll_no')
        password = request.POST.get('password')
        user = authenticate(request, username=roll_no, password=password)
        if user is not None:
            auth_login(request, user)  # call django's login here
            return redirect('userpanel')  # change to your home url name
        else:
            messages.error(request, 'Invalid roll number or password')
    return render(request, 'login.html')



from django.contrib.auth.decorators import login_required
@login_required
def userprofile(request):
    user = request.user
    try:
        profile = Register.objects.get(user=user)
    except Register.DoesNotExist:
        profile = None

    context = {
        'user': user,
        'profile': profile,
    }
    return render(request, 'userprofile.html', context)


@login_required
def userpanel(request):
    try:
        profile = Register.objects.get(user=request.user)
    except Register.DoesNotExist:
        profile = None
    return render(request, 'userpanel.html', {'user': request.user, 'profile': profile})


from django.contrib.auth import authenticate, login as auth_login

def adminlogin(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None and user.is_staff:
            auth_login(request, user)  # ✅ Use Django's login
            return redirect('adminpanel')
        else:
            messages.error(request, "Invalid credentials or not an admin.")
    return render(request, 'adminlogin.html')


@login_required
def adminpanel(request):
    return render(request, 'adminpanel.html')


from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Register, Subject, Attendance
from django.core.files.base import ContentFile
from django.utils import timezone
import face_recognition
import cv2
import base64
import numpy as np

@login_required
def liveattendance(request):
    branches = ['IT','CSE','ECE','EE','CE']
    semester_subjects = {
        "IT": {
            "First": ["Computer Basics", "Maths-I", "Physics-I"],
            "Second": ["Programming Fundamentals", "Maths-II", "Digital Logic"],
            "Third": ["Data Structures", "Operating Systems", "Database Management"],
            "Fourth": ["Computer Networks", "Software Engineering", "Web Development"],
            "Fifth": ["Python", "Java", "Artificial Intelligence"],
            "Sixth": ["Machine Learning", "DNT", "Cloud Computing"]
        },
        "CSE": {
            "First": ["Maths-I", "Physics-I", "Introduction to Computers"],
            "Second": ["Maths-II", "Programming Basics", "Digital Logic"],
            "Third": ["Data Structures", "Operating Systems", "DBMS"],
            "Fourth": ["Computer Networks", "Algorithms", "Software Engg"],
            "Fifth": ["Java", "Python", "Compiler Design"],
            "Sixth": ["AI", "DNT", "Cloud Computing"]
        },
        "ECE": {
            "First": ["Maths-I", "Physics-I", "Basic Electronics"],
            "Second": ["Maths-II", "Circuit Theory", "Digital Electronics"],
            "Third": ["Signals & Systems", "Electromagnetics", "Microprocessors"],
            "Fourth": ["Communication Systems", "Analog Circuits", "Digital Communication"],
            "Fifth": ["VLSI Design", "Python", "Embedded Systems"],
            "Sixth": ["Computer Networks", "DNT", "Control Systems"]
        },
        "EE": {
            "First": ["Maths-I", "Physics-I", "Electrical Basics"],
            "Second": ["Maths-II", "Circuit Theory", "Electrical Machines-I"],
            "Third": ["Electronics", "Control Systems", "Power Systems-I"],
            "Fourth": ["Power Systems-II", "Electrical Machines-II", "Digital Systems"],
            "Fifth": ["Python", "DNT", "Renewable Energy"],
            "Sixth": ["Microgrids", "AI", "Communication Systems"]
        },
        "CE": {
            "First": ["Maths-I", "Physics-I", "Engineering Drawing"],
            "Second": ["Maths-II", "Mechanics", "Materials Science"],
            "Third": ["Surveying", "Building Materials", "Structural Analysis"],
            "Fourth": ["Design of Concrete Structures", "Fluid Mechanics", "Soil Mechanics"],
            "Fifth": ["Python", "Transportation Engineering", "DNT"],
            "Sixth": ["Environmental Engg", "Construction Management", "Computer Networks"]
        }
    }

    context = {'branches': branches, 'semester_subjects': semester_subjects}

    if request.method == 'POST':
        branch = request.POST.get('branch')
        semester = request.POST.get('semester')
        subject_name = request.POST.get('subject')
        face_data = request.POST.get('face_image_data')

        if not branch or not semester or not subject_name or not face_data:
            context['error'] = "Please fill all fields and capture face."
            return render(request, 'liveattendance.html', context)

        # Decode face image
        try:
            format, imgstr = face_data.split(';base64,')
            img_bytes = base64.b64decode(imgstr)
            nparr = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        except Exception:
            context['error'] = "Failed to decode face image."
            return render(request, 'liveattendance.html', context)

        # Get subject instance
        subject, _ = Subject.objects.get_or_create(name=subject_name)

        # Get students of branch & semester
        students = Register.objects.filter(branch=branch, semester=semester)
        matched_student = None

        for student in students:
            if not student.face_image:
                continue
            try:
                ref_image = face_recognition.load_image_file(student.face_image.path)
                ref_encoding = face_recognition.face_encodings(ref_image)[0]
                encodings = face_recognition.face_encodings(rgb_frame)
                if encodings and face_recognition.compare_faces([ref_encoding], encodings[0])[0]:
                    matched_student = student

                    # Save attendance
                    _, jpeg = cv2.imencode('.jpg', frame)
                    image_bytes = jpeg.tobytes()
                    attendance = Attendance.objects.create(
                        student=student.user,
                        subject=subject
                    )
                    filename = f"{student.roll_no}_{timezone.now().strftime('%Y%m%d%H%M%S')}.jpg"
                    attendance.face_image.save(filename, ContentFile(image_bytes))
                    attendance.save()
                    break
            except Exception:
                continue

        if matched_student:
            context['success'] = "Attendance marked successfully!"
            context['student'] = matched_student
            context['subject'] = subject
        else:
            context['error'] = "No matching face found."

    return render(request, 'liveattendance.html', context)









import base64
import uuid
from django.core.files.base import ContentFile
from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from .models import Register
import face_recognition


def register(request):
    if request.method == 'POST':
        student_name = request.POST.get('student_name')
        roll_no = request.POST.get('roll_no')
        semester = request.POST.get('semester')
        branch = request.POST.get('branch')
        password = request.POST.get('password')
        face_image_data = request.POST.get('face_image_data')

        # ✅ Roll Number check
        if User.objects.filter(username=roll_no).exists() or Register.objects.filter(roll_no=roll_no).exists():
            messages.error(request, "❌ User with this Roll Number already exists.")
            return render(request, 'register.html')

        # ✅ Face image required check
        if not face_image_data:
            messages.error(request, "❌ Please capture your face before registering.")
            return render(request, 'register.html')

        # ✅ Decode base64 face image
        format, imgstr = face_image_data.split(';base64,')
        ext = format.split('/')[-1]
        img_data = base64.b64decode(imgstr)
        file_name = f"{uuid.uuid4()}.{ext}"
        face_image_file = ContentFile(img_data, name=file_name)

        # ✅ Load face encoding of new student
        try:
            new_image_np = face_recognition.load_image_file(face_image_file)
            new_encoding = face_recognition.face_encodings(new_image_np)
        except Exception as e:
            messages.error(request, "❌ Error reading face image. Try again.")
            return render(request, 'register.html')

        if len(new_encoding) == 0:
            messages.error(request, "❌ No face detected. Please capture clearly.")
            return render(request, 'register.html')

        new_encoding = new_encoding[0]

        # ✅ Compare with existing student faces
        for student in Register.objects.all():
            try:
                existing_image = face_recognition.load_image_file(student.face_image.path)
                existing_encoding = face_recognition.face_encodings(existing_image)
                if len(existing_encoding) > 0:
                    match = face_recognition.compare_faces([existing_encoding[0]], new_encoding)[0]
                    if match:
                        messages.error(request, "❌ This face is already registered in the system.")
                        return render(request, 'register.html')
            except Exception:
                continue

        # ✅ Create new user
        user = User.objects.create_user(username=roll_no, password=password)
        user.save()

        # ✅ Save student data
        reg = Register.objects.create(
            user=user,
            student_name=student_name,
            roll_no=roll_no,
            semester=semester,
            branch=branch,
            face_image=face_image_file
        )
        reg.save()

        messages.success(request, "✅ Registration successful! Please login.")
        return redirect('login')

    return render(request, 'register.html')




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


def edit_student(request, student_id):
    student = get_object_or_404(Register, id=student_id)   # ✅ corrected

    if request.method == "POST":
        student.student_name = request.POST.get("student_name")
        student.roll_no = request.POST.get("roll_no")
        student.semester = request.POST.get("semester")
        student.branch = request.POST.get("branch")

        # ✅ Update linked User username if roll_no changes
        if student.user:
            student.user.username = student.roll_no
            student.user.save()

        student.save()

        messages.success(request, "Student updated successfully.")
        return redirect("manage_students")

    return render(request, "edit_student.html", {"student": student})


def delete_student(request, student_id):
    student = get_object_or_404(Register, id=student_id)   # ✅ corrected
    user = student.user
    student.delete()

    if user:
        user.delete()

    messages.success(request, "Student deleted successfully.")
    return redirect("manage_students")





from django.shortcuts import render
from .models import Register, Attendance

def student_search(request):
    student_data = None
    summary = []
    overall_percentage = 0
    total_attended = 0
    overall_total_classes = 0
    last_attendance = None
    error = None

    if request.method == "POST":
        roll_no = request.POST.get('roll_no')
        try:
            student_data = Register.objects.get(roll_no=roll_no)

            # ✅ Get all distinct subjects where this student has attendance records
            subjects = Attendance.objects.filter(student=student_data.user).values_list('subject', flat=True).distinct()

            for subject_id in subjects:
                subject_attendances = Attendance.objects.filter(subject_id=subject_id)
                total_classes = subject_attendances.count()
                attended = subject_attendances.filter(student=student_data.user).count()

                percentage = round((attended / total_classes) * 100, 2) if total_classes > 0 else 0

                summary.append({
                    'name': subject_attendances.first().subject.name,  # subject name
                    'attended': attended,
                    'total': total_classes,
                    'percentage': percentage
                })

                total_attended += attended
                overall_total_classes += total_classes

            overall_percentage = round((total_attended / overall_total_classes) * 100, 2) if overall_total_classes > 0 else 0

            # Last attendance
            last_attendance_qs = Attendance.objects.filter(student=student_data.user).order_by('-timestamp')
            last_attendance = last_attendance_qs.first().timestamp if last_attendance_qs.exists() else None

        except Register.DoesNotExist:
            error = "Student with this roll number does not exist."

    context = {
        'student_data': student_data,
        'summary': summary,
        'overall_percentage': overall_percentage,
        'total_attended': total_attended,
        'overall_total_classes': overall_total_classes,
        'last_attendance': last_attendance,
        'error': error
    }
    return render(request, 'student_search.html', context)

