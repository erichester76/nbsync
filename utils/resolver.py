from functools import lru_cache
import dpath.util


class Resolver:
    def __init__(self):
        self._cache = {}

    def resolve_nested_context(self,item):
        """Resolve nested attributes or keys in an object or dictionary using dpath."""
        context = {}

        if isinstance(item, dict):
            # Flatten the dictionary using dpath
            flat_dict = dpath.util.search(item, '**', yielded=True, separator='.')
            for path, value in flat_dict:
                context[path] = value
        else:
            # Handle objects with attributes
            for attr in dir(item):
                if not attr.startswith('_') and not callable(getattr(item, attr, None)):
                    value = getattr(item, attr, None)
                    if isinstance(value, dict):
                        # Recursively flatten nested dictionaries
                        nested_flat = resolve_nested_context(value)
                        for sub_path, sub_value in nested_flat.items():
                            context[f"{attr}.{sub_path}"] = sub_value
                    else:
                        context[attr] = value

        return context

