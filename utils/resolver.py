
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
                if isinstance(current_obj, dict):
                    current_obj = current_obj.get(attr)
                else:
                    current_obj = getattr(current_obj, attr, None)
                if current_obj is None:
                    break
            return current_obj
        except AttributeError:
            return None

    def to_dict(self):
        """
        Expose a dictionary-like interface for template rendering.
        """
        return self  # Self acts as a resolver for unresolved fields

    def __getitem__(self, attr_path):
        return self.resolve(attr_path)

    def __getattr__(self, attr):
        return self.resolve(attr)
