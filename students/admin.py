from django.contrib import admin

from .models import AcademicYear, AttendanceRecord, Enrollment, ExitRecord, Student


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("label", "start_year", "is_complete")


class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0
    fields = ("year", "school", "standard", "attendance_pct", "status")
    raw_id_fields = ("school",)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("name", "student_uid", "gender", "category", "school", "income_band")
    list_filter = ("gender", "category", "income_band", "is_cwsn", "school__block__district")
    search_fields = ("name", "student_uid")
    raw_id_fields = ("school",)
    inlines = [EnrollmentInline]


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "year", "school", "standard", "attendance_pct", "status")
    list_filter = ("year", "status", "standard", "school__block__district")
    search_fields = ("student__name", "student__student_uid")
    raw_id_fields = ("student", "school")
    list_select_related = ("student", "school", "year")


@admin.register(ExitRecord)
class ExitRecordAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "reason", "exit_date", "to_school", "verified")
    list_filter = ("reason", "verified")
    raw_id_fields = ("enrollment", "to_school")


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "month", "pct")
    raw_id_fields = ("enrollment",)
