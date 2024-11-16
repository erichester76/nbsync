class Resolver:
    def __init__(self, item):
        self.item = item
        self._cached_keys = None
        self._cached_items = None

    def resolve(self, attr_path):
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
        return self.resolve(attr)

    def __getattr__(self, attr):
        return self.resolve(attr)

    def keys(self):
        """
        Cache keys to avoid recomputation.
        """
        if self._cached_keys is None:
            if isinstance(self.item, dict):
                self._cached_keys = list(self.item.keys())
            else:
                self._cached_keys = [
                    attr for attr in dir(self.item)
                    if not attr.startswith('_') and not callable(getattr(self.item, attr, None))
                ]
        return self._cached_keys

    def items(self):
        """
        Cache items to avoid recomputation.
        """
        if self._cached_items is None:
            self._cached_items = [(key, self[key]) for key in self.keys()]
        return self._cached_items

    def values(self):
        """
        Compute values based on cached keys.
        """
        return [self[key] for key in self.keys()]
