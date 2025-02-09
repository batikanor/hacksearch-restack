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
                    
                    location_parts = [p for p in [city, state, country] if p]
                    location_string = ", ".join(location_parts)
                    search_locations = [f'"{p}"' for p in location_parts if p]
                    log.info(f"Location resolved to: {location_string}")
                else:
                    location_string = f"{lat:.2f}, {lng:.2f}"
                    search_locations = [location_string]
                    log.warning(f"Could not resolve location, using coordinates: {location_string}")
        except Exception as e:
            log.error(f"Error getting location name: {e}")
            location_string = f"{lat:.2f}, {lng:.2f}"
            search_locations = [location_string]

    # Improved search query with more specific terms and date context
    current_year = datetime.now().year
    search_query = (
        f'("hackathon" OR "coding competition" OR "tech conference" OR "developer event") '
        f'AND ({" OR ".join(search_locations)}) '
        f'AND (("{current_year}" OR "{current_year + 1}") OR "upcoming" OR "scheduled") '
        f'AND ("registration open" OR "register now" OR "sign up") '
        f'-"past" -"completed" -"ended" -"archive"'
    )
    log.info(f"Using enhanced search query: {search_query}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_api_key,
                    "query": search_query,
                    "search_depth": "advanced",
                    "max_results": 20,
                    "sort_by": "relevance",
                    "include_raw_content": True
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])
                    log.info(f"Initial search returned {len(results)} results")
                    
                    filtered_results = []
                    location_terms = set(location_string.lower().split(", "))
                    
                    for result in results:
                        # Safely get content fields with fallbacks
                        title = result.get("title", "").lower() or ""
                        snippet = result.get("snippet", "").lower() or ""
                        raw_content = result.get("raw_content", "").lower() or ""
                        
                        # Combine all content for analysis
                        content = f"{title} {snippet} {raw_content}"
                        
                        log.info(f"Processing result: {result.get('title', '')}")
                        log.debug(f"Content length: {len(content)} chars")
                        
                        # Enhanced filtering criteria
                        location_match = any(term.lower() in content for term in location_terms)
                        
                        # Check for date indicators
                        has_date = any(str(year) in content for year in range(current_year, current_year + 2))
                        is_upcoming = "upcoming" in content or "scheduled" in content
                        
                        # Check if it's a specific event
                        is_specific_event = not any(generic in title for generic in [
                            "upcoming hackathons", "hackathon list", "events near",
                            "find hackathons", "hackathon calendar", "all events"
                        ])
                        
                        # Check for registration indicators
                        has_registration = any(term in content for term in [
                            "register now", "registration open", "sign up",
                            "join now", "participate", "apply now"
                        ])
                        
                        if location_match and is_specific_event and (has_date or is_upcoming) and has_registration:
                            # Clean up the title
                            clean_title = result.get("title", "")
                            for separator in [":", "|", "-", "–"]:
                                if separator in clean_title:
                                    clean_title = clean_title.split(separator)[0].strip()
                            
                            result["title"] = clean_title
                            filtered_results.append(result)
                            log.info(f"Accepted result: {clean_title}")
                            log.debug(f"Match criteria - Location: {location_match}, Date: {has_date}, "
                                    f"Registration: {has_registration}")
                        else:
                            log.debug(
                                f"Filtered out: {result.get('title', '')} - "
                                f"Location match: {location_match}, "
                                f"Specific event: {is_specific_event}, "
                                f"Has date: {has_date}, "
                                f"Has registration: {has_registration}"
                            )
                    
                    final_results = filtered_results[:10]
                    log.info(
                        f"Filtering complete: {len(results)} initial results -> "
                        f"{len(filtered_results)} filtered -> {len(final_results)} final results"
                    )
                    return final_results
                else:
                    log.error(f"Tavily API request failed with status {response.status}")
                    return []
        except Exception as e:
            log.error(f"Error calling Tavily API: {str(e)}")
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