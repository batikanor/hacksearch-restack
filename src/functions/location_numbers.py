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
                    county = address.get('county')
                    
                    # Build location parts with all available granularity
                    location_parts = [p for p in [city, county, state, country] if p]
                    location_string = ", ".join(location_parts)
                    search_locations = [
                        f'"{p}"' for p in location_parts if p
                    ]  # Quote each location part for exact matching
                else:
                    location_string = f"{lat:.2f}, {lng:.2f}"
                    search_locations = [location_string]
        except Exception as e:
            log.error(f"Error getting location name: {e}")
            location_string = f"{lat:.2f}, {lng:.2f}"
            search_locations = [location_string]

    # Construct more specific search query with exact location matching
    search_query = (
        f'("tech event" OR "hackathon" OR "coding competition" OR "developer conference") '
        f'AND ({" OR ".join(search_locations)}) '
        f'AND ("registration open" OR "tickets available") '
        f'AND (venue OR location OR "taking place at") '
        f'date:{start_date.strftime("%Y-%m-%d")} to {end_date.strftime("%Y-%m-%d")}'
    )
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_api_key,
                    "query": search_query,
                    "search_depth": "advanced",
                    "max_results": 15,  # Increased to have more candidates for filtering
                    "sort_by": "relevance",
                    "include_answer": True,
                    "include_raw_content": True
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])
                    
                    # More strict filtering of results
                    filtered_results = []
                    location_terms = set(location_string.lower().split(", "))
                    
                    for result in results:
                        content = (
                            result.get("title", "").lower() + " " +
                            result.get("snippet", "").lower() + " " +
                            result.get("raw_content", "").lower()
                        )
                        
                        # Stricter filtering criteria
                        location_match_count = sum(1 for term in location_terms if term in content)
                        has_specific_venue = any(phrase in content for phrase in [
                            "venue:", "location:", "address:", "held at", "taking place at",
                            "will be held", "hosted at", "convention center", "university"
                        ])
                        is_specific_event = not any(generic in result.get("title", "").lower() for generic in [
                            "upcoming hackathons", "hackathon list", "events near", "tech events",
                            "upcoming events", "find hackathons", "hackathon calendar"
                        ])
                        
                        # Only include results that match all criteria
                        if (location_match_count >= 2 and  # Must match at least 2 location terms
                            has_specific_venue and 
                            is_specific_event):
                            
                            # Clean up the title if needed
                            title = result.get("title", "")
                            if ":" in title:  # Often helps remove website names
                                title = title.split(":", 1)[1].strip()
                            
                            result["title"] = title
                            filtered_results.append(result)
                    
                    return filtered_results[:5]  # Return top 5 most relevant results
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