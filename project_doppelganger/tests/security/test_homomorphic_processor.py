import unittest
from project_doppelganger.src.security.homomorphic_processor import (
    HomomorphicProcessor,
    EncryptedData,
    HESchemeDetails
)

class TestHomomorphicProcessor(unittest.TestCase):

    def setUp(self):
        self.default_scheme = HESchemeDetails()
        self.he_processor = HomomorphicProcessor(scheme_details=self.default_scheme)

    def test_encryption_decryption_int(self):
        original_data = 123
        encrypted_data = self.he_processor.encrypt(original_data, "int")

        self.assertIsInstance(encrypted_data, EncryptedData)
        self.assertEqual(encrypted_data.scheme_details, self.default_scheme)
        self.assertEqual(encrypted_data.original_type_hint, "int")
        self.assertTrue(encrypted_data.ciphertext.startswith(f"HE_CIPHERTEXT::{self.default_scheme.name}::"))

        decrypted_data = self.he_processor.decrypt(encrypted_data)
        self.assertEqual(decrypted_data, original_data)
        self.assertIsInstance(decrypted_data, int)

    def test_encryption_decryption_str(self):
        original_data = "hello homomorphic world"
        encrypted_data = self.he_processor.encrypt(original_data) # Type hint inferred

        self.assertEqual(encrypted_data.original_type_hint, "str")

        decrypted_data = self.he_processor.decrypt(encrypted_data)
        self.assertEqual(decrypted_data, original_data)
        self.assertIsInstance(decrypted_data, str)

    def test_encryption_decryption_bool(self):
        original_data = True
        encrypted_data = self.he_processor.encrypt(original_data, "bool")
        decrypted_data = self.he_processor.decrypt(encrypted_data)
        self.assertEqual(decrypted_data, original_data)
        self.assertIsInstance(decrypted_data, bool)

        original_data_false = False
        encrypted_data_f = self.he_processor.encrypt(original_data_false)
        decrypted_data_f = self.he_processor.decrypt(encrypted_data_f)
        self.assertEqual(decrypted_data_f, original_data_false)
        self.assertIsInstance(decrypted_data_f, bool)


    def test_decrypt_mismatched_scheme(self):
        original_data = 42
        encrypted_data = self.he_processor.encrypt(original_data)

        other_scheme = HESchemeDetails(name="DifferentScheme")
        encrypted_data_wrong_scheme = EncryptedData(
            ciphertext=encrypted_data.ciphertext, # Same ciphertext, different scheme obj
            scheme_details=other_scheme,
            original_type_hint="int"
        )
        decrypted_data = self.he_processor.decrypt(encrypted_data_wrong_scheme)
        self.assertIsNone(decrypted_data) # Should fail due to scheme mismatch

    def test_decrypt_invalid_ciphertext_format(self):
        invalid_ciphertext = EncryptedData(
            ciphertext="NOT_A_VALID_CIPHERTEXT",
            scheme_details=self.default_scheme,
            original_type_hint="int"
        )
        decrypted_data = self.he_processor.decrypt(invalid_ciphertext)
        self.assertIsNone(decrypted_data) # Should fail due to format

    def test_conceptual_add_encrypted(self):
        val1 = 10
        val2 = 25
        enc1 = self.he_processor.encrypt(val1, "int")
        enc2 = self.he_processor.encrypt(val2, "int")

        enc_sum = self.he_processor.add_encrypted(enc1, enc2)
        self.assertIsNotNone(enc_sum)
        self.assertIsInstance(enc_sum, EncryptedData)

        dec_sum = self.he_processor.decrypt(enc_sum) # type: ignore
        self.assertEqual(dec_sum, val1 + val2)

    def test_conceptual_add_encrypted_type_error_simulation(self):
        val1 = 10
        val_str = "oops"
        enc1 = self.he_processor.encrypt(val1, "int")
        enc_str = self.he_processor.encrypt(val_str, "str")

        enc_sum_error = self.he_processor.add_encrypted(enc1, enc_str)
        self.assertIsNone(enc_sum_error) # Simulated decryption and add would raise TypeError


    def test_conceptual_multiply_by_plain(self):
        val = 7
        scalar = 3
        enc_val = self.he_processor.encrypt(val, "int")

        enc_prod = self.he_processor.multiply_by_plain(enc_val, scalar)
        self.assertIsNotNone(enc_prod)
        self.assertIsInstance(enc_prod, EncryptedData)

        dec_prod = self.he_processor.decrypt(enc_prod) # type: ignore
        self.assertEqual(dec_prod, val * scalar)

    def test_unsupported_operation(self):
        limited_scheme = HESchemeDetails(supported_operations=["add"])
        limited_processor = HomomorphicProcessor(scheme_details=limited_scheme)

        val = 5
        scalar = 2
        enc_val = limited_processor.encrypt(val, "int") # Encryption itself is not an "operation" here

        # Try multiply_by_plain which is not in supported_operations
        enc_prod_unsupported = limited_processor.multiply_by_plain(enc_val, scalar)
        self.assertIsNone(enc_prod_unsupported)


if __name__ == '__main__':
    unittest.main()
