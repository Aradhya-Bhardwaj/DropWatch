from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect

from analytics import services as s
from analytics.filters import get_filters, get_profile
from core.shortcuts import flash, render_page
from students.models import AcademicYear

from . import engine
from .forms import ActionForm
from .models import ActionLog, Recommendation, Scheme


def _visible(profile):
    qs = Recommendation.objects.select_related("scheme", "district", "baseline_year", "owner")
    if profile and profile.role in ("DISTRICT", "SCHOOL"):
        qs = qs.filter(district=profile.district_id)
    return qs


@login_required
def recommendation_list(request):
    profile = get_profile(request)
    status = request.GET.get("status", "")
    recs = _visible(profile)
    if status in dict(Recommendation.STATUS_CHOICES):
        recs = recs.filter(status=status)
    statuses = [(c, label, _visible(profile).filter(status=c).count()) for c, label in Recommendation.STATUS_CHOICES]
    return render_page(request, "interventions/list.html", {
        "recs": recs, "status": status, "statuses": statuses,
        "section": "interventions", "can_generate": request.user.has_perm("interventions.add_recommendation"),
    })


@login_required
@permission_required("interventions.add_recommendation", raise_exception=True)
def generate(request):
    if request.method != "POST":       # creates records, so GET is refused
        return HttpResponseNotAllowed(["POST"])
    _, filters = get_filters(request)
    qs = s.enrollments(filters, get_profile(request))
    n = engine.create_recommendations(qs, filters["year"], request.user)
    if n:
        flash(request, f"Proposed {n} new recommendations from the current hotspots.")
    else:
        flash(request, "No new recommendations. Every district hotspot already has one.")
    return redirect("interventions:list")


@login_required
def recommendation_detail(request, pk):
    rec = get_object_or_404(Recommendation.objects.select_related("scheme", "district", "baseline_year",
                                                                  "started_year", "owner"), pk=pk)
    profile = get_profile(request)
    if profile and profile.role in ("DISTRICT", "SCHOOL") and rec.district_id != profile.district_id:
        raise PermissionDenied("This recommendation is for another district.")
    can_act = request.user.has_perm("interventions.change_recommendation")

    if request.method == "POST":
        if not can_act:
            raise PermissionDenied("You can view this recommendation but not change it.")
        form = ActionForm(request.POST, recommendation=rec)
        if form.is_valid():
            rec.status = form.cleaned_data["status"]
            if form.cleaned_data["started_year"]:
                rec.started_year = AcademicYear.objects.filter(is_complete=False).last()
            if rec.owner is None:
                rec.owner = request.user
            rec.save()
            ActionLog.objects.create(recommendation=rec, user=request.user, note=form.cleaned_data["note"],
                                     status_after=rec.status)
            flash(request, f"Saved. Status is now {rec.get_status_display().lower()}.")
            return redirect("interventions:detail", pk=rec.pk)
    else:
        form = ActionForm(recommendation=rec)

    result = engine.impact(rec)
    seg_rows = [r for r in result["rows"]]
    cost = rec.scheme.cost_per_student * rec.students_in_segment
    return render_page(request, "interventions/detail.html", {
        "rec": rec, "form": form, "can_act": can_act, "impact": result, "cost": cost,
        "actions": rec.actions.select_related("user"), "section": "interventions",
        "trend": {"years": [r["year"].label for r in seg_rows],
                  "series": [{"label": rec.district.name, "values": [r["target"]["rate"] for r in seg_rows]},
                             {"label": "Other districts", "values": [r["comparison"]["rate"] for r in seg_rows]}],
                  "marker": rec.started_year.label if rec.started_year else None},
    })


@login_required
def scheme_list(request):
    schemes = Scheme.objects.prefetch_related("rules")
    return render_page(request, "interventions/schemes.html", {"schemes": schemes, "section": "schemes"})
