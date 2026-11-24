from django.conf import settings
from django.db import models

from schools.models import District, School


class Profile(models.Model):
    """Role and jurisdiction for each user. Decides which data a user may see."""

    STATE, DISTRICT, SCHOOL = "STATE", "DISTRICT", "SCHOOL"
    ROLE_CHOICES = [
        (STATE, "State education officer"),
        (DISTRICT, "District education officer"),
        (SCHOOL, "School head / teacher"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=8, choices=ROLE_CHOICES, default=STATE)
    district = models.ForeignKey(District, null=True, blank=True, on_delete=models.SET_NULL)
    school = models.ForeignKey(School, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def scope_label(self):
        if self.role == self.SCHOOL and self.school:
            return self.school.name
        if self.role == self.DISTRICT and self.district:
            return f"{self.district.name} district"
        return "All districts"
