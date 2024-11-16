from functools import lru_cache

class Resolver:
    def __init__(self):
        self._cache = {}

    def resolve_nested_context(self, item):
        """Resolve flat or top-level attributes and keys in an object or dict."""
        context = {}

        if isinstance(item, dict):
            for key, value in item.items():
                # Directly map keys to their values if they're not complex nested structures
                if not isinstance(value, (dict, list, tuple)):
                    context[key] = value
        else:
            attrs = [
                attr for attr in dir(item)
                if not attr.startswith('_') and not callable(getattr(item, attr, None))
            ]
            for attr in attrs:
                value = getattr(item, attr, None)
                # Avoid resolving nested structures
                if not isinstance(value, (dict, list, tuple)):
                    context[attr] = value

        return context
