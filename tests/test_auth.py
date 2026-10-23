import unittest

from hargasync.auth import hash_password, verify_password
from tests.support import PASSWORD, csrf, login, make_client


class TestPasswords(unittest.TestCase):
    def test_round_trip(self):
        stored = hash_password("s3cret")
        self.assertTrue(verify_password("s3cret", stored))
        self.assertFalse(verify_password("wrong", stored))

    def test_garbage_hash_rejected(self):
        self.assertFalse(verify_password("x", "not-a-hash"))


class TestLogin(unittest.TestCase):
    def setUp(self):
        self.client, self.settings = make_client(self)

    def test_protected_page_redirects_to_login(self):
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login")

    def test_wrong_password(self):
        token = csrf(self.client)
        response = self.client.post("/login", data={"username": "owner_ali", "password": "nope", "csrf_token": token})
        self.assertEqual(response.status_code, 401)
        self.assertIn("Wrong username or password", response.text)

    def test_login_without_csrf_rejected(self):
        response = self.client.post("/login", data={"username": "owner_ali", "password": PASSWORD})
        self.assertEqual(response.status_code, 403)

    def test_owner_login_shows_shop(self):
        response = login(self.client, "owner_ali")
        self.assertEqual(response.headers["location"], "/")
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Kedai Runcit Pak Ali", page.text)
        self.assertIn("Owner", page.text)

    def test_other_shop_user_sees_own_shop(self):
        login(self.client, "owner_siti")
        page = self.client.get("/")
        self.assertIn("Mini Market Seri Kembangan", page.text)
        self.assertNotIn("Kedai Runcit Pak Ali", page.text)

    def test_logout_requires_csrf(self):
        login(self.client, "owner_ali")
        self.assertEqual(self.client.post("/logout", data={}).status_code, 403)

    def test_logout_clears_session(self):
        login(self.client, "owner_ali")
        token = csrf(self.client, "/")
        response = self.client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.client.get("/", follow_redirects=False).status_code, 303)


if __name__ == "__main__":
    unittest.main()
