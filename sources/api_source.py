import ssl
import importlib
from sources.base import DataSource

class APIDataSource(DataSource):
    def __init__(self, name, config):
        super().__init__(config)
        self.name = name  # Store the section name
        self.api = None
        self.clients = []  # Initialize the clients list

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
                self.api = auth_func(base_url, token=self.config['auth_params']['token'])

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
                    self.api = auth_func(**auth_args)
                else:
                    raise ValueError("Login-based authentication requires auth_args to be set.")
                    
            else:
                raise ValueError(f"Unsupported auth method: {auth_method}")

            # Store the authenticated client
            print(f"Connected to {self.name} at {base_url}")
            self.clients.append(self.api)
            
    def fetch_data(self, obj_config, api_client):
        """
        Fetch data from the API using either a direct fetch_data_function or a series of steps (fetch_data_steps).
        """

        # Check if 'fetch_data_function' is defined
        fetch_data_function = obj_config.get('fetch_data_function')
        
        if fetch_data_function:
            print(f"Using fetch_data_function: {fetch_data_function}")
            func = self.get_nested_function(api_client, fetch_data_function)
            return func()  # Call the function directly

        steps = obj_config.get('fetch_data_steps')
        result = None
        special_vars = {}

        for step in steps:
            method_name = step.get('method')
            attribute_name = step.get('attribute')
            params = step.get('params', [])

            # Resolve parameters with special variables
            resolved_params = []
            for param in params:
                if isinstance(param, str) and param.startswith("{") and param.endswith("}"):
                    # Resolve special variables like {content.rootFolder}
                    special_var_name = param[1:-1]
                    if special_var_name in special_vars:
                        resolved_params.append(special_vars[special_var_name])
                    else:
                        raise ValueError(f"Could not resolve special variable: {param}")
                elif isinstance(param, list) and "vim.VirtualMachine" in param:
                    resolved_params.append([pyVmomi.vim.VirtualMachine])
                else:
                    resolved_params.append(param)

            # If there's an attribute to access instead of a method
            if attribute_name:
                # Access the attribute (like viewManager) from the result (content)
                result = getattr(special_vars.get('content'), attribute_name)
            else:
                func = getattr(api_client, method_name) if method_name else result
                result = func(*resolved_params)

            # Store result for later steps if necessary
            if 'store_as' in step:
                special_vars[step['store_as']] = result

        return result
    
    
    def get_nested_function(self, api_client, function_path):
        """
        Recursively get a function from the API client.
        
        :param api_client: The API client (e.g., NetBox client)
        :param function_path: Path to the function (e.g., 'dcim.device_types.filter')
        :return: The function object
        """
        parts = function_path.split('.')
        func = api_client  # Start with the root client (e.g., pynetbox.NetBox())

        # Traverse down the client object tree
        for part in parts:
            try:
                func = getattr(func, part)
            except AttributeError:
                raise AttributeError(f"Attribute '{part}' not found in API client at path '{function_path}'")
        
        # Ensure the final attribute is callable
        if not callable(func):
            raise TypeError(f"Final attribute in path '{function_path}' is not callable.")
        
        return func

    def get_nested_attr(self, obj, attrs):
        """
        Recursively get attributes from an object based on a list of attribute names.
        Handles attributes like 'runtime.powerState' from YAML.
        """
        for attr in attrs:
            obj = getattr(obj, attr, None)
            if obj is None:
                break  # Stop if any attribute in the chain is None
        return obj