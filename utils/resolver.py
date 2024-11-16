class Resolver:
    def __init__(self, item, required_keys=None):
        self.item = item
        self.required_keys = required_keys or []
        self.pre_resolved = self._pre_resolve()

    def _pre_resolve(self):
        resolved = {}
        for key in self.required_keys:
            attrs = key.split('.')
            current_obj = self.item
            full_path = []

            try:
                for attr in attrs:
                    full_path.append(attr)
                    full_path_str = '.'.join(full_path)

                    if full_path_str not in resolved:
                        if isinstance(current_obj, dict):
                            current_obj = current_obj.get(attr)
                        elif hasattr(current_obj, attr):
                            current_obj = getattr(current_obj, attr, None)
                        else:
                            current_obj = None

                        if current_obj is None:
                            print(f"Unable to resolve '{full_path_str}'")
                            break

                        resolved[full_path_str] = current_obj
                    else:
                        current_obj = resolved[full_path_str]
            except Exception as e:
                print(f"Error resolving '{key}': {e}")
                resolved[key] = None

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
