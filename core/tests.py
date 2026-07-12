from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from applications.models import Application
from companies.models import Company, JobPosition


class DashboardTests(TestCase):
    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_only_counts_current_user(self):
        user = get_user_model().objects.create_user('alice', password='pass')
        other = get_user_model().objects.create_user('bob', password='pass')
        company = Company.objects.create(user=other, name='Other')
        job = JobPosition.objects.create(company=company, title='Developer')
        Application.objects.create(user=other, job_position=job)
        self.client.force_login(user)
        response = self.client.get(reverse('core:dashboard'))
        self.assertContains(response, '<div class="display-6">0</div>', html=True)

    def test_dashboard_monthly_chart_does_not_require_mysql_timezone_tables(self):
        user = get_user_model().objects.create_user('alice', password='pass')
        company = Company.objects.create(user=user, name='Example')
        job = JobPosition.objects.create(company=company, title='Developer')
        Application.objects.create(user=user, job_position=job)
        self.client.force_login(user)

        response = self.client.get(reverse('core:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'monthly-data')
