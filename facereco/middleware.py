import time

from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.models import AnonymousUser


class SessionInactivityTimeoutMiddleware:
    """Expire authenticated sessions after a sliding period of inactivity."""

    activity_key = "_last_activity"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            now = int(time.time())
            idle_timeout = getattr(settings, "SESSION_IDLE_TIMEOUT", 30 * 60)
            last_activity = request.session.get(self.activity_key)
            try:
                expired = last_activity is not None and now - int(last_activity) >= idle_timeout
            except (TypeError, ValueError):
                expired = True

            if expired:
                logout(request)
                # Ensure downstream login_required checks see the expired session.
                request.user = AnonymousUser()
            else:
                request.session[self.activity_key] = now
                request.session.set_expiry(idle_timeout)

        return self.get_response(request)


class NoCacheAuthenticatedMiddleware:
    """Prevent browsers and shared caches from reusing authenticated pages after logout."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(request, "user", None) is not None and request.user.is_authenticated:
            response["Cache-Control"] = "private, no-store, no-cache, max-age=0, must-revalidate"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
        return response


class AdminMFAGateMiddleware:
    """Require opted-in staff to complete the app's second factor per session."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.is_staff:
            from .models import AdminMFAProfile
            from django.shortcuts import redirect

            mfa_enabled = AdminMFAProfile.objects.filter(
                user_id=user.pk,
                enabled=True,
            ).exists()
            allowed_path = request.path_info.rstrip("/") == "/admin-login"
            verified = request.session.get("admin_mfa_verified_user") == user.pk
            if mfa_enabled and not verified and not allowed_path:
                return redirect("adminlogin")
        return self.get_response(request)
