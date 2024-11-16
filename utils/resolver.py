class Resolver:
    def __init__(self, item):
        """
        Initialize the Resolver with the given item.
        """
        self.item = item
        self.resolved_data = {}  # Stores pre-resolved values
        print("Initializing Resolver with item:", vars(item) if hasattr(item, '__dict__') else item)

    def pre_resolve(self, required_keys):
        """
        Pre-resolve only the required keys from the item.
        """
        for key in required_keys:
            value = self.resolve(key)
            if value is not None:
                self.resolved_data[key] = value
        print("Pre-resolved data:", self.resolved_data)

    def resolve(self, path):
        """
        Resolve a dot-notation path dynamically.
        """
        print(f"Attempting to resolve path: {path}")
        if path in self.resolved_data:
            print(f"Resolved from cache: {path} -> {self.resolved_data[path]}")
            return self.resolved_data[path]

        attrs = path.split('.')
        current_obj = self.item
        for attr in attrs:
            try:
                if current_obj is None:
                    print(f"Stopping resolution: '{attr}' is undefined in '{path}'")
                    return None
                if isinstance(current_obj, dict):
                    current_obj = current_obj.get(attr)
                else:
                    current_obj = getattr(current_obj, attr, None)
            except Exception as e:
                print(f"Error resolving '{path}' at '{attr}': {e}")
                return None
        print(f"Resolved path: {path} -> {current_obj}")
        return current_obj

    def __getitem__(self, path):
        """
        Allow dictionary-like access to resolve paths.
        """
        return self.resolve(path)

    def __getattr__(self, path):
        """
        Allow attribute-like access to resolve paths.
        """
        return self.resolve(path)

    def keys(self):
        """
        Provide all pre-resolved keys.
        """
        return self.resolved_data.keys()

    def items(self):
        """
        Provide all pre-resolved key-value pairs.
        """
        return self.resolved_data.items()

    def values(self):
        """
        Provide all pre-resolved values.
        """
        return self.resolved_data.values()
