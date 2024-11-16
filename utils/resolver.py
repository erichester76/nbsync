from collections import defaultdict

class Resolver:
    def __init__(self, item, required_keys=None):
        self.item = item
        self.required_keys = required_keys or []
        self.pre_resolved = self._pre_resolve()

    def _pre_resolve(self):
        """
        Pre-resolve required keys by grouping shared prefixes and traversing them once.
        """
        resolved = {}
        grouped_keys = self._group_keys_by_prefix(self.required_keys)

        for prefix, keys in grouped_keys.items():
            # Resolve the shared prefix once
            prefix_obj = self.resolve(prefix)

            if prefix_obj is None:
                # If the prefix itself cannot be resolved, skip all keys in this group
                for key in keys:
                    resolved[key] = None
                continue

            # Extract all sub-keys for this prefix
            for key in keys:
                suffix = key[len(prefix) + 1:]  # Remove prefix + dot
                resolved[key] = self._extract_nested_value(prefix_obj, suffix)

        return resolved

    def _group_keys_by_prefix(self, keys):
        """
        Group keys by their shared prefix (up to the second-to-last part of the path).
        """
        grouped = defaultdict(list)
        for key in keys:
            if '.' in key:
                prefix = key.rsplit('.', 1)[0]
            else:
                prefix = key
            grouped[prefix].append(key)
        return grouped

    def _extract_nested_value(self, obj, path):
        """
        Extract the nested value for a given path starting from `obj`.
        """
        if not path:  # If the path is empty, return the object itself
            return obj
        attrs = path.split('.')
        current_obj = obj
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
            print(f"Error resolving nested path '{path}': {e}")
            return None

    def resolve(self, attr_path):
        """
        Dynamically resolve a dot-notation path from the root item.
        """
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
        return self.pre_resolved.get(attr)

    def __getattr__(self, attr):
        return self.pre_resolved.get(attr)

    def keys(self):
        return self.pre_resolved.keys()

    def items(self):
        return self.pre_resolved.items()

    def values(self):
        return self.pre_resolved.values()
