from functools import lru_cache
import dpath.util


class Resolver:
    def __init__(self):
        self._cache = {}

    def resolve_nested_context(self,item):
        """Resolve nested attributes in a dictionary using dpath."""
        context = {}

        if isinstance(item, dict):
            for key in item.keys():
                try:
                    value = dpath.util.get(item, key, separator='.')
                    context[key] = value
                except KeyError:
                    continue
        return context
