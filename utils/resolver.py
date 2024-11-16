from functools import lru_cache
import dpath.util


class Resolver:
    def __init__(self):
        self._cache = {}

    def resolve_nested_context(self, item, key=None):
        """Resolve specified keys/attributes for an object or dict."""
        context = {}
        print(f'resolving {key}')
        if key is None:
            key = []

        if isinstance(item, dict):
            if key in item:
                context[key] = item[key]
        else:
            if hasattr(item, key):
                context[key] = getattr(item, key)

        return context


