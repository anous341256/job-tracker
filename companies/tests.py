from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import Company, JobPosition
from .forms import JobPositionForm


class CompanyAndJobPositionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='alice', password='test-pass')

    def test_company_name_is_unique_per_user(self):
        Company.objects.create(user=self.user, name='Example')

        with self.assertRaises(IntegrityError), transaction.atomic():
            Company.objects.create(user=self.user, name='Example')

    def test_same_company_name_is_allowed_for_different_users(self):
        other_user = get_user_model().objects.create_user(username='bob', password='test-pass')
        Company.objects.create(user=self.user, name='Example')
        Company.objects.create(user=other_user, name='Example')

        self.assertEqual(Company.objects.filter(name='Example').count(), 2)

    def test_salary_minimum_cannot_exceed_maximum(self):
        company = Company.objects.create(user=self.user, name='Example')
        job = JobPosition(
            company=company,
            title='Python Developer',
            salary_min=Decimal('6000000'),
            salary_max=Decimal('5000000'),
        )

        with self.assertRaises(ValidationError):
            job.full_clean()

    def test_company_detail_hides_other_users_data(self):
        other_user = get_user_model().objects.create_user(username='bob', password='test-pass')
        company = Company.objects.create(user=other_user, name='Private')
        self.client.force_login(self.user)

        self.assertEqual(self.client.get(reverse('companies:detail', args=[company.pk])).status_code, 404)

    def test_other_category_requires_custom_value(self):
        company = Company.objects.create(user=self.user, name='Example')
        form = JobPositionForm(data={
            'company': company.pk,
            'title': 'Researcher',
            'category': JobPosition.Category.OTHER,
            'category_other': '',
            'status': JobPosition.Status.OPEN,
            'work_mode': JobPosition.WorkMode.UNKNOWN,
            'employment_type': JobPosition.EmploymentType.FULL_TIME,
            'salary_currency': 'JPY',
            'salary_period': JobPosition.SalaryPeriod.YEARLY,
        }, user=self.user)

        self.assertFalse(form.is_valid())
        self.assertIn('category_other', form.errors)

    def test_all_job_dates_use_date_pickers(self):
        form = JobPositionForm(user=self.user)

        self.assertEqual(form.fields['application_deadline'].widget.input_type, 'date')
        self.assertEqual(form.fields['published_at'].widget.input_type, 'date')

    def test_company_page_preselects_company_when_adding_job(self):
        company = Company.objects.create(user=self.user, name='Example')
        self.client.force_login(self.user)

        response = self.client.get(reverse('companies:job-create'), {'company': company.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(response.context['form'].initial['company']), str(company.pk))

    def test_empty_company_urls_render_as_missing_not_links(self):
        company = Company.objects.create(user=self.user, name='Test')
        self.client.force_login(self.user)

        response = self.client.get(reverse('companies:detail', args=[company.pk]))

        self.assertContains(response, '尚未填写', count=3)
        self.assertNotContains(response, 'atom.com')
