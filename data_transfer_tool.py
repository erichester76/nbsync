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


    def get_nested_function(self, api_client, function_path):
        """
        Resolves a nested function path, such as 'dcim.device_types.filter', and returns the function.
        
        :param api_client: The API client to resolve the function from.
        :param function_path: The full function path (e.g., 'dcim.device_types.filter').
        :return: The resolved function.
        """
        parts = function_path.split('.')
        func = api_client

        # Resolve each part of the function path step by step
        for part in parts:
            func = getattr(func, part)
        
        if not callable(func):
            raise ValueError(f"{function_path} is not a valid callable function.")
        
        return func

    
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

    def lookup_device_type(self, value):
        """
        Lookup device type ID from the NetBox API based on the device type name.
        """
        # Assuming you have a NetBox API client instance already authenticated
        device_type_obj = self.sources['netbox'].api.dcim.device_types.get(name=value)
        
        if device_type_obj:
            return device_type_obj.id  # Return the device type ID
        else:
            raise ValueError(f"Device type '{value}' not found in NetBox.")

    def lookup_site(self, value):
        """
        Lookup site ID from the NetBox API based on the site name.
        """
        # Assuming you have a NetBox API client instance already authenticated
        site_obj = self.sources['netbox'].api.dcim.sites.get(name=value)
        
        if site_obj:
            return site_obj.id  # Return the site ID
        else:
            raise ValueError(f"Site '{value}' not found in NetBox.")
    
    def apply_transform_function(self, value, transform, obj_config, field_name, item):
        """
        Apply a transformation to a value, based on the transform rule provided in the YAML.
        
        :param value: The value from the source that needs transformation.
        :param transform: The transform rule (e.g., regex_replace, lookup_field, lookup_object).
        :param obj_config: The object configuration for the current data being processed.
        :return: Transformed value.
        """
        if transform:
            # Perform regex replace
            if "regex_replace" in transform:
                pattern, replacement = re.findall(r"regex_replace\('(.*)',\s*'(.*)'\)", transform)[0]
                value = re.sub(pattern, replacement, value)

            # Generic lookup using find_function and create_function passed directly in the transform
            elif "lookup_object" in transform:
                # Check if the correct format is being used in the transform
                matches = re.findall(r"lookup_object\('(.*)',\s*'(.*)',\s*'(.*)'\)", transform)
                if not matches:
                    raise ValueError(
                        "Incorrect format for lookup_object transform. "
                        "Expected format: lookup_object('object_type', 'find_function', 'create_function')."
                    )

                lookup_type, find_function_path, create_function_path = matches[0]

                # Retrieve the API client (assuming it's a destination API in this case)
                api_client = self.sources[obj_config['destination_api']].api

                # Resolve nested find_function and create_function paths (e.g., 'dcim.device_types.filter')
                find_function = self.get_nested_function(api_client, find_function_path)
                create_function = self.get_nested_function(api_client, create_function_path)

                # Build the RHS of the lookup call using the lookup_type as the key and value from the source field
                lookup_param_name = lookup_type  # The name of the parameter should match the lookup_type
                lookup_param_value = value  # The value passed in should be the current field's value from the source

                # Execute the find function with the dynamically built parameter
                print(f"Looking up in {find_function_path} via model = {lookup_param_value}")
                found_object = find_function({lookup_param_name: lookup_param_value})

                # Check if the object exists
                found_object = found_object.first() if hasattr(found_object, 'first') else None

                if found_object:
                    # If object exists, return its ID
                    value = found_object.id
                    print(f'Object found {found_object.name} {found_object.id}')
                    
                else:
                    print(f'Object not found {lookup_param_value}')
                    # If object does not exist, create it using the create_function
                    additional_data = {}
                    
                    if 'included_fields' in obj_config['mapping'].get(field_name, {}):
                        # Retrieve the included fields from the YAML configuration
                        additional_fields = obj_config['mapping'].get(field_name, {}).get('included_fields', [])
                        print(f'{self.mapped_data}')
                        
                        for field in additional_fields:
                            # Get the value of the additional field from the source data or the mapped data
                            field_value = item.get(field)
                            additional_data[field] = field_value
                            print(f"adding required field {field} {field_value}")


                    create_data = {lookup_param_name: lookup_param_value}
                    create_data.update(additional_data)  # Merge with the additional data
                    print(f"Creating new bject {field_name}")
                    created_object = create_function(create_data)
                    value = created_object.id

            return value


    def process_mappings(self):
        """
        Process the mappings defined in the object_mappings section of the YAML.
        Fetch data from the source CSV files and send it to the destination API.
        """
        for obj_type, obj_config in self.config['object_mappings'].items():
            # Get the source CSV object (already authenticated)
            source = self.sources[obj_config['source_api']]

            # Iterate over all file paths (treated as clients) for the source
            for file_path in source.clients:
                # Fetch data from the CSV file
                source_data = source.fetch_data(obj_config, file_path)

                # Access the destination API object
                destination_api = self.sources[obj_config['destination_api']]

                # Iterate over all clients (API instances) for the destination
                for destination_client in destination_api.clients:
                    # Get CRUD functions for the destination API (create, update, find)
                    create_function = obj_config.get('create_function')
                    update_function = obj_config.get('update_function')
                    find_function = obj_config.get('find_function')

                    # Map and push the data to the destination API
                    for item in source_data:
                        mapped_data = {}

                        # Perform field mappings defined in the YAML
                        for dest_field, field_info in obj_config['mapping'].items():
                            source_value = item.get(field_info['source'])
                            transform = field_info.get('transform_function')
                            mapped_data[dest_field] = self.apply_transform_function(source_value, transform, obj_config, dest_field, item)

                        # Create or update the destination object and return the ID
                        object_id = self.create_or_update(destination_api, find_function, create_function, update_function, mapped_data)
                        print(f"Processed object with ID: {object_id}")

    def create_or_update(self, api_client, find_function_path, create_function_path, update_function_path, mapped_data):
        """
        Create or update objects in the destination API.

        :param api_client: The destination API client.
        :param find_function_path: Path to the function used to find existing objects.
        :param create_function_path: Path to the function used to create new objects.
        :param update_function_path: Path to the function used to update existing objects.
        :param mapped_data: The data to be created or updated.
        :return: The ID of the created or updated object.
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
            return existing_object.id
        else:
            # Create a new object if no match is found
            create_function = self.get_nested_function(api_client, create_function_path)
            new_object = create_function(mapped_data)

            # Print status message for create
            print(f"Created new object with data: {mapped_data}")

            # Return the new object's ID
            return new_object.id

def main():
    parser = argparse.ArgumentParser(description='Data Transfer Tool')
    parser.add_argument('-f', '--file', required=True, help='YAML file to load configurations')
    args = parser.parse_args()

    tool = DataTransferTool(args.file)
    tool.initialize_sources()
    tool.process_mappings()

if __name__ == "__main__":
    main()
