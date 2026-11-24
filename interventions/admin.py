from django.contrib import admin

from .models import ActionLog, InterventionRule, Recommendation, Scheme


class RuleInline(admin.TabularInline):
    model = InterventionRule
    extra = 0


@admin.register(Scheme)
class SchemeAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "cost_per_student")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [RuleInline]


@admin.register(InterventionRule)
class InterventionRuleAdmin(admin.ModelAdmin):
    list_display = ("scheme", "gender", "category", "min_standard", "max_standard", "area_type", "reason", "priority", "active")
    list_filter = ("active", "scheme")
    list_editable = ("priority", "active")


class ActionInline(admin.TabularInline):
    model = ActionLog
    extra = 0


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "baseline_rate", "status", "owner")
    list_filter = ("status", "district", "scheme")
    inlines = [ActionInline]
