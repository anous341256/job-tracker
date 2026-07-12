from django import forms

from core.form_widgets import apply_date_picker_widgets

from .models import Profile


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ('display_name', 'location', 'timezone', 'target_role', 'default_currency', 'email_reminders')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_date_picker_widgets(self.fields)
