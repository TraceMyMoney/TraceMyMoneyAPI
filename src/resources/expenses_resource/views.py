from src.extensions import config
from src.common.base_resource import BaseResource
from src.helpers.authentication import token_required

class ExpensesResource(BaseResource):


    @token_required
    def get(self, **kwargs):
        pass
