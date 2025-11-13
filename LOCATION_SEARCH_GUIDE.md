# Location Search Guide - City & Country Support

## New Feature: Search by City or Country

You can now search for YouTube channels by **country code** OR **city name**!

## How to Use

### Run the tool:
```bash
python find_creators.py
```

### Enter location:
```
Enter location (country code or city, e.g., US, Miami - optional): Miami
```

## Examples

### Search by City:
```
Enter niche: fitness
Enter sub-niche: yoga
Enter location: Miami
```

**Finds:** Channels mentioning "Miami" in About page, video titles, or descriptions

### Search by Country:
```
Enter niche: tech reviews
Enter sub-niche: smartphones
Enter location: UK
```

**Finds:** Channels from the United Kingdom

### Search by Country Code:
```
Enter location: US
```

**Matches:** USA, United States, America, American

## Supported Locations

### Countries (by code or name):
- **USA** - US, USA, United States, America
- **UK** - UK, United Kingdom, Britain, England
- **Canada** - CA, Canada
- **Australia** - AU, Australia
- **India** - IN, India
- **Germany** - DE, Germany
- **France** - FR, France
- **Spain** - ES, Spain
- **Brazil** - BR, Brazil
- **Mexico** - MX, Mexico
- **Italy** - IT, Italy
- **Netherlands** - NL, Netherlands, Holland
- **Japan** - JP, Japan
- **South Korea** - KR, Korea
- **Philippines** - PH, Philippines

### Major Cities Supported:

**USA:**
- New York, NYC, Los Angeles, LA, Chicago, Houston, Miami, Phoenix
- Philadelphia, San Antonio, San Diego, Dallas, San Jose, Austin
- Jacksonville, San Francisco, Seattle, Denver, Boston, Portland
- Las Vegas, Atlanta

**UK:**
- London, Manchester, Birmingham, Liverpool, Leeds, Glasgow
- Edinburgh, Bristol, Cardiff, Belfast

**Canada:**
- Toronto, Vancouver, Montreal, Calgary, Ottawa, Edmonton

**Australia:**
- Sydney, Melbourne, Brisbane, Perth, Adelaide, Canberra

**India:**
- Mumbai, Delhi, Bangalore, Hyderabad, Chennai, Kolkata, Pune

**And many more...**

## How Location Detection Works

### 1. About Page Text
Scans the channel's About page for mentions of:
- Country names (e.g., "Based in USA")
- City names (e.g., "Miami-based creator")
- Location keywords

### 2. Video Titles
Checks video titles for location mentions:
- "Miami Vlog"
- "London Street Food"
- "NYC Travel Guide"

### 3. Domain TLDs
Infers country from website domains:
- `.uk` → United Kingdom
- `.ca` → Canada
- `.au` → Australia
- `.de` → Germany

### 4. API Data
Uses YouTube API's `snippet.country` field if available

## Confidence Scoring

Location match contributes **0-20 points** to overall confidence:

- **Direct city match**: +20 points
  - You search "Miami", channel mentions "Miami"
  
- **Country match**: +20 points
  - You search "US", channel is from USA
  
- **Location found but doesn't match**: +5 points
  - Shows channel has location info

- **Multiple sources**: Higher confidence
  - Found in About page + video titles = more reliable

## Output Format

### Terminal Display:
```
1. Miami Yoga Girl
   Subscribers: 250,000
   Location: Miami, USA
   Confidence: 92.3/100
   Email: hello@miamiyogagirl.com
```

### JSON Output:
```json
{
  "channel_name": "Miami Yoga Girl",
  "detected_location": {
    "country": "USA",
    "city": "Miami",
    "confidence": 20,
    "sources": ["about_page", "video_titles"]
  },
  "location_sources": ["about_page", "video_titles"]
}
```

### CSV Output:
```csv
channel_name,detected_location,location_sources
Miami Yoga Girl,"{""country"": ""USA"", ""city"": ""Miami""}","[""about_page"", ""video_titles""]"
```

## Tips for Best Results

### For City Searches:
1. **Use major cities** - Better detection for well-known cities
2. **Check spelling** - "New York" not "Newyork"
3. **Be specific** - "Miami" better than "South Florida"

### For Country Searches:
1. **Use 2-letter codes** - US, UK, CA (faster API search)
2. **Or full names** - United States, Canada, Australia
3. **Common variations work** - America = USA, Britain = UK

### Combining Filters:
```
Niche: food
Sub-niche: vegan
Location: London
Min subscribers: 50000
```

**Result:** Vegan food channels from London with 50K+ subscribers

## Troubleshooting

**No location detected:**
- Channel may not mention location publicly
- Try broader search (country instead of city)
- Check `location_sources` field to see what was checked

**Wrong location detected:**
- Some channels mention multiple locations
- First mention is usually used
- Check `about_text` field to verify

**City not recognized:**
- Only major cities are in the database
- Try searching by country instead
- Or use niche keywords that imply location

## Examples

### Find Miami Fitness Creators:
```bash
python find_creators.py

Enter niche: fitness
Enter sub-niche: 
Enter location: Miami
Max results: 20
Min subscribers: 10000
```

### Find UK Tech Reviewers:
```bash
python find_creators.py

Enter niche: tech reviews
Enter sub-niche: smartphones
Enter location: UK
Max results: 50
Min subscribers: 100000
```

### Find Toronto Food Vloggers:
```bash
python find_creators.py

Enter niche: food
Enter sub-niche: vegan
Enter location: Toronto
Max results: 30
Min subscribers: 5000
```

## Advanced: Location Confidence

The `confidence` score in `detected_location` shows how certain we are:

- **15-20**: Very confident (multiple sources)
- **10-14**: Confident (one strong source)
- **5-9**: Possible (weak signals)
- **0-4**: Uncertain (minimal evidence)

Higher confidence = more reliable location match!
