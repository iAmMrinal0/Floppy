import time

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.shortcuts import redirect

STALE_RETRY_SESSION_KEY = "sso_stale_callback_retry_at"
STALE_RETRY_WINDOW_SECONDS = 120


class StaleCallbackSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Recover from OAuth callbacks whose state is no longer in the session.

    A callback URL reopened from browser history, a restored tab, or a reload
    carries a state that was already consumed. allauth renders "Third-Party
    Login Failure" for it even when the user is logged in, or when simply
    starting the login again would succeed.
    """

    def on_authentication_error(
        self,
        request,
        provider,
        error=None,
        exception=None,
        extra_context=None,
    ):
        """Redirect instead of failing when only the callback state is stale."""
        extra_context = extra_context or {}
        # allauth passes state_id without state only when the state lookup
        # failed. Provider errors (denied, cancelled, bad code) carry state.
        if "state" not in extra_context and "state_id" in extra_context:
            if request.user.is_authenticated:
                raise ImmediateHttpResponse(redirect(settings.LOGIN_REDIRECT_URL))
            if self._may_retry_login(request):
                request.session[STALE_RETRY_SESSION_KEY] = time.time()
                raise ImmediateHttpResponse(redirect(provider.get_login_url(request)))
        super().on_authentication_error(
            request,
            provider,
            error=error,
            exception=exception,
            extra_context=extra_context,
        )

    def _may_retry_login(self, request):
        # Without a session cookie the new state would be lost as well, and
        # retrying would loop between the app and the provider.
        if settings.SESSION_COOKIE_NAME not in request.COOKIES:
            return False
        last_retry = request.session.get(STALE_RETRY_SESSION_KEY)
        return (
            last_retry is None or time.time() - last_retry > STALE_RETRY_WINDOW_SECONDS
        )
