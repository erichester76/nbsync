from functools import lru_cache
import dpath.util


class Resolver:
    def __init__(self):
        self._cache = {}

    def resolve_nested_context(self,item):
        """Resolve flat attributes and keys with minimal overhead."""
        context = {}

        # Handle dictionary objects
        if isinstance(item, dict):
            context.update(item)
        else:
            # Filter attributes to skip private and callable ones
            attrs = [
                attr for attr in dir(item)
                if not attr.startswith('_') and not callable(getattr(item, attr, None))
            ]
            for attr in attrs:
                context[attr] = getattr(item, attr, None)

        return context
