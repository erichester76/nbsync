from jinja2.defaults import DEFAULT_FILTERS

class Resolver:
    def __init__(self, item):
        self.item = item
        self.reserved_words = set(DEFAULT_FILTERS.keys())  # Includes 'replace', 'join', etc.

    def resolve(self, attr_path):
        """
        Dynamically resolve a dot-notation path from an object or dictionary.
        """
        print(f"resolving {attr_path}")
        attrs = attr_path.split('.')
        current_obj = self.item
        try:
            for attr in attrs:
                if isinstance(current_obj, dict):
                    current_obj = current_obj.get(attr)
                elif hasattr(current_obj, attr):
                    current_obj = getattr(current_obj, attr, None)
                else:
                    current_obj = None
                if current_obj is None:
                    break
            return current_obj
        except Exception as e:
            print(f"Error resolving '{attr_path}': {e}")
            return None

    def __getitem__(self, attr):
        """
        Handle key-like access, e.g., resolver['key'].
        """
        if attr in self.reserved_words:
            raise KeyError(f"Attribute '{attr}' conflicts with Jinja2 reserved words.")
        return self.resolve(attr)

    def __getattr__(self, attr):
        """
        Handle attribute-like access, e.g., resolver.key.
        """
        if attr in self.reserved_words:
            raise AttributeError(f"Attribute '{attr}' conflicts with Jinja2 reserved words.")
        return self.resolve(attr)

    # Implement dictionary-like behavior
    def keys(self):
        """
        Provide keys for Jinja2 to iterate over.
        """
        if isinstance(self.item, dict):
            return self.item.keys()
        return [attr for attr in dir(self.item) if not attr.startswith('_') and not callable(getattr(self.item, attr, None))]

    def items(self):
        """
        Provide items for Jinja2 to iterate over.
        """
        return [(key, self[key]) for key in self.keys()]

    def values(self):
        """
        Provide values for Jinja2 to iterate over.
        """
        return [self[key] for key in self.keys()]
