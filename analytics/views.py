import csv
from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404

from core.shortcuts import paginate, render_page

from schools.models import School
from students.models import AcademicYear, Enrollment

from . import services as s
from .filters import describe, get_filters, get_profile
from .forms import ExploreForm


def _context(request, **extra):
    form, filters = get_filters(request)
    profile = get_profile(request)
    qs = s.enrollments(filters, profile)
    ctx = {"filter_form": form, "filters": filters, "filter_label": describe(filters),
           "year": filters["year"], "qs": qs, "profile": profile, "overall": s.summary(qs)}
    ctx.update(extra)
    return ctx


def _bar(rows, label_key, value_key="rate", highlight=None):
    return {"labels": [r[label_key] for r in rows], "values": [r[value_key] for r in rows],
            "highlight": highlight}


@login_required
def schools_view(request):
    ctx = _context(request, section="schools")
    rows = s.shade(s.by_school(ctx["qs"]), ctx["overall"]["rate"])
    ctx["rows"] = paginate(request, rows, 25)
    ranked = [r for r in rows if r["rate"] is not None][:15]
    ctx["chart"] = {"labels": [r["school__name"].split(", ")[-1] for r in ranked],
                    "values": [r["rate"] for r in ranked], "reference": ctx["overall"]["rate"]}
    ctx["struggling"] = [r for r in rows if r["vs_block"] and r["vs_block"] >= 1.5]
    ctx["no_toilet"] = s.summary(ctx["qs"].filter(student__gender="F", standard__gte=6,
                                                   school__has_girls_toilet=False))
    ctx["with_toilet"] = s.summary(ctx["qs"].filter(student__gender="F", standard__gte=6,
                                                     school__has_girls_toilet=True))
    s.shade([ctx["no_toilet"], ctx["with_toilet"]], scale_max=20)
    return render_page(request, "analytics/schools.html", ctx)


@login_required
def area_view(request):
    ctx = _context(request, section="area")
    districts = s.by_district(ctx["qs"])
    ctx["districts"] = s.shade(districts, ctx["overall"]["rate"])
    ctx["areas"] = s.by_area(ctx["qs"])
    blocks = s.by_block(ctx["qs"])
    rates = [b["rate"] for b in blocks if b["rate"] is not None]
    ctx["blocks"] = s.shade(blocks, ctx["overall"]["rate"], max(rates) if rates else 1)
    ctx["chart"] = _bar(districts, "school__block__district__name")
    ctx["chart"]["reference"] = ctx["overall"]["rate"]
    ctx["trend"] = s.trend(ctx["filters"], ctx["profile"], "school__area_type", s.AREA)
    return render_page(request, "analytics/area.html", ctx)


@login_required
def gender_view(request):
    ctx = _context(request, section="gender")
    ctx["genders"] = s.by_gender(ctx["qs"])
    by_class = s.gender_by_class(ctx["qs"])
    for r in by_class:
        s.shade([r.get("F"), r.get("M")], ctx["overall"]["rate"])
    ctx["by_class"] = by_class
    ctx["chart"] = {"labels": [f"Class {r['standard']}" for r in by_class],
                    "series": [{"label": "Girls", "values": [r.get("F", {}) and r["F"]["rate"] for r in by_class]},
                               {"label": "Boys", "values": [r.get("M", {}) and r["M"]["rate"] for r in by_class]}]}
    ctx["trend"] = s.trend(ctx["filters"], ctx["profile"], "student__gender", s.GENDER)
    ctx["girls_reasons"] = s.top_reasons(ctx["qs"].filter(student__gender="F", standard__gte=8), limit=5)
    ctx["boys_reasons"] = s.top_reasons(ctx["qs"].filter(student__gender="M", standard__gte=8), limit=5)
    gaps = [r for r in by_class if r["gap"] is not None]
    ctx["widest"] = max(gaps, key=lambda r: r["gap"]) if gaps else None
    return render_page(request, "analytics/gender.html", ctx)


@login_required
def caste_view(request):
    ctx = _context(request, section="caste")
    ctx["categories"] = s.by_category(ctx["qs"])
    ctx["chart"] = _bar(ctx["categories"], "label")
    ctx["chart"]["reference"] = ctx["overall"]["rate"]
    ctx["trend"] = s.trend(ctx["filters"], ctx["profile"], "student__category", s.CATEGORY)
    ctx["matrix"] = s.explore(ctx["qs"], "category", "standard")
    for row in ctx["matrix"]["rows"]:
        s.shade(row["cells"], ctx["overall"]["rate"])
    ctx["reasons"] = [{"label": c["label"], "reasons": s.top_reasons(ctx["qs"].filter(student__category=c["student__category"]))}
                      for c in ctx["categories"]]
    return render_page(request, "analytics/caste.html", ctx)


@login_required
def standard_view(request):
    ctx = _context(request, section="standard")
    classes = s.by_standard(ctx["qs"])
    ctx["classes"] = classes
    ctx["stages"] = s.shade(s.by_stage(ctx["qs"]), ctx["overall"]["rate"])
    ctx["transitions"] = s.shade(s.transitions(ctx["qs"]), ctx["overall"]["rate"])
    ctx["chart"] = {"labels": [f"Class {r['standard']}" for r in classes], "values": [r["rate"] for r in classes],
                    "reference": ctx["overall"]["rate"]}
    ctx["trend"] = s.trend(ctx["filters"], ctx["profile"])
    # Age-for-class: students two or more years older than usual for their class
    over = 0
    total = 0
    for e in ctx["qs"].select_related("student", "year").only("standard", "student__date_of_birth", "year__start_year"):
        total += 1
        if e.student.age_on(date(e.year.start_year, 4, 1)) >= e.standard + 7:
            over += 1
    ctx["overage_share"] = round(100 * over / total, 1) if total else 0
    return render_page(request, "analytics/standard.html", ctx)


@login_required
def explore_view(request):
    ctx = _context(request, section="explore")
    form = ExploreForm(request.GET if "rows" in request.GET else None)
    rows_dim, cols_dim = "standard", "gender"
    if form.is_bound and form.is_valid():
        rows_dim, cols_dim = form.cleaned_data["rows"], form.cleaned_data["cols"]
    ctx["explore_form"] = form
    ctx["table"] = s.explore(ctx["qs"], rows_dim, cols_dim)
    for row in ctx["table"]["rows"]:
        s.shade(row["cells"], ctx["overall"]["rate"])
    ctx["rows_label"] = s.EXPLORE_DIMENSIONS[rows_dim][1]
    ctx["cols_label"] = s.EXPLORE_DIMENSIONS[cols_dim][1]
    return render_page(request, "analytics/explore.html", ctx)


@login_required
def hotspots_view(request):
    from interventions.engine import suggestions

    ctx = _context(request, section="hotspots")
    ctx["spots"], _ = suggestions(ctx["qs"], limit=20)
    return render_page(request, "analytics/hotspots.html", ctx)


@login_required
def watchlist_view(request):
    ctx = _context(request, section="watchlist")
    year, rows = s.watchlist(ctx["profile"], ctx["filters"])
    ctx["current_year"] = year
    ctx["total"] = len(rows)
    ctx["rows"] = paginate(request, rows, 30)
    return render_page(request, "analytics/watchlist.html", ctx)


@login_required
def data_quality_view(request):
    ctx = _context(request, section="quality")
    checks = s.data_quality(ctx["profile"])
    for c in checks:
        c["count"] = len(c["rows"])
        c["rows"] = c["rows"][:40]
    ctx["checks"] = checks
    return render_page(request, "analytics/data_quality.html", ctx)


@login_required
def school_detail(request, udise):
    """Mapped with a regular expression in urls.py: the UDISE code must be 11 digits."""
    school = get_object_or_404(School.objects.select_related("block__district"), udise_code=udise)
    profile = get_profile(request)
    if profile and profile.role == "DISTRICT" and school.block.district_id != profile.district_id:
        raise PermissionDenied("This school is outside your district.")
    if profile and profile.role == "SCHOOL" and school.pk != profile.school_id:
        raise PermissionDenied("You can only view your own school.")

    # Remember recently viewed schools in the session (most recent first, at most five)
    recent = [c for c in request.session.get("recent_schools", []) if c[0] != udise]
    request.session["recent_schools"] = [[udise, school.name]] + recent[:4]

    _, filters = get_filters(request)
    year = filters["year"]
    qs = Enrollment.objects.filter(school=school, year=year).exclude(status=Enrollment.TRANSFERRED)
    block_qs = Enrollment.objects.filter(school__block=school.block, year=year).exclude(status=Enrollment.TRANSFERRED)
    years = list(s.completed_years())
    history = [{"year": y.label, **s.summary(Enrollment.objects.filter(school=school, year=y)
                                                  .exclude(status=Enrollment.TRANSFERRED))} for y in years]
    _, watch = s.watchlist(None, {})
    watch = [w for w in watch if w["e"].school_id == school.pk]
    summary, block_summary = s.summary(qs), s.summary(block_qs)
    by_class = s.gender_by_class(qs)
    for r in by_class:
        s.shade([r.get("F"), r.get("M")], block_summary["rate"])
    vs_block = (round(summary["rate"] / block_summary["rate"], 1)
                if summary["rate"] is not None and block_summary["rate"] else None)
    ctx = {
        "school": school, "year": year, "summary": summary, "block_summary": block_summary, "vs_block": vs_block,
        "above_block": vs_block is not None and vs_block >= 1,
        "by_class": by_class, "categories": s.by_category(qs), "reasons": s.top_reasons(qs, limit=6),
        "history": history, "watch": watch[:20], "watch_total": len(watch), "section": "schools",
        "trend": {"years": [h["year"] for h in history],
                  "series": [{"label": school.name.split(", ")[-1], "values": [h["rate"] for h in history]}]},
    }
    return render_page(request, "analytics/school_detail.html", ctx)


EXPORTS = {
    "school": (s.by_school, ["school__udise_code", "school__name", "school__block__name", "school__block__district__name"]),
    "district": (s.by_district, ["school__block__district__name"]),
    "block": (s.by_block, ["school__block__district__name", "school__block__name", "school__area_type"]),
    "gender": (s.by_gender, ["label"]),
    "category": (s.by_category, ["label"]),
    "standard": (s.by_standard, ["standard"]),
    "area": (s.by_area, ["label"]),
}


@login_required
def export_csv(request, dimension):
    """URL uses a regular expression, so only known dimensions reach this view."""
    if dimension not in EXPORTS:
        raise Http404("Unknown export.")
    form, filters = get_filters(request)
    qs = s.enrollments(filters, get_profile(request))
    fn, cols = EXPORTS[dimension]
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="dropout_by_{dimension}_{filters["year"]}.csv"'
    writer = csv.writer(response)
    writer.writerow([f"Dropout by {dimension}", str(filters["year"]), describe(filters)])
    writer.writerow([c.replace("school__", "").replace("block__", "").replace("__", " ") for c in cols]
                    + ["enrolled", "dropped", "dropout_rate_pct"])
    for r in fn(qs):
        writer.writerow([r[c] for c in cols] + [r["enrolled"], r["dropped"],
                                                "suppressed" if r["suppressed"] else r["rate"]])
    return response
