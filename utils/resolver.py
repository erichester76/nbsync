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
    
    
    def _extract_nested_values(self, obj, paths):
        """
        Extract multiple nested values for given paths from a base object.
        """
        results = {}
        for path in paths:
            current_obj = obj
            attrs = path.split('.')
            try:
                for attr in attrs:
                    if isinstance(current_obj, dict):
                        current_obj = current_obj.get(attr)
                    elif hasattr(current_obj, attr):
                        print(f"b4 {attr}")
                        current_obj = getattr(current_obj, attr, None)
                        print(f"after {attr}")

                    else:
                        current_obj = None
                        break
                results[path] = current_obj
            except Exception as e:
                print(f"Error resolving nested path '{path}': {e}")
                results[path] = None
        return results


    
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

                # If the prefix is resolved, extract all sub-values
                if current_obj is not None:
                    sub_keys = [key[len(prefix) + 1:] for key in keys if key != prefix]
                    
                    sub_values = self._extract_nested_values(current_obj, sub_keys)
                    for suffix, value in sub_values.items():
                        resolved[f"{prefix}.{suffix}"] = value

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
