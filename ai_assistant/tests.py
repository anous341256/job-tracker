from unittest.mock import patch

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from companies.models import Company, JobPosition
from .crypto import decrypt_api_key, encrypt_api_key
from .models import AISettings, AITask
from .services import create_ai_task, redact_contact_details
from .providers import OpenAIProvider
from .schemas import JDParseResult


TEST_KEY = Fernet.generate_key().decode()


@override_settings(AI_CREDENTIAL_ENCRYPTION_KEY=TEST_KEY)
class AIAssistantTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='ai-user', password='pass')
        self.other = get_user_model().objects.create_user(username='other-ai', password='pass')
        self.company = Company.objects.create(user=self.user, name='AI Corp')
        self.job = JobPosition.objects.create(company=self.company, title='Python Engineer')

    def test_api_key_round_trip_is_encrypted(self):
        encrypted = encrypt_api_key('sk-test-secret')
        self.assertNotIn('sk-test-secret', encrypted)
        self.assertEqual(decrypt_api_key(encrypted), 'sk-test-secret')

    def test_contact_details_are_redacted(self):
        value = redact_contact_details('Me test@example.com +81 90-1234-5678')
        self.assertNotIn('test@example.com', value)
        self.assertNotIn('90-1234-5678', value)

    @patch('ai_assistant.tasks.execute_ai_task.delay')
    def test_duplicate_active_task_is_reused(self, delay):
        first, created = create_ai_task(user=self.user, task_type=AITask.Type.JD_PARSE, job=self.job, provider=AISettings.Provider.OLLAMA, source_text='Python role')
        second, created_again = create_ai_task(user=self.user, task_type=AITask.Type.JD_PARSE, job=self.job, provider=AISettings.Provider.OLLAMA, source_text='Changed text')
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first, second)
        delay.assert_called_once()

    @patch('ai_assistant.tasks.execute_ai_task.delay')
    def test_cloud_match_requires_sensitive_consent(self, delay):
        config = AISettings.objects.create(user=self.user, encrypted_openai_api_key=encrypt_api_key('sk-test'), openai_key_verified=True)
        from productivity.models import Resume
        resume = Resume(user=self.user, name='CV')
        with self.assertRaisesMessage(ValueError, '授权'):
            create_ai_task(user=self.user, task_type=AITask.Type.JOB_MATCH, job=self.job, provider=AISettings.Provider.OPENAI, resume=resume)

    def test_other_user_cannot_view_task(self):
        task = AITask.objects.create(user=self.user, task_type=AITask.Type.JD_PARSE, provider='ollama', model='qwen3:8b', job=self.job, input_fingerprint='x')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('ai_assistant:task-detail', args=[task.pk])).status_code, 404)

    def test_selective_jd_apply(self):
        task = AITask.objects.create(user=self.user, task_type=AITask.Type.JD_PARSE, provider='ollama', model='qwen3:8b', job=self.job, input_fingerprint='x', status=AITask.Status.SUCCEEDED, result={'title': 'Senior Python Engineer', 'location': 'Tokyo', 'skills': ['Python']}, finished_at=timezone.now())
        self.client.force_login(self.user)
        self.client.post(reverse('ai_assistant:task-apply', args=[task.pk]), {'fields': ['location', 'skills']})
        self.job.refresh_from_db()
        self.assertEqual(self.job.title, 'Python Engineer')
        self.assertEqual(self.job.location, 'Tokyo')
        self.assertEqual(self.job.ai_metadata['skills'], ['Python'])

    def test_settings_page_does_not_expose_encrypted_key(self):
        AISettings.objects.create(user=self.user, encrypted_openai_api_key=encrypt_api_key('sk-super-secret'), openai_key_suffix='cret', openai_key_verified=True)
        self.client.force_login(self.user)
        response = self.client.get(reverse('ai_assistant:settings'))
        self.assertContains(response, '••••cret')
        self.assertNotContains(response, 'sk-super-secret')

    @patch('openai.OpenAI')
    def test_openai_provider_uses_parsed_structured_output(self, client_class):
        parsed = JDParseResult(title='Engineer', skills=['Python'])
        response = client_class.return_value.responses.parse.return_value
        response.output_parsed = parsed
        response.usage.input_tokens = 12
        response.usage.output_tokens = 8
        result = OpenAIProvider('sk-test').generate(model='test-model', prompt='JD', schema=JDParseResult)
        self.assertEqual(result.data['title'], 'Engineer')
        _, kwargs = client_class.return_value.responses.parse.call_args
        self.assertFalse(kwargs['store'])
