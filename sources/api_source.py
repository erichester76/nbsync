import ssl
import importlib
from sources.base import DataSource
import requests
from bravado.client import SwaggerClient
from bravado.requests_client import RequestsClient
import datetime

class APIDataSource(DataSource):
    def __init__(self, name, config):
        super().__init__(config)
        self.name = name
        self.api = None
        self.clients = []
        self.session_expiry = {}

    def is_session_valid(self, base_url):
        if base_url in self.session_expiry:
            return datetime.datetime.now() < self.session_expiry[base_url]
        return False

    def authenticate(self):
        """Handle authentication, supporting both Swagger (Bravado) and non-Swagger clients."""
        api_type = self.config.get('type')
        base_url = self.config['auth_args'].get('base_url')

        if api_type == 'api_swagger':
            self._authenticate_swagger(base_url)
        else:
            self._authenticate_standard(base_url)

    def _authenticate_swagger(self, base_url):
        """Authenticate using Bravado (Swagger) with various auth methods."""
        http_client = RequestsClient()
        auth_method = self.config['auth_method']

        if auth_method == 'apiKey':
            api_key = self.config['auth_args'].get('api_key')
            api_key_header = self.config['auth_args'].get('api_key_header', 'Authorization')
            http_client.session.headers.update({api_key_header: api_key})

        elif auth_method == 'basic':
            username = self.config['auth_args']['username']
            password = self.config['auth_args']['password']
            http_client.session.auth = (username, password)

        elif auth_method == 'bearer':
            token = self.config['auth_args']['api_key']
            http_client.session.headers.update({'Authorization': f'Bearer {token}'})

        elif auth_method == 'custom_login':
            self._handle_custom_login(http_client, base_url)

        else:
            raise ValueError(f"Unsupported auth_method for Swagger: {auth_method}")

        # Initialize Swagger client with authenticated HTTP client
        self.api = SwaggerClient.from_url(
            f"{base_url}/swagger.json",
            http_client=http_client,
            config={'also_return_response': True}
        )
        self.clients.append(self.api)
        print(f"Connected to Swagger API at {base_url}")

    def _authenticate_standard(self, base_url):
       # Dynamically load the module specified in the YAML
        module_name = self.config['module']
        module = importlib.import_module(module_name)
        auth_method = self.config['auth_method']

        # Function to handle both simple function names and paths with submodules (e.g., connect.SmartConnect)
        def get_auth_function(module, function_path):
            func_parts = function_path.split(".")
            if len(func_parts) == 1:
                auth_func = getattr(module, func_parts[0])
            else:
                submodule = importlib.import_module(f"{module.__name__}.{func_parts[0]}")
                auth_func = getattr(submodule, func_parts[1])
            return auth_func

        for base_url in self.config['base_urls']:
            print(f"Connecting to {self.name} at {base_url}...")

            # Dynamically retrieve the authentication function
            auth_func = get_auth_function(module, self.config['auth_function'])
            
            if not callable(auth_func):
                raise TypeError(f"{auth_func} is not callable. Please check your function path.")

            # Convert auth_args from list to dictionary, if applicable
            if 'auth_args' in self.config:
                auth_args = self.config['auth_args']
                if isinstance(auth_args, list):
                    auth_args = {arg['name']: arg['value'] for arg in auth_args}
                    if 'sslContext' in auth_args:
                        if auth_args['sslContext'] == 'ignore':
                            auth_args['sslContext'] = ssl._create_unverified_context()
                        elif auth_args['sslContext'] == 'None':
                            auth_args['sslContext'] = None
                    if 'host' in auth_args:
                        auth_args['host']=base_url
                        
            else:
                auth_args = {}

            # Add base_url if required
            if 'base_url' in inspect.signature(auth_func).parameters:
                auth_args['base_url'] = base_url

            if self.api and self.is_session_valid(base_url):
                    print(f"Using existing session for {self.name} @ {base_url}.")
            else:
                print(f"(re)authenticating for {self.name} @ {base_url}.")
                # Handle authentication methods
                if auth_method == 'token':
                    self.api = auth_func(base_url, token=self.config['auth_args']['token'])
                    if base_url not in self.session_expiry: 
                        self.clients.append(self.api)
                        print(f"Connected to {self.name} at {base_url}")

                    self.session_expiry[base_url] = datetime.datetime.now() + datetime.timedelta(minutes=2)

                elif auth_method == 'login':
                    if auth_args:
                        self.api = auth_func(**auth_args)
                        if base_url not in self.session_expiry: 
                            self.clients.append(self.api)
                            print(f"Connected to {self.name} at {base_url}")

                        self.session_expiry[base_url] = datetime.datetime.now() + datetime.timedelta(minutes=2)

                    else:
                        raise ValueError("Login-based authentication requires auth_args to be set.")

    def _prepare_auth_args(self, base_url):
        # Expect auth_args to be a dictionary with key-value pairs
        auth_args = self.config.get('auth_args', {})

        if not isinstance(auth_args, dict):
            raise TypeError("auth_args must be a dictionary")

        # Inject base_url if required
        auth_args['host'] = auth_args.get('host', base_url)

        return auth_args


    def _handle_custom_login(self, http_client, base_url):
        """Handle custom login flow for Swagger."""
        token_endpoint = self.config['auth_args'].get('token_endpoint')
        username = self.config['auth_args'].get('username')
        password = self.config['auth_args'].get('password')
        custom_params = self.config['auth_args'].get('custom_params', {})
        token_key = self.config['auth_args'].get('token_key', 'access_token')

        login_url = f"{base_url}{token_endpoint}"
        login_data = {'username': username, 'password': password, **custom_params}
        response = requests.post(login_url, data=login_data, verify=False)

        if response.status_code == 200:
            token = response.json().get(token_key)
            if token:
                http_client.session.headers.update({'Authorization': f'Bearer {token}'})
                self.session_expiry[base_url] = datetime.datetime.now() + datetime.timedelta(minutes=30)
            else:
                raise ValueError("Token not found in login response")
        else:
            raise ConnectionError(f"Login failed with status code {response.status_code}")

    # fetch_data and get_nested_function remain as previously defined, with no changes
