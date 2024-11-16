from jinja2.defaults import DEFAULT_FILTERS

class Resolver:
    def __init__(self, item):
        self.item = item
        self.reserved_words = set(DEFAULT_FILTERS.keys())  # Jinja2 filters like 'replace', 'join', etc.

    def resolve(self, attr_path):
        """
        Resolve a dot-notation path dynamically from an object or dictionary.
        """
        attrs = attr_path.split('.')
        current_obj = self.item
        try:
            for attr in attrs:
                if isinstance(current_obj, dict):
                    current_obj = current_obj.get(attr)
                else:
                    # Handle attributes on objects
                    current_obj = getattr(current_obj, attr, None)
                if current_obj is None:
                    break
            return current_obj
        except AttributeError:
            return None

    def __getitem__(self, attr):
        """
        Handle key-like access, e.g., resolver['key'].
        """
        if attr in self.reserved_words:
            # Avoid reserved conflicts
            raise KeyError(f"Attribute '{attr}' conflicts with Jinja2 reserved words.")
        return self.resolve(attr)

    def __getattr__(self, attr):
        """
        Handle attribute-like access, e.g., resolver.key.
        """
        if attr in self.reserved_words:
            # Avoid reserved conflicts
            raise AttributeError(f"Attribute '{attr}' conflicts with Jinja2 reserved words.")
        return self.resolve(attr)
