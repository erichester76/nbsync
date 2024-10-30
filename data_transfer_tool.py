#!/usr/bin/env python3

import yaml
import re
import os
import argparse
from sources.api_source import APIDataSource
from sources.csv_source import CSVDataSource
from sources.xls_source import XLSDataSource
from sources.snmp_source import SNMPDataSource
import jinja2
import deepdiff

# Register custom Jinja2 filters

def regex_replace(value, pattern, replacement):
    return re.sub(pattern, replacement, value)

# Custom slugify filter
def slugify(value):
    return re.sub(r'\W+', '-', value.lower())

# Create a new Jinja2 environment and add the filters
env = jinja2.Environment(loader=jinja2.FileSystemLoader('./'))
env.filters['regex_replace'] = regex_replace
env.filters['slugify'] = slugify

def env_var_constructor(loader, node):
    """Extracts the environment variable from the node value."""
    value = loader.construct_scalar(node)
    matches = env_var_pattern.findall(value)
    
    for match in matches:
        env_value = os.getenv(match, None)
        if env_value:
            value = value.replace(f"${{{match}}}", env_value)
        else:
            raise ValueError(f"Environment variable '{match}' not set.")
    
    return value


env_var_pattern = re.compile(r'\$\{([^}^{]+)\}')

yaml.add_implicit_resolver('!envvar', env_var_pattern)
yaml.add_constructor('!envvar', env_var_constructor)


class DataTransferTool:
    def __init__(self, yaml_file, dry_run):

        # Read the YAML file line by line and build yaml_content until object_mappings
        yaml_content = []
        object_mappings = []
        is_object_mappings = False

        with open(yaml_file, 'r') as file:
            for line in file:
                # Once we hit the object_mappings section, we stop adding lines to yaml_content
                if line.strip().startswith('object_mappings:'):
                    is_object_mappings = True

                if is_object_mappings:
                    # Collect object_mappings into a separate list
                    object_mappings.append(line)
                else:
                    # Collect all other lines into yaml_content
                    yaml_content.append(line)

        # Join the non-object_mappings section into a full YAML string
        yaml_content_str = ''.join(yaml_content)

        # Substitute environment variables in the YAML content
        yaml_content_str = os.path.expandvars(yaml_content_str)

        # Load the YAML content (excluding object_mappings) into self.config
        self.config = yaml.load(yaml_content_str, Loader=yaml.FullLoader)

        # Keep the object_mappings section as a string (to be rendered later)
        self.raw_object_mappings = ''.join(object_mappings)

        # Store the dry_run flag
        self.dry_run = dry_run
        self.sources = {}
        self.mapped_data = {}
        self.DEBUG = 1

    def initialize_sources(self):
        for name, config in self.config['api_definitions'].items():
            source_type = config['type']
            if source_type == 'api':
                self.sources[name] = APIDataSource(name, config)
            elif source_type == 'csv':
                self.sources[name] = CSVDataSource(name, config)
            elif source_type == 'xls':
                self.sources[name] = XLSDataSource(config)
            elif source_type == 'snmp':
                self.sources[name] = SNMPDataSource(config)
            self.sources[name].authenticate()

    def process_mappings(self):
        """Process the mappings defined in the object_mappings section of the YAML."""
     
        # Render the object_mappings section with Jinja2 dynamically
        rendered_object_mappings = env(self.raw_object_mappings).render()
        object_mappings_config = yaml.load(rendered_object_mappings, Loader=yaml.FullLoader)
        self.config['object_mappings'] = object_mappings_config['object_mappings']
        
        for obj_type, obj_config in self.config['object_mappings'].items():
            source = self.sources[obj_config['source_api']]

            for source_client in source.clients:
                source_api = obj_config.get('source_api')
                print(f"Fetching data from {source_api}...")
                source_data = source.fetch_data(obj_config, source_client)
                destination_api = self.sources[obj_config['destination_api']]
                for destination_client in destination_api.clients:
                    create_function = obj_config.get('create_function')
                    update_function = obj_config.get('update_function')
                    find_function = obj_config.get('find_function')
                    mappings = obj_config['mapping']

                    for item in source_data:
                        mapped_data = {}

                        for dest_field, field_info in mappings.items():
                            source_value = field_info['source']
                            if ('action' in field_info):
                                action = field_info.get('action')
                                source_value = self.apply_transform_function(source_value, action, obj_config, dest_field, item)
                            mapped_data[dest_field] = source_value
                                
                        object_id = self.create_or_update(destination_client, find_function, create_function, update_function, mapped_data)
                        if self.DEBUG == 1: print(f"Processed object with ID: {object_id}")

    def apply_transform_function(self, value, actions, obj_config, field_name, item):
        """Apply transformations using Jinja2 filters directly."""
        if value is None:
            return value

        if isinstance(actions, str):
            actions = [action]

        for action in actions:
            if 'regex_replace' in action:
                pattern, replacement = re.findall(r"regex_replace\('(.*?)',\s*'*(.*?)'*\)", action)[0]
                value = env.filters['regex_replace'](value, pattern, replacement)
            elif 'lookup_object' in action:
                matches = re.findall(r"lookup_object\('(.*?)',\s*'(.*?)',\s*'(.*?)'\)", trans)
                if matches:
                    lookup_type, find_function_path, create_function_path = matches[0]
                    value = self.lookup_object(value, lookup_type, find_function_path, create_function_path, obj_config, map, field_name, item)
            
        return value

    def lookup_object(self, value, lookup_type, find_function_path, create_function_path, obj_config, map, field_name, item):
        """Perform API lookup or create an object on the server side."""
        api_client = self.sources[obj_config['destination_api']].api
        find_function = self.get_nested_function(api_client, find_function_path)
        create_function = self.get_nested_function(api_client, create_function_path)
        
        filter_params = {lookup_type: value}
        
        # Handle additional fields from the mapping
        additional_data = self.get_included_fields_data(obj_config, field_name, item)
        filter_params.update(additional_data)

        # Try finding the object
        try:
            found_object = find_function(**filter_params)
            if found_object:
                return list(found_object)[0]  # Return first found object
        except Exception as e:
            print(f"Error calling find_function: {str(e)}")

        # If not found, create the object
        try:
            create_data = {lookup_type: value, 'slug': re.sub(r'\W+', '-', value.lower()), **additional_data}
            created_object = create_function(create_data)
            return created_object.id if hasattr(created_object, 'id') else None
        except Exception as e:
            print(f"Error calling create_function: {str(e)}")
            return None


    def create_or_update(self, api_client, find_function_path, create_function_path, update_function_path, mapped_data):
        """Create or update objects in the destination API."""
        # Find function
        find_function = self.get_nested_function(api_client, find_function_path)
        # Automatically extract the first field from mapped_data as the key field
        key_field = list(mapped_data.keys())[0]
        filter_params = {key_field: mapped_data[key_field]}

        try:
            found_object = find_function(**filter_params)
        except Exception as e:
            print(f"Error calling find_function: {str(e)}")
            raise

        if found_object:
            existing_object = list(found_object)[0]
            if self.dry_run:
                print(f"[DRY RUN] Would update object {existing_object.id} with data: {mapped_data}")
            else:
                mapped_data['id'] = existing_object.id
                update_function = self.get_nested_function(api_client, update_function_path)
                update_function([mapped_data])
                return existing_object.id
        else:
            if self.dry_run:
                print(f"[DRY RUN] Would create new object {mapped_data['name']}: {mapped_data}")
            else:
                create_function = self.get_nested_function(api_client, create_function_path)
                new_object = create_function(mapped_data)
                return new_object.id

def main():
    parser = argparse.ArgumentParser(description='Data Transfer Tool')
    parser.add_argument('-f', '--file', required=True, help='YAML file to load configurations')
    parser.add_argument('--dry-run', action='store_true', help='Run in dry-run mode without making any changes')
    args = parser.parse_args()

    tool = DataTransferTool(args.file, args.dry_run)
    tool.initialize_sources()
    tool.process_mappings()

if __name__ == "__main__":
    main()
