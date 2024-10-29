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
        env = jinja2.Environment(loader=jinja2.FileSystemLoader('./'))
        template = env.get_template(yaml_file)
        rendered_yaml = template.render(os.environ)
        self.config = yaml.load(rendered_yaml, Loader=yaml.FullLoader)
        self.dry_run = dry_run  # Store the dry_run flag
        self.sources = {}
        self.mapped_data = {}
        self.DEBUG = 0


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
    
    def get_nested_attribute(self, obj, attr_paths, default=None):
        """
        This function retrieves the value of a nested attribute from an object.
        It now supports handling a list of attribute paths and concatenating them.
        """
        if isinstance(attr_paths, list):
            # If we have multiple attribute paths, we will concatenate their values
            values = []
            for attr_path in attr_paths:
                try:
                    attrs = attr_path.split('.')
                    value = obj
                    for attr in attrs:
                        if '[' in attr and ']' in attr:  # Handle array indexing
                            attr_name, index = attr.split('[')
                            index = int(index[:-1])
                            value = getattr(value, attr_name)[index]
                        else:
                            value = getattr(value, attr)
                    values.append(str(value))  # Convert to string for concatenation
                except (AttributeError, IndexError):
                    values.append(str(default))  # Append default value if any error occurs
            return ''.join(values)  # Concatenate all values
        else:
            # Handle the single attribute path (original logic)
            try:
                attrs = attr_paths.split('.')
                value = obj
                for attr in attrs:
                    if '[' in attr and ']' in attr:  # Handle array indexing
                        attr_name, index = attr.split('[')
                        index = int(index[:-1])
                        value = getattr(value, attr_name)[index]
                    else:
                        value = getattr(value, attr)
                return value
            except (AttributeError, IndexError):
                return default

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

    def get_included_fields_data(self, obj_config, field_name, item):
        """Retrieve additional fields to be included in the create/update operation."""
        included_data = {}
        included_fields = obj_config['mapping'].get(field_name, {}).get('included_fields', [])

        for field_info in included_fields:
            field = field_info['field']
            key = field_info.get('key', 'id')
            transform = field_info.get('transform_function')
            create_if_missing = field_info.get('create_if_missing', False)

            # Handle dictionary-like data sources
            if isinstance(item, dict):
                field_value = item.get(field)
            else:
                # Handle object-like data sources, retrieve nested attributes
                field_value = self.get_nested_attribute(item, field, None)

            # Handle creation or transformation of missing fields
            if field_value is None and create_if_missing:
                field_value = self.apply_transform_function(
                    self.get_nested_attribute(item, field_name, None),  # Pass the field_name to apply transform on
                    transform, obj_config, field_name, item
                )
            elif field_value is not None and transform:
                field_value = self.apply_transform_function(field_value, transform, obj_config, field_name, item)

            # Add the key-value pair if field_value is not None
            if field_value is not None:
                included_data[key] = field_value

        return included_data


    def apply_transform_function(self, value, transform, obj_config, field_name, item):
        """Apply a transformation to a value, based on the transform rule."""
        if value is None:
            return value  # Skip transformation if value is None

        if transform:
            # If transform is a string, convert it into a list with a single item
            if isinstance(transform, str):
                transform = [transform]

            # Apply all transformations in the list
            for trans in transform:
                if "regex_replace" in trans:
                    # Extract pattern and replacement from the transform rule
                    pattern, replacement = re.findall(r"regex_replace\('(.*?)',\s*'(.*?)'\)", trans)[0]
                    if self.DEBUG == 1: print(f'Applying regex: {value} {pattern} {replacement}')
                    value = re.sub(pattern, replacement, value)
            
                elif "change_case" in trans:
                    case_type = re.findall(r"change_case\('(.*)'\)", trans)[0]
                    if case_type == 'lower':
                        value = value.lower()
                    elif case_type == 'upper':
                        value = value.upper()
                    elif case_type == 'title':
                        value = value.title()
                    elif case_type == 'camel':
                        value = ''.join(word.capitalize() if i > 0 else word for i, word in enumerate(value.split()))
                    else:
                        raise ValueError(f"Unknown case transformation type: {case_type}")
                    
                elif "skip_if_field_equals" in trans:
                    field, expected_value = re.findall(r"skip_if_field_equals\('(.*)',\s*(.*)\)", trans)[0]
                    # Retrieve the actual value of the specified field
                    actual_value = self.get_nested_attribute(item, field, None)
                    if str(actual_value) == expected_value:
                        print(f"Skipping item because {field} equals {expected_value}")
                        return None  # Skip this item

                elif "slugify" in trans:
                    value = re.sub(r'\W+', '-', value.lower())
                    if self.DEBUG == 1: print(f'Slugifying value: {value}')
                
                elif 'expand' in trans:
                    expand_field = obj_config['mapping'].get(field_name, {}).get('expand_reference')
                    if expand_field:
                        value = {expand_field: value}
                        if self.DEBUG == 1: print(f"Expanding field {field_name} as reference: {value}")
                    else:
                        raise ValueError(f"Expand transform requires 'expand_reference' key in mapping for {field_name}")

                elif 'concat' in trans:
                    # Get the list of source fields to concatenate
                    fields_to_concat = obj_config['mapping'][field_name]['source']
                    delimiter = re.findall(r"concat\([\'\"](.*)[\'\"]\)", trans)[0]
                    if self.DEBUG == 1:print(f"Concating fields {field_name} : {value}")
                    # Get the values of the fields to concatenate
                    values = [self.get_nested_attribute(item, field, None) for field in fields_to_concat]
                    value = delimiter.join([str(v) for v in values if v])  # Join non-empty values
                
                elif "convert_to_type" in transform:
                    if isinstance(transform, list):
                        for trans in transform:
                            if "convert_to_type" in trans:
                                type_to_convert = re.findall(r"convert_to_type\('(.*?)'\)", trans)[0]
                                if type_to_convert == 'int':
                                    value = int(value)
                                elif type_to_convert == 'float':
                                    value = float(value)
                                    
                elif 'extract_by_type' in trans:
                     # Adjusted regex to make the second item optional
                    args = re.findall(r"extract_by_type\('(.*?)', '(.*?)'(?:, '(.*?)')?\)", trans)[0]
                    item_type = args[0]
                    item1 = args[1]
                    item2 = args[2] if len(args) > 2 and args[2] else None

                    # Process the value (assuming it's a list of dictionaries or objects)
                    if isinstance(value, list):
                        for entry in value:
                            # Use getattr() for object-like access and dict.get() for dictionary access
                            value1 = getattr(entry, item1, None) if hasattr(entry, item1) else entry.get(item1, None)
                            
                            if item_type == 'ipv4' and value1 and '.' in value1:
                                # If item2 (e.g., prefix) exists, return both as a list
                                if item2:
                                    value2 = getattr(entry, item2, None) if hasattr(entry, item2) else entry.get(item2, None)
                                    value = [value1, str(value2)] if value2 else [value1]
                                else:
                                    value = [value1]
                                break
                            elif item_type == 'ipv6' and value1 and ':' in value1:
                                if item2:
                                    value2 = getattr(entry, item2, None) if hasattr(entry, item2) else entry.get(item2, None)
                                    value = [value1, str(value2)] if value2 else [value1]
                                else:
                                    value = [value1]
                                break

                        
                elif "extract_identifier" in trans:
                    # Extract the identifier type (e.g., 'SerialNumberTag')
                    identifier_key = re.findall(r"extract_identifier\('(.*)'\)", trans)[0]
                    if isinstance(value, list):
                        for identifier in value:
                            identifier_value = getattr(identifier, 'identifierValue', None)
                            identifier_type = getattr(identifier.identifierType, 'key', None)
                            if identifier_type == identifier_key:
                                value = identifier_value
                                break
                        
                elif "lookup_object" in trans:
                    matches = re.findall(r"lookup_object\('(.*?)',\s*'(.*?)',\s*'(.*?)'\)", trans)
                    if not matches:
                        raise ValueError(
                            "Incorrect format for lookup_object transform. "
                            "Expected format: lookup_object('object_type', 'find_function', 'create_function')."
                        )
                    lookup_type, find_function_path, create_function_path = matches[0]
                    api_client = self.sources[obj_config['destination_api']].api
                    find_function = self.get_nested_function(api_client, find_function_path)
                    create_function = self.get_nested_function(api_client, create_function_path)
                    lookup_param_name = lookup_type
                    lookup_param_value = value
                    
                    filter_params = {lookup_param_name: lookup_param_value}
                    additional_data = {}
                    if 'included_fields' in obj_config['mapping'][field_name]:
                        additional_data = self.get_included_fields_data(obj_config, field_name, item)
                    
                        field_name_for_nesting = None
                        for included_field in obj_config['mapping'][field_name].get('included_fields', []):
                            field_name_for_nesting = included_field.get('field')
                            break
                        if self.DEBUG == 1: print(f"Added {additional_data} and {field_name_for_nesting}")
                        
                    for _, nested_value in additional_data.items():
                        nested_value = re.sub(r'\W+', '-', nested_value.lower())
                        filter_params[field_name_for_nesting] = nested_value
                        break
                    try:
                        found_object = find_function(**filter_params)
                    except Exception as e:
                        if self.DEBUG == 1: print(f"Error calling find_function: {str(e)}")
                        raise
                    
                    if found_object:
                        value = list(found_object)[0]
                    else:
                        if additional_data and field_name_for_nesting:
                            create_data = {lookup_param_name: lookup_param_value, 'slug': re.sub(r'\W+', '-', lookup_param_value.lower()), field_name_for_nesting: {**additional_data}}
                        else:
                            create_data = {lookup_param_name: lookup_param_value, 'slug': re.sub(r'\W+', '-', lookup_param_value.lower())}

                        print(f'Creating sub object: {create_data}')
                        created_object = create_function(create_data)
                        value = created_object.id if hasattr(created_object, 'id') else None
                    
        return value

    def process_mappings(self):
        """Process the mappings defined in the object_mappings section of the YAML."""
        for obj_type, obj_config in self.config['object_mappings'].items():
            source = self.sources[obj_config['source_api']]

            for source_client in source.clients:
                # Authenticate the source (move authentication here)
                source_api = obj_config.get('source_api')
                print(f"Authenticating source {source_api}...")
                source.authenticate()
                print(f"Fetching data from {source_api}...")
                source_data = source.fetch_data(obj_config, source_client)
                # Log the raw data fetched from the source
                destination_api = self.sources[obj_config['destination_api']]
                for destination_client in destination_api.clients:
                    create_function = obj_config.get('create_function')
                    update_function = obj_config.get('update_function')
                    find_function = obj_config.get('find_function')
                    for item in source_data:
                        mapped_data = {}
                        for dest_field, field_info in obj_config['mapping'].items():
                            source_value = None
                            
                            # Check if the source is a static string (applies to any data type)
                            if 'str:' in field_info['source']:
                                source_value = field_info['source'].split("str:")[1].strip().strip("'\"")                            
                            # Handle dictionary-like data sources (e.g., CSV)
                            elif isinstance(item, dict):
                                source_value = item.get(field_info['source'])
                                
                            # Handle object-like data sources (e.g., vim.VirtualMachine)
                            else:
                                if self.DEBUG == 1: print(f"Mapping source field {field_info['source']} to {dest_field}")
                                
                                # Check if the source is a list (for concatenation)
                                if isinstance(field_info['source'], list):
                                    # Handle concatenation by retrieving values from multiple fields
                                    source_value_list = [self.get_nested_attribute(item, src, None) for src in field_info['source']]
                                    source_value = ' '.join([str(v) for v in source_value_list if v])  # Join non-empty values with a space
                                else:
                                    source_value = self.get_nested_attribute(item, field_info['source'], None)

                            # Debugging: Log the value we're about to map
                            if self.DEBUG == 1: print(f"Mapped value for {dest_field}: {source_value}")

                            if ('transform_function' in field_info):
                                transform = field_info.get('transform_function')
                                if self.DEBUG == 1: print(f"Applying transform to field {dest_field} {source_value} {transform}")
                                mapped_data[dest_field] = self.apply_transform_function(source_value, transform, obj_config, dest_field, item)
                                if self.DEBUG == 1: print(f'Value is now: {mapped_data[dest_field]}')
                            else:
                                if self.DEBUG == 1: print(f"Directly mapping {source_value} to {dest_field}")
                                mapped_data[dest_field] = source_value
                                
                        object_id = self.create_or_update(destination_client, find_function, create_function, update_function, mapped_data)
                        if self.DEBUG == 1: print(f"Processed object with ID: {object_id}")

    def create_or_update(self, api_client, find_function_path, create_function_path, update_function_path, mapped_data):
        """Create or update objects in the destination API."""
       # Find function
        find_function = self.get_nested_function(api_client, find_function_path)
        
        # Extract key field (like in the transform logic)
        key_field = None
        filter_params = {}

        # Automatically extract the first field from mapped_data as the key field
        for field_name, field_value in mapped_data.items():
            if field_value is not None:
                key_field = field_name
                filter_params[key_field] = field_value
                break

        # Add additional fields to filter params based on 'included_fields', if present
        for dest_field, field_info in self.config['object_mappings'].get('mapping', {}).items():
            if 'included_fields' in field_info:
                additional_data = self.get_included_fields_data(self.config['object_mappings'], dest_field, mapped_data)
                filter_params.update(additional_data)

        if self.DEBUG == 1: print(f"Looking up {key_field} with filter params: {filter_params}")
        
        # Search for the object using the find function (e.g., dcim.devices.filter)
        try:
            found_object = find_function(**filter_params)
        except Exception as e:
            print(f"Error calling find_function: {str(e)}")
            raise
                
        # Check if the result set is not empty (using .first() if available)        
        if found_object:
            existing_object = list(found_object)[0]
            if self.dry_run:
                print(f"[DRY RUN] Would update object {existing_object.id} with data: {mapped_data}")
            else:
                mapped_data['id'] = existing_object.id
                current_data = self.sanitize_data(existing_object.serialize())
                filtered_current_data = {key: current_data.get(key) for key in mapped_data}
                sanitized_mapped_data = self.sanitize_data(mapped_data)
                
                #check for changes in object to determine if we should update
                differences = deepdiff.DeepDiff(filtered_current_data, sanitized_mapped_data, ignore_order=True, report_repetition=True, ignore_type_in_groups=[(int, float)])
                if differences:
                    print(f"Differences found for {existing_object.name}: {differences}")
                    print(f"Updating object {existing_object.name}: {sanitized_mapped_data}")
                    update_function = self.get_nested_function(api_client, update_function_path)
                    update_function([sanitized_mapped_data])
                else:
                    print(f"No changes detected for object {existing_object.name}, skipping update.")
                return existing_object.id
        else:
            if self.dry_run:
                print(f"[DRY RUN] Would create new object {mapped_data['name']}: {mapped_data}")
            else:
                print(f"Creating new object {mapped_data['name']}: {mapped_data}")
                create_function = self.get_nested_function(api_client, create_function_path)
                new_object = create_function(self.sanitize_data(mapped_data))
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
