from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.shortcuts import redirect

STALE_RETRY_COOKIE = "sso_stale_callback_retry"
STALE_RETRY_WINDOW_SECONDS = 120


class StaleCallbackSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Recover from OAuth callbacks whose state is not in the session.

    The state is missing when a consumed callback URL is reopened (history, a
    restored tab, a reload), or when the callback arrives without the session
    cookie set at login start, e.g. when the browser reopens the provider in a
    different cookie container. allauth renders "Third-Party Login Failure"
    for both, even though sending a logged-in user home, or starting the login
    again from the callback's own context, succeeds.
    """

    def on_authentication_error(
        self,
        request,
        provider,
        error=None,
        exception=None,
        extra_context=None,
    ):
        """Redirect instead of failing when only the callback state is missing."""
        extra_context = extra_context or {}
        # allauth passes state_id without state only when the state lookup
        # failed. Provider errors (denied, cancelled, bad code) carry state.
        if "state" not in extra_context and "state_id" in extra_context:
            if request.user.is_authenticated:
                raise ImmediateHttpResponse(redirect(settings.LOGIN_REDIRECT_URL))
            # A cookie rather than the session marks the retry: the session is
            # exactly what may be missing. If cookies are blocked entirely the
            # marker is lost too, and the browser's redirect limit ends it.
            if STALE_RETRY_COOKIE not in request.COOKIES:
                response = redirect(provider.get_login_url(request))
                response.set_cookie(
                    STALE_RETRY_COOKIE,
                    "1",
                    max_age=STALE_RETRY_WINDOW_SECONDS,
                    path=settings.SESSION_COOKIE_PATH,
                    secure=request.is_secure(),
                    httponly=True,
                    samesite="Lax",
                )
                raise ImmediateHttpResponse(response)
        super().on_authentication_error(
            request,
            provider,
            error=error,
            exception=exception,
            extra_context=extra_context,
        )
