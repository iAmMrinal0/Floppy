import time
from unittest.mock import Mock

from allauth.core.exceptions import ImmediateHttpResponse
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase

from users.socialaccount_adapter import (
    STALE_RETRY_SESSION_KEY,
    StaleCallbackSocialAccountAdapter,
)

LOGIN_URL = "/accounts/oidc/pocketid/login/"
STALE_CONTEXT = {"state_id": "consumed", "callback_view": None}


class StaleCallbackSocialAccountAdapterTests(TestCase):
    """Tests for recovering from OAuth callbacks with a consumed state."""

    def setUp(self):
        """Build a callback request with a session and a stub provider."""
        self.adapter = StaleCallbackSocialAccountAdapter()
        self.provider = Mock()
        self.provider.get_login_url.return_value = LOGIN_URL
        self.request = RequestFactory().get("/accounts/oidc/pocketid/login/callback/")
        self.request.session = SessionStore()
        self.request.user = AnonymousUser()
        self.request.COOKIES[settings.SESSION_COOKIE_NAME] = "existing"

    def _redirect_for(self, extra_context):
        with self.assertRaises(ImmediateHttpResponse) as caught:
            self.adapter.on_authentication_error(
                self.request,
                self.provider,
                extra_context=extra_context,
            )
        return caught.exception.response

    def test_authenticated_user_goes_home(self):
        """A logged-in user reopening an old callback should land on home."""
        self.request.user = get_user_model().objects.create_user(username="viewer")

        response = self._redirect_for(dict(STALE_CONTEXT))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

    def test_anonymous_user_restarts_login_once(self):
        """A stale callback should restart the provider login and mark the retry."""
        response = self._redirect_for(dict(STALE_CONTEXT))

        self.assertEqual(response.url, LOGIN_URL)
        self.assertIn(STALE_RETRY_SESSION_KEY, self.request.session)

    def test_recent_retry_falls_back_to_error_page(self):
        """A second stale callback within the window should not loop."""
        self.request.session[STALE_RETRY_SESSION_KEY] = time.time()

        self.adapter.on_authentication_error(
            self.request,
            self.provider,
            extra_context=dict(STALE_CONTEXT),
        )

        self.provider.get_login_url.assert_not_called()

    def test_old_retry_marker_allows_new_retry(self):
        """A retry marker outside the window should not block recovery."""
        self.request.session[STALE_RETRY_SESSION_KEY] = time.time() - 3600

        response = self._redirect_for(dict(STALE_CONTEXT))

        self.assertEqual(response.url, LOGIN_URL)

    def test_missing_session_cookie_falls_back_to_error_page(self):
        """Without a session cookie a retry could never keep its state."""
        del self.request.COOKIES[settings.SESSION_COOKIE_NAME]

        self.adapter.on_authentication_error(
            self.request,
            self.provider,
            extra_context=dict(STALE_CONTEXT),
        )

        self.provider.get_login_url.assert_not_called()

    def test_provider_errors_still_render(self):
        """Errors that carry a state come from the provider and must surface."""
        self.request.user = get_user_model().objects.create_user(username="viewer")

        self.adapter.on_authentication_error(
            self.request,
            self.provider,
            extra_context={"state": {"process": "login"}, "callback_view": None},
        )

        self.provider.get_login_url.assert_not_called()
