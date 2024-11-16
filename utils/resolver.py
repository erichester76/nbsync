from functools import lru_cache
import dpath.util


class Resolver:
    def __init__(self):
        self._cache = {}

    def resolve_nested_context(self, item):
        """Resolve nested attributes in an object using dot notation."""
        context = {}

        def get_nested_value(obj, attr_path):
            """Recursively get a nested value from an object or dict using dot notation."""
            attrs = attr_path.split('.')
            current_obj = obj
            try:
                for attr in attrs:
                    if isinstance(current_obj, dict):
                        current_obj = current_obj.get(attr)
                    else:
                        current_obj = getattr(current_obj, attr)
                    if current_obj is None:
                        break
                return current_obj
            except AttributeError:
                return None

        # Build the context with dot notation support for nested attributes
        if isinstance(item, dict):
            for key in item:
                context[key] = get_nested_value(item, key)
        else:
            for attr in dir(item):
                try:
                    if attr.startswith('_') or callable(getattr(item, attr)):
                        print(f'{attr} Skipped')
                        continue
                    print(f'{attr} Processed')
                    context[attr] = get_nested_value(item, attr)
                except Exception as e:
                    continue

        return context
