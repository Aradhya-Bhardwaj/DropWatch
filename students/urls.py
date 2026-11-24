from django.urls import path

from . import views

app_name = "students"

urlpatterns = [
    path("", views.student_list, name="list"),
    path("add/", views.student_add, name="add"),
    path("enrolment/<int:pk>/exit/", views.record_exit, name="exit"),
    path("upload/", views.upload, name="upload"),
    path("upload/template.csv", views.sample_csv, name="sample_csv"),
]
