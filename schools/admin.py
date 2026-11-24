from django.contrib import admin

from .models import Block, District, School


class BlockInline(admin.TabularInline):
    model = Block
    extra = 0


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name",)
    inlines = [BlockInline]


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("name", "district", "is_rural")
    list_filter = ("district", "is_rural")


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "udise_code", "block", "school_type", "management", "area_type", "has_girls_toilet")
    list_filter = ("school_type", "management", "area_type", "has_girls_toilet", "block__district")
    search_fields = ("name", "udise_code")
