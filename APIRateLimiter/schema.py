from pydantic import BaseModel

class RequestData(BaseModel):
    user_id: int
    endpoint: str

