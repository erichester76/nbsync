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
            print(f"Connected to {self.name} API @ {base_url}")
            self.clients.append(client)
