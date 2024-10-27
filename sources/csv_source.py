
import csv
from sources.base import DataSource

class CSVDataSource(DataSource):
    def fetch_data(self):
        all_data = []
        for source_file in self.config['source_files']:  # Iterate through multiple files
            with open(source_file, mode='r') as file:
                reader = csv.DictReader(file)
                all_data.extend([row for row in reader])
        return all_data
