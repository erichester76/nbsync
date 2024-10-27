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

    def initialize_sources(self):
        for name, config in self.config['api_definitions'].items():
            source_type = config['type']
            if source_type == 'api':
                self.sources[name] = APIDataSource(name, config)
            elif source_type == 'csv':
                self.sources[name] = CSVDataSource(config)
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
        Create or update objects in the destination API based on the YAML configuration.

        :param api_client: The authenticated client for the destination API.
        :param find_function_path: Path to the function that finds existing objects (from object_mappings).
        :param create_function_path: Path to the function that creates new objects (from object_mappings).
        :param update_function_path: Path to the function that updates existing objects (from object_mappings).
        :param mapped_data: The mapped data from the source API, ready for creation or update.
        """
        # Dynamically retrieve the find, create, and update functions from the API client
        find_function = self.get_nested_function(api_client, find_function_path)
        create_function = self.get_nested_function(api_client, create_function_path)
        update_function = self.get_nested_function(api_client, update_function_path)

        # Check if the find function exists and is callable
        if find_function:
            # Attempt to find existing objects using the find function
            existing_objects = find_function(name=mapped_data['name'])
        else:
            existing_objects = []

        if existing_objects:
            # If the object exists, update it
            if update_function:
                print(f"Updating object {mapped_data['name']} in {api_client}.")
                update_function(existing_objects[0].id, **mapped_data)
            else:
                print(f"No update function defined for {api_client}.")
        else:
            # If the object doesn't exist, create a new one
            if create_function:
                print(f"Creating new object {mapped_data['name']} in {api_client}.")
                create_function(**mapped_data)
            else:
                print(f"No create function defined for {api_client}.")


def main():
    parser = argparse.ArgumentParser(description='Data Transfer Tool')
    parser.add_argument('-f', '--file', required=True, help='YAML file to load configurations')
    args = parser.parse_args()

    tool = DataTransferTool(args.file)
    tool.initialize_sources()
    tool.process_mappings()

if __name__ == "__main__":
    main()
