# Search Results Scraping Feature

## New Feature: Scrape Videos from YouTube Search Results

The scraper now supports **two types of YouTube URLs**:

### 1. Individual Video URLs (Original)
```
https://www.youtube.com/watch?v=dQw4w9WgXcQ
https://youtu.be/dQw4w9WgXcQ
```

### 2. Search Results URLs (NEW!)
```
https://www.youtube.com/results?search_query=rick+and+morty
https://www.youtube.com/results?search_query=python+tutorial
```

## How It Works

When you provide a search results URL, the scraper will:

1. **Navigate to the search page** using Playwright
2. **Scroll to load more results** (scrolls 5 times to load up to 50 videos)
3. **Extract video IDs** from the search results (handles both relative and absolute URLs)
4. **Scrape each video** individually (same as before):
   - Video data (title, description, views, likes, comments, etc.)
   - Channel data (name, subscribers, etc.)
   - Channel About page (email, social links, etc.)
5. **Save results** to CSV and JSON (same format as before)

## Usage Examples

### Example 1: Single Search Query
```bash
python scraper.py
```

**Input:**
```
Enter YouTube URLs: https://www.youtube.com/results?search_query=rick+and+morty
```

**Result:** Scrapes up to 50 videos from "rick and morty" search results

### Example 2: Multiple Individual Videos
```bash
python scraper.py
```

**Input:**
```
Enter YouTube URLs: https://www.youtube.com/watch?v=dQw4w9WgXcQ, https://www.youtube.com/watch?v=9bZkp7q19f0
```

**Result:** Scrapes those 2 specific videos

### Example 3: Mix Both Types
```bash
python scraper.py
```

**Input:**
```
Enter YouTube URLs: https://www.youtube.com/watch?v=dQw4w9WgXcQ, https://www.youtube.com/results?search_query=python+tutorial
```

**Result:** Scrapes 1 specific video + up to 50 videos from search results

## How to Create Search URLs

### Method 1: Copy from Browser
1. Go to YouTube
2. Search for anything (e.g., "rick and morty")
3. Copy the URL from address bar
4. Paste into scraper

### Method 2: Manual Construction
Format: `https://www.youtube.com/results?search_query=YOUR+SEARCH+TERMS`

Examples:
- `https://www.youtube.com/results?search_query=python+tutorial`
- `https://www.youtube.com/results?search_query=cooking+recipes`
- `https://www.youtube.com/results?search_query=gaming+highlights`

**Note:** Replace spaces with `+` signs

## Output Format

The output is **exactly the same** as before:

### CSV File: `results/YYYY-MM-DD_HHMM_videos.csv`
All video data in flat format

### JSON File: `results/YYYY-MM-DD_HHMM_videos.json`
Full structured data with arrays

### Failed Videos: `results/failed.csv`
List of videos that couldn't be scraped

## Features

✅ **Automatic detection** - Detects search URLs vs video URLs automatically
✅ **Proxy support** - Uses proxies from `proxies.txt` for search page too
✅ **CAPTCHA handling** - Detects CAPTCHAs on search page
✅ **Deduplication** - Removes duplicate video IDs from search results
✅ **Scrolling** - Automatically scrolls 5 times to load up to 50 results
✅ **URL handling** - Handles both relative (/watch?v=...) and absolute URLs
✅ **Same output format** - Results look identical to individual video scraping

## Workflow

```
Search URL Input
    ↓
Navigate to Search Page (Playwright)
    ↓
Scroll to Load More Videos
    ↓
Extract 20-25 Video IDs
    ↓
For Each Video:
    ├─ Scrape Video Page
    ├─ Scrape Channel About Page
    └─ Extract Contact Info
    ↓
Enrich with API (if needed)
    ↓
Save to CSV + JSON
```

## Limitations

- **Max 50 videos per search** - Extracts up to 50 results
- **CAPTCHA blocks search** - If CAPTCHA appears on search page, cannot proceed
- **Requires scrolling** - Takes ~6 seconds to scroll and load results
- **No filtering** - Gets whatever YouTube shows first (no date/view filters)

## Tips

### For Best Results:
1. **Use specific search terms** - "python pandas tutorial" better than "python"
2. **Check proxy rotation** - Search page uses 1 proxy, then rotates for videos
3. **Monitor for CAPTCHAs** - If search page shows CAPTCHA, try different proxy
4. **Combine with filters** - Use YouTube's search filters in browser, then copy URL

### Performance:
- **Search page extraction**: ~12-18 seconds (with scrolling)
- **Per video scraping**: ~40-50 seconds
- **Total for 50 videos**: ~35-45 minutes

## Troubleshooting

**No videos extracted from search:**
- Check if CAPTCHA appeared (check logs)
- Try different proxy
- Verify search URL format is correct

**Search page timeout:**
- Increase timeout in code (currently 30 seconds)
- Check internet connection
- Try without proxy first

**Duplicate videos in results:**
- Scraper automatically deduplicates by video ID
- If you see duplicates, it's from different search URLs

## Example Run

```bash
$ python scraper.py

============================================================
YouTube Video Scraper
============================================================

Supported URL types:
  1. Individual video: https://www.youtube.com/watch?v=VIDEO_ID
  2. Search results: https://www.youtube.com/results?search_query=YOUR_QUERY
     (Will scrape first 20-25 videos from search)

You can mix both types, separated by commas
============================================================

Enter YouTube URLs: https://www.youtube.com/results?search_query=rick+and+morty

============================================================
Detected YouTube search results URL
============================================================

Extracting videos from search results...
Search URL: https://www.youtube.com/results?search_query=rick+and+morty
Using proxy: 216.98.249.139
Scrolling to load more videos...
Found 70 video elements using selector: ytd-video-renderer a#video-title
✓ Extracted 50 unique video IDs from search results

============================================================
Starting scrape for 50 videos
============================================================

[1/25] Processing dQw4w9WgXcQ
  Attempt 1/3 with proxy 154.194.27.141
  ✓ Scraped successfully — channel: Rick Astley
  Visiting channel About page...
  Found 4 social links

[2/50] Processing abc123xyz...
...
```

## Next Steps

After running, you'll have:
- CSV with up to 50 videos
- JSON with full structured data
- Same fields as individual video scraping
- Ready for analysis/outreach

Enjoy the new feature! 🎉
