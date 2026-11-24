from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("about/", views.about, name="about"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("account/password/", views.change_password, name="password"),
    path("users/", views.user_list, name="users"),
    path("users/new/", views.user_create, name="user_create"),
    path("users/<int:pk>/toggle/", views.user_toggle, name="user_toggle"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("filters/reset/", views.reset_filters, name="reset_filters"),
    path("notice/dismiss/", views.dismiss_notice, name="dismiss_notice"),
]
