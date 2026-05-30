"""Tiny URLConf for exercising HxTestClient through the middleware stack."""

from django.http import JsonResponse
from django.urls import path


def whoami(request):
    return JsonResponse(
        {
            "htmx": bool(request.htmx),
            "request_type": request.headers.get("HX-Request-Type"),
            "method": request.method,
            "posted": request.POST.get("x"),
            "query": request.GET.get("x"),
        }
    )


urlpatterns = [path("whoami/", whoami)]
