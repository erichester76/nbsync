import importlib
from sources.base import DataSource

class APIDataSource(DataSource):
    def __init__(self, config):
        super().__init__(config)
        self.clients = []

    def authenticate(self):
        # Dynamically load the module specified in the YAML
        module_name = self.config['module']
        module = importlib.import_module(module_name)
        auth_method = self.config['auth_method']

        # Function to handle both simple function names and paths with submodules (e.g., connect.SmartConnect)
        def get_auth_function(module, function_path):
            func_parts = function_path.split(".")
            
            # Try to retrieve the function directly from the module (e.g., pynetbox.api)
            if hasattr(module, func_parts[0]):
                auth_func = getattr(module, func_parts[0])
            else:
                # If not found, dynamically import the submodule (e.g., pyVim.connect)
                submodule = importlib.import_module(f"{module.__name__}.{func_parts[0]}")
                auth_func = getattr(submodule, func_parts[1])
            
            return auth_func

        # Iterate through the base URLs (for multi-instance APIs, if needed)
        for base_url in self.config['base_urls']:
            # Dynamically retrieve the authentication function (supports paths like connect.SmartConnect)
            auth_func = get_auth_function(module, self.config['auth_function'])

            if auth_method == 'token':
                # Token-based authentication, using the token from auth_params
                client = auth_func(base_url, token=self.config['auth_params']['token'])

            elif auth_method == 'login':
                # Login-based authentication
                # Handle cases where auth_args may be empty or not defined
                if 'auth_args' in self.config and self.config['auth_args']:
                    # Collect arguments from auth_args if they exist
                    auth_args = [self.config['auth_params'][arg] for arg in self.config['auth_args']]
                    client = auth_func(*auth_args)
                else:
                    # Fallback to use auth_params directly (for APIs like NetBox)
                    client = auth_func(base_url, **self.config['auth_params'])

            else:
                raise ValueError(f"Unsupported auth method: {auth_method}")

            # Store the authenticated client
            self.clients.append(client)
