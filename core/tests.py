"""Tests for login, logout, sessions and cookies."""
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from analytics.tests import make_world
from core.models import Profile


class AuthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_world()
        u = User.objects.create_user("officer", password="pass12345!", first_name="Gurdeep")
        Profile.objects.create(user=u, role="STATE")

    def test_landing_is_public(self):
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_wrong_password(self):
        r = self.client.post(reverse("core:login"), {"username": "officer", "password": "nope"})
        self.assertContains(r, "don&#x27;t match")

    def test_login_sets_cookie_and_session_expiry(self):
        r = self.client.post(reverse("core:login"), {"username": "officer", "password": "pass12345!"})
        self.assertRedirects(r, reverse("core:dashboard"))
        self.assertEqual(r.cookies["dw_last_user"].value, "officer")
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_remember_me_keeps_session(self):
        self.client.post(reverse("core:login"), {"username": "officer", "password": "pass12345!", "remember": "on"})
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_next_url_is_honoured_but_not_offsite(self):
        r = self.client.post(reverse("core:login") + "?next=/analysis/gender/",
                             {"username": "officer", "password": "pass12345!", "next": "/analysis/gender/"})
        self.assertRedirects(r, "/analysis/gender/")
        self.client.logout()
        r = self.client.post(reverse("core:login"), {"username": "officer", "password": "pass12345!",
                                                     "next": "https://evil.example.com/"})
        self.assertRedirects(r, reverse("core:dashboard"))

    def test_logout_requires_post(self):
        self.client.login(username="officer", password="pass12345!")
        self.assertEqual(self.client.get(reverse("core:logout")).status_code, 405)
        self.client.post(reverse("core:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_dismiss_notice_cookie(self):
        r = self.client.get(reverse("core:dismiss_notice") + "?next=/about/")
        self.assertEqual(r.cookies["dw_notice_dismissed"].value, "1")

    def test_dashboard_renders(self):
        self.client.login(username="officer", password="pass12345!")
        r = self.client.get(reverse("core:dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["overall"]["dropped"], 14)


class UserManagementTests(TestCase):
    """Creating and managing users (Unit VI): only users with auth permissions may do it."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import Permission
        cls.year, cls.d1, cls.d2, cls.s1, cls.s2 = make_world()
        cls.boss = User.objects.create_user("boss", password="pass12345!")
        cls.boss.user_permissions.set(Permission.objects.filter(codename__in=["view_user", "add_user", "change_user"]))
        Profile.objects.create(user=cls.boss, role="STATE")
        cls.plain = User.objects.create_user("plain", password="pass12345!")
        Profile.objects.create(user=cls.plain, role="STATE")

    def form(self, **kw):
        d = {"username": "deo_ldh", "first_name": "Harjit", "role": "DISTRICT", "district": self.d2.pk,
             "password1": "Punjab#Schools9", "password2": "Punjab#Schools9"}
        d.update(kw)
        return d

    def test_needs_permission(self):
        self.client.login(username="plain", password="pass12345!")
        self.assertEqual(self.client.get(reverse("core:users")).status_code, 403)

    def test_create_district_officer(self):
        self.client.login(username="boss", password="pass12345!")
        r = self.client.post(reverse("core:user_create"), self.form())
        self.assertRedirects(r, reverse("core:users"))
        u = User.objects.get(username="deo_ldh")
        self.assertEqual(u.profile.district, self.d2)
        self.assertEqual(u.groups.get().name, "District officers")
        self.assertTrue(self.client.login(username="deo_ldh", password="Punjab#Schools9"))

    def test_district_required_and_passwords_validated(self):
        self.client.login(username="boss", password="pass12345!")
        r = self.client.post(reverse("core:user_create"), self.form(district="", password1="12345678",
                                                                     password2="12345678"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("district", r.context["form"].errors)
        self.assertIn("password1", r.context["form"].errors)    # entirely numeric, too common

    def test_switch_off_blocks_login(self):
        self.client.login(username="boss", password="pass12345!")
        self.client.post(reverse("core:user_toggle", args=[self.plain.pk]))
        self.plain.refresh_from_db()
        self.assertFalse(self.plain.is_active)
        self.assertFalse(Client().login(username="plain", password="pass12345!"))

    def test_toggle_is_post_only(self):
        self.client.login(username="boss", password="pass12345!")
        self.assertEqual(self.client.get(reverse("core:user_toggle", args=[self.plain.pk])).status_code, 405)

    def test_change_password(self):
        self.client.login(username="plain", password="pass12345!")
        r = self.client.post(reverse("core:password"), {"old_password": "wrong", "new_password1": "Ludhiana#2027x",
                                                        "new_password2": "Ludhiana#2027x"})
        self.assertIn("old_password", r.context["form"].errors)
        r = self.client.post(reverse("core:password"), {"old_password": "pass12345!", "new_password1": "Ludhiana#2027x",
                                                        "new_password2": "Ludhiana#2027x"})
        self.assertRedirects(r, reverse("core:dashboard"))
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)   # still signed in


class FlashAndErrorPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_world()
        u = User.objects.create_user("officer", password="pass12345!")
        Profile.objects.create(user=u, role="STATE")

    def test_flash_message_shows_once_after_redirect(self):
        r = self.client.post(reverse("core:login"), {"username": "officer", "password": "pass12345!"}, follow=True)
        self.assertContains(r, "Signed in as officer")
        self.assertNotContains(self.client.get(reverse("core:dashboard")), "Signed in as officer")

    @override_settings(DEBUG=False)
    def test_custom_404_page(self):
        r = self.client.get("/no-such-page/")
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "<p class=\"code\">404</p>", status_code=404, html=False)
