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
    
    # Get approximate location name using reverse geocoding
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=10",
                headers={'User-Agent': 'HackathonFinder/1.0'}
            ) as response:
                if response.status == 200:
                    location_data = await response.json()
                    address = location_data.get('address', {})
                    city = address.get('city') or address.get('town') or address.get('village')
                    state = address.get('state')
                    country = address.get('country')
                    
                    # Build location parts
                    location_parts = [p for p in [city, state, country] if p]
                    location_string = ", ".join(location_parts)
                    search_locations = [
                        f'"{p}"' for p in location_parts if p
                    ]
                else:
                    location_string = f"{lat:.2f}, {lng:.2f}"
                    search_locations = [location_string]
        except Exception as e:
            log.error(f"Error getting location name: {e}")
            location_string = f"{lat:.2f}, {lng:.2f}"
            search_locations = [location_string]

    # Simpler search query focusing on event types and location
    search_query = (
        f'("hackathon" OR "tech event" OR "coding competition" OR "developer conference" OR "tech conference") '
        f'AND ({" OR ".join(search_locations)}) '
        f'AND (venue OR location OR event)'
    )
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_api_key,
                    "query": search_query,
                    "search_depth": "advanced",
                    "max_results": 20,  # Increased for more results
                    "sort_by": "relevance",
                    "include_raw_content": True
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])
                    
                    # Basic filtering to ensure location relevance and individual events
                    filtered_results = []
                    location_terms = set(location_string.lower().split(", "))
                    
                    for result in results:
                        content = (
                            result.get("title", "").lower() + " " +
                            result.get("snippet", "").lower() + " " +
                            result.get("raw_content", "").lower()
                        )
                        
                        # Simpler filtering criteria
                        location_match = any(term in content for term in location_terms)
                        is_specific_event = not any(generic in result.get("title", "").lower() for generic in [
                            "upcoming hackathons", "hackathon list", "events near",
                            "find hackathons", "hackathon calendar"
                        ])
                        
                        if location_match and is_specific_event:
                            # Clean up the title
                            title = result.get("title", "")
                            if ":" in title:
                                title = title.split(":", 1)[1].strip()
                            if "|" in title:
                                title = title.split("|", 1)[0].strip()
                            
                            result["title"] = title
                            filtered_results.append(result)
                    
                    return filtered_results[:10]  # Return up to 10 results
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