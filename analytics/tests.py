"""Tests for the dropout calculations, URL patterns and jurisdiction rules."""
from datetime import date

from django.contrib.auth.models import Group, Permission, User
from django.test import Client, TestCase
from django.urls import resolve, reverse

from core.models import Profile
from schools.models import Block, District, School
from students.models import AcademicYear, Enrollment, ExitRecord, Student

from . import services


def make_world():
    """Two districts, one school each, a completed year with known numbers."""
    y = AcademicYear.objects.create(label="2025-26", start_year=2025, is_complete=True)
    AcademicYear.objects.create(label="2026-27", start_year=2026, is_complete=False)
    d1 = District.objects.create(name="Firozpur", code="FZR")
    d2 = District.objects.create(name="Ludhiana", code="LDH")
    s1 = School.objects.create(udise_code="03030100001", name="Govt High School, Zira",
                               block=Block.objects.create(name="Zira", district=d1), school_type="SEC")
    s2 = School.objects.create(udise_code="03080100001", name="Govt High School, Khanna",
                               block=Block.objects.create(name="Khanna", district=d2), school_type="SEC")
    n = 0

    def add(school, gender, status, count, standard=9):
        nonlocal n
        for _ in range(count):
            n += 1
            st = Student.objects.create(student_uid=f"PB{n:010d}", name=f"Student {n}", gender=gender,
                                        category="SC", date_of_birth=date(2011, 1, 1), school=school)
            e = Enrollment.objects.create(student=st, school=school, year=y, standard=standard, status=status)
            if status == "DROPPED":
                ExitRecord.objects.create(enrollment=e, exit_date=date(2025, 9, 1), reason="DISTANCE")

    # Firozpur: 40 girls, 10 dropped (25%); 40 boys, 2 dropped (5%); 5 transfers (excluded)
    add(s1, "F", "DROPPED", 10); add(s1, "F", "PROMOTED", 30)
    add(s1, "M", "DROPPED", 2); add(s1, "M", "PROMOTED", 38)
    add(s1, "M", "TRANSFERRED", 5)
    # Ludhiana: 40 girls, 2 dropped (5%)
    add(s2, "F", "DROPPED", 2); add(s2, "F", "PROMOTED", 38)
    return y, d1, d2, s1, s2


class RateCalculationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.year, cls.d1, cls.d2, cls.s1, cls.s2 = make_world()

    def test_overall_rate_excludes_transfers(self):
        result = services.summary(services.enrollments({"year": self.year}, None))
        self.assertEqual(result["enrolled"], 120)       # 125 rows minus 5 transfers
        self.assertEqual(result["dropped"], 14)
        self.assertEqual(result["rate"], 11.7)

    def test_gender_breakdown(self):
        qs = services.enrollments({"year": self.year, "district": self.d1}, None)
        rates = {r["student__gender"]: r["rate"] for r in services.by_gender(qs)}
        self.assertEqual(rates, {"F": 25.0, "M": 5.0})

    def test_small_groups_are_suppressed(self):
        qs = services.enrollments({"year": self.year}, None).filter(status="DROPPED", student__gender="M")
        self.assertTrue(services.summary(qs)["suppressed"])
        self.assertIsNone(services.summary(qs)["rate"])

    def test_hotspot_finds_firozpur_girls(self):
        spots, overall = services.hotspots(services.enrollments({"year": self.year}, None))
        self.assertEqual(overall, 11.7)
        top = spots[0]
        self.assertEqual(top["segment"]["gender"], "F")
        self.assertEqual(top["segment"]["district"][1], "Firozpur")
        self.assertEqual(top["rate"], 25.0)

    def test_top_reason(self):
        qs = services.enrollments({"year": self.year}, None)
        self.assertEqual(services.top_reasons(qs)[0]["code"], "DISTANCE")

    def test_segment_label_reads_naturally(self):
        label = services.segment_label({"gender": "F", "category": "SC", "stage": "SEC",
                                        "district": (1, "Firozpur")})
        self.assertEqual(label, "SC girls in Classes 9 and 10 in Firozpur")


class UrlTests(TestCase):
    def test_school_regex_accepts_11_digits(self):
        self.assertEqual(resolve("/analysis/schools/03030100001/").url_name, "school_detail")

    def test_school_regex_rejects_other_codes(self):
        self.assertEqual(self.client.get("/analysis/schools/123/").status_code, 404)

    def test_export_regex_only_known_dimensions(self):
        self.assertEqual(resolve("/analysis/export/gender.csv").kwargs, {"dimension": "gender"})
        self.assertEqual(self.client.get("/analysis/export/password.csv").status_code, 404)

    def test_reverse(self):
        self.assertEqual(reverse("analytics:school_detail", args=["03030100001"]), "/analysis/schools/03030100001/")


class ViewAndPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.year, cls.d1, cls.d2, cls.s1, cls.s2 = make_world()
        group = Group.objects.create(name="District officers")
        group.permissions.set(Permission.objects.filter(codename__startswith="view_"))
        cls.deo = User.objects.create_user("deo", password="pass12345!")
        cls.deo.groups.add(group)
        Profile.objects.create(user=cls.deo, role="DISTRICT", district=cls.d1)
        cls.state = User.objects.create_user("state", password="pass12345!")
        Profile.objects.create(user=cls.state, role="STATE")

    def test_login_required(self):
        r = self.client.get(reverse("analytics:gender"))
        self.assertRedirects(r, f"{reverse('core:login')}?next={reverse('analytics:gender')}")

    def test_all_analysis_pages_render(self):
        self.client.login(username="state", password="pass12345!")
        for name in ["schools", "area", "gender", "caste", "standard", "explore", "hotspots", "watchlist", "quality"]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f"analytics:{name}")).status_code, 200)

    def test_district_officer_cannot_open_other_district_school(self):
        self.client.login(username="deo", password="pass12345!")
        self.assertEqual(self.client.get(self.s1.get_absolute_url()).status_code, 200)
        self.assertEqual(self.client.get(self.s2.get_absolute_url()).status_code, 403)

    def test_district_officer_only_sees_own_district(self):
        self.client.login(username="deo", password="pass12345!")
        r = self.client.get(reverse("analytics:area"))
        names = [d["school__block__district__name"] for d in r.context["districts"]]
        self.assertEqual(names, ["Firozpur"])

    def test_filters_are_remembered_in_session(self):
        self.client.login(username="state", password="pass12345!")
        self.client.get(reverse("analytics:gender"), {"district": self.d2.pk, "year": self.year.pk})
        self.assertEqual(self.client.session["dw_filters"]["district"], self.d2.pk)
        r = self.client.get(reverse("analytics:caste"))      # no GET filters: comes from the session
        self.assertEqual(r.context["filters"]["district"], self.d2)

    def test_block_outside_district_is_a_validation_error(self):
        self.client.login(username="state", password="pass12345!")
        zira = Block.objects.get(name="Zira")
        r = self.client.get(reverse("analytics:gender"), {"district": self.d2.pk, "block": zira.pk})
        self.assertIn("is not in Ludhiana", str(r.context["filter_form"].non_field_errors()))

    def test_csv_export(self):
        self.client.login(username="state", password="pass12345!")
        r = self.client.get(reverse("analytics:export", args=["gender"]))
        self.assertEqual(r["Content-Type"], "text/csv")
        self.assertIn("Girls", r.content.decode())
