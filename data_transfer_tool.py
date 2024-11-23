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
from utils.timer import Timer
from utils.resolver import Resolver

# Custom Jinja2 filters
def regex_replace(value, pattern, replacement):
   if value: 
      return re.sub(pattern, replacement, value)
  
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

env_var_pattern = re.compile(r'\$\{([^}^{]+)\}')
yaml.add_implicit_resolver('!envvar', env_var_pattern)
yaml.add_constructor('!envvar', env_var_constructor)

class DataTransferTool:
    def __init__(self, yaml_file, dry_run, debug):
        # Read the YAML file line by line and build yaml_content until object_mappings
        yaml_content = []
        object_mappings = []

        with open(yaml_file, 'r') as file:
            yaml_content = file.read()

        #replace jinjas {{}} with <<>> so it wont parse them yet.
        yaml_content = yaml_content.replace('{{', '<<').replace('}}', '>>')
        yaml_content = yaml_content.replace('{%', '#<<')
        # Substitute environment variables in the YAML content
        yaml_content = os.path.expandvars(yaml_content)

        # Load the YAML content (excluding object_mappings) into self.config
        self.config = yaml.load(yaml_content, Loader=yaml.FullLoader)

        # Keep the object_mappings section as a string (to be rendered later)
        self.raw_object_mappings = ''.join(object_mappings)

        # Store the dry_run flag
        self.dry_run = dry_run
        self.debug = debug

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

    def extract_required_keys(self,template_string):
        """
        Extract keys referenced in a Jinja template.
        """
        key_pattern = r"{{[\s\(\[]*([\w\.]+)"
        return re.findall(key_pattern, template_string)

    def process_mappings(self):
        """Process the mappings defined in the object_mappings section of the YAML."""
                
        for obj_type, obj_config in self.config['object_mappings'].items():
            timer.start_timer(f"Total {obj_type} Runtime")
            source = self.sources[obj_config['source_api']]

            for source_client in source.clients:

                source_api = obj_config.get('source_api')

                timer.start_timer(f"Fetch Data {obj_type} {source_api}")
                if self.debug: print(f"Fetching {obj_type} from {source_api}...")
                source_data = source.fetch_data(obj_config, source_client)
                timer.stop_timer(f"Fetch Data {obj_type} {source_api}")

                destination_api = self.sources[obj_config['destination_api']]
                timer.start_timer(f"API Endpoint Processing Total {source_api}")
     
                mappings = obj_config['mapping']

                for item in source_data:
                    timer.start_timer(f"Per Object Timing {obj_type}")
                    rendered_mappings = {}
                    for dest_field, field_info in mappings.items():
                        if 'source' in field_info:
                            source_template = field_info['source'].replace('#<<', '{%')
                            source_template = field_info['source'].replace('<<', '{{').replace('>>', '}}')
                            required_keys=self.extract_required_keys(source_template)
                            timer.start_timer(f"Extract Required Keys {required_keys}")
                            resolver = Resolver(item, required_keys=required_keys)
                            timer.stop_timer(f"Extract Required Keys {required_keys}")

                            # Debug: Ensure the source template is valid
                            template = env.from_string(source_template)
                            timer.start_timer("Render Source Template")
                            try:
                                rendered_source_value = template.render(resolver)
                            except Exception as e:
                                print(f"Error during rendering: {e}")
                                raise

                            timer.stop_timer("Render Source Template")
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
                            
                            if 'action' in mappings[dest_field] and not exclude_object:
                                action = mappings[dest_field].get('action')
                                timer.start_timer("Apply Transforms")
                                rendered_source_value = self.apply_transform_function(rendered_source_value, action, obj_config, dest_field, mapped_data)
                                timer.stop_timer("Apply Transforms")
                            
                            mapped_data[dest_field] = rendered_source_value
                    
                    if 'exclude' in rendered_source_value:
                        continue
                    
                    if exclude_object:
                        if self.debug: print(f"Excluding object {rendered_mappings['name']} based on exclusion criteria.")
                    else:                            
                        # Create or update the object in the destination
                        for destination_client in destination_api.clients:
                            create_function = obj_config.get('create_function')
                            update_function = obj_config.get('update_function')
                            find_function = obj_config.get('find_function')
                            timer.start_timer(f"Create or Update {obj_type}")
                            self.create_or_update(destination_client, find_function, create_function, update_function, mapped_data)    
                            timer.stop_timer(f"Create or Update {obj_type}")

                    timer.stop_timer(f"Per Object Timing {obj_type}")
                        
                timer.stop_timer(f"API Endpoint Processing Total {source_api}")
                #timer.show_timers()

            timer.stop_timer(f"Total {obj_type} Runtime")
            timer.show_timers()

    def apply_transform_function(self, value, actions, obj_config, field_name, mapped_data):
        """Apply transformations using Jinja2 filters directly."""
        if value is None:
            return value

        if isinstance(actions, str):
            actions = [actions]

        for action in actions:
            if "exclude" in action:
                if value in action:
                    return 'exclude'
            elif 'regex_replace' in action:
                pattern, replacement = re.findall(r"regex_replace\('(.*?)',\s*'*(.*?)'*\)", action)[0]
                value = env.filters['regex_replace'](value, pattern, replacement)

            elif 'lookup_object' in action:
                matches = re.findall(r"lookup_object\('(.*?)',\s*'(.*?)',\s*'(.*?)'\)", action)
                if matches:
                    lookup_type, find_function_path, create_function_path = matches[0]

                    # Extract additional fields from actions (if any)
                    additional_fields = []
                    for sub_action in actions:

                        if isinstance(sub_action, dict) and "append" in sub_action:
                            field, template = sub_action["append"]
                            field_value = self.render_template(template, obj_config)
                            additional_fields.append({"field": field, "value": field_value})

                    value = self.lookup_object(
                        value, lookup_type, find_function_path, create_function_path,
                        obj_config, additional_fields
                    ).id

            elif 'include_object' in action:
                matches = re.findall(r"include_object\('(.*?)',\s*'(.*?)',\s*'(.*?)',\s*'(.*?)'\)", action)
                if matches:
                    reference_field, lookup_type, find_function_path, create_function_path = matches[0]
                    # Get the reference field value from mapped_data or item
                    sub_value = mapped_data.get(reference_field) or obj_config.get(reference_field)

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

    def lookup_object(self, value, lookup_type, find_function_path, create_function_path, obj_config, additional_fields=None):
        """Perform API lookup or create an object on the server side with support for additional fields."""
        additional_fields = additional_fields or []

        cache_key = f"{lookup_type}:{value}"
        if cache_key in self.lookup_cache:
            return self.lookup_cache[cache_key]

        api_client = self.sources[obj_config['destination_api']].api
        find_function = self.get_nested_function(api_client, find_function_path)
        create_function = self.get_nested_function(api_client, create_function_path)

        # Prepare filter parameters for lookup
        filter_params = {lookup_type: value}
        for field_info in additional_fields:
            filter_params[field_info["field"]] = field_info["value"]

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

        # If not found, prepare data for creation
        try:
            create_data = {lookup_type: value, 'slug': re.sub(r'\W+', '-', value.lower())}
            for field_info in additional_fields:
                create_data[field_info["field"]] = field_info["value"]

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
            if data.lower() in ['true', 'false']:
               return data.lower() == 'true'
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
        # Automatically extract the first two fields from mapped_data as key fields
        key_fields = list(mapped_data.keys())[:2]

        filter_params = {}
        for key_field in key_fields:
            value = mapped_data[key_field]
            if value is None:
                return None
            # Append '_id' to the key if the value is a number
            if isinstance(value, (int)):
                key_field = f"{key_field}_id"
            filter_params[key_field] = value
        
        # Attempt to find the object
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
                if self.debug: print(f"Differences found for {existing_object.name}: {differences}")
                if self.dry_run:
                    print(f"[DRY RUN] Would update object {existing_object.id} with data")
                else: 
                    if self.debug: print(f"Updating object {existing_object.id}:")
                    update_function = self.get_nested_function(api_client, update_function_path)
                    timer.start_timer(f"Update object")
                    update_function([sanitized_mapped_data])
                    timer.stop_timer(f"Update object")

            else:
                if self.debug: print(f"No changes detected for object {existing_object.name}, skipping update.")
            return existing_object.id
        
        else:
            if self.dry_run:
                print(f"[DRY RUN] Would create new object {mapped_data['name']}")
            else:
                if self.debug: print(f"Creating new object {mapped_data['name']}: {mapped_data}")
                create_function = self.get_nested_function(api_client, create_function_path)
                timer.start_timer(f"Create object")
                new_object = create_function(self.sanitize_data(mapped_data))
                timer.stop_timer(f"Create object")
                if self.debug: print(f"Created New Object {mapped_data['name']} #{new_object.id}")
                return new_object.id

def main():
    parser = argparse.ArgumentParser(description='Data Transfer Tool')
    parser.add_argument('-f', '--file', required=True, help='YAML file to load configurations')
    parser.add_argument('--dry-run', action='store_true', help='Run in dry-run mode without making any changes')
    parser.add_argument('-d','--debug', action='store_true', help='enable debug')
    args = parser.parse_args()
    debug=args.debug
    tool = DataTransferTool(args.file, args.dry_run, args.debug)
    tool.initialize_sources()
    tool.process_mappings()

if __name__ == "__main__":
    timer = Timer(True)
    timer.start_timer(f"Total Runtime")
    main()
    timer.stop_timer(f"Total Runtime")
    timer.show_timers()


    
