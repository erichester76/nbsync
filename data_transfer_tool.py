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

    
    def _render_template(self, template_str, context):
        """
        Render a Jinja2 template string with the given context.
        """
        try:
            template_str = template_str.replace('<<', '{{').replace('>>', '}}')
            required_keys=self.extract_required_keys(template_str)
            resolver = Resolver(context, required_keys=required_keys)
            template = env.from_string(template_str)
            rendered_template = template.render(resolver)
            return rendered_template
        except Exception as e:
            print(f"Error rendering template '{template_str}': {e}")
            return None
        
    def _render_nested_structure(self, structure, context):
        """
        Recursively render a nested structure (dict or list) with Jinja2 templates.
        """
        if isinstance(structure, dict):
            rendered = {}
            for key, value in structure.items():
                if isinstance(value, (dict, list)):
                    # Recursively render nested dicts or lists
                    rendered[key] = self._render_nested_structure(value, context)
                elif isinstance(value, str):
                    # Render the string template with the current context
                    rendered[key] = self._render_template(value, context)
                else:
                    # Pass non-template values through as-is
                    rendered[key] = value
            return rendered
        elif isinstance(structure, list):
            return [self._render_nested_structure(item, context) for item in structure]
        elif isinstance(structure, str):
            return self._render_template(structure, context)
        else:
            return structure


    def process_mappings(self):
        """Process the mappings defined in the object_mappings section of the YAML."""
        for obj_type, obj_config in self.config['object_mappings'].items():
            timer.start_timer(f"Total {obj_type} Runtime")
            source = self.sources[obj_config['source_api']]

            for source_client in source.clients:
                source_api = obj_config.get('source_api')
                destination_api = self.sources[obj_config['destination_api']]

                # Fetch root-level data
                timer.start_timer(f"Fetch Data {obj_type} {source_api}")
                if self.debug: print(f"Fetching {obj_type} from {source_api}...")
                source_data = source.fetch_data(obj_config, source_client)
                timer.stop_timer(f"Fetch Data {obj_type} {source_api}")

                # Process each root-level object
                for item in source_data:
                    self.process_single_mapping(obj_type, obj_config, destination_api, item)

            timer.stop_timer(f"Total {obj_type} Runtime")
            timer.show_timers()


    def process_single_mapping(self, obj_type, obj_config, destination_api, item, parent_id=None):
        """Process a single mapping including nested mappings."""
        timer.start_timer(f"Per Object Timing {obj_type}")

        # Ensure rendered_mappings includes parent_id
        rendered_mappings = {'parent_id': parent_id}
        mappings = obj_config.get('mapping', {})
        if not mappings:
            print(f"No mappings defined for {obj_type}. Skipping.")
            return
        # Separate nested_mappings from regular mappings
        nested_mappings = mappings.pop('nested_mappings', None)

        for dest_field, field_info in mappings.items():
            if field_info is None:
                print(f"Skipping field {dest_field} because field_info is None.")
                continue

            # Render the source template for the field
            if 'source' in field_info:
                try:
                    context = {**item}  # Base context is the item itself
                    context.update({'parent_id': parent_id}) 
                    rendered_mappings[dest_field] = self._render_template(
                        field_info['source'], context
                    )
                except Exception as e:
                    print(f"Error rendering field {dest_field}: {e}")
                    rendered_mappings[dest_field] = None

        # Process the mapped data
        mapped_data = {}
        exclude_object = False

        for dest_field, rendered_source_value in rendered_mappings.items():
            field_info = mappings.get(dest_field, {})
            if not field_info and 'parent_id' not in dest_field:
                print(f"Skipping field {dest_field} because its mapping is missing.")
                continue

            # Apply exclusion logic
            exclude_patterns = field_info.get('exclude', [])
            if isinstance(exclude_patterns, list):
                for pattern in exclude_patterns:
                    if bool(re.match(pattern, str(rendered_source_value))):
                        exclude_object = True
                        break
            elif bool(re.match(str(exclude_patterns), str(rendered_source_value))):
                exclude_object = True

            # Apply transformations
            if 'action' in field_info and not exclude_object:
                action = field_info.get('action')
                timer.start_timer("Apply Transforms")
                rendered_source_value = self.apply_transform_function(
                    rendered_source_value, action, obj_config, destination_api, dest_field, mapped_data, item
                )
                timer.stop_timer("Apply Transforms")
                if 'exclude_field' in str(rendered_source_value):
                    continue

            mapped_data[dest_field] = rendered_source_value

        # Skip excluded objects
        if exclude_object:
            if self.debug:
                print(f"Excluding object {rendered_mappings.get('name', '<unknown>')} based on exclusion criteria.")
            return

        # Create or update the object in the destination
        for destination_client in destination_api.clients:
            create_function = obj_config.get('create_function')
            update_function = obj_config.get('update_function')
            find_function = obj_config.get('find_function')
            timer.start_timer(f"Create or Update {obj_type}")
            self.create_or_update(destination_client, find_function, create_function, update_function, mapped_data)
            timer.stop_timer(f"Create or Update {obj_type}")

        # Process nested mappings explicitly
        if nested_mappings:
            for nested_obj_type, nested_obj_config in nested_mappings.items():
                print(f"Found Nested {nested_obj_type} mapping under {obj_type} Mapping.")

                # Use the parent API if destination_api is not explicitly defined'
                self._process_nested_mappings(nested_obj_type, nested_obj_config, item, parent_id, destination_api)


        timer.stop_timer(f"Per Object Timing {obj_type}")


    def _process_nested_mappings(self, nested_obj_type, nested_obj_config, item, parent_id, parent_destination_api):
        """Process nested mappings recursively."""
        nested_data = item.get(nested_obj_type, [])
        destination_api = nested_obj_config.get('destination_api', parent_destination_api)

        for nested_item in nested_data:
            self.process_single_mapping(nested_obj_type, nested_obj_config, destination_api, nested_item, parent_id)

  
    def apply_transform_function(self, value, actions, obj_config, destination_api, field_name, mapped_data, item):
        if value is None:
            return value

        if isinstance(actions, str):
            actions = [actions]

        additional_data = {}  # Store appended fields for lookup_object

        for action in actions:
        
            if "exclude" in action:
                if value in action:
                    #leave function and loop because we are skipping this field and all actions after this
                    return 'exclude_field'
                
            elif 'regex_replace' in action:
                pattern, replacement = re.findall(r"regex_replace\('(.*?)',\s*'*(.*?)'*\)", action)[0]
                value = env.filters['regex_replace'](str(value), pattern, replacement)
                
            elif 'listify' in action:
                if not isinstance(value, list):
                 value = [value]

            if isinstance(action, dict) and 'lookup_object' in action:
                lookup_config = action['lookup_object']
                lookup_field = lookup_config.get('field')
                find_function_path = lookup_config.get('find_function')
                create_function_path = lookup_config.get('create_function')
                append_fields = lookup_config.get('append', {})
                print(f"Append: {append_fields}")
                additional_data = self._render_nested_structure(append_fields, mapped_data)
                lookup_result = self.lookup_object(
                    value, lookup_field, find_function_path, create_function_path, destination_api,
                    obj_config, additional_data
                )
                if lookup_result is not None:
                    value = lookup_result.id
                else:
                    print(f"Warning: Lookup failed for {lookup_field} with value {value}")
            elif 'exclude' in action:
                # Handle `exclude`
                exclude_value = action['exclude']
                if value.startswith(exclude_value):
                    return None, []
                    
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

    def lookup_object(self, value, lookup_type, find_function_path, create_function_path, destination_api, obj_config, additional_fields=None):
        """Perform API lookup or create an object on the server side with support for additional fields."""
        additional_fields = additional_fields or []

        cache_key = f"{lookup_type}:{value}"
        if cache_key in self.lookup_cache:
            return self.lookup_cache[cache_key]

        api_client = destination_api.api
        find_function = self.get_nested_function(api_client, find_function_path)
        create_function = self.get_nested_function(api_client, create_function_path)
        # Validate lookup_type and value
        print("lookup_type={lookup_type}, value={value}")
        if not lookup_type or value is None:
            raise ValueError(f"Invalid lookup_type or value: lookup_type={lookup_type}, value={value}")

        filter_params = {lookup_type: value}        
        # Try finding the object
        try:
            timer.start_timer(f"Find Object {lookup_type}")
            found_object = find_function(**filter_params)
            timer.stop_timer(f"Find Object {lookup_type}")

            if found_object:
                first_object = list(found_object)[0]
                self.lookup_cache[cache_key] = first_object
                print(f"looked up {filter_params} and found {first_object.name}")
                return first_object

        except Exception as e:
            print(f"Error calling find_function: {str(e)}")

        # If not found, prepare data for creation
        try:
            create_data = {lookup_type: value}
            create_data.update(additional_fields)  # Include appended fields
            if 'slug' not in create_data:
                create_data['slug'] = re.sub(r'\W+', '-', value.lower())

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
                print(f"Differences found for {existing_object.name}: {differences}")
                if self.dry_run:
                    print(f"[DRY RUN] Would update object {existing_object.id} with data")
                else: 
                    print(f"Updating object {existing_object.name} {sanitized_mapped_data}:")
                    update_function = self.get_nested_function(api_client, update_function_path)
                    timer.start_timer(f"Update object")
                    update_function([sanitized_mapped_data])
                    timer.stop_timer(f"Update object")
                    print(f"Updated object {existing_object.name}:")


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
                timer.stop_timer(f"Create object")
                print(f"Created New Object {mapped_data['name']} #{new_object.id}")
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


    