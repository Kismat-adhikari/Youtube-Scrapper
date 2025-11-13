# YouTube Channel Finder - find_creators.py

Find YouTube channels by niche, sub-niche, and country using API + Playwright scraping.

## How to Use

### 1. Run the Tool
```bash
python find_creators.py
```

### 2. Answer the Prompts
```
Enter niche (required): fitness
Enter sub-niche (optional, press Enter to skip): yoga
Enter location (country code or city, e.g., US, Miami - optional): Miami
Max results (default 50): 20
Min subscribers (optional, press Enter to skip): 10000
```

**Location Examples:**
- Country codes: `US`, `UK`, `CA`, `AU`, `IN`
- Cities: `Miami`, `New York`, `London`, `Toronto`, `Sydney`

### 3. Results Location

Results are saved to the `results/` folder with timestamped filenames:

**CSV File:**
```
results/2025-11-11_2230_fitness_yoga_channels.csv
```

**JSON File:**
```
results/2025-11-11_2230_fitness_yoga_channels.json
```

## Output Format

### CSV Columns:
- `channel_id` - YouTube channel ID
- `channel_name` - Channel name
- `channel_url` - Full channel URL
- `channel_description` - Channel description from API
- `subscriber_count` - Number of subscribers
- `channel_video_count` - Total videos
- `channel_view_count` - Total views
- `sample_video_id` - Sample video ID
- `sample_video_title` - Sample video title
- `sample_video_url` - Sample video URL
- `detected_location` - Detected location (JSON object with country/city)
- `location_sources` - Where location was found (about_page, video_titles, domain)
- `about_text` - Full About page text
- `social_links` - Social media links (JSON array in CSV)
- `websites` - Website links (JSON array in CSV)
- `contact_email_public` - Public email if found
- `all_emails` - All emails found (JSON array in CSV)
- `confidence_score` - Match confidence (0-100)
- `extraction_path` - Data source (api+playwright)
- `scraped_at` - Timestamp

### JSON Format:
Full structured data with arrays preserved.

## What It Does

### Step 1: API Search
- Searches YouTube Data API for channels/videos matching your niche
- Extracts unique channel IDs
- Fetches channel statistics

### Step 2: Filter
- Filters by minimum subscribers (if specified)
- Deduplicates channels

### Step 3: Scrape Each Channel
For each channel, uses Playwright to:
- Visit About page
- Extract About text, social links, websites
- Find public emails in About text
- Detect country from text mentions
- Visit Videos page
- Extract 3 sample videos

### Step 4: Rank & Score
Calculates confidence score based on:
- **Keyword match** (0-40 points) - Niche in title/description
- **Subscriber count** (0-30 points) - Logarithmic scale
- **Location match** (0-20 points) - Matches target country OR city
- **Contact info** (0-10 points) - Has email/social links

**Total: 0-100 points**

**Location Detection:**
- Checks About page text for country/city mentions
- Analyzes video titles for location keywords
- Infers from domain TLDs (.uk, .ca, .au, etc.)
- Uses API country data if available
- Assigns confidence score for location match

### Step 5: Save Results
- Sorts by confidence score (highest first)
- Saves to timestamped CSV + JSON
- Shows summary

## Example Output

### Terminal Display:
```
Found 20 channels
============================================================

1. Yoga With Adriene
   Subscribers: 12,500,000
   Location: Austin, USA
   Confidence: 95.5/100
   Email: contact@yogawithadriene.com
   Social: 4 links

2. Miami Yoga Girl
   Subscribers: 250,000
   Location: Miami, USA
   Confidence: 92.3/100
   Email: hello@miamiyogagirl.com
   Social: 3 links

...

============================================================
Summary
============================================================
Total channels found: 20
Total API calls: 8
Results saved to:
  - results/2025-11-11_2230_fitness_yoga_channels.csv
  - results/2025-11-11_2230_fitness_yoga_channels.json
============================================================
```

### CSV Example:
```csv
channel_id,channel_name,subscriber_count,detected_country,contact_email_public,confidence_score
UCvze...,Yoga With Adriene,12500000,USA,contact@yoga.com,95.5
UCj0V...,Boho Beautiful,3200000,Canada,,88.2
```

### JSON Example:
```json
[
  {
    "channel_id": "UCvze...",
    "channel_name": "Yoga With Adriene",
    "channel_url": "https://www.youtube.com/channel/UCvze...",
    "subscriber_count": 12500000,
    "detected_country": "USA",
    "social_links": [
      "https://www.instagram.com/yogawithadriene",
      "https://www.facebook.com/yogawithadriene",
      "https://twitter.com/yogawithadriene"
    ],
    "contact_email_public": "contact@yogawithadriene.com",
    "confidence_score": 95.5
  }
]
```

## Features

✅ **Hybrid Approach** - API search + Playwright scraping
✅ **Proxy Rotation** - Auto-loads from `proxies.txt`
✅ **Country Detection** - From About page text + API
✅ **Email Extraction** - Finds public emails in About text
✅ **Social Links** - Decodes YouTube redirects
✅ **Confidence Scoring** - Ranks channels by relevance
✅ **Sample Videos** - Includes sample video from each channel
✅ **Timestamped Output** - Never overwrites previous results
✅ **Headed Mode** - See the browser (for now)

## Requirements

- Python 3.x
- Dependencies from `requirements.txt`
- YouTube API key in `.env`
- Optional: Proxies in `proxies.txt`

## Tips

### For Best Results:
1. **Be specific with niche** - "fitness yoga" better than just "fitness"
2. **Use country codes** - US, UK, CA, AU, etc.
3. **Set min subscribers** - Filter out small channels
4. **Check confidence scores** - Higher = better match

### Country Codes:
- US - United States
- UK - United Kingdom
- CA - Canada
- AU - Australia
- IN - India
- DE - Germany
- FR - France
- ES - Spain
- BR - Brazil
- MX - Mexico

## Troubleshooting

**No results found:**
- Try broader niche terms
- Remove country filter
- Lower min_subscribers

**CAPTCHA issues:**
- Proxies help avoid CAPTCHAs
- Headed mode lets you solve manually
- Add more proxies to `proxies.txt`

**API quota exceeded:**
- YouTube API has daily limits
- Wait 24 hours or use different API key
- Reduce max_results

## Next Steps

After running, open the CSV file in Excel/Google Sheets to:
- Sort by confidence_score
- Filter by country
- Filter by subscriber_count
- Copy emails and social links for outreach
