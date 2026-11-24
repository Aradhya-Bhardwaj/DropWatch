from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse


class District(models.Model):
    name = models.CharField(max_length=80, unique=True)
    code = models.CharField(max_length=6, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Block(models.Model):
    name = models.CharField(max_length=80)
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name="blocks")
    is_rural = models.BooleanField(default=True)

    class Meta:
        ordering = ["district__name", "name"]
        unique_together = [("district", "name")]

    def __str__(self):
        return f"{self.name}, {self.district.name}"


class School(models.Model):
    PRIMARY, UPPER_PRIMARY, SECONDARY, HIGHER_SECONDARY = "PRI", "UPR", "SEC", "HSC"
    TYPE_CHOICES = [
        (PRIMARY, "Primary (1–5)"),
        (UPPER_PRIMARY, "Upper primary (1–8)"),
        (SECONDARY, "Secondary (1–10)"),
        (HIGHER_SECONDARY, "Senior secondary (1–12)"),
    ]
    HIGHEST_CLASS = {PRIMARY: 5, UPPER_PRIMARY: 8, SECONDARY: 10, HIGHER_SECONDARY: 12}

    MANAGEMENT_CHOICES = [("GOVT", "Government"), ("AIDED", "Government aided"), ("PVT", "Private unaided")]
    AREA_CHOICES = [("RURAL", "Rural"), ("URBAN", "Urban")]

    udise_code = models.CharField(
        "UDISE code",
        max_length=11,
        unique=True,
        validators=[RegexValidator(r"^\d{11}$", "UDISE code must be exactly 11 digits.")],
    )
    name = models.CharField(max_length=150)
    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name="schools")
    school_type = models.CharField(max_length=3, choices=TYPE_CHOICES)
    management = models.CharField(max_length=5, choices=MANAGEMENT_CHOICES, default="GOVT")
    area_type = models.CharField(max_length=5, choices=AREA_CHOICES, default="RURAL")
    has_girls_toilet = models.BooleanField("Separate girls' toilet", default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.udise_code})"

    @property
    def district(self):
        return self.block.district

    @property
    def highest_class(self):
        return self.HIGHEST_CLASS[self.school_type]

    def get_absolute_url(self):
        return reverse("analytics:school_detail", args=[self.udise_code])
