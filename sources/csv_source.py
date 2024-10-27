import csv
from sources.base import DataSource

class CSVDataSource(DataSource):
    def fetch_data(self, api_mapping):
        """
        Fetch data from CSV files based on the provided YAML configuration.
        
        :param api_mapping: Mapping that defines the source and how to fetch the data.
        :return: Retrieved data in a structured format.
        """
        all_data = []
        
        for source_file in api_mapping['source_mapping']['file_path']:  # Multiple file support
            delimiter = api_mapping['source_mapping'].get('delimiter', ',')  # Default to comma

            with open(source_file, mode='r') as file:
                reader = csv.DictReader(file, delimiter=delimiter)
                for row in reader:
                    row_data = {}

                    # Perform dynamic field mapping from CSV columns to destination fields
                    for dest_field, field_info in api_mapping['mapping'].items():
                        source_field = field_info['source']
                        row_data[dest_field] = row.get(source_field)  # Map CSV field to destination field

                    all_data.append(row_data)

        return all_data
