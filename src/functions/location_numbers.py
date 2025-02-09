from restack_ai.function import function, log
from pydantic import BaseModel
import random
from typing import List

class LocationParams(BaseModel):
    lat: float
    lng: float

class LocationResponse(BaseModel):
    numbers: List[int]

@function.defn()
async def get_location_numbers(params: LocationParams) -> LocationResponse:
    try:
        # Generate 3 random numbers for this location
        random_numbers = [random.randint(1, 100) for _ in range(3)]
        return LocationResponse(numbers=random_numbers)
    except Exception as e:
        log.error("location_numbers function failed", error=e)
        raise e