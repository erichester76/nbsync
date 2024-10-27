import ssl
import importlib
from sources.base import DataSource

class APIDataSource(DataSource):
    def __init__(self, name, config):
        super().__init__(config)
        self.name = name  # Store the section name
        self.clients = []

    def authenticate(self):
        # Dynamically load the module specified in the YAML
        module_name = self.config['module']
        module = importlib.import_module(module_name)
        auth_method = self.config['auth_method']

        # Function to handle both simple function names and paths with submodules (e.g., connect.SmartConnect)
        def get_auth_function(module, function_path):
            func_parts = function_path.split(".")
            
            # If it's a single part (no "."), we assume it's directly from the module
            if len(func_parts) == 1:
                auth_func = getattr(module, func_parts[0])
            else:
                # Otherwise, we treat it as a submodule or subpath (e.g., connect.SmartConnect)
                submodule = importlib.import_module(f"{module.__name__}.{func_parts[0]}")
                auth_func = getattr(submodule, func_parts[1])
            
            return auth_func

        # Iterate through the base URLs (for multi-instance APIs, if needed)
        for base_url in self.config['base_urls']:
            print(f"Connecting to {self.name} at {base_url}...")

            # Dynamically retrieve the authentication function (supports paths like connect.SmartConnect)
            auth_func = get_auth_function(module, self.config['auth_function'])

            if not callable(auth_func):
                raise TypeError(f"{auth_func} is not callable. Please check your function path.")

            if auth_method == 'token':
                # Token-based authentication, calling the auth_function dynamically
                client = auth_func(base_url, token=self.config['auth_params']['token'])

            elif auth_method == 'login':
                # Login-based authentication
                if 'auth_args' in self.config and self.config['auth_args']:
                    # Handle SSL context (ignore if specified)
                    if 'sslContext' in self.config['auth_params'] and self.config['auth_params']['sslContext'] == 'ignore':
                        ssl_context = ssl._create_unverified_context()  # Ignore SSL errors
                    else:
                        ssl_context = None
                    
                    # Collect arguments for SmartConnect: host, user, pwd, and sslContext
                    auth_args = {
                        "host": base_url,
                        "user": self.config['auth_params']['username'],
                        "pwd": self.config['auth_params']['password'],
                        "sslContext": ssl_context
                    }

                    # Call the SmartConnect function with explicit arguments
                    client = auth_func(**auth_args)
                else:
                    raise ValueError("Login-based authentication requires auth_args to be set.")
                    
            else:
                raise ValueError(f"Unsupported auth method: {auth_method}")

            # Store the authenticated client
            print(f"Connected to {self.name} at {base_url}")
            self.clients.append(client)
            
            
def fetch_data(self, api_mapping):
    """
    Fetch data from the API dynamically based on the provided api_mapping.
    
    :param api_mapping: Mapping that defines which API data to fetch, the endpoint, and query parameters.
    :return: Retrieved data (usually in a structured format).
    """
    data = []
    print(f'Retrieving Objects from API')
    method = api_mapping.get('method', 'GET').upper()

    # VMware or other API requiring a custom function (like CreateContainerView)
    if method == 'CUSTOM' and 'fetch_data_function' in api_mapping:
        fetch_function = api_mapping['fetch_data_function']
        custom_func = getattr(self.client.content.viewManager, fetch_function.split('.')[-1])  # Extract function dynamically

        # Use parameters from the YAML to call the custom function
        object_type = api_mapping['params']['object_type']
        view_type = api_mapping['params']['view_type']
        container_view = custom_func(self.client.content.rootFolder, [object_type], view_type)

        # Dynamically fetch the list of objects (e.g., VMs)
        object_list = container_view.view
        container_view.Destroy()

        # Dynamically map fields based on the YAML mapping
        for obj in object_list:
            obj_data = {}
            for dest_field, field_info in api_mapping['mapping'].items():
                # Dynamically traverse the object tree to fetch the required fields
                source_value = self.get_nested_attr(obj, field_info['source'].split('.'))
                obj_data[dest_field] = source_value
            data.append(obj_data)

    return data

def get_nested_attr(self, obj, attrs):
    """
    Recursively get attributes from an object based on a list of attribute names.
    Handles attributes like "runtime.powerState" from YAML.
    
    :param obj: The base object (e.g., a VMware VirtualMachine object).
    :param attrs: List of attribute names (e.g., ["runtime", "powerState"]).
    :return: The retrieved attribute value.
    """
    for attr in attrs:
        obj = getattr(obj, attr, None)  # Get the attribute, or None if not found
        if obj is None:
            break  # Stop if any attribute in the chain is None
    return obj

