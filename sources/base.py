
class DataSource:
    def __init__(self, config):
        self.config = config

    def authenticate(self):
        raise NotImplementedError("Subclasses should implement this method!")

    def fetch_data(self):
        raise NotImplementedError("Subclasses should implement this method!")
