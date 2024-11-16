from collections import defaultdict

class Resolver:
    def __init__(self, item, required_keys=None):
        self.item = item
        self.required_keys = required_keys or []
        self.pre_resolved = self._pre_resolve()


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

    
    def _pre_resolve(self):
        """
        Pre-resolve only the required keys, handling grouped prefixes dynamically.
        """
        resolved = {}
        grouped_keys = self._group_keys_by_prefix(self.required_keys)

        for prefix, keys in grouped_keys.items():
            current_obj = self.item
            full_path = []

            try:
                # Resolve the shared prefix
                for attr in prefix.split('.'):
                    full_path.append(attr)
                    full_path_str = '.'.join(full_path)

                    if full_path_str not in resolved:
                        if isinstance(current_obj, dict):
                            current_obj = current_obj.get(attr)
                        elif hasattr(current_obj, attr):
                            current_obj = getattr(current_obj, attr, None)
                        else:
                            current_obj = None

                        resolved[full_path_str] = current_obj
                        if current_obj is None:
                            break  # Stop resolving deeper if the prefix is None
                    else:
                        # Use already resolved value for the current path
                        current_obj = resolved[full_path_str]

                # Extract values for all keys in this group
                if current_obj is not None:
                    for key in keys:
                        suffix = key[len(prefix) + 1:]  # Remove prefix + dot
                        if suffix:
                            resolved[key] = self._extract_nested_value(current_obj, suffix)
                        else:
                            resolved[key] = current_obj

            except Exception as e:
                print(f"Error resolving prefix '{prefix}': {e}")
                for key in keys:
                    resolved[key] = None  # Safeguard unresolved paths

        return resolved

    def resolve(self, attr_path):
        """
        Dynamically resolve a dot-notation path from an object or dictionary.
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
