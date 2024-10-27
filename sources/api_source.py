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

        # Function to handle function paths with or without periods (e.g., connect.SmartConnect)
        def get_auth_function(module, function_path):
            func_parts = function_path.split(".")
            # Dynamically resolve the function path step by step
            auth_func = getattr(module, func_parts[0])
            for part in func_parts[1:]:
                auth_func = getattr(auth_func, part)
            return auth_func

        # Iterate through the base URLs (for multi-instance APIs, if needed)
        for base_url in self.config['base_urls']:
            # Dynamically retrieve the authentication function (supports paths like connect.SmartConnect)
            auth_func = get_auth_function(module, self.config['auth_function'])

            if auth_method == 'token':
                # Token-based authentication, calling the auth_function dynamically
                client = auth_func(base_url, token=self.config['auth_params']['token'])

            elif auth_method == 'login':
                # Login-based authentication, passing the auth_args dynamically
                auth_args = [self.config['auth_params'][arg] for arg in self.config['auth_args']]
                client = auth_func(*auth_args)

            else:
                raise ValueError(f"Unsupported auth method: {auth_method}")

            # Store the authenticated client
            self.clients.append(client)

