class Resolver:
    def __init__(self, item):
        self.item = item

    def resolve(self, attr_path):
        """
        Dynamically resolve a dot-notation path in an object or dictionary.
        """
        attrs = attr_path.split('.')
        current_obj = self.item
        try:
            for attr in attrs:
                # Check for dot-notation conflicts dynamically
                if isinstance(current_obj, dict):
                    current_obj = current_obj.get(attr)
                else:
                    # Skip reserved names dynamically
                    if attr in dir(current_obj):
                        if callable(getattr(current_obj, attr, None)):
                            raise AttributeError(f"Conflicting attribute: {attr}")
                    current_obj = getattr(current_obj, attr, None)
                if current_obj is None:
                    break
            return current_obj or ""
        except AttributeError:
            return ""

    def to_dict(self):
        """
        Expose the Resolver itself for lazy resolution in Jinja2.
        """
        return self

    def __getitem__(self, attr_path):
        return self.resolve(attr_path)

    def __getattr__(self, attr):
        return self.resolve(attr)
