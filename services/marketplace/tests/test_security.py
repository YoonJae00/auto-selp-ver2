from security import decrypt_credentials, encrypt_credentials


def test_credentials_encryption_roundtrip_hides_secret():
    credentials = {"client_id": "id", "client_secret": "secret"}

    encrypted = encrypt_credentials(credentials)

    assert "secret" not in encrypted
    assert decrypt_credentials(encrypted) == credentials
