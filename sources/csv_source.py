import csv
import os
from sources.base import DataSource

class CSVDataSource(DataSource):
    def __init__(self, name, config):
        """
        Initialize the CSV data source.
        """
        super().__init__(config)
        self.name = name
        self.config = config
        self.clients = []  # Just for consistency with other sources

    def authenticate(self):
        """
        Authenticate for CSV files means checking if the files exist and are readable.
        """
        file_paths = self.config['source_mapping']['file_path']
        for file_path in file_paths:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"CSV file not found: {file_path}")
            if not os.access(file_path, os.R_OK):
                raise PermissionError(f"CSV file is not readable: {file_path}")
        print(f"CSV files found and readable for {self.name}.")

    def fetch_data(self, obj_config, _):
        """
        Fetch data from the CSV file using the provided file path and delimiter.
        Since there's no API client, we ignore the second parameter.
        """
        # Retrieve file path and delimiter from source_mapping
        file_paths = obj_config['source_mapping']['file_path']
        delimiter = obj_config['source_mapping'].get('delimiter', ',')

        all_data = []

        # Iterate over multiple files
        for file_path in file_paths:
            with open(file_path, mode='r') as file:
                reader = csv.DictReader(file, delimiter=delimiter)

                # Process each row in the CSV and map fields according to YAML mapping
                for row in reader:
                    obj_data = {}
                    for dest_field, field_info in obj_config['mapping'].items():
                        source_field = field_info['source']
                        obj_data[dest_field] = row.get(source_field)
                    all_data.append(obj_data)

        return all_data
