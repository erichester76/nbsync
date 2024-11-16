class Resolver:
    def __init__(self, item):
        """
        Initialize the Resolver with a flattened version of the item.
        """
        self.item = item
        self.flattened_item = self._flatten_structure(item)

    def _flatten_structure(self, item, parent_key='', sep='.'):
        """
        Flatten a nested dictionary or object-like structure into a single-level dictionary.
        """
        flat_dict = {}
        if isinstance(item, dict):
            for k, v in item.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                flat_dict.update(self._flatten_structure(v, new_key, sep=sep))
        elif hasattr(item, '__dict__'):  # Handle object-like structures
            for k, v in vars(item).items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                flat_dict.update(self._flatten_structure(v, new_key, sep=sep))
        else:
            flat_dict[parent_key] = item
        return flat_dict

    def resolve(self, path):
        """
        Resolve a dot-notation path using the pre-flattened structure.
        """
        return self.flattened_item.get(path, None)

    def __getitem__(self, path):
        return self.resolve(path)

    def __getattr__(self, path):
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
