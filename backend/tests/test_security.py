"""PBKDF2 password hashing: round-trips, rejects wrong passwords, salts so two
hashes of the same password differ, and never raises on a corrupt stored value."""

from backend.utils.security import hash_password, verify_password


def test_hash_verifies_correct_password():
    stored = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", stored)


def test_rejects_wrong_password():
    stored = hash_password("s3cret-password")
    assert not verify_password("wrong-password", stored)


def test_same_password_hashes_differently():
    # Distinct random salts ⇒ distinct hashes, both valid.
    a = hash_password("same-password")
    b = hash_password("same-password")
    assert a != b
    assert verify_password("same-password", a)
    assert verify_password("same-password", b)


def test_stored_format_is_self_describing():
    stored = hash_password("whatever-123")
    algo, iterations, salt, digest = stored.split("$")
    assert algo == "pbkdf2_sha256"
    assert int(iterations) >= 100_000


def test_corrupt_stored_value_returns_false_not_raises():
    for bad in ("", "garbage", "pbkdf2_sha256$notanint$aa$bb", "a$b$c"):
        assert verify_password("x", bad) is False
