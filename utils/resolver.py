class Resolver:
    def __init__(self, item):
        """
        Initialize the Resolver with the given item and pre-flatten its structure.
        """
        self.item = item
        print("Initializing Resolver with item:", vars(item) if hasattr(item, '__dict__') else item)
        self.flattened_item = self._flatten_structure(item)
        print("Flattened structure:", self.flattened_item)

    def _flatten_structure(self, item, parent_key='', sep='.'):
        """
        Flatten a nested dictionary or object-like structure into a single-level dictionary.
        """
        flat_dict = {}
        if isinstance(item, dict):
            for k, v in item.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                print(f"Processing dict key: {new_key} -> {v}")
                flat_dict.update(self._flatten_structure(v, new_key, sep=sep))
        elif hasattr(item, '__dict__'):  # Handle object-like structures
            for k, v in vars(item).items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                print(f"Processing object attribute: {new_key} -> {v}")
                flat_dict.update(self._flatten_structure(v, new_key, sep=sep))
        else:
            flat_dict[parent_key] = item
            print(f"Added flat value: {parent_key} -> {item}")
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
