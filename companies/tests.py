from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import Company, JobPosition


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
