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

class DataTransferTool:
    def __init__(self, yaml_file, dry_run):
        env = jinja2.Environment(loader=jinja2.FileSystemLoader('./'))
        template = env.get_template(yaml_file)
        rendered_yaml = template.render()
        self.config = yaml.safe_load(rendered_yaml)
        self.dry_run = dry_run  # Store the dry_run flag
        self.sources = {}
        self.mapped_data = {}

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

    def get_included_fields_data(self, obj_config, field_name, item):
        """Retrieve additional fields to be included in the create/update operation."""
        included_data = {}
        included_fields = obj_config['mapping'].get(field_name, {}).get('included_fields', [])
        for field_info in included_fields:
            field = field_info['field']
            key = field_info.get('key', 'id')
            transform = field_info.get('transform_function')
            create_if_missing = field_info.get('create_if_missing', False)
            field_value = item.get(field)

            if field_value is None and create_if_missing:
                field_value = self.apply_transform_function(item.get(field_name), transform, obj_config, field_name, item)
            elif field_value is not None and transform:
                field_value = self.apply_transform_function(field_value, transform, obj_config, field_name, item)

            if field_value is not None:
                included_data[key] = field_value
        return included_data

    def apply_transform_function(self, value, transform, obj_config, field_name, item):
        """Apply a transformation to a value, based on the transform rule."""
        if value is None:
            return value  # Skip transformation if value is None

        if transform:
            if "regex_replace" in transform:
                pattern, replacement = re.findall(r"regex_replace\('(.*)',\s*'(.*)'\)", transform)[0]
                value = re.sub(pattern, replacement, value)
            elif transform == "slugify":
                value = re.sub(r'\W+', '-', value.lower())
            elif "lookup_object" in transform:
                matches = re.findall(r"lookup_object\('(.*)',\s*'(.*)',\s*'(.*)'\)", transform)
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
                    
                for _, nested_value in additional_data.items():
                    nested_value = re.sub(r'\W+', '-', nested_value.lower())
                    filter_params[field_name_for_nesting] = nested_value
                    break
                try:
                    found_object = find_function(**filter_params)
                except Exception as e:
                    print(f"Error calling find_function: {str(e)}")
                    raise
                
                if found_object:
                    value = list(found_object)[0]
                else:
                    if additional_data and field_name_for_nesting:
                        create_data = {lookup_param_name: lookup_param_value, 'slug': re.sub(r'\W+', '-', lookup_param_value.lower()), field_name_for_nesting: {**additional_data}}
                    else:
                        create_data = {lookup_param_name: lookup_param_value}

                    print(f'Creating object: {create_data}')
                    created_object = create_function(create_data)
                    value = created_object.id if hasattr(created_object, 'id') else None
                    
        return value

    def process_mappings(self):
        """Process the mappings defined in the object_mappings section of the YAML."""
        for obj_type, obj_config in self.config['object_mappings'].items():
            source = self.sources[obj_config['source_api']]
            for source_client in source.clients:
                source_data = source.fetch_data(obj_config, source_client)
                destination_api = self.sources[obj_config['destination_api']]
                for destination_client in destination_api.clients:
                    create_function = obj_config.get('create_function')
                    update_function = obj_config.get('update_function')
                    find_function = obj_config.get('find_function')
                    for item in source_data:
                        mapped_data = {}
                        for dest_field, field_info in obj_config['mapping'].items():
                            source_value = item.get(field_info['source'])
                            transform = field_info.get('transform_function')
                            mapped_data[dest_field] = self.apply_transform_function(source_value, transform, obj_config, dest_field, item)
                        object_id = self.create_or_update(destination_client, find_function, create_function, update_function, mapped_data)
                        print(f"Processed object with ID: {object_id}")

    def create_or_update(self, api_client, find_function_path, create_function_path, update_function_path, mapped_data):
        """Create or update objects in the destination API."""
        find_function = self.get_nested_function(api_client, find_function_path)
        found_objects = find_function(mapped_data)
        existing_object = found_objects.first() if hasattr(found_objects, 'first') else found_objects[0] if found_objects else None

        if existing_object:
            if self.dry_run:
                print(f"[DRY RUN] Would update object {existing_object.id} with data: {mapped_data}")
            else:
                print(f"Updating object {existing_object.id} with data: {mapped_data}")
                update_function = self.get_nested_function(api_client, update_function_path)
                update_function(existing_object.id, **self.sanitize_data(mapped_data))
            return existing_object.id
        else:
            if self.dry_run:
                print(f"[DRY RUN] Would create new object with data: {mapped_data}")
            else:
                print(f"Creating new object with data: {mapped_data}")
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
