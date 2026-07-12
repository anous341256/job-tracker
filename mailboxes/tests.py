from django.test import SimpleTestCase

from .services import decrypt_token, encrypt_token


class TokenEncryptionTests(SimpleTestCase):
    def test_token_round_trip_is_encrypted(self):
        encrypted = encrypt_token('secret-token')
        self.assertNotIn('secret-token', encrypted)
        self.assertEqual(decrypt_token(encrypted), 'secret-token')
