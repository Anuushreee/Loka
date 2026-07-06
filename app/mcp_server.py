from mcp.server.fastmcp import FastMCP

# Create a FastMCP server instance
mcp = FastMCP("Loka Travel Server")

@mcp.tool()
def get_flight_deals(origin: str, destination: str) -> str:
    """Get sample flight options and pricing between origin and destination.
    
    Args:
        origin: The departure city.
        destination: The arrival city.
    """
    return (
        f"Flights from {origin} to {destination}:\n"
        f"1. StarFlyer: $350 (Non-stop, 4h, Recommended)\n"
        f"2. CloudTransit: $280 (1 layover, 6.5h)\n"
        f"3. EcoJet: $210 (2 layovers, 9h)"
    )

@mcp.tool()
def get_hotel_recommendations(city: str, budget: str) -> str:
    """Get lodging and hotel recommendations in a city based on budget tier.
    
    Args:
        city: The destination city to find hotels in.
        budget: The budget tier, e.g., 'budget', 'mid-range', or 'luxury'.
    """
    budget_lower = budget.lower()
    if "luxury" in budget_lower:
        return (
            f"Luxury Hotels in {city}:\n"
            f"1. Grand Palace Hotel ($450/night, 5-star, rooftop pool)\n"
            f"2. The Meridian ($380/night, Boutique style, central location)"
        )
    elif "budget" in budget_lower:
        return (
            f"Budget Hotels in {city}:\n"
            f"1. Traveler's Inn ($75/night, clean, basic amenities)\n"
            f"2. Backpacker's Hostel ($40/night, shared dormitory, high rating)"
        )
    else:
        return (
            f"Mid-Range Hotels in {city}:\n"
            f"1. Urban Suites ($160/night, breakfast included, business friendly)\n"
            f"2. Comfort Stay ($120/night, family friendly, near subway)"
        )

@mcp.tool()
def get_local_attractions(city: str, interest: str) -> str:
    """Get points of interest or activities in a city based on user interest category.
    
    Args:
        city: The city to get recommendations for.
        interest: The interest category (culture, food, nature, shopping, etc.).
    """
    interest_lower = interest.lower()
    if "culture" in interest_lower or "history" in interest_lower:
        return f"Cultural spots in {city}:\n- Historic Museum of Art\n- Old Town Guided Walking Tour"
    elif "nature" in interest_lower or "outdoors" in interest_lower:
        return f"Outdoor activities in {city}:\n- Central Botanical Gardens\n- Skyline Mountain Hiking Trail"
    elif "food" in interest_lower or "dining" in interest_lower:
        return f"Culinary highlights in {city}:\n- Downtown Local Food Market\n- The Gourmet District (Michelin recommended)"
    else:
        return f"General highlights in {city}:\n- Main Square Clock Tower\n- Local Handicrafts Market"

if __name__ == "__main__":
    mcp.run()
