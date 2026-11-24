from datetime import timedelta

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Group, User
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render

from analytics import services as s
from analytics.filters import SESSION_KEY, describe, get_filters, get_profile
from interventions.models import Recommendation
from students.models import Student

from .forms import LoginForm, PasswordChangeForm, UserCreateForm
from .models import Profile
from .shortcuts import flash, render_page, safe_next


def landing(request):
    """Public front page. The hero shows the worst large hotspot as 100 children."""
    year = s.latest_completed_year()
    qs = s.enrollments({"year": year}, None)
    spots, overall = s.hotspots(qs, limit=10)
    hero = next((h for h in spots if "district" in h["segment"] and "gender" in h["segment"]),
                spots[0] if spots else None)
    phrase = None
    if hero:
        label = hero["label"]
        phrase = label if label.startswith(("SC", "ST", "OBC")) else label[0].lower() + label[1:]
    stages = {r["code"]: r for r in s.by_stage(qs)}
    return render_page(request, "core/landing.html", {
        "year": year, "hero": hero, "hero_phrase": phrase, "left": round(hero["rate"]) if hero else 0,
        "dots": range(100), "overall": overall, "students": Student.objects.count(),
        "secondary": stages.get("SEC"), "primary": stages.get("PRI"), "districts": s.by_district(qs)[:3],
    })


# ---------------------------------------------------------------- login and logout (Unit VI)

def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if request.method == "POST":
        form = LoginForm(request.POST, request=request)
        if form.is_valid():
            login(request, form.user)
            # Session length: browser session by default, two weeks when "keep me signed in" is ticked
            request.session.set_expiry(timedelta(days=14) if form.cleaned_data["remember"] else 0)
            flash(request, f"Signed in as {form.user.get_full_name() or form.user.username}.")
            response = redirect(safe_next(next_url, "core:dashboard"))
            # A plain cookie remembers the last username so the login form can prefill it
            response.set_cookie("dw_last_user", form.user.username, max_age=60 * 60 * 24 * 30, samesite="Lax")
            return response
    else:
        form = LoginForm(request=request, initial={"username": request.COOKIES.get("dw_last_user", "")})
    return render_page(request, "core/login.html", {"form": form, "next": next_url})


def logout_view(request):
    # Signing out changes state, so only POST is allowed (a link or prefetch can't sign someone out)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    logout(request)  # also flushes the session, including saved filters
    flash(request, "You are signed out.", "info")
    return redirect("core:landing")


@login_required
def change_password(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.POST, user=request.user)
        if form.is_valid():
            request.user.set_password(form.cleaned_data["new_password1"])
            request.user.save()
            login(request, request.user)  # changing the password ends the session; sign straight back in
            flash(request, "Password changed.")
            return redirect("core:dashboard")
    else:
        form = PasswordChangeForm(user=request.user)
    return render_page(request, "core/password.html", {"form": form, "section": "account"})


# ---------------------------------------------------------------- managing users (Unit V and VI)

ROLE_GROUPS = {Profile.STATE: "State officers", Profile.DISTRICT: "District officers", Profile.SCHOOL: "School staff"}


@login_required
@permission_required("auth.view_user", raise_exception=True)
def user_list(request):
    users = (User.objects.select_related("profile", "profile__district", "profile__school")
             .prefetch_related("groups").order_by("-is_active", "username"))
    return render_page(request, "core/users.html", {"users": users, "section": "users"})


@login_required
@permission_required("auth.add_user", raise_exception=True)
def user_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            user = User.objects.create_user(d["username"], email=d["email"], password=d["password1"],
                                            first_name=d["first_name"], last_name=d["last_name"])
            user.groups.add(Group.objects.get_or_create(name=ROLE_GROUPS[d["role"]])[0])
            Profile.objects.create(user=user, role=d["role"], district=d.get("district"), school=d.get("school"))
            flash(request, f"Created {user.username} as {user.profile.get_role_display().lower()}.")
            return redirect("core:users")
    else:
        form = UserCreateForm()
    return render_page(request, "core/user_form.html", {"form": form, "section": "users"})


@login_required
@permission_required("auth.change_user", raise_exception=True)
def user_toggle(request, pk):
    """Switch an account off or back on. Accounts are never deleted, so their records keep an author."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        flash(request, "You can't switch off your own account.", "error")
    elif user.is_superuser:
        flash(request, "Administrator accounts can only be changed in the administration site.", "error")
    else:
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        flash(request, f"{user.username} is now {'active' if user.is_active else 'switched off'}.")
    return redirect("core:users")


# ---------------------------------------------------------------- dashboard

@login_required
def dashboard(request):
    form, filters = get_filters(request)
    profile = get_profile(request)
    qs = s.enrollments(filters, profile)
    years = list(s.completed_years())
    year = filters["year"]
    prev = next((y for y in reversed(years) if y.start_year < year.start_year), None)
    prev_summary = s.summary(s.enrollments(filters, profile, prev)) if prev else None
    overall = s.summary(qs)
    change = (round(overall["rate"] - prev_summary["rate"], 1)
              if prev_summary and overall["rate"] is not None and prev_summary["rate"] is not None else None)
    genders = {g["student__gender"]: g for g in s.by_gender(qs)}
    spots, _ = s.hotspots(qs, limit=5)
    _, watch = s.watchlist(profile, filters)
    recs = Recommendation.objects.all()
    if profile and profile.role in ("DISTRICT", "SCHOOL"):
        recs = recs.filter(district=profile.district_id)
    classes = s.by_standard(qs)
    reasons = s.top_reasons(qs, limit=6)
    return render_page(request, "core/dashboard.html", {
        "filter_form": form, "filters": filters, "filter_label": describe(filters), "year": year, "prev": prev,
        "overall": overall, "change": change, "change_text": s.fmt_signed(change),
        "girls": genders.get("F"), "boys": genders.get("M"),
        "stages": s.shade(s.by_stage(qs), overall["rate"], scale_max=20), "spots": spots,
        "watch_count": len(watch), "open_recs": recs.exclude(status__in=["DONE", "REJECTED"]).count(),
        "recs_done": recs.filter(status="DONE").count(),
        "districts": s.by_district(qs), "reasons": reasons, "section": "dashboard",
        "recent_schools": request.session.get("recent_schools", []),
        "class_chart": {"labels": [f"{r['standard']}" for r in classes], "values": [r["rate"] for r in classes],
                        "reference": overall["rate"]},
        "reason_chart": {"labels": [r["label"] for r in reasons], "values": [r["share"] for r in reasons]},
    })


def reset_filters(request):
    request.session.pop(SESSION_KEY, None)
    flash(request, "Filters cleared.", "info")
    return redirect(safe_next(request.GET.get("next", ""), "core:dashboard"))


def dismiss_notice(request):
    """Hide the demo-data banner for a year by setting a cookie."""
    response = redirect(safe_next(request.GET.get("next", ""), "core:landing"))
    response.set_cookie("dw_notice_dismissed", "1", max_age=60 * 60 * 24 * 365, samesite="Lax")
    return response


def about(request):
    return render_page(request, "core/about.html", {"section": "about"})


# ---------------------------------------------------------------- error handling (Unit II)

def error_404(request, exception):
    return render(request, "errors/404.html", {"message": str(exception) if exception else ""}, status=404)


def error_403(request, exception):
    return render(request, "errors/403.html", {"message": str(exception) if exception else ""}, status=403)


def error_500(request):
    return render(request, "errors/500.html", status=500)
