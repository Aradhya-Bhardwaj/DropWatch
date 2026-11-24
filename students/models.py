from datetime import date

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from schools.models import School


class AcademicYear(models.Model):
    label = models.CharField(max_length=7, unique=True, help_text="Format 2025-26")
    start_year = models.PositiveIntegerField(unique=True)
    is_complete = models.BooleanField(
        default=True, help_text="Completed years have final statuses and are used for dropout rates."
    )

    class Meta:
        ordering = ["start_year"]

    def __str__(self):
        return self.label


GENDER_CHOICES = [("F", "Girls"), ("M", "Boys")]
CATEGORY_CHOICES = [("GEN", "General"), ("OBC", "OBC"), ("SC", "SC"), ("ST", "ST")]
INCOME_CHOICES = [("BPL", "Below poverty line"), ("LOW", "Low income"), ("MID", "Middle income")]


class Student(models.Model):
    student_uid = models.CharField("Student ID", max_length=12, unique=True)
    name = models.CharField(max_length=120)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    category = models.CharField("Social category", max_length=3, choices=CATEGORY_CHOICES)
    date_of_birth = models.DateField()
    is_cwsn = models.BooleanField("Child with special needs", default=False)
    income_band = models.CharField(max_length=3, choices=INCOME_CHOICES, default="LOW")
    distance_km = models.DecimalField(
        "Distance from home (km)", max_digits=4, decimal_places=1, default=1,
        validators=[MinValueValidator(0), MaxValueValidator(50)],
    )
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="students")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.student_uid})"

    def age_on(self, when=None):
        when = when or date.today()
        d = self.date_of_birth
        return when.year - d.year - ((when.month, when.day) < (d.month, d.day))


class Enrollment(models.Model):
    """One row per student per academic year. Every dropout analysis is a GROUP BY over this table."""

    ENROLLED, PROMOTED, REPEATED, DROPPED, TRANSFERRED, COMPLETED = (
        "ENROLLED", "PROMOTED", "REPEATED", "DROPPED", "TRANSFERRED", "COMPLETED",
    )
    STATUS_CHOICES = [
        (ENROLLED, "Studying"),
        (PROMOTED, "Promoted"),
        (REPEATED, "Repeated class"),
        (DROPPED, "Dropped out"),
        (TRANSFERRED, "Transferred"),
        (COMPLETED, "Completed school"),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="enrollments")
    year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="enrollments")
    standard = models.PositiveSmallIntegerField(
        "Class", validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    attendance_pct = models.PositiveSmallIntegerField(default=90, validators=[MaxValueValidator(100)])
    status = models.CharField(max_length=11, choices=STATUS_CHOICES, default=ENROLLED)

    class Meta:
        unique_together = [("student", "year")]
        indexes = [
            models.Index(fields=["year", "status"]),
            models.Index(fields=["year", "standard"]),
        ]

    def __str__(self):
        return f"{self.student.name} — Class {self.standard}, {self.year}"


class ExitRecord(models.Model):
    """Why and where a student left. Transfers point at the receiving school so they are not counted as dropouts."""

    REASON_CHOICES = [
        ("FINANCIAL", "Cannot afford costs"),
        ("LABOUR", "Working to support family"),
        ("MIGRATION", "Family migrated"),
        ("DISTANCE", "School too far"),
        ("MARRIAGE", "Early marriage"),
        ("HOUSEHOLD", "Household duties"),
        ("INTEREST", "Lost interest in studies"),
        ("FAILED", "Failed exam"),
        ("HEALTH", "Illness or disability"),
        ("FACILITY", "No girls' toilet or safety concern"),
        ("TRANSFER", "Moved to another school"),
        ("UNKNOWN", "Not recorded"),
    ]

    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name="exit")
    exit_date = models.DateField()
    reason = models.CharField(max_length=10, choices=REASON_CHOICES, default="UNKNOWN")
    notes = models.TextField(blank=True)
    to_school = models.ForeignKey(
        School, null=True, blank=True, on_delete=models.SET_NULL, related_name="transfers_in",
        help_text="Receiving school, for transfers",
    )
    verified = models.BooleanField(default=False, help_text="Confirmed on a home or field visit")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.enrollment.student.name}: {self.get_reason_display()}"


class AttendanceRecord(models.Model):
    MONTH_CHOICES = [(m, n) for m, n in enumerate(
        ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]) if m]

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="attendance")
    month = models.PositiveSmallIntegerField(choices=MONTH_CHOICES)
    seq = models.PositiveSmallIntegerField(help_text="Month number within the school year (Apr = 1)")
    pct = models.PositiveSmallIntegerField(validators=[MaxValueValidator(100)])

    class Meta:
        unique_together = [("enrollment", "month")]
        ordering = ["seq"]

    def __str__(self):
        return f"{self.enrollment} {self.get_month_display()}: {self.pct}%"
