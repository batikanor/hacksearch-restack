from restack_ai.function import function, log
from pydantic import BaseModel
from typing import List, Optional
import aiohttp
import os
from datetime import datetime, timedelta

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

async def search_hackathons(lat: float, lng: float) -> List[dict]:
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    if not tavily_api_key:
        log.error("TAVILY_API_KEY not found in environment variables")
        return []

    # Calculate date range for last 4 weeks
    end_date = datetime.now()
    start_date = end_date - timedelta(weeks=4)
    date_range = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"

    # Construct search query with more natural language
    search_query = f"hackathon events competitions programming coding near {lat},{lng} happening after {start_date.strftime('%Y-%m-%d')}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_api_key,
                    "query": search_query,
                    "search_depth": "advanced",
                    # Removed the include_domains restriction
                    "max_results": 8,  # Increased results since we're searching more broadly
                    "sort_by": "relevance"  # Ensure most relevant results come first
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("results", [])
                else:
                    log.error(f"Tavily API request failed with status {response.status}")
                    return []
        except Exception as e:
            log.error(f"Error calling Tavily API: {e}")
            return []

@function.defn()
async def get_location_numbers(params: LocationParams) -> LocationResponse:
    try:
        search_results = await search_hackathons(params.lat, params.lng)
        
        hackathons = []
        for result in search_results:
            # Extract relevant information from search results
            hackathons.append(
                HackathonInfo(
                    name=result.get("title", "Unnamed Hackathon"),
                    description=result.get("snippet", "No description available"),
                    location=f"Near {params.lat:.2f}, {params.lng:.2f}",
                    date=result.get("published_date", None)
                )
            )

        return LocationResponse(hackathons=hackathons)
    except Exception as e:
        log.error("location_numbers function failed", error=e)
        return LocationResponse(hackathons=[])