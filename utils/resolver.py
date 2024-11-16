from functools import lru_cache

class Resolver:
    def __init__(self):
        self._cache = {}

    @lru_cache(maxsize=1024)
    def get_nested_value(self, obj, attr_path):
        """Recursively get a nested value from an object or dict using dot notation."""
        attrs = attr_path.split('.')
        current_obj = obj
        try:
            for attr in attrs:
                if isinstance(current_obj, dict):
                    current_obj = current_obj.get(attr)
                else:
                    current_obj = getattr(current_obj, attr, None)
                if current_obj is None:
                    break
            return current_obj
        except AttributeError:
            return None

    def resolve_nested_context(self, item):
        """Resolve nested attributes in an object using dot notation."""
        if id(item) in self._cache:
            print("Used Nested Cache")
            return self._cache[id(item)]

        context = {}

        # Build the context with dot notation support for nested attributes
        if isinstance(item, dict):
            for key in item:
                context[key] = self.get_nested_value(item, key)
        else:
            attrs = (attr for attr in dir(item) if not attr.startswith('_') and not callable(getattr(item, attr, None)))
            for attr in attrs:
                context[attr] = self.get_nested_value(item, attr)

        # Cache the result for future use
        self._cache[id(item)] = context
        return context
