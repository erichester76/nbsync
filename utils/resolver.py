class Resolver:
    def __init__(self, item):
        """
        Initialize the Resolver with the given item and pre-flatten its structure.
        """
        self.item = item
        print("Initializing Resolver with item:", vars(item) if hasattr(item, '__dict__') else item)
        self.flattened_item = self._flatten_structure(item)
        print("Flattened structure:", self.flattened_item)

    def _flatten_structure(self, item, parent_key='', sep='.', visited=None, max_depth=20, current_depth=0):
        """
        Flatten a nested dictionary or object-like structure into a single-level dictionary,
        with protections against infinite recursion, permissions errors, and remote calls.
        """
        if visited is None:
            visited = set()

        flat_dict = {}

        # Prevent infinite recursion by checking max depth
        if current_depth > max_depth:
            print(f"Max depth reached at key: {parent_key}")
            return flat_dict

        # Prevent revisiting objects
        if id(item) in visited:
            print(f"Circular reference detected at key: {parent_key}")
            return flat_dict
        visited.add(id(item))

        def is_remote_object(value):
            """
            Determine if a value is likely to be a remote or lazy-loaded object.
            """
            return hasattr(value, "__call__") or "pyVmomi" in str(type(value))

        def get_value(obj, attr):
            """Safely get a value from an object or dict."""
            try:
                if isinstance(obj, dict):
                    return obj.get(attr, None)
                elif hasattr(obj, attr):
                    value = getattr(obj, attr, None)
                    if is_remote_object(value):
                        print(f"Skipping remote-like attribute: {attr}")
                        return None
                    return value
            except Exception as e:
                print(f"Skipping attribute {attr} due to error: {e}")
                return None

        if isinstance(item, dict):
            for k, v in item.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                flat_dict.update(self._flatten_structure(v, new_key, sep=sep, visited=visited, max_depth=max_depth, current_depth=current_depth + 1))
        elif hasattr(item, '__dict__') or isinstance(item, object):
            for attr in dir(item):
                if attr.startswith('_') or callable(getattr(item, attr, None)):
                    continue  # Skip private and callable attributes
                value = get_value(item, attr)
                if value is None:
                    continue
                new_key = f"{parent_key}{sep}{attr}" if parent_key else attr
                flat_dict.update(self._flatten_structure(value, new_key, sep=sep, visited=visited, max_depth=max_depth, current_depth=current_depth + 1))
        else:
            flat_dict[parent_key] = item

        return flat_dict

    def resolve(self, path):
        """
        Resolve a dot-notation path using the pre-flattened structure or dynamically.
        """
        print(f"Attempting to resolve path: {path}")

        # Check the flattened structure
        if path in self.flattened_item:
            value = self.flattened_item[path]
            print(f"Resolved from flattened: {path} -> {value}")
            return value

        # Resolve dynamically for missing keys
        attrs = path.split('.')
        current_obj = self.item
        for attr in attrs:
            if current_obj is None:
                print(f"Stopping resolution: '{attr}' is undefined in '{path}'")
                return None
            if isinstance(current_obj, dict):
                current_obj = current_obj.get(attr)
            elif hasattr(current_obj, attr):
                current_obj = getattr(current_obj, attr, None)
            else:
                print(f"Attribute '{attr}' not found in '{path}'")
                return None
        print(f"Dynamically resolved: {path} -> {current_obj}")
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
        Provide all available paths in the flattened structure.
        """
        return self.flattened_item.keys()

    def items(self):
        """
        Provide all key-value pairs in the flattened structure.
        """
        return self.flattened_item.items()

    def values(self):
        """
        Provide all values in the flattened structure.
        """
        return self.flattened_item.values()
