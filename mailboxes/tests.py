from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from companies.models import Company
from .models import DeletedEmailMarker, EmailAccount, SyncedEmail
from .services import cleanup_stored_emails, decrypt_token, encrypt_token


class TokenEncryptionTests(SimpleTestCase):
    def test_token_round_trip_is_encrypted(self):
        encrypted = encrypt_token('secret-token')
        self.assertNotIn('secret-token', encrypted)
        self.assertEqual(decrypt_token(encrypted), 'secret-token')


class MessageDetailTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='reader', password='test-pass')
        self.other_user = get_user_model().objects.create_user(username='other', password='test-pass')
        self.account = EmailAccount.objects.create(
            user=self.user,
            provider=EmailAccount.Provider.OUTLOOK_LOCAL,
            email_address='reader@example.com',
        )
        self.email = SyncedEmail.objects.create(
            account=self.account,
            provider_message_id='outlook-entry-id',
            direction=SyncedEmail.Direction.INBOUND,
            sender='sender@example.com',
            recipients=['reader@example.com'],
            subject='Interview invitation',
            body_text='Message body',
            received_at=timezone.now(),
        )

    def test_owner_can_read_message_detail(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('mailboxes:message-detail', args=[self.email.pk]))
        self.assertContains(response, 'Interview invitation')
        self.assertContains(response, 'Message body')

    def test_other_user_cannot_read_message_detail(self):
        self.client.force_login(self.other_user)
        response = self.client.get(reverse('mailboxes:message-detail', args=[self.email.pk]))
        self.assertEqual(response.status_code, 404)

    def test_provider_message_id_is_unique_per_account(self):
        with self.assertRaises(Exception):
            SyncedEmail.objects.create(
                account=self.account,
                provider_message_id='outlook-entry-id',
                direction=SyncedEmail.Direction.INBOUND,
                sender='sender@example.com',
                recipients=[],
                received_at=timezone.now(),
            )

    def test_search_and_pagination_keep_user_scope(self):
        for index in range(25):
            SyncedEmail.objects.create(account=self.account, provider_message_id=f'id-{index}', direction=SyncedEmail.Direction.INBOUND, sender='jobs@example.com', recipients=[], subject=f'Role {index}', body_text='keyword', received_at=timezone.now() - timedelta(minutes=index))
        self.client.force_login(self.user)
        response = self.client.get(reverse('mailboxes:messages'), {'q': 'keyword'})
        self.assertEqual(len(response.context['emails']), 20)
        self.assertTrue(response.context['page_obj'].has_next())

    def test_quick_company_link_is_owner_scoped(self):
        company = Company.objects.create(user=self.user, name='Example Corp')
        other_company = Company.objects.create(user=self.other_user, name='Other Corp')
        self.client.force_login(self.user)
        self.client.post(reverse('mailboxes:quick-link-company', args=[self.email.pk]), {'company': company.pk})
        self.email.refresh_from_db()
        self.assertEqual(self.email.company, company)
        self.client.post(reverse('mailboxes:quick-link-company', args=[self.email.pk]), {'company': other_company.pk})
        self.email.refresh_from_db()
        self.assertEqual(self.email.company, company)

    def test_delete_creates_marker_and_removes_only_database_copy(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('mailboxes:message-delete', args=[self.email.pk]), {'confirm': 'yes'})
        self.assertRedirects(response, reverse('mailboxes:messages'))
        self.assertFalse(SyncedEmail.objects.filter(pk=self.email.pk).exists())
        self.assertTrue(DeletedEmailMarker.objects.filter(account=self.account).exists())

    def test_cleanup_removes_old_unlinked_but_preserves_linked(self):
        old = timezone.now() - timedelta(days=181)
        unlinked = SyncedEmail.objects.create(account=self.account, provider_message_id='old-unlinked', direction=SyncedEmail.Direction.INBOUND, sender='sender@example.com', recipients=[], received_at=old)
        company = Company.objects.create(user=self.user, name='Keep Corp')
        linked = SyncedEmail.objects.create(account=self.account, provider_message_id='old-linked', direction=SyncedEmail.Direction.INBOUND, sender='sender@example.com', recipients=[], received_at=old, company=company)
        cleanup_stored_emails()
        self.assertFalse(SyncedEmail.objects.filter(pk=unlinked.pk).exists())
        self.assertTrue(SyncedEmail.objects.filter(pk=linked.pk).exists())
