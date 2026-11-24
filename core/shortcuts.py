"""
Small helpers shared by every app, built only from syllabus topics:
sessions and cookies (Unit VI), request.GET (Unit II) and render (Unit III).
"""
from math import ceil

from django.shortcuts import render

FLASH_KEY = "dw_flash"


def flash(request, text, level="success"):
    """
    Store a one-time message in the session. It is shown on the next page rendered with
    render_page and then removed, so it survives the redirect after a POST (Post/Redirect/Get).
    level: success, info or error.
    """
    messages = request.session.get(FLASH_KEY, [])
    messages.append({"text": text, "level": level})
    request.session[FLASH_KEY] = messages


def render_page(request, template, context=None, status=200):
    """render() plus the values every page needs: pending flash messages, the user's
    profile, and whether the demo-data notice was dismissed (read from a cookie)."""
    context = dict(context or {})
    context["flash"] = request.session.pop(FLASH_KEY, [])
    context["user_profile"] = getattr(request.user, "profile", None) if request.user.is_authenticated else None
    context["show_demo_notice"] = request.COOKIES.get("dw_notice_dismissed") != "1"
    return render(request, template, context, status=status)


def safe_next(url, default):
    """Only follow ?next= links that stay on this site (a path like /analysis/gender/)."""
    if url and url.startswith("/") and not url.startswith("//"):
        return url
    return default


def paginate(request, items, per_page):
    """
    Split a list or queryset into pages using the ?page= number from the URL.
    Returns a dict the shared pager template understands; `query` keeps the other
    GET parameters (search, filters) so page links don't lose them.
    """
    total = items.count() if hasattr(items, "count") and not isinstance(items, list) else len(items)
    num_pages = max(1, ceil(total / per_page))
    try:
        number = int(request.GET.get("page", 1))
    except ValueError:
        number = 1
    number = min(max(number, 1), num_pages)
    start = (number - 1) * per_page
    query = request.GET.copy()
    query.pop("page", None)
    return {
        "items": items[start:start + per_page], "number": number, "num_pages": num_pages,
        "has_previous": number > 1, "has_next": number < num_pages,
        "previous": number - 1, "next": number + 1, "start_index": start + 1,
        "total": total, "query": query.urlencode(),
    }
