from django.urls import path, re_path

from . import views

app_name = "analytics"

urlpatterns = [
    path("schools/", views.schools_view, name="schools"),
    path("area/", views.area_view, name="area"),
    path("gender/", views.gender_view, name="gender"),
    path("caste/", views.caste_view, name="caste"),
    path("class/", views.standard_view, name="standard"),
    path("explore/", views.explore_view, name="explore"),
    path("hotspots/", views.hotspots_view, name="hotspots"),
    path("watchlist/", views.watchlist_view, name="watchlist"),
    path("data-quality/", views.data_quality_view, name="quality"),
    # Regular expressions: an 11-digit UDISE code, and a fixed set of export names
    re_path(r"^schools/(?P<udise>\d{11})/$", views.school_detail, name="school_detail"),
    re_path(r"^export/(?P<dimension>school|district|block|gender|category|standard|area)\.csv$",
            views.export_csv, name="export"),
]
