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
        self.clients = []  # Initialize the clients list (this will hold file paths)

    def authenticate(self):
        """
        Authenticate for CSV files means checking if the files exist and are readable.
        Also, add the file paths to self.clients.
        """
        file_paths = self.config['source_mapping']['file_path']
        for file_path in file_paths:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"CSV file not found: {file_path}")
            if not os.access(file_path, os.R_OK):
                raise PermissionError(f"CSV file is not readable: {file_path}")
            
            # Add the file path to clients as a "client"
            self.clients.append(file_path)

        print(f"CSV files found and readable for {self.name}.")

    def fetch_data(self, obj_config, file_path):
        """
        Fetch raw data from the CSV file without applying any mapping.
        """
        # Retrieve delimiter from source_mapping (use self.config to access source_mapping)
        delimiter = self.config['source_mapping'].get('delimiter', ',')

        all_data = []

        # Open the file and read the CSV content
        with open(file_path, mode='r') as file:
            reader = csv.DictReader(file, delimiter=delimiter)

            # Collect raw rows without mapping
            for row in reader:
                all_data.append(row)

        return all_data