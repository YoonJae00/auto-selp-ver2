import pytest
from security import (
    get_password_hash, 
    verify_password, 
    create_access_token, 
    decode_access_token,
    encrypt_value,
    decrypt_value
)
from datetime import timedelta

def test_password_hashing():
    password = "secretpassword"
    hashed = get_password_hash(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrongpassword", hashed) is False

def test_jwt_token_creation_and_decoding():
    data = {"sub": "testuser"}
    token = create_access_token(data, expires_delta=timedelta(minutes=15))
    assert token is not None
    
    decoded_data = decode_access_token(token)
    assert decoded_data["sub"] == "testuser"

def test_value_encryption_decryption():
    original_value = "my-api-key-123"
    encrypted = encrypt_value(original_value)
    assert encrypted != original_value
    
    decrypted = decrypt_value(encrypted)
    assert decrypted == original_value
