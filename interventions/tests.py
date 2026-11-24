"""Tests for rule matching, generating recommendations and the action form."""
from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from analytics import services
from analytics.tests import make_world
from core.models import Profile

from . import engine
from .models import InterventionRule, Recommendation, Scheme


class EngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.year, cls.d1, cls.d2, cls.s1, cls.s2 = make_world()
        cls.bikes = Scheme.objects.create(name="Bicycles", slug="bikes", level="STATE", description="x")
        cls.sc = Scheme.objects.create(name="SC scholarship", slug="sc", level="CENTRAL", description="x")
        InterventionRule.objects.create(scheme=cls.bikes, gender="F", reason="DISTANCE", priority=9)
        InterventionRule.objects.create(scheme=cls.sc, category="SC", reason="FINANCIAL", priority=9)
        cls.officer = User.objects.create_user("o", password="pass12345!")
        cls.officer.user_permissions.set(Permission.objects.filter(
            codename__in=["add_recommendation", "change_recommendation", "view_recommendation"]))
        Profile.objects.create(user=cls.officer, role="STATE")

    def test_rule_needs_matching_reason(self):
        seg = {"gender": "F", "category": "SC"}
        names = [m["scheme"].name for m in engine.match_rules(seg, [{"code": "DISTANCE"}])]
        self.assertEqual(names, ["Bicycles"])          # SC rule needs FINANCIAL, which isn't a top reason

    def test_rule_needs_matching_gender(self):
        self.assertEqual(engine.match_rules({"gender": "M"}, [{"code": "DISTANCE"}]), [])

    def test_generate_creates_once(self):
        qs = services.enrollments({"year": self.year}, None)
        first = engine.create_recommendations(qs, self.year, self.officer)
        self.assertGreaterEqual(first, 1)
        self.assertEqual(engine.create_recommendations(qs, self.year, self.officer), 0)
        rec = Recommendation.objects.filter(district=self.d1, gender="F").first()
        self.assertEqual(rec.scheme, self.bikes)

    def test_cannot_jump_from_proposed_to_done(self):
        rec = Recommendation.objects.create(scheme=self.bikes, district=self.d1, baseline_year=self.year,
                                            baseline_rate=Decimal("25"), gender="F")
        self.client.login(username="o", password="pass12345!")
        r = self.client.post(reverse("interventions:detail", args=[rec.pk]),
                             {"status": "DONE", "note": "All bicycles handed out."})
        self.assertContains(r, "Approve the recommendation before")
        r = self.client.post(reverse("interventions:detail", args=[rec.pk]),
                             {"status": "APPROVED", "note": "Approved in the district meeting."})
        self.assertRedirects(r, reverse("interventions:detail", args=[rec.pk]))
        rec.refresh_from_db()
        self.assertEqual(rec.status, "APPROVED")
        self.assertEqual(rec.actions.count(), 1)
