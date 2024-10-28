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

        fetch_steps = obj_config.get('fetch_data_steps', [])
        result = api_client  # Start from the base client (ServiceInstance)

        # Track special objects so they can be used in later steps
        special_vars = {}

        for step in fetch_steps:
            method_name = step['method']
            params = step.get('params', [])

            # Check if the method_name is an attribute (like viewManager) or a method (like CreateContainerView)
            if hasattr(result, method_name):
                func = getattr(result, method_name)

                # If it's callable (a method), invoke it
                if callable(func):
                    # Replace special variables (like content.rootFolder) with the actual object from earlier steps
                    resolved_params = []
                    for param in params:
                        if isinstance(param, str) and param.startswith('{') and param.endswith('}'):
                            # Resolve the nested attributes (e.g., content.rootFolder)
                            parts = param.strip('{}').split('.')
                            value = special_vars.get(parts[0], None)
                            if value is None:
                                raise ValueError(f"Could not resolve special variable: {param}")
                            for part in parts[1:]:
                                value = getattr(value, part, None)
                                if value is None:
                                    raise ValueError(f"Could not resolve nested attribute '{part}' in {param}")
                            resolved_params.append(value)
                            
                        elif isinstance(param, str) and param.startswith("eval(") and param.endswith(")"):
                            # Evaluate Python expression and ensure it's passed as a type, not string
                            eval_expression = param[5:-1]  # Strip off 'eval(' and ')'
                            # Check if the evaluated object is a type
                            if isinstance(eval_expression, type):
                                resolved_params.append(eval_expression)
                            else:
                                raise TypeError(f"Expected a Python type, but got {type(eval_expression).__name__}")

                    print(f"Executing step: {method_name} with params: {resolved_params}")
                    result = func(*resolved_params)
                else:
                    # It's an attribute, just get the value
                    print(f"Accessing attribute: {method_name}")
                    result = func
            else:
                raise AttributeError(f"{method_name} not found on {result}")

            # Store result for later steps if 'store_as' is provided
            store_as = step.get('store_as')
            if store_as:
                print(f"Storing result of {method_name} as '{store_as}'")
                special_vars[store_as] = result

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