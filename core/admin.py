from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import Profile


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False


class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    list_display = ("username", "first_name", "last_name", "is_staff", "role")

    @admin.display(description="Role")
    def role(self, obj):
        return obj.profile.get_role_display() if hasattr(obj, "profile") else "—"


admin.site.unregister(User)
admin.site.register(User, UserAdmin)

admin.site.site_header = "DropWatch administration"
admin.site.site_title = "DropWatch admin"
admin.site.index_title = "Master data, schemes and users"
