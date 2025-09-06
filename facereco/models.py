from django.db import models
from django.contrib.auth.models import User

class Register(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    student_name = models.CharField(max_length=100)
    roll_no = models.CharField(max_length=20, unique=True)
    semester = models.CharField(max_length=20)
    branch = models.CharField(max_length=50)
    face_image = models.ImageField(upload_to='face_images/', null=True, blank=True)


    def __str__(self):
        return self.student_name
    
    
class Subject(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name
    
class Attendance(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    face_image = models.ImageField(upload_to='attendance_faces/')

    def __str__(self):
        return f"{self.student.username} - {self.subject.name} at {self.timestamp}"
    

