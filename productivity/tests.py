import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Resume
from .forms import CommunicationForm, ContactForm


class ResumeUploadTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_dir.name)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self.media_dir.cleanup()

    def test_upload_redirects_to_resume_list_not_dashboard(self):
        user = get_user_model().objects.create_user('alice', password='pass')
        self.client.force_login(user)
        file = SimpleUploadedFile('resume.pdf', b'%PDF-1.4 test', content_type='application/pdf')

        response = self.client.post(reverse('productivity:resume-create'), {
            'name': 'Backend Resume',
            'language': 'zh-hans',
            'file': file,
        })

        self.assertRedirects(response, reverse('productivity:resumes'))
        resume = Resume.objects.get(user=user, name='Backend Resume')
        self.assertEqual(self.client.get(reverse('productivity:resume-detail', args=[resume.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('productivity:resume-edit', args=[resume.pk])).status_code, 200)

    def test_other_user_cannot_view_or_edit_resume(self):
        owner = get_user_model().objects.create_user('owner', password='pass')
        visitor = get_user_model().objects.create_user('visitor', password='pass')
        file = SimpleUploadedFile('private.pdf', b'%PDF-1.4 private', content_type='application/pdf')
        resume = Resume.objects.create(user=owner, name='Private', file=file)
        self.client.force_login(visitor)

        self.assertEqual(self.client.get(reverse('productivity:resume-detail', args=[resume.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('productivity:resume-edit', args=[resume.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('productivity:resume-download', args=[resume.pk])).status_code, 404)


class ProductivityDateWidgetTests(TestCase):
    def test_contact_last_contact_uses_date_picker(self):
        form = ContactForm()
        self.assertEqual(form.fields['last_contact_at'].widget.input_type, 'date')

    def test_communication_time_uses_datetime_picker(self):
        form = CommunicationForm()
        self.assertEqual(form.fields['occurred_at'].widget.input_type, 'datetime-local')
