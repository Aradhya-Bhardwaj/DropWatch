"""
Dropout calculations. Every number in DropWatch comes from these functions.

Dropout rate for a group in a completed school year:

    rate = students in the group who DROPPED that year
           ----------------------------------------------- x 100
           students in the group enrolled that year (transfers excluded)

Transfers are excluded from the denominator because those students continued
school elsewhere; counting them would overstate the rate of the sending school.
"""
from collections import defaultdict
from itertools import combinations
import math

from django.conf import settings
from django.db.models import Count, Max, Q

from schools.models import School
from students.models import (CATEGORY_CHOICES, GENDER_CHOICES, INCOME_CHOICES, AcademicYear, AttendanceRecord,
                             Enrollment, ExitRecord)

CFG = settings.DROPWATCH

STAGES = [
    ("PRI", "Primary (1–5)", 1, 5),
    ("UPR", "Upper primary (6–8)", 6, 8),
    ("SEC", "Secondary (9–10)", 9, 10),
    ("SSC", "Senior secondary (11–12)", 11, 12),
]
STAGE_RANGE = {code: (lo, hi) for code, _, lo, hi in STAGES}
STAGE_LABEL = {code: label for code, label, _, _ in STAGES}

GENDER = dict(GENDER_CHOICES)
CATEGORY = dict(CATEGORY_CHOICES)
INCOME = dict(INCOME_CHOICES)
AREA = dict(School.AREA_CHOICES)
MANAGEMENT = dict(School.MANAGEMENT_CHOICES)
REASON = dict(ExitRecord.REASON_CHOICES)


def stage_of(standard):
    for code, _, lo, hi in STAGES:
        if lo <= standard <= hi:
            return code
    return None


# ---------------------------------------------------------------- years and scope

def completed_years():
    return AcademicYear.objects.filter(is_complete=True).order_by("start_year")


def latest_completed_year():
    return completed_years().last()


def current_year():
    return AcademicYear.objects.filter(is_complete=False).order_by("start_year").last()


def scope(qs, profile, prefix=""):
    """Limit a queryset to what the user may see. `prefix` points from the model to Enrollment's fields."""
    if profile is None:
        return qs
    if profile.role == "SCHOOL" and profile.school_id:
        return qs.filter(**{f"{prefix}school": profile.school_id})
    if profile.role == "DISTRICT" and profile.district_id:
        return qs.filter(**{f"{prefix}school__block__district": profile.district_id})
    return qs


def enrollments(filters, profile, year=None):
    """Completed-year enrolments matching the filter bar, inside the user's jurisdiction, transfers excluded."""
    year = year or filters.get("year") or latest_completed_year()
    qs = Enrollment.objects.filter(year=year).exclude(status=Enrollment.TRANSFERRED)
    qs = scope(qs, profile)
    if filters.get("district"):
        qs = qs.filter(school__block__district=filters["district"])
    if filters.get("block"):
        qs = qs.filter(school__block=filters["block"])
    if filters.get("gender"):
        qs = qs.filter(student__gender=filters["gender"])
    if filters.get("category"):
        qs = qs.filter(student__category=filters["category"])
    if filters.get("area"):
        qs = qs.filter(school__area_type=filters["area"])
    if filters.get("stage"):
        lo, hi = STAGE_RANGE[filters["stage"]]
        qs = qs.filter(standard__gte=lo, standard__lte=hi)
    return qs


# ---------------------------------------------------------------- rates

def fmt_rate(rate):
    """'12.3%', or a dash when the rate is hidden because the group is too small."""
    return "–" if rate is None else f"{rate:.1f}%"


def fmt_signed(value):
    """'+2.1' / '-0.8' for changes between rates."""
    if value is None:
        return "–"
    return f"+{value}" if value > 0 else f"{value}"


def make_rate(enrolled, dropped):
    suppressed = enrolled < CFG["SUPPRESS_BELOW"]
    rate = None if suppressed or not enrolled else round(100.0 * dropped / enrolled, 1)
    return {"enrolled": enrolled, "dropped": dropped, "rate": rate, "suppressed": suppressed,
            "text": fmt_rate(rate)}


def shade(items, reference=None, scale_max=None):
    """
    Add display values to each rate dict so templates only need built-in tags:
      heat  - CSS for a table cell, stronger marigold as the rate climbs above `reference`
      width - bar length in % of `scale_max`
    Empty cells (None) are skipped.
    """
    for item in items:
        if not item:
            continue
        r = item.get("rate")
        item["heat"] = f"--heat:{min(r / (reference * 3), 1):.2f}" if r is not None and reference else ""
        item["width"] = round(min(100.0, 100 * r / scale_max), 1) if r is not None and scale_max else 0
        item["high"] = bool(r is not None and reference and r >= reference)
    return items


def summary(qs):
    agg = qs.aggregate(enrolled=Count("id"), dropped=Count("id", filter=Q(status=Enrollment.DROPPED)))
    return make_rate(agg["enrolled"], agg["dropped"])


def grouped(qs, *fields):
    """Dropout rate per group. Returns a list of dicts with the group fields plus enrolled/dropped/rate."""
    rows = (qs.values(*fields)
              .annotate(enrolled=Count("id"), dropped=Count("id", filter=Q(status=Enrollment.DROPPED)))
              .order_by(*fields))
    out = []
    for r in rows:
        item = {f: r[f] for f in fields}
        item.update(make_rate(r["enrolled"], r["dropped"]))
        out.append(item)
    return out


def sort_by_rate(rows):
    return sorted(rows, key=lambda r: (r["rate"] is None, -(r["rate"] or 0), -r["enrolled"]))


def top_reasons(qs, limit=3):
    rows = (qs.filter(status=Enrollment.DROPPED).values("exit__reason")
              .annotate(n=Count("id")).order_by("-n"))
    total = sum(r["n"] for r in rows)
    out = []
    for r in list(rows)[:limit] if limit else rows:
        code = r["exit__reason"] or "UNKNOWN"
        out.append({"code": code, "label": REASON.get(code, "Not recorded"), "n": r["n"],
                    "share": round(100 * r["n"] / total) if total else 0})
    return out


def trend(filters, profile, field=None, labels=None):
    """Rate for each completed year, overall or split by one field (e.g. student__gender)."""
    years = list(completed_years())
    if field is None:
        return {"years": [y.label for y in years],
                "series": [{"label": "All students",
                            "values": [summary(enrollments(filters, profile, y))["rate"] for y in years]}]}
    series = defaultdict(dict)
    for y in years:
        for row in grouped(enrollments(filters, profile, y), field):
            series[row[field]][y.label] = row["rate"]
    return {"years": [y.label for y in years],
            "series": [{"label": (labels or {}).get(k, k), "key": k,
                        "values": [v.get(y.label) for y in years]} for k, v in sorted(series.items())]}


# ---------------------------------------------------------------- the five dimensions

def by_school(qs):
    rows = grouped(qs, "school__udise_code", "school__name", "school__block__name",
                   "school__block__district__name", "school__school_type", "school__has_girls_toilet")
    block_rates = {(r["school__block__district__name"], r["school__block__name"]): r["rate"]
                   for r in grouped(qs, "school__block__district__name", "school__block__name")}
    for r in rows:
        r["block_rate"] = block_rates.get((r["school__block__district__name"], r["school__block__name"]))
        r["block_text"] = fmt_rate(r["block_rate"])
        r["vs_block"] = (round(r["rate"] / r["block_rate"], 1)
                         if r["rate"] is not None and r["block_rate"] else None)
        r["type_label"] = dict(School.TYPE_CHOICES)[r["school__school_type"]]
    return sort_by_rate(rows)


def by_district(qs):
    return sort_by_rate(grouped(qs, "school__block__district__name", "school__block__district_id"))


def by_block(qs):
    return sort_by_rate(grouped(qs, "school__block__district__name", "school__block__name", "school__area_type"))


def by_area(qs):
    rows = grouped(qs, "school__area_type")
    for r in rows:
        r["label"] = AREA[r["school__area_type"]]
    return rows


def by_gender(qs):
    rows = grouped(qs, "student__gender")
    for r in rows:
        r["label"] = GENDER[r["student__gender"]]
    return rows


def by_category(qs):
    rows = grouped(qs, "student__category")
    for r in rows:
        r["label"] = CATEGORY[r["student__category"]]
    return sort_by_rate(rows)


def by_standard(qs):
    return grouped(qs, "standard")


def by_stage(qs):
    rows = defaultdict(lambda: [0, 0])
    for r in grouped(qs, "standard"):
        s = stage_of(r["standard"])
        rows[s][0] += r["enrolled"]
        rows[s][1] += r["dropped"]
    return [{"code": c, "label": STAGE_LABEL[c], **make_rate(*rows[c])} for c, *_ in STAGES if c in rows]


def matrix(qs, row_field, col_field):
    """Two-way table of rates, e.g. class x gender."""
    data = grouped(qs, row_field, col_field)
    rows = sorted({d[row_field] for d in data})
    cols = sorted({d[col_field] for d in data})
    cell = {(d[row_field], d[col_field]): d for d in data}
    return rows, cols, [[cell.get((r, c)) for c in cols] for r in rows]


def gender_by_class(qs):
    rows, cols, cells = matrix(qs, "standard", "student__gender")
    out = []
    for std, row in zip(rows, cells):
        rec = {"standard": std}
        for g, c in zip(cols, row):
            rec[g] = c
        f, m = rec.get("F"), rec.get("M")
        rec["gap"] = (round(f["rate"] - m["rate"], 1)
                      if f and m and f["rate"] is not None and m["rate"] is not None else None)
        rec["gap_text"] = fmt_signed(rec["gap"])
        out.append(rec)
    return out


def transitions(qs):
    """Dropout in the class that ends a stage: Class 5 (to 6), 8 (to 9), 10 (to 11)."""
    by_std = {r["standard"]: r for r in grouped(qs, "standard")}
    return [{"label": f"Class {a} to {a + 1}", **by_std[a]} for a in (5, 8, 10) if a in by_std]


# ---------------------------------------------------------------- explore: any two dimensions

EXPLORE_DIMENSIONS = {
    "district": ("school__block__district__name", "District", None),
    "area": ("school__area_type", "Rural / urban", AREA),
    "gender": ("student__gender", "Gender", GENDER),
    "category": ("student__category", "Social category", CATEGORY),
    "standard": ("standard", "Class", None),
    "income": ("student__income_band", "Family income", INCOME),
    "management": ("school__management", "School management", MANAGEMENT),
}


def explore(qs, row_dim, col_dim):
    rf, _, rlabels = EXPLORE_DIMENSIONS[row_dim]
    cf, _, clabels = EXPLORE_DIMENSIONS[col_dim]
    rows, cols, cells = matrix(qs, rf, cf)
    fmt = lambda v, labels, dim: (labels or {}).get(v, f"Class {v}" if dim == "standard" else v)
    totals = {r[rf]: r for r in grouped(qs, rf)}
    return {
        "cols": [fmt(c, clabels, col_dim) for c in cols],
        "rows": [{"label": fmt(r, rlabels, row_dim), "cells": row, "total": totals.get(r)}
                 for r, row in zip(rows, cells)],
    }


# ---------------------------------------------------------------- hotspots

HOTSPOT_DIMS = ["district", "gender", "category", "stage", "area"]


def hotspots(qs, limit=20, max_dims=3):
    """
    Rank groups (combinations of up to three dimensions) whose dropout rate is both high and
    meaningful: at least MIN_GROUP_SIZE students and a rate at least HOTSPOT_MULTIPLIER x the
    overall rate. Score = rate x log(dropped + 1), so large groups outrank tiny ones.
    One database query; the combinations are rolled up in Python.
    """
    base = (qs.values("school__block__district_id", "school__block__district__name", "student__gender",
                      "student__category", "standard", "school__area_type")
              .annotate(enrolled=Count("id"), dropped=Count("id", filter=Q(status=Enrollment.DROPPED))))
    cube = []
    tot_e = tot_d = 0
    for r in base:
        cube.append(({
            "district": (r["school__block__district_id"], r["school__block__district__name"]),
            "gender": r["student__gender"], "category": r["student__category"],
            "stage": stage_of(r["standard"]), "area": r["school__area_type"],
        }, r["enrolled"], r["dropped"]))
        tot_e += r["enrolled"]
        tot_d += r["dropped"]
    if not tot_e:
        return [], None
    overall = 100.0 * tot_d / tot_e

    found = []
    for n in range(1, max_dims + 1):
        for dims in combinations(HOTSPOT_DIMS, n):
            agg = defaultdict(lambda: [0, 0])
            for keys, e, d in cube:
                k = tuple(keys[x] for x in dims)
                agg[k][0] += e
                agg[k][1] += d
            for k, (e, d) in agg.items():
                if e < CFG["MIN_GROUP_SIZE"] or d == 0:
                    continue
                rate = 100.0 * d / e
                if rate < CFG["HOTSPOT_MULTIPLIER"] * overall:
                    continue
                seg = dict(zip(dims, k))
                found.append({
                    "segment": seg, "label": segment_label(seg), "enrolled": e, "dropped": d,
                    "rate": round(rate, 1), "times": round(rate / overall, 1),
                    "score": rate * math.log(d + 1),
                })
    found.sort(key=lambda h: -h["score"])
    # Keep the list varied: skip a group that contains, or is contained in, one already listed.
    # "Girls in Classes 9-10" adds nothing once "Girls in Classes 9-10 at rural schools" is shown.
    kept = []
    for h in found:
        mine = set(h["segment"].items())
        nested = any(mine <= set(k["segment"].items()) or set(k["segment"].items()) <= mine for k in kept)
        if not nested:
            kept.append(h)
        if len(kept) >= limit:
            break
    return kept, round(overall, 1)


STAGE_PHRASE = {"PRI": "in Classes 1 to 5", "UPR": "in Classes 6 to 8",
                "SEC": "in Classes 9 and 10", "SSC": "in Classes 11 and 12"}


def segment_label(seg):
    """Plain-language name for a group, e.g. 'SC girls in Classes 9 and 10 at rural schools in Firozpur'."""
    who = {"F": "girls", "M": "boys"}.get(seg.get("gender"), "students")
    if seg.get("category"):
        who = f"{CATEGORY[seg['category']]} {who}" if seg["category"] != "GEN" else f"{who} from the general category"
    parts = [who]
    if seg.get("stage"):
        parts.append(STAGE_PHRASE[seg["stage"]])
    if seg.get("area"):
        parts.append(f"at {AREA[seg['area']].lower()} schools")
    if seg.get("district"):
        parts.append(f"in {seg['district'][1]}")
    text = " ".join(parts)
    return text[0].upper() + text[1:]


def segment_filters(seg):
    f = {}
    if seg.get("district"):
        f["school__block__district"] = seg["district"][0]
    if seg.get("gender"):
        f["student__gender"] = seg["gender"]
    if seg.get("category"):
        f["student__category"] = seg["category"]
    if seg.get("area"):
        f["school__area_type"] = seg["area"]
    if seg.get("stage"):
        lo, hi = STAGE_RANGE[seg["stage"]]
        f["standard__gte"], f["standard__lte"] = lo, hi
    return f


# ---------------------------------------------------------------- watchlist (year in progress)

def watchlist(profile, filters=None):
    """
    Students in the current year whose attendance stayed below WATCH_THRESHOLD for the last
    WATCH_MONTHS recorded months. Catches children while they are still on the roll.
    """
    year = current_year()
    if not year:
        return None, []
    filters = filters or {}
    last_seq = AttendanceRecord.objects.filter(enrollment__year=year).aggregate(m=Max("seq"))["m"] or 0
    first_seq = last_seq - CFG["WATCH_MONTHS"] + 1
    att = AttendanceRecord.objects.filter(enrollment__year=year, seq__gte=first_seq,
                                          enrollment__status=Enrollment.ENROLLED)
    att = scope(att, profile, prefix="enrollment__")
    if filters.get("district"):
        att = att.filter(enrollment__school__block__district=filters["district"])
    if filters.get("block"):
        att = att.filter(enrollment__school__block=filters["block"])
    if filters.get("gender"):
        att = att.filter(enrollment__student__gender=filters["gender"])
    if filters.get("category"):
        att = att.filter(enrollment__student__category=filters["category"])
    flagged = (att.values("enrollment_id")
                  .annotate(low=Count("id", filter=Q(pct__lt=CFG["WATCH_THRESHOLD"])))
                  .filter(low=CFG["WATCH_MONTHS"]).values_list("enrollment_id", flat=True))
    rows = (Enrollment.objects.filter(id__in=list(flagged))
            .select_related("student", "school", "school__block__district")
            .prefetch_related("attendance").order_by("school__name", "standard"))
    out = []
    for e in rows:
        months = list(e.attendance.all())
        out.append({"e": e, "months": months, "latest": months[-1].pct if months else None,
                    "drop": (months[0].pct - months[-1].pct) if months else 0})
    out.sort(key=lambda r: (r["latest"] or 0))
    return year, out


# ---------------------------------------------------------------- data quality

def data_quality(profile):
    """Problems that hide real dropouts. Returns a list of checks, each with the rows that failed it."""
    years = list(AcademicYear.objects.order_by("start_year"))
    checks = []

    # 1. Promoted but never enrolled the next year: silent dropouts
    silent = []
    for y, nxt in zip(years, years[1:]):
        if not y.is_complete:
            continue
        promoted = scope(Enrollment.objects.filter(year=y, status__in=["PROMOTED", "REPEATED"]), profile)
        missing = (promoted.exclude(student__enrollments__year=nxt)
                   .values("school__udise_code", "school__name").annotate(n=Count("id")).order_by("-n"))
        for m in missing:
            if m["n"] >= 3:
                silent.append({"year": y.label, **m})
    checks.append({
        "key": "silent", "title": "Promoted, then never enrolled again",
        "explain": "These students were marked promoted, but no school enrolled them the next year. "
                   "They are probably dropouts the school did not report.",
        "rows": sorted(silent, key=lambda r: -r["n"]),
        "columns": ["School", "Year", "Students missing"],
    })

    # 2. Schools reporting zero dropouts while their numbers fall
    zero = []
    for y, nxt in zip(years, years[1:]):
        if not y.is_complete:
            continue
        cur = {r["school__udise_code"]: r for r in grouped(scope(Enrollment.objects.filter(year=y), profile),
                                                           "school__udise_code", "school__name")}
        later = {r["school__udise_code"]: r for r in grouped(scope(Enrollment.objects.filter(year=nxt), profile),
                                                             "school__udise_code")}
        for code, r in cur.items():
            if r["dropped"] == 0 and code in later and later[code]["enrolled"] < r["enrolled"]:
                zero.append({"year": y.label, "school__udise_code": code, "school__name": r["school__name"],
                             "n": f"{r['enrolled']} to {later[code]['enrolled']}"})
    checks.append({
        "key": "zero", "title": "Zero dropouts reported while enrolment fell",
        "explain": "A school with falling numbers and no reported dropouts usually has missing exit records.",
        "rows": zero, "columns": ["School", "Year", "Enrolment"],
    })

    # 3. Transfers that never arrived
    untraced = []
    for y, nxt in zip(years, years[1:]):
        t = scope(ExitRecord.objects.filter(enrollment__year=y, reason="TRANSFER"), profile, "enrollment__")
        for x in t.exclude(enrollment__student__enrollments__year=nxt).select_related(
                "enrollment__student", "enrollment__school", "to_school"):
            untraced.append({"year": y.label, "student": x.enrollment.student, "from": x.enrollment.school,
                             "to": x.to_school})
    checks.append({
        "key": "untraced", "title": "Transfers that never reached the new school",
        "explain": "Counted as transfers, so they are left out of dropout rates. Until the receiving school "
                   "confirms them, treat them as untraced.",
        "rows": untraced, "columns": ["Student", "Year", "From", "To"],
    })

    # 4. Dropouts with no reason recorded
    unknown = (scope(ExitRecord.objects.filter(reason="UNKNOWN"), profile, "enrollment__")
               .values("enrollment__school__udise_code", "enrollment__school__name", "enrollment__year__label")
               .annotate(n=Count("id")).order_by("-n"))
    checks.append({
        "key": "unknown", "title": "Dropouts with no reason recorded",
        "explain": "Without a reason, the intervention engine cannot match a scheme to the group.",
        "rows": list(unknown), "columns": ["School", "Year", "Dropouts"],
    })
    return checks
