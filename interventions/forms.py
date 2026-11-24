from django import forms

from .models import Recommendation


class ActionForm(forms.Form):
    status = forms.ChoiceField(choices=Recommendation.STATUS_CHOICES, label="New status")
    note = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), min_length=10,
                           label="What happened",
                           help_text="For example: approved in the district meeting, 120 bicycles ordered.")
    started_year = forms.BooleanField(required=False, label="Implementation starts this school year")

    def __init__(self, *args, recommendation=None, **kwargs):
        self.recommendation = recommendation
        super().__init__(*args, **kwargs)
        if recommendation:
            self.fields["status"].initial = recommendation.status

    def clean_status(self):
        status = self.cleaned_data["status"]
        rec = self.recommendation
        if rec and rec.status == Recommendation.PROPOSED and status in (Recommendation.IN_PROGRESS, Recommendation.DONE):
            raise forms.ValidationError("Approve the recommendation before marking it as being implemented.")
        return status
