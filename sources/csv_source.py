import os
import csv
from sources.base import DataSource

class CSVDataSource(DataSource):
    def authenticate(self):
        pass

    def fetch_data(self, api_mapping):
        """
        Fetch data from multiple CSV files based on the provided YAML configuration.
        
        :param api_mapping: Mapping that defines the source and how to fetch the data.
        :return: Retrieved data in a structured format.
        """
        all_data = []
        
        # Retrieve file paths and delimiter from source_mapping
        file_paths = api_mapping['source_mapping']['file_path']
        delimiter = api_mapping['source_mapping'].get('delimiter', ',')  # Default to comma

        # Read each CSV file
        for file_path in file_paths:
            with open(file_path, mode='r') as file:
                reader = csv.DictReader(file, delimiter=delimiter)
                for row in reader:
                    row_data = {}

                    # Perform dynamic field mapping from CSV columns to destination fields
                    for dest_field, field_info in api_mapping['mapping'].items():
                        source_field = field_info['source']
                        row_data[dest_field] = row.get(source_field)  # Map CSV field to destination field

                    all_data.append(row_data)

        return all_data
