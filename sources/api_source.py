
import importlib
from sources.base import DataSource

class APIDataSource(DataSource):
    def __init__(self, config):
        super().__init__(config)
        self.clients = []  # Multiple clients for multiple URLs

    def authenticate(self):
        module_name = self.config['module']
        module = importlib.import_module(module_name)
        auth_method = self.config['auth_method']

        for base_url in self.config['base_urls']:  # Iterate through multiple base URLs
            if auth_method == 'token':
                client = module.api(base_url, token=self.config['auth_params']['token'])
            elif auth_method == 'login':
                login_func = getattr(module, self.config['login_function'])
                login_args = [self.config['auth_params'][arg] for arg in self.config['login_args']]
                client = login_func(*login_args)
            else:
                raise ValueError(f"Unsupported auth method: {auth_method}")
            self.clients.append(client)

    def fetch_data(self):
        all_data = []
        fetch_func_name = self.config['fetch_data_function']
        for client in self.clients:
            fetch_func = getattr(client, fetch_func_name)
            data = fetch_func(*self.config.get('fetch_data_args', []))
            all_data.extend(data)
        return all_data
