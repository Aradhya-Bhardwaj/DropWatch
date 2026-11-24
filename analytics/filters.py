"""
Filter bar handling. Filters arrive by GET (so a filtered page can be bookmarked or shared) and are
remembered in the session (Unit VI), so moving from the gender page to the caste page keeps them.
"""
from .forms import FilterForm

SESSION_KEY = "dw_filters"
FIELDS = list(FilterForm.base_fields)


def get_profile(request):
    return getattr(request.user, "profile", None) if request.user.is_authenticated else None


def get_filters(request):
    profile = get_profile(request)
    if any(k in request.GET for k in FIELDS):
        data = request.GET
    else:
        data = request.session.get(SESSION_KEY)

    form = FilterForm(data or None, profile=profile)
    filters = {}
    if form.is_bound and form.is_valid():
        filters = {k: v for k, v in form.cleaned_data.items() if v}
        request.session[SESSION_KEY] = {k: (v.pk if hasattr(v, "pk") else v) for k, v in filters.items()}
    elif form.is_bound:
        # Invalid combination: keep showing the form with its error, but analyse without the bad filters
        filters = {k: v for k, v in getattr(form, "cleaned_data", {}).items() if v and k != "block"}

    if profile and profile.role in ("DISTRICT", "SCHOOL") and profile.district_id:
        filters["district"] = profile.district
    if "year" not in filters:
        filters["year"] = form.fields["year"].initial
    return form, filters


def describe(filters):
    """Short human description of the active filters, e.g. 'Girls, SC, Firozpur'."""
    from .services import AREA, CATEGORY, GENDER, STAGE_LABEL

    parts = []
    if filters.get("gender"):
        parts.append(GENDER[filters["gender"]])
    if filters.get("category"):
        parts.append(CATEGORY[filters["category"]])
    if filters.get("stage"):
        parts.append(STAGE_LABEL[filters["stage"]])
    if filters.get("area"):
        parts.append(AREA[filters["area"]] + " schools")
    if filters.get("block"):
        parts.append(filters["block"].name)
    elif filters.get("district"):
        parts.append(filters["district"].name)
    return ", ".join(parts) or "All students"
