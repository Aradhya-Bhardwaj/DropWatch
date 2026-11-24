"""
Matches hotspots to schemes, and measures whether a recommendation worked.

Matching: a rule applies to a hotspot when every condition the rule sets agrees with the
hotspot's segment, and (if the rule names a reason) that reason is among the segment's top
three recorded exit reasons. Matches are ranked by rule priority x hotspot score.
"""
from decimal import Decimal

from analytics import services
from students.models import Enrollment

from .models import InterventionRule, Recommendation


def _overlaps(rule, lo, hi):
    return rule.min_standard <= hi and rule.max_standard >= lo


def match_rules(segment, reasons, rules=None):
    rules = rules if rules is not None else list(InterventionRule.objects.filter(active=True).select_related("scheme"))
    reason_codes = {r["code"] for r in reasons}
    lo, hi = services.STAGE_RANGE.get(segment.get("stage"), (1, 12))
    matches = {}
    for rule in rules:
        if rule.gender and rule.gender != segment.get("gender"):
            continue
        if rule.category and rule.category != segment.get("category"):
            continue
        if rule.area_type and rule.area_type != segment.get("area"):
            continue
        if not _overlaps(rule, lo, hi):
            continue
        if rule.reason and rule.reason not in reason_codes:
            continue
        why = []
        if rule.reason:
            why.append(f"top reason: {services.REASON[rule.reason].lower()}")
        if rule.gender or rule.category:
            why.append("targets this group")
        best = matches.get(rule.scheme_id)
        if not best or rule.priority > best["priority"]:
            matches[rule.scheme_id] = {"scheme": rule.scheme, "priority": rule.priority, "why": ", ".join(why)}
    return sorted(matches.values(), key=lambda m: -m["priority"])


def suggestions(qs, limit=12):
    """Hotspots with their top reasons and matching schemes."""
    spots, overall = services.hotspots(qs, limit=limit)
    rules = list(InterventionRule.objects.filter(active=True).select_related("scheme"))
    for h in spots:
        seg_qs = qs.filter(**services.segment_filters(h["segment"]))
        h["reasons"] = services.top_reasons(seg_qs)
        h["schemes"] = match_rules(h["segment"], h["reasons"], rules)[:3]
        h["has_district"] = "district" in h["segment"]
    return spots, overall


def create_recommendations(qs, year, user, limit=12):
    """Turn district-level hotspots into Proposed recommendations. Skips ones that already exist."""
    spots, _ = suggestions(qs, limit=limit * 2)
    created = 0
    for h in spots:
        seg = h["segment"]
        if "district" not in seg or not h["schemes"]:
            continue
        lo, hi = services.STAGE_RANGE.get(seg.get("stage"), (1, 12))
        scheme = h["schemes"][0]["scheme"]
        fields = dict(scheme=scheme, district_id=seg["district"][0], gender=seg.get("gender", ""),
                      category=seg.get("category", ""), min_standard=lo, max_standard=hi,
                      area_type=seg.get("area", ""))
        if Recommendation.objects.filter(**fields).exclude(status=Recommendation.REJECTED).exists():
            continue
        Recommendation.objects.create(
            **fields, baseline_year=year, baseline_rate=Decimal(str(h["rate"])),
            students_in_segment=h["enrolled"], owner=user,
        )
        created += 1
        if created >= limit:
            break
    return created


def impact(rec):
    """
    Segment rate in each completed year, in the target district and in all other districts.
    The change in the other districts is the comparison: if everyone improved, the scheme
    only gets credit for the extra improvement (a simple difference-in-differences).
    """
    years = list(services.completed_years())
    f = rec.segment_filters()
    other = {k: v for k, v in f.items() if k != "school__block__district"}
    rows = []
    for y in years:
        base = Enrollment.objects.filter(year=y).exclude(status=Enrollment.TRANSFERRED)
        target = services.summary(base.filter(**f))
        comparison = services.summary(base.filter(**other).exclude(school__block__district=rec.district))
        rows.append({"year": y, "target": target, "comparison": comparison,
                     "is_baseline": y == rec.baseline_year,
                     "after": rec.started_year and y.start_year >= rec.started_year.start_year})
    result = {"rows": rows, "verdict": None}
    base_row = next((r for r in rows if r["is_baseline"]), None)
    after_rows = [r for r in rows if r["after"]]
    if base_row and after_rows and base_row["target"]["rate"] is not None:
        last = after_rows[-1]
        if last["target"]["rate"] is not None and last["comparison"]["rate"] is not None:
            t_change = round(last["target"]["rate"] - base_row["target"]["rate"], 1)
            c_change = round(last["comparison"]["rate"] - base_row["comparison"]["rate"], 1)
            effect = round(t_change - c_change, 1)
            result["verdict"] = {"target_change": t_change, "comparison_change": c_change, "effect": effect,
                                 "target_text": services.fmt_signed(t_change),
                                 "comparison_text": services.fmt_signed(c_change),
                                 "effect_text": services.fmt_signed(effect),
                                 "year": last["year"],
                                 "students_kept": max(0, round(-effect / 100 * last["target"]["enrolled"]))}
    return result
