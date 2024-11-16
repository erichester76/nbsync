from functools import lru_cache
import dpath.util


class Resolver:
    def __init__(self):
        self._cache = {}

    def resolve_nested_context(self, item, keys_to_resolve=None):
        """Resolve specified keys/attributes for an object or dict."""
        context = {}
        print(f'resolving {keys_to_resolve}')
        if keys_to_resolve is None:
            keys_to_resolve = []

        if isinstance(item, dict):
            for key in keys_to_resolve:
                if key in item:
                    context[key] = item[key]
        else:
            for key in keys_to_resolve:
                if hasattr(item, key):
                    context[key] = getattr(item, key)

        return context


