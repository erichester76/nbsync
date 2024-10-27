
import pandas as pd
from sources.base import DataSource

class XLSDataSource(DataSource):
    def fetch_data(self):
        all_data = []
        for source_file in self.config['source_files']:  # Iterate through multiple Excel files
            df = pd.read_excel(source_file, sheet_name=self.config.get('sheet_name', 0))
            all_data.extend(df.to_dict(orient='records'))
        return all_data
