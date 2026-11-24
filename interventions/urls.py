from django.urls import path

from . import views

app_name = "interventions"

urlpatterns = [
    path("", views.recommendation_list, name="list"),
    path("generate/", views.generate, name="generate"),
    path("<int:pk>/", views.recommendation_detail, name="detail"),
    path("schemes/", views.scheme_list, name="schemes"),
]
