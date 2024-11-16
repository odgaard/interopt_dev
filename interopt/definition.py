from pydantic import BaseModel
from interopt.search_space import SearchSpace

# Redefine ProblemDefinition with Pydantic
class ProblemDefinition(BaseModel):
    name: str
    search_space: SearchSpace