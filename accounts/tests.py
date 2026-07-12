from django.contrib.auth import get_user_model
from django.test import TestCase


class UserModelTests(TestCase):
    def test_custom_user_model_is_active(self):
        user_model = get_user_model()

        self.assertEqual(user_model._meta.label, 'accounts.User')

    def test_user_string_uses_full_name_then_username(self):
        user_model = get_user_model()
        user = user_model(username='alice', first_name='Alice')

        self.assertEqual(str(user), 'Alice')

        user.first_name = ''
        self.assertEqual(str(user), 'alice')
