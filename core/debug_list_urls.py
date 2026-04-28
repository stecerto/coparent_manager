from django.urls import get_resolver, URLPattern, URLResolver


def list_urls(urlpatterns=None, prefix=""):
    if urlpatterns is None:
        urlpatterns = get_resolver().url_patterns

    for pattern in urlpatterns:
        if isinstance(pattern, URLPattern):
            print(
                f"{prefix}{pattern.pattern} "
                f"--> {pattern.name}"
            )

        elif isinstance(pattern, URLResolver):
            list_urls(
                pattern.url_patterns,
                prefix + str(pattern.pattern)
            )

def print_urls():
    resolver = get_resolver()

    for pattern in resolver.url_patterns:
        try:
            print(f"PATH: {pattern.pattern} -> NAME: {pattern.name}")
        except Exception:
            print(pattern)
