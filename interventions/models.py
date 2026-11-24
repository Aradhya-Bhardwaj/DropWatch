from django.conf import settings
from django.db import models

from schools.models import District, School
from students.models import CATEGORY_CHOICES, GENDER_CHOICES, AcademicYear, ExitRecord


class Scheme(models.Model):
    LEVEL_CHOICES = [("CENTRAL", "Central"), ("STATE", "State"), ("DISTRICT", "District / school action")]

    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)
    level = models.CharField(max_length=8, choices=LEVEL_CHOICES)
    description = models.TextField()
    cost_per_student = models.PositiveIntegerField("Estimated cost per student (₹ per year)", default=0)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class InterventionRule(models.Model):
    """When a hotspot segment matches these conditions, recommend the scheme. Blank fields match anything."""

    scheme = models.ForeignKey(Scheme, on_delete=models.CASCADE, related_name="rules")
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    category = models.CharField(max_length=3, choices=CATEGORY_CHOICES, blank=True)
    min_standard = models.PositiveSmallIntegerField(default=1)
    max_standard = models.PositiveSmallIntegerField(default=12)
    area_type = models.CharField(max_length=5, choices=School.AREA_CHOICES, blank=True)
    reason = models.CharField(
        max_length=10, choices=ExitRecord.REASON_CHOICES, blank=True,
        help_text="Matches when this is one of the segment's top three exit reasons",
    )
    priority = models.PositiveSmallIntegerField(default=5, help_text="1 (low) to 10 (high)")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-priority"]

    def __str__(self):
        return f"{self.scheme.name} (priority {self.priority})"


class Recommendation(models.Model):
    PROPOSED, APPROVED, IN_PROGRESS, DONE, REJECTED = "PROPOSED", "APPROVED", "IN_PROGRESS", "DONE", "REJECTED"
    STATUS_CHOICES = [
        (PROPOSED, "Proposed"),
        (APPROVED, "Approved"),
        (IN_PROGRESS, "Being implemented"),
        (DONE, "Implemented"),
        (REJECTED, "Rejected"),
    ]

    scheme = models.ForeignKey(Scheme, on_delete=models.PROTECT, related_name="recommendations")
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name="recommendations")
    # The segment this recommendation targets (blank = everyone)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    category = models.CharField(max_length=3, choices=CATEGORY_CHOICES, blank=True)
    min_standard = models.PositiveSmallIntegerField(default=1)
    max_standard = models.PositiveSmallIntegerField(default=12)
    area_type = models.CharField(max_length=5, choices=School.AREA_CHOICES, blank=True)

    baseline_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, related_name="+")
    baseline_rate = models.DecimalField(max_digits=5, decimal_places=2)
    students_in_segment = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=11, choices=STATUS_CHOICES, default=PROPOSED)
    started_year = models.ForeignKey(
        AcademicYear, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="School year in which the intervention started",
    )
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-baseline_rate"]

    def __str__(self):
        return f"{self.scheme} for {self.segment_label()}"

    def segment_label(self):
        parts = []
        if self.gender:
            parts.append(self.get_gender_display())
        else:
            parts.append("Students")
        if self.category:
            parts.append(f"({self.get_category_display()})")
        if self.min_standard == self.max_standard:
            parts.append(f"in Class {self.min_standard}")
        elif (self.min_standard, self.max_standard) != (1, 12):
            parts.append(f"in Classes {self.min_standard}–{self.max_standard}")
        if self.area_type:
            parts.append(f"at {self.get_area_type_display().lower()} schools")
        parts.append(f"in {self.district.name}")
        return " ".join(parts)

    def segment_filters(self):
        """Filters on Enrollment that select this segment."""
        f = {"school__block__district": self.district,
             "standard__gte": self.min_standard, "standard__lte": self.max_standard}
        if self.gender:
            f["student__gender"] = self.gender
        if self.category:
            f["student__category"] = self.category
        if self.area_type:
            f["school__area_type"] = self.area_type
        return f


class ActionLog(models.Model):
    recommendation = models.ForeignKey(Recommendation, on_delete=models.CASCADE, related_name="actions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    note = models.TextField()
    status_after = models.CharField(max_length=11, choices=Recommendation.STATUS_CHOICES)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.recommendation_id}: {self.note[:40]}"
