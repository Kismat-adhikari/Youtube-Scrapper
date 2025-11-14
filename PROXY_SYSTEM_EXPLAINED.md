# Proxy System Explained 🔄

## How Proxies Work in This Scraper

### 1. **Automatic Loading**

When the scraper starts, it automatically looks for `proxies.txt`:

```python
# Auto-load proxies.txt if it exists
proxy_file = 'proxies.txt' if os.path.exists('proxies.txt') else None
self.proxy_manager = ProxyManager(proxy_file, args.blacklist_threshold)
```

**If `proxies.txt` exists:** Loads all proxies
**If `proxies.txt` doesn't exist:** Runs without proxies

### 2. **Proxy File Format**

`proxies.txt` should contain one proxy per line:

```
216.98.249.139:8080:username:password
154.194.27.141:3128:user2:pass2
45.76.123.45:8080:user3:pass3
# This is a comment (ignored)
192.168.1.1:8080:user4:pass4
```

**Format:** `ip:port:username:password`
- Lines starting with `#` are ignored (comments)
- Empty lines are ignored
- Username/password are optional (can be just `ip:port`)

### 3. **Round-Robin Rotation**

Proxies rotate in a **circular pattern**:

```
Proxy 1 → Proxy 2 → Proxy 3 → Proxy 4 → Proxy 5 → Proxy 6 → Proxy 7 → Proxy 1 → ...
```

**Example with 7 proxies:**
```
Search page:     Uses Proxy 1
Video 1:         Uses Proxy 2
Video 2:         Uses Proxy 3
Video 3:         Uses Proxy 4
...
Video 7:         Uses Proxy 1 (back to start)
Video 8:         Uses Proxy 2
```

### 4. **When Proxies Are Used**

#### A. Search Results Extraction
```
Search URL → Uses 1 proxy → Extracts 30 video IDs
```

#### B. Each Video Scraping
```
Video 1 → Attempt 1 with Proxy A
       → If fails, Attempt 2 with Proxy B
       → If fails, Attempt 3 with Proxy C
```

**Default:** 3 retry attempts per video (configurable with `--proxy_retries`)

### 5. **Proxy Failure Tracking**

The scraper tracks failures for each proxy:

```python
proxy_failures = {
    '216.98.249.139:8080:user:pass': 2,  # Failed 2 times
    '154.194.27.141:3128:user2:pass2': 5, # Failed 5 times (BLACKLISTED)
    '45.76.123.45:8080:user3:pass3': 0    # No failures
}
```

### 6. **Blacklisting System**

**Default threshold:** 5 failures

When a proxy fails 5 times:
```
2025-11-14 00:29:15 - WARNING - Proxy 154.194.27.141 blacklisted after 5 failures
```

**Blacklisted proxies are skipped** in future rotations.

### 7. **Complete Workflow**

#### Scenario: Scraping 30 videos with 7 proxies

```
1. Load proxies from proxies.txt
   → Loaded 7 proxies

2. Extract search results
   → Using proxy: 216.98.249.139
   → Extracted 30 video IDs

3. Scrape Video 1
   → Attempt 1/3 with proxy 154.194.27.141
   → ✓ Success

4. Scrape Video 2
   → Attempt 1/3 with proxy 45.76.123.45
   → ✗ Failed (CAPTCHA)
   → Attempt 2/3 with proxy 192.168.1.1
   → ✓ Success

5. Scrape Video 3
   → Attempt 1/3 with proxy 10.0.0.1
   → ✓ Success

... continues rotating through all proxies ...
```

### 8. **Proxy Configuration**

#### Default Settings:
```bash
python scraper.py
```
- Proxy retries: 3 attempts per video
- Blacklist threshold: 5 failures

#### Custom Settings:
```bash
python scraper.py --proxy_retries 5 --blacklist_threshold 3
```
- Proxy retries: 5 attempts per video
- Blacklist threshold: 3 failures (more aggressive)

### 9. **What Happens Without Proxies**

If `proxies.txt` doesn't exist or is empty:

```
2025-11-14 00:29:15 - INFO - Starting scrape for 30 videos

[1/30] Processing dQw4w9WgXcQ
  Attempt 1/3 without proxy
  ✓ Scraped successfully
```

**Scraper still works** but:
- Higher CAPTCHA risk
- More likely to get rate-limited
- YouTube may block your IP

### 10. **Proxy Format in Code**

The scraper parses proxies like this:

```python
proxy = "216.98.249.139:8080:username:password"
parts = proxy.split(':')

# parts[0] = "216.98.249.139" (IP)
# parts[1] = "8080" (Port)
# parts[2] = "username" (optional)
# parts[3] = "password" (optional)

proxy_config = {
    'server': 'http://216.98.249.139:8080',
    'username': 'username',  # if provided
    'password': 'password'   # if provided
}
```

### 11. **Proxy Success/Failure Logic**

#### Success:
```python
result = scrape_video_with_playwright(video_id, proxy)
if result:
    # Success! Move to next video
    return result
```

#### Failure:
```python
else:
    # Failed - report to proxy manager
    proxy_manager.report_failure(proxy)
    # Try next proxy (up to 3 attempts)
```

### 12. **Real-World Example**

#### proxies.txt:
```
216.98.249.139:8080:user1:pass1
154.194.27.141:3128:user2:pass2
45.76.123.45:8080:user3:pass3
```

#### Terminal Output:
```
2025-11-14 00:29:15 - INFO - Loaded 3 proxies

Extracting videos from search results...
Using proxy: 216.98.249.139
✓ Extracted 30 unique video IDs

[1/30] Processing dQw4w9WgXcQ
  Attempt 1/3 with proxy 154.194.27.141
  ✓ Scraped successfully — channel: Rick Astley

[2/30] Processing 9bZkp7q19f0
  Attempt 1/3 with proxy 45.76.123.45
  ✗ Failed (CAPTCHA or error)
  Attempt 2/3 with proxy 216.98.249.139
  ✓ Scraped successfully — channel: officialpsy

[3/30] Processing jNQXAC9IVRw
  Attempt 1/3 with proxy 154.194.27.141
  ✓ Scraped successfully — channel: Me at the zoo
```

### 13. **Proxy Rotation Pattern**

With 3 proxies (A, B, C) and 10 videos:

```
Search:    A
Video 1:   B → Success
Video 2:   C → Fail → A → Success
Video 3:   B → Success
Video 4:   C → Success
Video 5:   A → Success
Video 6:   B → Fail → C → Fail → A → Success
Video 7:   B → Success
Video 8:   C → Success
Video 9:   A → Success
Video 10:  B → Success
```

### 14. **Benefits of This System**

✅ **Automatic rotation** - No manual switching
✅ **Failure tracking** - Bad proxies get blacklisted
✅ **Retry logic** - 3 chances per video
✅ **No configuration needed** - Just add proxies.txt
✅ **Works without proxies** - Optional feature
✅ **Circular rotation** - Evenly distributes load
✅ **Smart blacklisting** - Removes dead proxies

### 15. **Common Issues**

#### Issue: "Loaded 0 proxies"
**Cause:** `proxies.txt` doesn't exist or is empty
**Solution:** Create `proxies.txt` with proxy list

#### Issue: All proxies blacklisted
**Cause:** All proxies failed 5+ times
**Solution:** 
- Get better proxies
- Increase blacklist threshold: `--blacklist_threshold 10`

#### Issue: Still getting CAPTCHAs
**Cause:** Proxies are detected or low quality
**Solution:**
- Use residential proxies (not datacenter)
- Add more proxies to rotate
- Increase retry attempts: `--proxy_retries 5`

### 16. **Best Practices**

1. **Use 5-10 proxies minimum** - Better rotation
2. **Test proxies first** - Make sure they work
3. **Use residential proxies** - Less likely to be blocked
4. **Monitor blacklist warnings** - Replace bad proxies
5. **Adjust thresholds** - Based on proxy quality

### 17. **Summary**

| Feature | How It Works |
|---------|-------------|
| Loading | Automatic from `proxies.txt` |
| Rotation | Round-robin (circular) |
| Retries | 3 attempts per video (default) |
| Blacklisting | After 5 failures (default) |
| Format | `ip:port:user:pass` |
| Optional | Works without proxies |
| Tracking | Per-proxy failure count |

The proxy system is **fully automatic** - just add proxies to `proxies.txt` and the scraper handles everything! 🚀
