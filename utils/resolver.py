from jinja2.defaults import DEFAULT_FILTERS


class Resolver:
    def __init__(self, item):
        self.item = item

    def resolve(self, attr_path):
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
            return current_obj or ""
        except AttributeError:
            return ""

    def sanitize_keys(self, data):
        """
        Sanitize dictionary keys to avoid conflicts with Jinja2 filters.
        """

        reserved_words = set(DEFAULT_FILTERS.keys())        
        sanitized_data = {}
        for key, value in data.items():
            if key in reserved_words:
                sanitized_key = f"{key}_"  
                print(f"sanitized {key}")
            else:
               sanitized_key = key
            sanitized_data[sanitized_key] = value
        return sanitized_data

    def to_dict(self):
        print(f'{self}')
        if isinstance(self.item, dict):
            return self.sanitize_keys(self.item)
        return self
    
    def __getitem__(self, attr_path):
        return self.resolve(attr_path)

    def __getattr__(self, attr):
        return self.resolve(attr)
