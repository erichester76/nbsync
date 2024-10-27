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
    def __init__(self, yaml_file):
        
        env = jinja2.Environment(loader=jinja2.FileSystemLoader('./'))
        # Load the main YAML template
        template = env.get_template(yaml_file)
        # Render the template and parse as YAML
        rendered_yaml = template.render()
        self.config = yaml.safe_load(rendered_yaml)
                
        self.sources = {}
        self.mapped_data = {}


    def get_nested_function(self, obj, function_path):
        """
        Retrieve a nested function from an object (like API clients), given the function path.
        
        :param obj: The base object (e.g., an API client).
        :param function_path: The dot-separated path to the function (e.g., 'dcim.devices.filter').
        :return: The function object to be invoked.
        """
        func_parts = function_path.split('.')
        for part in func_parts:
            obj = getattr(obj, part, None)
            if obj is None:
                raise AttributeError(f"Function path '{function_path}' not found.")
        if not callable(obj):
            raise TypeError(f"'{function_path}' is not a callable function.")
        return obj
    
    def initialize_sources(self):
        for name, config in self.config['api_definitions'].items():
            source_type = config['type']
            if source_type == 'api':
                self.sources[name] = APIDataSource(name, config)
            elif source_type == 'csv':
                self.sources[name] = CSVDataSource(name,config)
            elif source_type == 'xls':
                self.sources[name] = XLSDataSource(config)
            elif source_type == 'snmp':
                self.sources[name] = SNMPDataSource(config)
            self.sources[name].authenticate()

    def apply_transform_function(self, value, transform):
        if transform:
            if "regex_replace" in transform:
                pattern, replacement = re.findall(r"regex_replace\('(.*)',\s*'(.*)'\)", transform)[0]
                value = re.sub(pattern, replacement, value)
            elif "lookup_field" in transform:
                section, field = re.findall(r"lookup_field\('(.*)',\s*'(.*)'\)", transform)[0]
                value = self.mapped_data.get(section, {}).get(field, value)
        return value

    def process_mappings(self):
        """
        Process the mappings defined in the object_mappings section of the YAML.
        Fetch data from the source API and send it to the destination API.
        """
        for obj_type, obj_config in self.config['object_mappings'].items():
            # Get the source API object (already authenticated)
            source = self.sources[obj_config['source_api']]

            # Iterate over all clients (API instances) for the source
            for source_client in source.clients:
                source_data = source.fetch_data(obj_config, source_client)

                # Access the destination API client
                destination_api = self.sources[obj_config['destination_api']]

                # Iterate over all clients (API instances) for the destination
                for destination_client in destination_api.clients:
                    # Get CRUD functions for the destination API (create and update)
                    create_function = obj_config.get('create_function')
                    update_function = obj_config.get('update_function')

                    # Get the find function for the destination API to check if objects exist
                    find_function = obj_config.get('find_function')

                    # Map and push the data to the destination API
                    for item in source_data:
                        mapped_data = {}

                        # Perform field mappings defined in the YAML
                        for dest_field, field_info in obj_config['mapping'].items():
                            source_value = item.get(field_info['source'])
                            transform = field_info.get('transform_function')
                            mapped_data[dest_field] = self.apply_transform_function(source_value, transform)

                        # Create or update the destination object
                        self.create_or_update(destination_client, find_function, create_function, update_function, mapped_data)

    def create_or_update(self, api_client, find_function_path, create_function_path, update_function_path, mapped_data):
        """
        Create or update objects in the destination API.
        
        :param api_client: The destination API client.
        :param find_function_path: Path to the function used to find existing objects.
        :param create_function_path: Path to the function used to create new objects.
        :param update_function_path: Path to the function used to update existing objects.
        :param mapped_data: The data to be created or updated.
        """
        # Find function
        find_function = self.get_nested_function(api_client, find_function_path)
        
        # Search for the object using the find function (e.g., dcim.devices.filter)
        found_objects = find_function(mapped_data)

        # Check if the result set is not empty (using .first() if available)
        existing_object = found_objects.first() if hasattr(found_objects, 'first') else None

        if existing_object:
            # Update existing object (use the object's ID if necessary)
            update_function = self.get_nested_function(api_client, update_function_path)
            update_function(existing_object.id, **mapped_data)

            # Print status message for update
            print(f"Updated object {existing_object.id} with data: {mapped_data}")
        else:
            # Create a new object if no match is found
            create_function = self.get_nested_function(api_client, create_function_path)
            new_object = create_function(mapped_data)

            # Print status message for create
            print(f"Created new object with data: {mapped_data}")

def main():
    parser = argparse.ArgumentParser(description='Data Transfer Tool')
    parser.add_argument('-f', '--file', required=True, help='YAML file to load configurations')
    args = parser.parse_args()

    tool = DataTransferTool(args.file)
    tool.initialize_sources()
    tool.process_mappings()

if __name__ == "__main__":
    main()
