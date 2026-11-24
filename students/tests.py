"""Tests for student forms, CSRF-protected POST + redirect, exit records and CSV upload."""
from datetime import date

from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from analytics.tests import make_world
from core.models import Profile

from .forms import ExitForm, StudentForm
from .models import Enrollment, ExitRecord, Student


class StudentFormValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.year, cls.d1, cls.d2, cls.s1, cls.s2 = make_world()

    def data(self, **kw):
        d = {"student_uid": "PB9000000001", "name": "simran  kaur", "gender": "F", "category": "SC",
             "date_of_birth": "2013-05-01", "income_band": "BPL", "distance_km": "3", "standard": 7}
        d.update(kw)
        return d

    def test_valid_and_name_is_cleaned(self):
        f = StudentForm(self.data(), school=self.s1)
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual(f.cleaned_data["name"], "Simran Kaur")

    def test_bad_uid(self):
        self.assertIn("student_uid", StudentForm(self.data(student_uid="XX12"), school=self.s1).errors)

    def test_class_above_school_range(self):
        self.assertIn("standard", StudentForm(self.data(standard=12), school=self.s1).errors)

    def test_age_too_young_for_class(self):
        f = StudentForm(self.data(date_of_birth="2020-01-01", standard=7), school=self.s1)
        self.assertFalse(f.is_valid())


class StaffWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.year, cls.d1, cls.d2, cls.s1, cls.s2 = make_world()
        cls.current = cls.year.__class__.objects.get(start_year=2026)
        cls.staff = User.objects.create_user("head", password="pass12345!")
        cls.staff.user_permissions.set(Permission.objects.filter(codename__in=[
            "add_student", "add_exitrecord", "view_student"]))
        Profile.objects.create(user=cls.staff, role="SCHOOL", district=cls.d1, school=cls.s1)

    def setUp(self):
        self.client.login(username="head", password="pass12345!")

    def test_add_student_post_redirects(self):
        r = self.client.post(reverse("students:add"), {
            "student_uid": "PB9000000009", "name": "Arjun Singh", "gender": "M", "category": "GEN",
            "date_of_birth": "2012-02-02", "income_band": "LOW", "distance_km": "2", "standard": 8})
        self.assertEqual(r.status_code, 302)          # Post/Redirect/Get
        self.assertTrue(Enrollment.objects.filter(student__student_uid="PB9000000009", year=self.current).exists())

    def test_csrf_is_enforced(self):
        c = Client(enforce_csrf_checks=True)
        c.login(username="head", password="pass12345!")
        self.assertEqual(c.post(reverse("students:add"), {}).status_code, 403)

    def test_transfer_needs_a_school(self):
        st = Student.objects.create(student_uid="PB9000000100", name="T One", gender="F", category="GEN",
                                    date_of_birth=date(2012, 1, 1), school=self.s1)
        e = Enrollment.objects.create(student=st, school=self.s1, year=self.current, standard=8)
        f = ExitForm({"left_as": "TRANSFERRED", "exit_date": "2026-07-01"}, enrollment=e)
        self.assertIn("to_school", f.errors)

    def test_record_dropout(self):
        st = Student.objects.create(student_uid="PB9000000101", name="D One", gender="F", category="GEN",
                                    date_of_birth=date(2011, 1, 1), school=self.s1)
        e = Enrollment.objects.create(student=st, school=self.s1, year=self.current, standard=9)
        r = self.client.post(reverse("students:exit", args=[e.pk]),
                             {"left_as": "DROPPED", "reason": "MARRIAGE", "exit_date": "2026-08-10"})
        self.assertRedirects(r, reverse("students:list"))
        e.refresh_from_db()
        self.assertEqual(e.status, "DROPPED")
        self.assertEqual(ExitRecord.objects.get(enrollment=e).recorded_by, self.staff)

    def test_csv_upload_all_or_nothing(self):
        bad = ("student_uid,name,gender,category,date_of_birth,standard,income_band,distance_km,is_cwsn\n"
               "PB9000000201,Good Row,F,SC,2013-01-01,6,BPL,2,no\n"
               "PB9000000202,Bad Row,X,SC,2013-01-01,6,BPL,2,no\n")
        r = self.client.post(reverse("students:upload"), {"school": self.s1.pk,
                             "file": SimpleUploadedFile("roll.csv", bad.encode())})
        self.assertRedirects(r, reverse("students:upload"))
        self.assertFalse(Student.objects.filter(student_uid="PB9000000201").exists())
        good = bad.replace(",X,", ",M,")
        r = self.client.post(reverse("students:upload"), {"school": self.s1.pk,
                             "file": SimpleUploadedFile("roll.csv", good.encode())})
        self.assertEqual(Student.objects.filter(student_uid__in=["PB9000000201", "PB9000000202"]).count(), 2)

    def test_upload_rejects_non_csv(self):
        r = self.client.post(reverse("students:upload"), {"school": self.s1.pk,
                             "file": SimpleUploadedFile("roll.xlsx", b"x")})
        self.assertContains(r, "Upload a .csv file")
