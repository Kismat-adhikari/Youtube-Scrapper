# Data Extraction Order

## How the Scraper Works

### 1. Playwright Scrapes EVERYTHING First (Headed Mode)

The scraper uses Playwright browser automation to extract:

**Video Data:**
- ✅ `title` - from page heading
- ✅ `description` - from description section
- ✅ `view_count` - **ACTUAL NUMBER** from page (e.g., 1,456,789,012)
- ✅ `like_count` - **ACTUAL NUMBER** from like button (e.g., 15,234,567)
- ✅ `comment_count` - **ACTUAL NUMBER** from comments section (e.g., 2,876,543)
- ✅ `upload_date` - from video info
- ✅ `duration_seconds` - from page metadata
- ✅ `tags` - from page keywords
- ✅ `is_live` - live status
- ✅ `thumbnail_urls` - generated URLs

**Channel Data:**
- ✅ `channel_name` - from uploader info
- ✅ `channel_id` - from channel URL
- ✅ `channel_url` - from uploader link

**Public Contact Info (from About page):**
- ✅ `business_email` - if publicly posted
- ✅ `social_links` - Twitter, Instagram, Facebook, TikTok
- ✅ `contact_source` - where info was found

### 2. API Fills Missing Data ONLY

The YouTube Data API is called **only when**:
- Playwright couldn't extract a field (CAPTCHA, page error, etc.)
- Channel statistics (subscriber count usually not visible on page)

**API fills gaps for:**
- Missing `view_count`, `like_count`, `comment_count`
- Missing `title`, `description`, `tags`
- Channel stats: `subscriber_count`, `video_count`, `channel_view_count`

### 3. Field Source Tracking

Every field tracks its source:

```json
{
  "view_count": 1712082561,
  "field_source_view_count": "scraped",  // ← Playwright got this
  
  "like_count": 18631917,
  "field_source_like_count": "scraped",  // ← Playwright got this
  
  "social_links": [
    "https://www.facebook.com/RickAstley/",
    "https://www.instagram.com/officialrickastley/",
    "https://twitter.com/rickastley"
  ],
  "contact_source": ["about_page_social"],  // ← Found on About page
  
  "channel_subscriber_count": 4420000,
  "field_source_channel_stats": "api"    // ← API got this (not on page)
}
```

### 4. Proxy Rotation

- Automatically loads `proxies.txt` if present
- Rotates through all proxies: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 1...
- Each retry uses the next proxy
- Blacklists proxies after 5 failures (configurable)

### 5. CAPTCHA Handling

If CAPTCHA detected:
1. Save HTML snapshot to `results/debug/`
2. Try next proxy (up to 3 retries)
3. If all fail, skip video and log to `failed.csv`

## Priority Order

```
1. Playwright scrapes → REAL DATA (numbers, text, everything)
2. API fills gaps → Only missing fields
3. Scraped data ALWAYS wins over API when both exist
```

## Example Flow

```
[1/2] Processing dQw4w9WgXcQ
  Attempt 1/3 with proxy 216.98.249.139
  ✓ Scraped successfully — channel: Rick Astley
  → Got: title, description, view_count (1.7B), like_count (18M)
  Visiting channel About page...
  Found 4 social links
  
Fetching channel stats for 2 channels
  → API filled: subscriber_count (4.4M), video_count (378), comment_count (2.4M)
  
[2/2] Processing 9bZkp7q19f0
  Attempt 1/3 with proxy 154.194.27.141
  ✓ Scraped successfully — channel: officialpsy
  → Got: title, description, view_count (5.7B), like_count (31M)
  Visiting channel About page...

Total API calls made: 4
CSV saved to results/2025-11-11_1905_videos.csv
JSON saved to results/2025-11-11_1905_videos.json
```

## Result

All numeric values (view_count, like_count, comment_count) are **actual numbers scraped by Playwright**, not just API fallback strings. The API only supplements with channel stats that aren't visible on the video page.
