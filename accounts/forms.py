from django import forms

from .models import Profile


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ('display_name', 'location', 'timezone', 'target_role', 'default_currency', 'email_reminders')
