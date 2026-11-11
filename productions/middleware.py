from django.shortcuts import render

from .services import TransitionInterdite


class TransitionInterditeMiddleware:
    """Convertit TransitionInterdite en réponse HTTP 409 avec une page explicative (RG09)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, TransitionInterdite):
            return render(
                request,
                "409.html",
                {"message": str(exception), "production": exception.production},
                status=409,
            )
        return None
