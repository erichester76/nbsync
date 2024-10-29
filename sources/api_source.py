import ssl
import importlib
from sources.base import DataSource
import types

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

        # Retrieve the authentication function dynamically
        auth_func = get_auth_function(module, self.config['auth_function'])

        # Iterate through base URLs if there are multiple
        for base_url in self.config['base_urls']:
            print(f"Connecting to {self.name} at {base_url}...")

            if auth_method == 'token':
                # Token-based authentication
                token = self.config['auth_params'].get('token')
                if token is None:
                    raise ValueError("Token is required for token-based authentication.")
                
                # Initialize the API client with token
                self.api = auth_func(base_url=base_url, access_token=token, version=self.config['auth_params'].get('version', '2.3.3'))
            
            elif auth_method == 'login':
                # Login-based authentication
                auth_args = self.config.get('auth_args', {})
                
                # Handle SSL context for VMware SmartConnect
                if 'sslContext' in auth_args and auth_args['sslContext'] == 'ignore':
                    ssl_context = ssl._create_unverified_context()
                    auth_args['sslContext'] = ssl_context  # Replace 'ignore' with the actual context
                elif 'sslContext' in auth_args:
                    auth_args['sslContext'] = None  # Option to pass an empty context
                
                # Inject base_url into auth_args if necessary (for VMware, DNAC doesn't need it here)
                if 'host' in auth_args:
                    auth_args['host'] = base_url

                # Dynamically call the auth function with auth_args
                self.api = auth_func(**auth_args)
            
            else:
                raise ValueError(f"Unsupported auth method: {auth_method}")

            # Store the authenticated client
            print(f"Connected to {self.name} at {base_url}")
            self.clients.append(self.api)

    def fetch_data(self, obj_config, api_client):
        """
        Fetch data from the API using either a direct fetch_data_function or a custom Python code block.
        Dynamically load modules specified in the 'imports' section of the YAML and inject into globals.
        """

        # Handle imports specified in YAML
        imports = obj_config.get('imports', [])
        local_vars = {'api_client': api_client}

        # Dynamically import modules and make them available in local_vars
        for import_path in imports:
            try:
                module_name, attr_name = import_path.rsplit('.', 1)
                module = __import__(module_name, fromlist=[attr_name])
                local_vars[attr_name] = getattr(module, attr_name)
            except ImportError as e:
                print(f"Error importing {import_path}: {e}")
                raise

        # Inject all imported local_vars into globals, except for 'api_client'
        for var_name, var_value in local_vars.items():
            if var_name != 'api_client':  # Skip api_client to prevent accidental overwrites
                globals()[var_name] = var_value

        # Fetch custom Python code to execute
        fetch_data_code = obj_config.get('fetch_data_code')

        if fetch_data_code:
            print(f"Using custom Python code for data fetch")

            # Execute the provided code within the local scope, passing in local_vars to exec
            exec(fetch_data_code, globals(), local_vars)

            # Ensure the 'fetch_data' function is defined in the code
            if 'fetch_data' not in local_vars:
                raise ValueError("The custom code must define a function 'fetch_data(api_client)'")

            # Call the dynamically defined function
            fetch_func = local_vars['fetch_data']
            if isinstance(fetch_func, types.FunctionType):
                return fetch_func(api_client)
            else:
                raise TypeError("fetch_data is not a valid function")

        # If no fetch method is specified, raise an error
        raise ValueError("No valid fetch method (fetch_data_function or fetch_data_code) found")

        
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