from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from schools.models import District, School

from .models import Profile


class LoginForm(forms.Form):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"autofocus": True,
                                                                             "autocomplete": "username"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    remember = forms.BooleanField(required=False, label="Keep me signed in on this device for 2 weeks")

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        if data.get("username") and data.get("password"):
            self.user = authenticate(self.request, username=data["username"], password=data["password"])
            if self.user is None:
                raise forms.ValidationError("That username and password don't match. Check both and try again.")
            if not self.user.is_active:
                raise forms.ValidationError("This account is switched off. Ask your state administrator.")
        return data


class UserCreateForm(forms.Form):
    """Create an officer or school account with a role. The role decides the group (permissions)
    and the jurisdiction (which district or school the user can see)."""

    username = forms.CharField(max_length=150, help_text="Letters, digits and _ only, e.g. deo_bathinda")
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    role = forms.ChoiceField(choices=Profile.ROLE_CHOICES)
    district = forms.ModelChoiceField(queryset=District.objects.all(), required=False,
                                      help_text="Needed for district officers and school staff")
    school = forms.ModelChoiceField(queryset=School.objects.select_related("block__district"), required=False,
                                    help_text="Needed for school staff")
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput,
                                help_text="At least 8 characters, not only numbers, not a common password.")
    password2 = forms.CharField(label="Repeat password", widget=forms.PasswordInput)

    def clean_username(self):
        name = self.cleaned_data["username"].strip()
        if not name.replace("_", "").isalnum():
            raise forms.ValidationError("Use only letters, digits and _.")
        if User.objects.filter(username__iexact=name).exists():
            raise forms.ValidationError("That username is taken.")
        return name

    def clean(self):
        data = super().clean()
        role, district, school = data.get("role"), data.get("district"), data.get("school")
        if role in (Profile.DISTRICT, Profile.SCHOOL) and not district:
            self.add_error("district", "Choose the district this person works in.")
        if role == Profile.SCHOOL:
            if not school:
                self.add_error("school", "Choose the school this person works in.")
            elif district and school.block.district_id != district.pk:
                self.add_error("school", f"{school.name} is not in {district.name}.")
        if role == Profile.STATE:
            data["district"], data["school"] = None, None
        if role == Profile.DISTRICT:
            data["school"] = None
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords don't match.")
        elif p1:
            try:
                validate_password(p1, User(username=data.get("username", ""), first_name=data.get("first_name", "")))
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return data


class PasswordChangeForm(forms.Form):
    old_password = forms.CharField(label="Current password", widget=forms.PasswordInput)
    new_password1 = forms.CharField(label="New password", widget=forms.PasswordInput)
    new_password2 = forms.CharField(label="Repeat new password", widget=forms.PasswordInput)

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_old_password(self):
        if not self.user.check_password(self.cleaned_data["old_password"]):
            raise forms.ValidationError("That isn't your current password.")
        return self.cleaned_data["old_password"]

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("new_password1"), data.get("new_password2")
        if p1 and p2 and p1 != p2:
            self.add_error("new_password2", "The two passwords don't match.")
        elif p1:
            try:
                validate_password(p1, self.user)
            except forms.ValidationError as e:
                self.add_error("new_password1", e)
        return data
