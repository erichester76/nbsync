import ssl
import importlib
from sources.base import DataSource
import requests
from bravado.client import SwaggerClient
from bravado.requests_client import RequestsClient
import datetime
import time
import inspect
import types
import urllib3

class APIDataSource(DataSource):
    def __init__(self, name, config):
        super().__init__(config)
        self.name = name
        self.api = None
        self.clients = []
        self.session_expiry = {}
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def is_session_valid(self, base_url):
        if base_url in self.session_expiry:
            return datetime.datetime.now() < self.session_expiry[base_url]
        return False

    def authenticate(self):
        """Handle authentication, supporting both Swagger and non-Swagger clients."""
        api_type = self.config['type']
        for base_url in self.config['base_urls']:
            if api_type == 'api-swagger':
                self._authenticate_swagger(base_url)
            else:
                self._authenticate_standard(base_url)

    def _authenticate_swagger(self, base_url):
        """Authenticate using Bravado (Swagger) with various auth methods."""
        http_client = RequestsClient()
        auth_method = self.config['auth_method']
        auth_args = self.config['auth_args']  # Assume auth_args is a dictionary
        
        # Apply authentication based on method
        if auth_method == 'apiKey':
            api_key = auth_args.get('api_key')
            api_key_header = auth_args.get('api_key_header', 'Authorization')
            http_client.session.headers.update({api_key_header: api_key})

        elif auth_method == 'basic':
            username = auth_args['username']
            password = auth_args['password']
            http_client.session.auth = (username, password)

        elif auth_method == 'bearer':
            token = auth_args['api_key']
            http_client.session.headers.update({'Authorization': f'Bearer {token}'})

        elif auth_method == 'login':
            print(f'using custom login method')
            self._handle_custom_login(http_client, base_url)

        else:
            raise ValueError(f"Unsupported auth_method for Swagger: {auth_method}")

        # Initialize Swagger client with authenticated HTTP client
        #self.api = SwaggerClient.from_url(
        #    f"{base_url}/api/swagger.json",
        #    http_client=http_client}
        #)
        
        self.clients.append(http_client)
        print(f"Connected to REST API")

    def _authenticate_standard(self, base_url):
        module = importlib.import_module(self.config['module'])
        auth_method = self.config['auth_method']
        auth_func = self._get_auth_function(module, self.config['auth_function'])
        auth_args = self._prepare_auth_args(base_url)
        branch = None
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
                self.api.http_session.verify = False
                if base_url not in self.session_expiry: 
                    self.clients.append(self.api)
                    print(f"Connected to {self.name} at {base_url}")
                    if 'branch' in self.config:
                        ts = datetime.datetime.now().strftime("%m%d%y%H%M")
                        print(f"Setting Branch Header to {self.config['branch']}")
                        status='new'
                        while 'ready' not in status:
                            result=list(self.api.plugins.branching.branches.filter(name=f"{self.config['branch']}"))[0]['status'].get('value')
                            if len(result)<1: 
                                branch = self.api.plugins.branching.branches.create(name=f"{self.config['branch']}", status='new')
                            else:
                                status=result.get('value')
                            print(f'waiting on branch to form {status}')
                            time.sleep(1)

                        self.api.http_session.headers["X-NetBox-Branch"] = branch.schema_id
                        print(f"Set Branch Header to {branch.schema_id} ({self.config['branch']} {ts})")
       
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
        """Prepare auth args, converting lists to dicts as needed and setting SSL context."""
        auth_args = self.config['auth_args']

        # Convert auth_args list to dictionary if necessary
        if isinstance(auth_args, list):
            auth_args = {arg['name']: arg['value'] for arg in auth_args}
  
        # Handle SSL context if specified
        if auth_args.get('sslContext') == 'ignore':
            auth_args['sslContext'] = ssl._create_unverified_context()
        elif auth_args.get('sslContext') == 'None':
            auth_args['sslContext'] = None

        if 'host' in auth_args:
            auth_args['host'] = base_url
        return auth_args

    def _get_auth_function(self, module, function_path):
        """Retrieve auth function from a module, allowing for submodules."""
        func_parts = function_path.split(".")
        if len(func_parts) == 1:
            return getattr(module, func_parts[0])
        else:
            submodule = importlib.import_module(f"{module.__name__}.{func_parts[0]}")
            return getattr(submodule, func_parts[1])

    def _handle_custom_login(self, http_client, base_url):
        """Handle custom login for Swagger APIs."""
        auth_args = self.config['auth_args']
        login_url = f"{base_url}{auth_args.get('login_endpoint')}"
        login_data = {'username': auth_args['username'], 'password': auth_args['password']}
        print(f"Logging in to {login_url}")
        headers = {'Content-Type': 'application/json'}

        print(f"Logging in to {login_url}")
        response = requests.post(login_url, json=login_data, headers=headers, verify=False)
        
        if response.status_code == 200:
            token = response.json().get(auth_args.get('token_key', 'access_token'))
            if token:
            
                http_client.session.headers.update({'Authorization': f'{token}'})
                self.session_expiry[base_url] = datetime.datetime.now() + datetime.timedelta(minutes=30)
            else:
                raise ValueError("Token not found in login response")
        else:
            raise ConnectionError(f"Login failed with status code {response.status_code}")

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
        return obj#