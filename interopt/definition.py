from interopt.search_space import SearchSpace

class ProblemDefinition:
    def __init__(self, name, search_space: SearchSpace):
        self.name = name
        self.search_space = search_space

    def get_name(self):
        return self.name

    def get_search_space(self):
        return self.search_space