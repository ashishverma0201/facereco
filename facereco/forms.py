from django import forms
from .models import Subject

class SubjectSelectionForm(forms.Form):
    subject = forms.ModelChoiceField(queryset=Subject.objects.all(), required=True)
    roll_no = forms.CharField(label="Roll Number", max_length=20, required=True)


from django import forms

class RollNumberForm(forms.Form):
    roll_no = forms.CharField(
        max_length=20, 
        label="Enter Roll Number",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter Roll Number'})
    )
