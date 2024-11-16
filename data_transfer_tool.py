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
import cProfile
import pstats
from utils.timer import Timer

# Register custom Jinja2 filters

def regex_replace(value, pattern, replacement):
   if value: 
      return re.sub(pattern, replacement, value)
  
# Custom slugify filter
def slugify(value):
    return re.sub(r'\W+', '-', value.lower())

def extract_item(value, key_name, identifier_key):
    """
    Extract a specific item from a list of dictionaries or objects based on an identifier key.
    value: the list of items (automatically passed by Jinja)
    key_name: the attribute name to extract (e.g., 'identifierValue')
    identifier_key: the attribute name to match against (e.g., 'SerialNumberTag')
    """
    if isinstance(value, list):
        for identifier in value:
            identifier_value = getattr(identifier, key_name, None)
            identifier_type = getattr(identifier.identifierType, 'key', None)
            if identifier_type == identifier_key:
                return identifier_value
    return None

def replace_map(value, filename):
    """
    Apply a series of regex replacements from a file to the value.
    Each line in the file should be in the format: pattern,replacement
    """
    #print(f"running replace map on {value} from map {filename}")
    try:
        with open(filename, 'r') as f:
            # Read the file line by line
            for line in f:
                # Split each line into pattern and replacement
                pattern, replacement = line.strip().split(',')
                # Apply the regex replacement
                value = re.sub(pattern, replacement, value)
        #print(f"after replace_map {value}")
        return value
    except Exception as e:
        print(f"Error in replace_map: {e}")
        return value  # Return the value unchanged in case of an error

    
# Create a new Jinja2 environment and add the filters
env = jinja2.Environment(loader=jinja2.FileSystemLoader('./'))
env.filters['regex_replace'] = regex_replace
env.filters['slugify'] = slugify
env.filters['extract_item'] = extract_item
env.filters['replace_map'] = replace_map

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

# Custom constructor to handle Jinja-like fields
def jinja_placeholder_constructor(loader, node):
    """This constructor will simply return the string for Jinja fields like '{{ }}'."""
    value = loader.construct_scalar(node)
    return value

env_var_pattern = re.compile(r'\$\{([^}^{]+)\}')
yaml.add_implicit_resolver('!envvar', env_var_pattern)
yaml.add_constructor('!envvar', env_var_constructor)


class DataTransferTool:
    def __init__(self, yaml_file, dry_run):
        # Read the YAML file line by line and build yaml_content until object_mappings
        yaml_content = []
        object_mappings = []

        with open(yaml_file, 'r') as file:
            yaml_content = file.read()

        #replace jinjas {{}} with <<>> so it wont parse them yet.
        yaml_content = yaml_content.replace('{{', '<<').replace('}}', '>>')

        # Substitute environment variables in the YAML content
        yaml_content = os.path.expandvars(yaml_content)

        # Load the YAML content (excluding object_mappings) into self.config
        self.config = yaml.load(yaml_content, Loader=yaml.FullLoader)

        # Keep the object_mappings section as a string (to be rendered later)
        self.raw_object_mappings = ''.join(object_mappings)

        # Store the dry_run flag
        self.dry_run = dry_run
        self.sources = {}
        self.mapped_data = {}
        self.DEBUG = 1
        self.lookup_cache = {}

    def initialize_sources(self):
        for name, config in self.config['api_definitions'].items():
            
            source_type = config['type']
            if source_type == 'api' or source_type == 'api-swagger':
                self.sources[name] = APIDataSource(name, config)
            elif source_type == 'csv':
                self.sources[name] = CSVDataSource(name, config)
            elif source_type == 'xls':
                self.sources[name] = XLSDataSource(config)
            elif source_type == 'snmp':
                self.sources[name] = SNMPDataSource(config)
            
            self.sources[name].authenticate()

    def resolve_nested_context(self, item):
        """Resolve nested attributes in an object using dot notation."""
        context = {}

        def get_nested_value(obj, attr_path):
            """Recursively get a nested value from an object or dict using dot notation."""
            attrs = attr_path.split('.')
            current_obj = obj
            try:
                for attr in attrs:
                    timer.start_timer(f"Resolve Nested Context {attrs} {attr}")
                    if isinstance(current_obj, dict):
                        current_obj = current_obj.get(attr)
                    else:
                        current_obj = getattr(current_obj, attr)
                    if current_obj is None:
                        break
                    timer.stop_timer(f"Resolve Nested Context {attrs} {attr}")
                return current_obj
            except AttributeError:
                return None

        # Build the context with dot notation support for nested attributes
        if isinstance(item, dict):
            for key in item:
                context[key] = get_nested_value(item, key)
        else:
            for attr in dir(item):
                try:
                    if attr.startswith('_'):
                        continue
                    context[attr] = get_nested_value(item, attr)
                except Exception as e:
                    continue

        return context

    def process_mappings(self):
        """Process the mappings defined in the object_mappings section of the YAML."""
                
        for obj_type, obj_config in self.config['object_mappings'].items():
            source = self.sources[obj_config['source_api']]

            for source_client in source.clients:
                source_api = obj_config.get('source_api')
                print(f"Fetching data from {source_api}...")
                
                timer.start_timer("Fetch Data")
                source_data = source.fetch_data(obj_config, source_client)
                timer.stop_timer("Fetch Data")

                destination_api = self.sources[obj_config['destination_api']]
                
                for destination_client in destination_api.clients:
                    create_function = obj_config.get('create_function')
                    update_function = obj_config.get('update_function')
                    find_function = obj_config.get('find_function')
                    mappings = obj_config['mapping']

                    for item in source_data:
                        # Prepare the context once per item
                        timer.start_timer("Resolve Nested Context")
                        context = self.resolve_nested_context(item)
                        timer.stop_timer("Resolve Nested Context")
                        # Render each source template for all mappings at once, only once per item
                        rendered_mappings = {}
                        for dest_field, field_info in mappings.items():
                            if 'source' in field_info:
                                source_template = field_info['source'].replace('<<', '{{').replace('>>', '}}')
                                template = env.from_string(source_template)
                                rendered_source_value = template.render(context)
                                rendered_mappings[dest_field] = rendered_source_value

                        # Now apply any transformations/actions to the rendered mappings
                        mapped_data = {}
                        exclude_object = False
                        for dest_field, rendered_source_value in rendered_mappings.items():
                            
                            exclude_patterns = mappings[dest_field].get('exclude',[])
                            if isinstance(exclude_patterns, list):
                                for pattern in exclude_patterns:
                                    if bool(re.match(pattern, rendered_mappings[dest_field])):
                                        exclude_object = True
                                        break
                            elif bool(re.match(exclude_patterns, rendered_mappings[dest_field])):
                                exclude_object = True
                            

                            if 'action' in mappings[dest_field]:
                                action = mappings[dest_field].get('action')
                                timer.start_timer("Apply Transforms")
                                rendered_source_value = self.apply_transform_function(rendered_source_value, action, obj_config, dest_field, mapped_data)
                                timer.stop_timer("Apply Transforms")
                            
                            mapped_data[dest_field] = rendered_source_value
  
                        if exclude_object:
                            print(f"Excluding object {rendered_mappings['name']} based on exclusion criteria.")
                        else:                            
                            #print(f'Mapped Data: {mapped_data}')
                            # Create or update the object in the destination
                            timer.start_timer("Create or Update")
                            self.create_or_update(destination_client, find_function, create_function, update_function, mapped_data)    
                            timer.stop_timer("Create or Update")

    def apply_transform_function(self, value, actions, obj_config, field_name, mapped_data):
        """Apply transformations using Jinja2 filters directly."""
        if value is None:
            return value
        
        if isinstance(actions, str):
            actions = [actions]
            
        for action in actions:
            #print(f'ACTION {action} for {value}')
            
            if 'regex_replace' in action:
                pattern, replacement = re.findall(r"regex_replace\('(.*?)',\s*'*(.*?)'*\)", action)[0]
                value = env.filters['regex_replace'](value, pattern, replacement)
            
            elif 'lookup_object' in action:
                matches = re.findall(r"lookup_object\('(.*?)',\s*'(.*?)',\s*'(.*?)'\)", action)
                if matches:
                    lookup_type, find_function_path, create_function_path = matches[0]
                    value = self.lookup_object(
                        value, lookup_type, find_function_path, create_function_path, 
                        obj_config
                    ).id

            elif 'include_object' in action:
                matches = re.findall(r"include_object\('(.*?)',\s*'(.*?)',\s*'(.*?)',\s*'(.*?)'\)", action)
                if matches:
                    reference_field, lookup_type, find_function_path, create_function_path = matches[0]
                    # Get the reference field value from mapped_data or item
                    sub_value = mapped_data.get(reference_field) or item.get(reference_field)
                    
                    if sub_value:
                        nested_obj = self.lookup_object(
                            sub_value, lookup_type, find_function_path, create_function_path, 
                            obj_config
                        )
                        # Instead of placing it in mapped_data, nest it within `value`
                        if isinstance(value, dict):
                            value[reference_field] = nested_obj.id
                        else:
                            value = {reference_field: nested_obj.id, field_name: value}
            
            #print(f'POST ACTION {action}: value now {value}')
        
        return value

    def get_nested_function(self, api_client, function_path):
        """Recursively get a function from the API client."""
        parts = function_path.split('.')
        func = api_client  # Start with the root client (e.g., pynetbox.NetBox())
        for part in parts:
            try:
                func = getattr(func, part)
            except AttributeError:
                raise AttributeError(f"Attribute '{part}' not found in API client at path '{function_path}'")
        if not callable(func):
            raise TypeError(f"Final attribute in path '{function_path}' is not callable.")
        return func

    
    
    def sanitize_data(self, data):
        """
        Sanitize the mapped_data to ensure all values are serializable.
        If any value is an object, extract its relevant attribute (e.g., 'id' or 'name').
        """
        sanitized_data = {}
        for key, value in data.items():
            if hasattr(value, 'id'):  # If it's an object with an 'id' attribute, use the 'id'
                sanitized_data[key] = value.id
            elif hasattr(value, 'name'):  # If it's an object with a 'name' attribute, use the 'name'
                sanitized_data[key] = value.name
            else:
                sanitized_data[key] = value  # Otherwise, use the value as is

        return sanitized_data

    def lookup_object(self, value, lookup_type, find_function_path, create_function_path, obj_config):
        """Perform API lookup or create an object on the server side."""
        
        cache_key = f"{lookup_type}:{value}"
        if cache_key in self.lookup_cache:
            #print(f"Found {cache_key} in cache.")
            return self.lookup_cache[cache_key]
        
        api_client = self.sources[obj_config['destination_api']].api
        find_function = self.get_nested_function(api_client, find_function_path)
        create_function = self.get_nested_function(api_client, create_function_path)
        
        filter_params = {lookup_type: value}

        # Try finding the object
        try:
            timer.start_timer(f"Find Object {lookup_type}")
            found_object = find_function(**filter_params)
            timer.stop_timer(f"Find Object {lookup_type}")

            if found_object:
                first_object = list(found_object)[0]
                self.lookup_cache[cache_key] = first_object
                return first_object
            
        except Exception as e:
            print(f"Error calling find_function: {str(e)}")

        # If not found, create the object
        try:
            
            create_data = {lookup_type: value, 'slug': re.sub(r'\W+', '-', value.lower())} #, **additional_data}
            if self.dry_run:
                print(f"[DRY RUN] Would create {lookup_type} object with data: {create_data}")
            else:
                print(f"Creating {create_function_path} object with data: {create_data}")
                timer.start_timer(f"Create Object {lookup_type}")
                created_object = create_function(create_data)
                timer.stop_timer(f"Create Object {lookup_type}")
                self.lookup_cache[cache_key] = created_object
                return created_object if hasattr(created_object, 'id') else None
            
        except Exception as e:
            print(f"Error calling create_function: {str(e)}")
            return None

    def normalize_types(self, data):
        if isinstance(data, dict):
            return {k: self.normalize_types(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.normalize_types(v) for v in data]
        elif isinstance(data, str):
            # Convert to int or float if the string represents a number
            try:
                return int(data)
            except ValueError:
                try:
                    return float(data)
                except ValueError:
                    return data
        else:
            return data
        
    def create_or_update(self, api_client, find_function_path, create_function_path, update_function_path, mapped_data):
        """Create or update objects in the destination API."""
        # Find function
        find_function = self.get_nested_function(api_client, find_function_path)
        # Automatically extract the first field from mapped_data as the key field
        key_field = list(mapped_data.keys())[0]
        if not mapped_data[key_field]: 
            return None
        
        filter_params = {key_field: mapped_data[key_field]}        
        try:
            found_object = find_function(**filter_params)
        except Exception as e:
            print(f"Error calling find_function: {str(e)}")
            raise

        if found_object:
            existing_object = list(found_object)[0]

            mapped_data['id'] = existing_object.id
            current_data = self.sanitize_data(existing_object.serialize())
            sanitized_mapped_data = self.sanitize_data(mapped_data)
            filtered_current_data = {key: current_data.get(key) for key in mapped_data}
            sanitized_mapped_data = self.sanitize_data(sanitized_mapped_data)
            # Check for changes in object to determine if we should update
            timer.start_timer(f"DeepDiff")
            differences = deepdiff.DeepDiff(filtered_current_data, self.normalize_types(sanitized_mapped_data), ignore_order=True, report_repetition=True, ignore_type_in_groups=[(int, str, float)])
            timer.stop_timer(f"DeepDiff")

            if differences:
                print(f"Differences found for {existing_object.name}: {differences}")
                if self.dry_run:
                    print(f"[DRY RUN] Would update object {existing_object.id} with data")
                else: 
                    print(f"Updating object {existing_object.id}:")
                    update_function = self.get_nested_function(api_client, update_function_path)
                    timer.start_timer(f"Update object")
                    update_function([sanitized_mapped_data])
                    timer.stop_timer(f"Update object")

            else:
                print(f"No changes detected for object {existing_object.name}, skipping update.")
            return existing_object.id
        
        else:
            if self.dry_run:
                print(f"[DRY RUN] Would create new object {mapped_data['name']}")
            else:
                print(f"Creating new object {mapped_data['name']}: {mapped_data}")
                create_function = self.get_nested_function(api_client, create_function_path)
                timer.start_timer(f"Create object")
                new_object = create_function(self.sanitize_data(mapped_data))
                timer.stopt_timer(f"Create object")
                print(f"Created New Object {mapped_data['name']} #{new_object.id}")
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
    timer = Timer()
    main()
    timer.show_timers()

    
