from django import forms

from schools.models import Block, District, School
from students.models import CATEGORY_CHOICES, GENDER_CHOICES, AcademicYear

from .services import EXPLORE_DIMENSIONS, STAGES

ANY = [("", "All")]


class FilterForm(forms.Form):
    """The filter bar shared by every analysis page. Submitted with GET so filtered pages can be bookmarked."""

    year = forms.ModelChoiceField(queryset=AcademicYear.objects.filter(is_complete=True), required=False,
                                  empty_label=None, label="School year")
    district = forms.ModelChoiceField(queryset=District.objects.all(), required=False, empty_label="All districts")
    block = forms.ModelChoiceField(queryset=Block.objects.select_related("district"), required=False,
                                   empty_label="All blocks")
    area = forms.ChoiceField(choices=ANY + School.AREA_CHOICES, required=False, label="Rural / urban")
    gender = forms.ChoiceField(choices=ANY + GENDER_CHOICES, required=False)
    category = forms.ChoiceField(choices=ANY + CATEGORY_CHOICES, required=False, label="Social category")
    stage = forms.ChoiceField(choices=ANY + [(c, l) for c, l, *_ in STAGES], required=False, label="Stage")

    def __init__(self, *args, profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["year"].initial = AcademicYear.objects.filter(is_complete=True).last()
        self.fields["block"].label_from_instance = lambda b: f"{b.name} ({b.district.name})"
        # District officers and school staff only ever see their own district
        if profile and profile.role in ("DISTRICT", "SCHOOL") and profile.district_id:
            self.fields["district"].queryset = District.objects.filter(pk=profile.district_id)
            self.fields["district"].empty_label = None
            self.fields["block"].queryset = Block.objects.filter(district=profile.district_id)

    def clean(self):
        data = super().clean()
        district, block = data.get("district"), data.get("block")
        if block and district and block.district_id != district.pk:
            raise forms.ValidationError(f"{block.name} is not in {district.name}. Pick a block in that district.")
        if block and not district:
            data["district"] = block.district
        return data


class ExploreForm(forms.Form):
    CHOICES = [(k, v[1]) for k, v in EXPLORE_DIMENSIONS.items()]
    rows = forms.ChoiceField(choices=CHOICES, initial="standard", label="Rows")
    cols = forms.ChoiceField(choices=CHOICES, initial="gender", label="Columns")

    def clean(self):
        data = super().clean()
        if data.get("rows") and data.get("rows") == data.get("cols"):
            raise forms.ValidationError("Choose two different dimensions to compare.")
        return data
