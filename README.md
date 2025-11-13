# YouTube Scraper 🎥

A powerful Python-based YouTube scraper that extracts video and channel metadata using Playwright browser automation and YouTube Data API v3.

## Features ✨

### Video Scraping
- **Individual Videos** - Scrape specific video URLs
- **Search Results** - Extract up to 30 videos from YouTube search results
- **Real-Time Saving** - Results saved after each video (no data loss on crashes)
- **Proxy Rotation** - Automatic proxy rotation from `proxies.txt`
- **CAPTCHA Handling** - Automatic retry with different proxies

### Data Extraction
- **Video Data**: Title, description, views, likes, comments, duration, tags, category
- **Channel Data**: Name, subscribers, total videos, total views
- **Contact Info**: Business emails, social media links (Twitter, Instagram, Facebook, TikTok, etc.)
- **Smart Extraction**: Clicks hidden email buttons, decodes YouTube redirect URLs
- **API Fallback**: Uses YouTube API only to fill missing data (saves quota)

### Output Formats
- **CSV** - Flat format for Excel/Google Sheets
- **JSON** - Full structured data with arrays
- **Real-Time Updates** - Files updated after each video

## Setup 🚀

### 1. Clone Repository
```bash
git clone https://github.com/Kismat-adhikari/Youtube-Scrapper.git
cd Youtube-Scrapper
```

### 2. Create Virtual Environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
playwright install
```

### 4. Configure Environment
Create a `.env` file:
```
YOUTUBE_API_KEY=your_api_key_here
```

Get your API key from [Google Cloud Console](https://console.cloud.google.com/)

### 5. (Optional) Add Proxies
Create `proxies.txt` with format: `ip:port:username:password`
```
216.98.249.139:8080:user:pass
154.194.27.141:3128:user2:pass2
```

## Usage 📖

### Basic Usage

#### Scrape Individual Video
```bash
python scraper.py
```
Enter: `https://www.youtube.com/watch?v=dQw4w9WgXcQ`

#### Scrape Search Results (up to 30 videos)
```bash
python scraper.py
```
Enter: `https://www.youtube.com/results?search_query=python+tutorial`

#### Mix Both Types
```bash
python scraper.py
```
Enter: `https://www.youtube.com/watch?v=abc123, https://www.youtube.com/results?search_query=coding`

### Find Creators by Niche
```bash
python find_creators.py
```

Follow the prompts:
- **Niche**: fitness, tech, gaming, etc.
- **Sub-niche**: yoga, smartphones, etc. (optional)
- **Location**: US, UK, Miami, London, etc. (optional)
- **Max results**: Number of channels to find
- **Min subscribers**: Filter by subscriber count (optional)

### Advanced Options
```bash
# Adjust retry attempts
python scraper.py --proxy_retries 5

# Change proxy blacklist threshold
python scraper.py --blacklist_threshold 3
```

## Output 📊

### Files Created
- `results/YYYY-MM-DD_HHMM_videos.csv` - All video data
- `results/YYYY-MM-DD_HHMM_videos.json` - Full structured data
- `results/failed.csv` - Videos that failed to scrape

### Data Fields

**Video Level:**
- video_id, title, description
- view_count, like_count, comment_count
- upload_date, duration_seconds, tags
- video_category, is_live
- description_emails, description_urls

**Channel Level:**
- channel_name, channel_id, channel_url
- channel_subscriber_count, channel_video_count
- channel_description
- business_email, social_links
- contact_source

**Metadata:**
- extraction_path (playwright/api)
- field_source_* (tracks data source)

## How It Works 🔧

### For Individual Videos:
1. Navigate to video page with Playwright
2. Extract video data (views, likes, title, etc.)
3. Navigate to channel About page
4. Click "View email address" button if present
5. Extract social links and decode YouTube redirects
6. Fill missing data with YouTube API
7. Save to CSV and JSON

### For Search Results:
1. Navigate to search results page
2. Scroll to load more videos (up to 30)
3. Extract video IDs from search results
4. For each video, follow same process as individual videos
5. Save after each video (real-time updates)

### Real-Time Saving:
```
Scrape Video 1 → Save → Scrape Video 2 → Save → ... → Final Save with API data
```
✅ No data loss on crashes
✅ Monitor progress in real-time
✅ Can stop anytime and keep results

## Features in Detail 📋

### Proxy Rotation
- Automatically loads from `proxies.txt`
- Rotates through all proxies: 1 → 2 → 3 → ... → 1
- Blacklists proxies after 5 failures (configurable)
- Each retry uses next proxy

### Email Extraction
- Waits for page to load
- Tries 7 different button selectors
- Clicks "View email address" button
- Waits 3 seconds for email to appear
- Falls back to page source if button not found
- Filters out noreply/test emails

### Social Links
- Decodes YouTube redirect URLs
- Extracts: Twitter, Instagram, Facebook, TikTok, LinkedIn, Twitch
- Removes duplicates and cleans URLs
- Tracks source (about_page_social)

### CAPTCHA Handling
- Detects CAPTCHA on page
- Saves HTML snapshot to `results/debug/`
- Retries with different proxy (up to 3 attempts)
- Skips video if all attempts fail

## Documentation 📚

- **README.md** - This file (main documentation)
- **DATA_EXTRACTION_ORDER.md** - How data extraction works
- **FIND_CREATORS_README.md** - Guide for find_creators.py
- **LOCATION_SEARCH_GUIDE.md** - How to search by location
- **SEARCH_RESULTS_FEATURE.md** - Search results scraping guide
- **REAL_TIME_SAVING.md** - Real-time saving feature details

## Requirements 📦

- Python 3.7+
- Playwright
- Pandas
- Requests
- python-dotenv
- YouTube Data API v3 key

See `requirements.txt` for exact versions.

## Tips 💡

### For Best Results:
1. **Use proxies** - Avoid CAPTCHAs and rate limits
2. **Specific searches** - "python pandas tutorial" better than "python"
3. **Monitor logs** - Watch for CAPTCHA warnings
4. **Check confidence scores** - Higher = better match (find_creators.py)

### Troubleshooting:
- **No videos extracted** - Check for CAPTCHA in browser window
- **No emails found** - Many channels don't have public emails
- **API quota exceeded** - Wait 24 hours or use different API key
- **Proxy blacklisted** - Add more proxies to `proxies.txt`

## Performance ⚡

- **Search page extraction**: ~12-18 seconds
- **Per video scraping**: ~40-50 seconds
- **Total for 30 videos**: ~35-45 minutes
- **Real-time saving overhead**: ~0.1-0.5 seconds per video

## Examples 🎯

### Example 1: Tech Tutorial Videos
```bash
python scraper.py
# Enter: https://www.youtube.com/results?search_query=python+tutorial
# Result: 30 Python tutorial videos with channel data
```

### Example 2: Find Fitness Creators in Miami
```bash
python find_creators.py
# Niche: fitness
# Sub-niche: yoga
# Location: Miami
# Result: Yoga channels from Miami with contact info
```

### Example 3: Specific Video Analysis
```bash
python scraper.py
# Enter: https://www.youtube.com/watch?v=dQw4w9WgXcQ
# Result: Full data for that video + channel info
```

## Contributing 🤝

Feel free to open issues or submit pull requests!

## License 📄

MIT License - See LICENSE file for details

## Disclaimer ⚠️

This tool is for educational purposes only. Always respect YouTube's Terms of Service and robots.txt. Only scrape publicly available data and use responsibly.

## Author 👨‍💻

Created by Kismat Adhikari

## Support 💬

For issues or questions, please open an issue on GitHub.

---

**Happy Scraping! 🎉**
