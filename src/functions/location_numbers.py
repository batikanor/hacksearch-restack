from restack_ai.function import function, log
from pydantic import BaseModel
from typing import List, Optional
import random

class HackathonInfo(BaseModel):
    name: str
    description: str
    location: Optional[str] = None
    date: Optional[str] = None

class LocationParams(BaseModel):
    lat: float
    lng: float

class LocationResponse(BaseModel):
    hackathons: List[HackathonInfo]

@function.defn()
async def get_location_numbers(params: LocationParams) -> LocationResponse:
    try:
        # Simulate getting hackathon data based on location
        # In a real implementation, this would call an AI service or API
        sample_hackathons = [
            HackathonInfo(
                name="TechCrunch Disrupt Hackathon",
                description="Join the world's largest hackathon focused on disruptive technologies",
                location=f"Near {params.lat:.2f}, {params.lng:.2f}",
                date="2024-06-15"
            ),
            HackathonInfo(
                name="Local Innovation Challenge",
                description="Community-driven hackathon focusing on local problems",
                location=None,
                date="2024-05-20"
            ),
            HackathonInfo(
                name="AI for Good Hackathon",
                description="Build AI solutions that make a positive impact on society",
                location=f"Virtual + Hybrid options available",
                date=None
            )
        ]
        return LocationResponse(hackathons=sample_hackathons)
    except Exception as e:
        log.error("location_numbers function failed", error=e)
        # Instead of raising, return empty hackathons list
        return LocationResponse(hackathons=[])