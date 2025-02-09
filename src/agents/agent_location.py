from datetime import timedelta
from typing import List
from pydantic import BaseModel
from restack_ai.agent import agent, log
from src.functions.location_numbers import LocationParams, get_location_numbers, HackathonInfo

class LocationEvent(BaseModel):
    lat: float
    lng: float

class EndEvent(BaseModel):
    end: bool

@agent.defn()
class AgentLocation:
    def __init__(self) -> None:
        self.end = False
        self.locations = []

    @agent.event
    async def location(self, params: LocationEvent) -> List[HackathonInfo]:
        try:
            log.info(f"Received location event: lat={params.lat}, lng={params.lng}")
            
            response = await agent.step(
                get_location_numbers,
                LocationParams(lat=params.lat, lng=params.lng),
                start_to_close_timeout=timedelta(seconds=30),
            )
            
            self.locations.append({
                'lat': params.lat,
                'lng': params.lng,
                'hackathons': response.hackathons
            })
            
            log.info(f"Found hackathons for location: {response.hackathons}")
            return response.hackathons
            
        except Exception as e:
            log.error(f"Error during location event: {e}")
            raise e

    @agent.event
    async def end(self, end: EndEvent) -> EndEvent:
        log.info("Received end event")
        self.end = True
        return {"end": True}

    @agent.run
    async def run(self, input: dict):
        await agent.condition(lambda: self.end)
        return