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
        Fetch data dynamically based on either a single fetch_data_function or multiple fetch_data_steps.

        :param obj_config: Object configuration that defines the fetch steps or single fetch function.
        :param api_client: Authenticated API client (e.g., VMware, NetBox).
        :return: List of objects (e.g., virtual machines).
        """
        if 'fetch_data_function' in obj_config:
            # Handle a single function call
            function_path = obj_config['fetch_data_function']
            parts = function_path.split('.')
            
            # Traverse the API client to get the function or attribute
            func = api_client
            for part in parts:
                func = getattr(func, part, None)
                if func is None:
                    raise AttributeError(f"Function '{function_path}' not found in API client.")
            
            # Call the function and return the result (assume no params for simplicity)
            return func()

        elif 'fetch_data_steps' in obj_config:
            # Handle multiple steps dynamically
            obj = api_client  # Start with the API client (e.g., vmware connection)
            for step in obj_config.get('fetch_data_steps', []):
                method_name = step.get('method')
                
                if 'params' in step:
                    params = []
                    for param in step['params']:
                        # Handle nested attributes (e.g., content.rootFolder)
                        if isinstance(param, str) and '.' in param:
                            attrs = param.split('.')
                            param_value = api_client
                            for attr in attrs:
                                param_value = getattr(param_value, attr)
                            params.append(param_value)
                        else:
                            params.append(eval(str(param)))
                    obj = getattr(obj, method_name)(*params)
                else:
                    obj = getattr(obj, method_name, None)
                    if obj is None:
                        raise AttributeError(f"Step '{method_name}' not found in API client.")
            return obj
        else:
            raise ValueError("No valid 'fetch_data_function' or 'fetch_data_steps' found in the YAML configuration.")


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