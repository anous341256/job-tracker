from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from companies.models import Company, JobPosition

from .models import Application, ApplicationStatusLog, Interview


class ApplicationWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='alice', password='test-pass')
        self.company = Company.objects.create(user=self.user, name='Example')
        self.job = JobPosition.objects.create(company=self.company, title='Python Developer')
        self.application = Application.objects.create(
            user=self.user,
            job_position=self.job,
            status=Application.Status.APPLIED,
        )

    def test_job_with_application_is_protected_from_deletion(self):
        with self.assertRaises(ProtectedError):
            self.job.delete()

    def test_application_owns_status_history_and_interviews(self):
        ApplicationStatusLog.objects.create(
            application=self.application,
            from_status=Application.Status.PREPARING,
            to_status=Application.Status.APPLIED,
            changed_by=self.user,
        )
        Interview.objects.create(
            application=self.application,
            round_number=1,
            title='技术一面',
            scheduled_at=timezone.now(),
        )

        self.assertEqual(self.application.status_logs.count(), 1)
        self.assertEqual(self.application.interviews.count(), 1)

    def test_status_endpoint_writes_history(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('applications:status', args=[self.application.pk]), {'status': Application.Status.INTERVIEWING})
        self.application.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.application.status, Application.Status.INTERVIEWING)
        self.assertTrue(self.application.status_logs.filter(from_status=Application.Status.APPLIED, to_status=Application.Status.INTERVIEWING).exists())
