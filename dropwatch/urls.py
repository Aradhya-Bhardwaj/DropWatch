"""DropWatch URL configuration."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    path("analysis/", include("analytics.urls")),
    path("students/", include("students.urls")),
    path("interventions/", include("interventions.urls")),
    path("admin/", admin.site.urls),
]

# Custom error pages (shown when DEBUG = False)
handler403 = "core.views.error_403"
handler404 = "core.views.error_404"
handler500 = "core.views.error_500"
