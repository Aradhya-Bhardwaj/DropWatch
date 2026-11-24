import csv
import logging

from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse

from analytics.filters import get_profile
from analytics.services import current_year, scope
from core.shortcuts import flash, paginate, render_page
from schools.models import School

from .forms import ExitForm, StudentForm, StudentRowForm, UploadForm
from .models import Enrollment, ExitRecord, Student

log = logging.getLogger("dropwatch")


def visible_schools(profile):
    qs = School.objects.select_related("block__district")
    if profile and profile.role == "SCHOOL":
        return qs.filter(pk=profile.school_id)
    if profile and profile.role == "DISTRICT":
        return qs.filter(block__district=profile.district_id)
    return qs


def pick_school(request):
    """The school being worked on: staff get their own; officers choose with ?school=<UDISE>, kept in the session."""
    profile = get_profile(request)
    schools = visible_schools(profile)
    if profile and profile.role == "SCHOOL":
        return schools.first(), schools
    code = request.GET.get("school") or request.session.get("dw_school")
    school = schools.filter(udise_code=code).first() if code else None
    if school:
        request.session["dw_school"] = school.udise_code
    return school, schools


@login_required
def student_list(request):
    school, schools = pick_school(request)
    year = current_year()
    ctx = {"school": school, "schools": schools, "year": year, "section": "students"}
    if school and year:
        qs = (Enrollment.objects.filter(school=school, year=year).select_related("student")
              .prefetch_related("attendance").order_by("standard", "student__name"))
        q = request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(student__name__icontains=q) | Q(student__student_uid__icontains=q))
        std = request.GET.get("standard")
        if std and std.isdigit():
            qs = qs.filter(standard=int(std))
        status = request.GET.get("status")
        if status in dict(Enrollment.STATUS_CHOICES):
            qs = qs.filter(status=status)
        ctx.update(q=q, std=std, status=status, classes=range(1, school.highest_class + 1),
                   page=paginate(request, qs, 40),
                   counts={"total": Enrollment.objects.filter(school=school, year=year).count(),
                           "left": Enrollment.objects.filter(school=school, year=year)
                                   .exclude(status=Enrollment.ENROLLED).count()})
    return render_page(request, "students/list.html", ctx)


@login_required
@permission_required("students.add_student", raise_exception=True)
def student_add(request):
    school, _ = pick_school(request)
    if not school:
        flash(request, "Choose a school first.", "info")
        return redirect("students:list")
    year = current_year()
    if request.method == "POST":
        form = StudentForm(request.POST, school=school)
        if form.is_valid():
            student = form.save(commit=False)
            student.school = school
            student.save()
            Enrollment.objects.create(student=student, school=school, year=year,
                                      standard=form.cleaned_data["standard"])
            log.info("Student %s added to %s by %s", student.student_uid, school.udise_code, request.user)
            flash(request, f"Added {student.name} to Class {form.cleaned_data['standard']}.")
            # Post/Redirect/Get: a refresh after saving won't submit the form twice
            if "add_another" in request.POST:
                return redirect("students:add")
            return redirect(f"{reverse('students:list')}?standard={form.cleaned_data['standard']}")
    else:
        form = StudentForm(school=school)
    return render_page(request, "students/form.html", {"form": form, "school": school, "year": year,
                                                  "section": "students"})


def _enrollment_for(request, pk):
    e = get_object_or_404(Enrollment.objects.select_related("student", "school__block__district", "year"), pk=pk)
    profile = get_profile(request)
    if not scope(Enrollment.objects.filter(pk=pk), profile).exists():
        raise PermissionDenied("This student is outside your school or district.")
    return e


@login_required
@permission_required("students.add_exitrecord", raise_exception=True)
def record_exit(request, pk):
    e = _enrollment_for(request, pk)
    if e.status != Enrollment.ENROLLED:
        flash(request, f"{e.student.name} is already marked as {e.get_status_display().lower()}.", "error")
        return redirect("students:list")
    if request.method == "POST":
        form = ExitForm(request.POST, enrollment=e)
        if form.is_valid():
            record = form.save(commit=False)
            record.enrollment = e
            record.reason = form.cleaned_data["reason"]
            record.recorded_by = request.user
            record.save()
            e.status = form.cleaned_data["left_as"]
            e.save(update_fields=["status"])
            if e.status == Enrollment.TRANSFERRED:
                flash(request, f"{e.student.name} recorded as moved to {record.to_school.name}. "
                                          "It won't count as a dropout once that school enrols them.")
            else:
                flash(request, f"{e.student.name} recorded as dropped out: {record.get_reason_display().lower()}.")
            return redirect("students:list")
    else:
        form = ExitForm(enrollment=e, initial={"left_as": Enrollment.DROPPED})
    months = list(e.attendance.all())
    return render_page(request, "students/exit_form.html", {"form": form, "e": e, "months": months,
                                                       "section": "students"})


@login_required
@permission_required("students.add_student", raise_exception=True)
def upload(request):
    profile = get_profile(request)
    schools = visible_schools(profile)
    year = current_year()
    result = request.session.pop("upload_result", None)
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES, schools=schools)
        if form.is_valid():
            school = form.cleaned_data["school"]
            rows = form.cleaned_data["file"]
            errors, good = [], []
            seen = set()
            for i, row in enumerate(rows, start=2):  # row 1 is the header
                rf = StudentRowForm(row, school)
                if not rf.is_valid():
                    for field, errs in rf.errors.items():
                        errors.append({"row": i, "field": "row" if field == "__all__" else field, "error": errs[0]})
                    continue
                uid = rf.cleaned_data["student_uid"]
                if uid in seen:
                    errors.append({"row": i, "field": "student_uid", "error": f"{uid} appears twice in the file."})
                    continue
                seen.add(uid)
                good.append(rf)
            if not errors:
                for rf in good:
                    st = rf.save(commit=False)
                    st.school = school
                    st.save()
                    Enrollment.objects.create(student=st, school=school, year=year,
                                              standard=rf.cleaned_data["standard"])
                flash(request, f"Imported {len(good)} students into {school.name}.")
                return redirect("students:list")
            # Nothing is saved when any row fails, so the file can be fixed and uploaded again
            request.session["upload_result"] = {"errors": errors[:200], "error_count": len(errors),
                                                "ok_count": len(good), "school": school.name}
            return redirect("students:upload")
    else:
        form = UploadForm(schools=schools, initial={"school": request.session.get("dw_school") and
                                                    schools.filter(udise_code=request.session["dw_school"]).first()})
    return render_page(request, "students/upload.html", {"form": form, "result": result, "year": year,
                                                    "section": "upload", "columns": UploadForm.COLUMNS})


@login_required
def sample_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="dropwatch_student_template.csv"'
    w = csv.writer(response)
    w.writerow(UploadForm.COLUMNS)
    w.writerow(["PB9000000001", "Simran Kaur", "F", "SC", "2014-06-12", "6", "BPL", "3.5", "no"])
    w.writerow(["PB9000000002", "Arjun Singh", "M", "GEN", "2012-01-30", "8", "LOW", "1.2", "no"])
    return response
