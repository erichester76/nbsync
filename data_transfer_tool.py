#!/usr/bin/env python3

import yaml
import re
import argparse
from sources.api_source import APIDataSource
from sources.csv_source import CSVDataSource
from sources.xls_source import XLSDataSource
from sources.snmp_source import SNMPDataSource
from yamlinclude import YamlIncludeConstructor

YamlIncludeConstructor.add_to_loader_class(loader_class=yaml.FullLoader)

class DataTransferTool:
    def __init__(self, yaml_file):
        with open('config/clemson/api_definitions.yaml', 'r') as f:
            api_definitions = yaml.safe_load(f)

        with open(yaml_file, 'r') as file:
            main_file = yaml.load(file, Loader=yaml.FullLoader)

        self.config = {**api_definitions, **main_file}
        self.sources = {}
        self.mapped_data = {}

    def initialize_sources(self):
        for name, config in self.config['api_definitions'].items():
            source_type = config['type']
            if source_type == 'api':
                self.sources[name] = APIDataSource(config)
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
        for obj_type, obj_config in self.config['object_mappings'].items():
            source = self.sources[obj_config['source_api']]
            data = source.fetch_data()

            destination_api_client = self.sources[obj_config['destination_api']].client
            destination_endpoint = obj_config['destination_endpoint']

            for item in data:
                mapped_data = {}
                for dest_field, field_info in obj_config['mapping'].items():
                    source_value = item.get(field_info['source'])
                    transform = field_info.get('transform_function')
                    mapped_data[dest_field] = self.apply_transform_function(source_value, transform)

                if obj_type not in self.mapped_data:
                    self.mapped_data[obj_type] = {}
                self.mapped_data[obj_type].update(mapped_data)

                self.create_or_update(destination_api_client, destination_endpoint, mapped_data)

    def create_or_update(self, api_client, endpoint, data):
        api_method = getattr(api_client, endpoint)
        existing_obj = api_method.get(name=data['name'])
        if existing_obj:
            for key, value in data.items():
                if getattr(existing_obj, key) != value:
                    setattr(existing_obj, key, value)
            existing_obj.save()
        else:
            api_method.create(data)

def main():
    parser = argparse.ArgumentParser(description='Data Transfer Tool')
    parser.add_argument('-f', '--file', required=True, help='YAML file to load configurations')
    args = parser.parse_args()

    tool = DataTransferTool(args.file)
    tool.initialize_sources()
    tool.process_mappings()

if __name__ == "__main__":
    main()
