import csv
import io
from datetime import date

from django import forms

from schools.models import School

from .models import CATEGORY_CHOICES, GENDER_CHOICES, INCOME_CHOICES, Enrollment, ExitRecord, Student


class StudentForm(forms.ModelForm):
    standard = forms.IntegerField(min_value=1, max_value=12, label="Class")

    class Meta:
        model = Student
        fields = ["student_uid", "name", "gender", "category", "date_of_birth", "income_band",
                  "distance_km", "is_cwsn"]
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}
        help_texts = {"student_uid": "PB followed by 10 digits, e.g. PB0000123456"}

    def __init__(self, *args, school=None, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)

    def clean_student_uid(self):
        uid = self.cleaned_data["student_uid"].strip().upper()
        if not (len(uid) == 12 and uid.startswith("PB") and uid[2:].isdigit()):
            raise forms.ValidationError("Use PB followed by 10 digits.")
        return uid

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if len(name) < 3:
            raise forms.ValidationError("Enter the student's full name.")
        return name.title()

    def clean_date_of_birth(self):
        dob = self.cleaned_data["date_of_birth"]
        age = (date.today() - dob).days // 365
        if not 4 <= age <= 22:
            raise forms.ValidationError(f"That makes the student {age} years old. School students are 4 to 22.")
        return dob

    def clean(self):
        data = super().clean()
        std, dob = data.get("standard"), data.get("date_of_birth")
        if self.school and std and std > self.school.highest_class:
            self.add_error("standard", f"This school only goes up to Class {self.school.highest_class}.")
        if std and dob:
            age = (date.today() - dob).days // 365
            if age < std + 3:
                self.add_error("date_of_birth", f"Age {age} is too young for Class {std}.")
        return data


class ExitForm(forms.ModelForm):
    """Record that a student left. A transfer needs the receiving school so it is not counted as a dropout."""

    LEFT_CHOICES = [(Enrollment.DROPPED, "Dropped out of school"), (Enrollment.TRANSFERRED, "Moved to another school")]
    left_as = forms.ChoiceField(choices=LEFT_CHOICES, widget=forms.RadioSelect, label="What happened")

    class Meta:
        model = ExitRecord
        fields = ["left_as", "reason", "exit_date", "to_school", "notes", "verified"]
        widgets = {"exit_date": forms.DateInput(attrs={"type": "date"}), "notes": forms.Textarea(attrs={"rows": 3})}
        labels = {"verified": "I confirmed this on a home visit or call"}

    def __init__(self, *args, enrollment=None, **kwargs):
        self.enrollment = enrollment
        super().__init__(*args, **kwargs)
        self.fields["reason"].choices = [c for c in ExitRecord.REASON_CHOICES if c[0] != "TRANSFER"]
        self.fields["reason"].required = False
        if enrollment:
            self.fields["to_school"].queryset = School.objects.filter(
                block__district=enrollment.school.block.district).exclude(pk=enrollment.school_id)

    def clean(self):
        data = super().clean()
        left_as = data.get("left_as")
        if left_as == Enrollment.TRANSFERRED:
            if not data.get("to_school"):
                self.add_error("to_school", "Choose the school the student moved to.")
            data["reason"] = "TRANSFER"
        elif left_as == Enrollment.DROPPED:
            data["to_school"] = None
            if not data.get("reason"):
                self.add_error("reason", "Choose the main reason. Pick “Not recorded” only if nobody knows.")
        d = data.get("exit_date")
        if d and self.enrollment:
            start = date(self.enrollment.year.start_year, 4, 1)
            end = date(self.enrollment.year.start_year + 1, 3, 31)
            if not start <= d <= end:
                self.add_error("exit_date", f"The date must fall in the {self.enrollment.year} school year.")
            if d > date.today():
                self.add_error("exit_date", "The date can't be in the future.")
        return data


class UploadForm(forms.Form):
    school = forms.ModelChoiceField(queryset=School.objects.all())
    file = forms.FileField(label="CSV file", help_text="Use the sample file's columns. Up to 2,000 rows.")

    COLUMNS = ["student_uid", "name", "gender", "category", "date_of_birth", "standard", "income_band",
               "distance_km", "is_cwsn"]

    def __init__(self, *args, schools=None, **kwargs):
        super().__init__(*args, **kwargs)
        if schools is not None:
            self.fields["school"].queryset = schools

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".csv"):
            raise forms.ValidationError("Upload a .csv file. In Excel, use File, Save as, CSV UTF-8.")
        try:
            text = f.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise forms.ValidationError("The file isn't UTF-8 text. Save it as CSV UTF-8 and try again.")
        reader = csv.DictReader(io.StringIO(text))
        missing = [c for c in self.COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise forms.ValidationError(f"Missing columns: {', '.join(missing)}.")
        rows = list(reader)
        if not rows:
            raise forms.ValidationError("The file has a header but no students.")
        if len(rows) > 2000:
            raise forms.ValidationError(f"The file has {len(rows):,} rows. Split it into files of 2,000 or fewer.")
        return rows


class StudentRowForm(StudentForm):
    """Validates one CSV row with the same rules as the single-student form."""

    def __init__(self, row, school):
        data = dict(row)
        data["is_cwsn"] = str(row.get("is_cwsn", "")).strip().lower() in ("1", "yes", "y", "true")
        data["gender"] = str(row.get("gender", "")).strip().upper()[:1]
        data["category"] = str(row.get("category", "")).strip().upper()
        data["income_band"] = str(row.get("income_band", "")).strip().upper()
        super().__init__(data, school=school)
