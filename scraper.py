#!/usr/bin/env python3
"""
YouTube Video Scraper
Extracts video and channel metadata using Playwright, yt-dlp, and YouTube Data API
"""

import os
import re
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qs, unquote

import requests
import pandas as pd
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def decode_youtube_redirect(url: str) -> Optional[str]:
    """
    Decode YouTube redirect URLs to get the actual destination URL.
    YouTube wraps external links like: youtube.com/redirect?...&q=https%3A%2F%2Fwww.instagram.com%2Fusername
    """
    if not url:
        return None
    
    # If it's a YouTube redirect URL
    if 'youtube.com/redirect' in url or 'youtube.com/attribution_link' in url:
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            
            # The actual URL is in the 'q' parameter
            if 'q' in params and params['q']:
                actual_url = unquote(params['q'][0])
                return actual_url
        except Exception as e:
            logger.debug(f"Could not decode redirect URL: {e}")
            return None
    
    # If it's already a direct URL, return as-is
    return url


def extract_emails_from_text(text: str) -> List[str]:
    """Extract valid email addresses from text"""
    if not text:
        return []
    
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(email_pattern, text)
    
    # Filter out common non-business emails
    filtered = [
        e for e in emails 
        if not any(x in e.lower() for x in ['noreply', 'example', 'test', '@youtube.com', '@google.com'])
    ]
    
    return list(set(filtered))  # Remove duplicates


def extract_urls_from_text(text: str) -> List[str]:
    """Extract URLs from text"""
    if not text:
        return []
    
    # Pattern for URLs
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)
    
    # Clean and deduplicate
    cleaned_urls = []
    seen = set()
    
    for url in urls:
        # Remove trailing punctuation
        url = url.rstrip('.,;:!?)')
        
        # Skip YouTube URLs
        if 'youtube.com' in url or 'youtu.be' in url:
            continue
        
        if url not in seen:
            cleaned_urls.append(url)
            seen.add(url)
    
    return cleaned_urls


class ProxyManager:
    """Manages proxy rotation and blacklisting"""
    
    def __init__(self, proxy_file: Optional[str] = None, blacklist_threshold: int = 5):
        self.proxies = []
        self.proxy_failures = {}
        self.blacklist_threshold = blacklist_threshold
        self.current_index = 0
        
        if proxy_file and os.path.exists(proxy_file):
            self._load_proxies(proxy_file)
    
    def _load_proxies(self, proxy_file: str):
        """Load proxies from file"""
        with open(proxy_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    self.proxies.append(line)
        logger.info(f"Loaded {len(self.proxies)} proxies")
    
    def get_next_proxy(self) -> Optional[str]:
        """Get next available proxy"""
        if not self.proxies:
            return None
        
        attempts = 0
        while attempts < len(self.proxies):
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)
            
            if self.proxy_failures.get(proxy, 0) < self.blacklist_threshold:
                return proxy
            attempts += 1
        
        return None
    
    def report_failure(self, proxy: str):
        """Report proxy failure"""
        if proxy:
            self.proxy_failures[proxy] = self.proxy_failures.get(proxy, 0) + 1
            if self.proxy_failures[proxy] >= self.blacklist_threshold:
                logger.warning(f"Proxy {proxy} blacklisted after {self.blacklist_threshold} failures")


class YouTubeAPI:
    """YouTube Data API v3 client"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.api_calls = 0
    
    def get_video_details(self, video_ids: List[str]) -> Dict:
        """Fetch video details for multiple video IDs"""
        if not video_ids:
            return {}
        
        # Batch up to 50 IDs per call
        results = {}
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i+50]
            url = f"{self.base_url}/videos"
            params = {
                'part': 'snippet,statistics,contentDetails,status',
                'id': ','.join(batch),
                'key': self.api_key
            }
            
            try:
                response = requests.get(url, params=params)
                response.raise_for_status()
                self.api_calls += 1
                
                data = response.json()
                for item in data.get('items', []):
                    results[item['id']] = item
                
                logger.info(f"API call successful: fetched {len(batch)} videos")
            except Exception as e:
                logger.error(f"API call failed: {e}")
        
        return results
    
    def get_channel_details(self, channel_ids: List[str]) -> Dict:
        """Fetch channel details for multiple channel IDs"""
        if not channel_ids:
            return {}
        
        results = {}
        for i in range(0, len(channel_ids), 50):
            batch = channel_ids[i:i+50]
            url = f"{self.base_url}/channels"
            params = {
                'part': 'snippet,statistics,contentDetails',
                'id': ','.join(batch),
                'key': self.api_key
            }
            
            try:
                response = requests.get(url, params=params)
                response.raise_for_status()
                self.api_calls += 1
                
                data = response.json()
                for item in data.get('items', []):
                    results[item['id']] = item
                
                logger.info(f"API call successful: fetched {len(batch)} channels")
            except Exception as e:
                logger.error(f"API call failed: {e}")
        
        return results


class YouTubeScraper:
    """Main scraper class"""
    
    def __init__(self, args):
        self.args = args
        # Auto-load proxies.txt if it exists
        proxy_file = 'proxies.txt' if os.path.exists('proxies.txt') else None
        self.proxy_manager = ProxyManager(proxy_file, args.blacklist_threshold)
        self.api = YouTubeAPI(os.getenv('YOUTUBE_API_KEY', ''))
        self.results_dir = Path('results')
        self.debug_dir = self.results_dir / 'debug'
        self.results_dir.mkdir(exist_ok=True)
        self.debug_dir.mkdir(exist_ok=True)
        
        self.scraped_videos = []
        self.failed_videos = []
    
    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        """Extract video ID from YouTube URL"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/v\/([a-zA-Z0-9_-]{11})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    @staticmethod
    def is_search_url(url: str) -> bool:
        """Check if URL is a YouTube search results URL"""
        return 'youtube.com/results' in url and 'search_query=' in url
    
    def extract_videos_from_search(self, search_url: str, max_videos: int = 30) -> List[str]:
        """Extract video IDs from YouTube search results page"""
        logger.info(f"Extracting videos from search results...")
        logger.info(f"Search URL: {search_url}")
        
        video_ids = []
        
        with sync_playwright() as p:
            browser_args = {'headless': False}
            
            # Use proxy if available
            proxy = self.proxy_manager.get_next_proxy()
            if proxy:
                parts = proxy.split(':')
                if len(parts) >= 2:
                    proxy_config = {
                        'server': f'http://{parts[0]}:{parts[1]}'
                    }
                    if len(parts) == 4:
                        proxy_config['username'] = parts[2]
                        proxy_config['password'] = parts[3]
                    browser_args['proxy'] = proxy_config
                    logger.info(f"Using proxy: {parts[0]}")
            
            try:
                browser = p.chromium.launch(**browser_args)
                context = browser.new_context()
                page = context.new_page()
                
                # Navigate to search results
                page.goto(search_url, timeout=30000)
                page.wait_for_load_state('networkidle', timeout=15000)
                
                # Check for CAPTCHA
                if self.detect_captcha(page):
                    logger.error("CAPTCHA detected on search page. Cannot proceed.")
                    browser.close()
                    return []
                
                # Wait for video results to load
                try:
                    page.wait_for_selector('ytd-video-renderer', timeout=10000)
                except:
                    logger.warning("Video results not found, trying alternative selector...")
                
                # Scroll to load more videos (to get up to 50 videos)
                logger.info("Scrolling to load more videos...")
                for i in range(5):  # Scroll 5 times to load more results
                    page.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)')
                    page.wait_for_timeout(2000)
                    logger.debug(f"  Scroll {i+1}/5 completed")
                
                # Extract video links
                video_selectors = [
                    'ytd-video-renderer a#video-title',
                    'ytd-video-renderer #video-title',
                    'a#video-title'
                ]
                
                video_links = []
                for selector in video_selectors:
                    try:
                        elements = page.locator(selector).all()
                        if elements:
                            video_links = elements
                            logger.info(f"Found {len(video_links)} video elements using selector: {selector}")
                            break
                    except:
                        continue
                
                if not video_links:
                    logger.error("Could not find any video links on search page")
                    browser.close()
                    return []
                
                # Extract video IDs from links
                seen_ids = set()
                skipped_count = 0
                
                for i, link in enumerate(video_links):
                    try:
                        href = link.get_attribute('href')
                        if not href:
                            skipped_count += 1
                            logger.debug(f"  Link {i+1}: No href attribute")
                            continue
                        
                        # Handle relative URLs (e.g., /watch?v=abc123)
                        video_id = None
                        if href.startswith('/watch?v='):
                            # Extract video ID directly from relative URL
                            match = re.search(r'/watch\?v=([a-zA-Z0-9_-]{11})', href)
                            if match:
                                video_id = match.group(1)
                            else:
                                logger.debug(f"  Link {i+1}: Could not parse relative URL: {href[:50]}")
                        elif '/watch?v=' in href:
                            # Handle absolute URLs
                            video_id = self.extract_video_id(href)
                            if not video_id:
                                logger.debug(f"  Link {i+1}: Could not parse absolute URL: {href[:50]}")
                        else:
                            skipped_count += 1
                            logger.debug(f"  Link {i+1}: Not a video link: {href[:50]}")
                            continue
                        
                        if video_id and video_id not in seen_ids:
                            video_ids.append(video_id)
                            seen_ids.add(video_id)
                            logger.debug(f"  ✓ Extracted video ID #{len(video_ids)}: {video_id}")
                            
                            if len(video_ids) >= max_videos:
                                logger.info(f"Reached max limit of {max_videos} videos")
                                break
                        elif video_id in seen_ids:
                            logger.debug(f"  Link {i+1}: Duplicate video ID: {video_id}")
                    except Exception as e:
                        logger.debug(f"  Link {i+1}: Error extracting video ID: {e}")
                        skipped_count += 1
                        continue
                
                logger.info(f"Processed {len(video_links)} links: {len(video_ids)} extracted, {skipped_count} skipped")
                
                browser.close()
                
                logger.info(f"✓ Extracted {len(video_ids)} unique video IDs from search results")
                
            except Exception as e:
                logger.error(f"Error extracting videos from search: {e}")
                if 'browser' in locals():
                    browser.close()
        
        return video_ids[:max_videos]
    
    def detect_captcha(self, page: Page) -> bool:
        """Check if CAPTCHA is present"""
        captcha_selectors = [
            'iframe[src*="recaptcha"]',
            '#recaptcha',
            '.g-recaptcha',
            'text=unusual traffic'
        ]
        
        for selector in captcha_selectors:
            try:
                if page.locator(selector).count() > 0:
                    return True
            except:
                pass
        return False

    def scrape_video_with_playwright(self, video_id: str, proxy: Optional[str] = None) -> Optional[Dict]:
        """Scrape video data using Playwright"""
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        with sync_playwright() as p:
            browser_args = {'headless': False}
            
            if proxy:
                # Parse proxy format: ip:port:username:password
                parts = proxy.split(':')
                if len(parts) >= 2:
                    proxy_config = {
                        'server': f'http://{parts[0]}:{parts[1]}'
                    }
                    if len(parts) == 4:
                        proxy_config['username'] = parts[2]
                        proxy_config['password'] = parts[3]
                    browser_args['proxy'] = proxy_config
            
            try:
                browser = p.chromium.launch(**browser_args)
                context = browser.new_context()
                page = context.new_page()
                
                page.goto(url, timeout=30000)
                page.wait_for_load_state('networkidle', timeout=15000)
                
                # Check for CAPTCHA
                if self.detect_captcha(page):
                    logger.warning(f"CAPTCHA detected for {video_id}")
                    # Save debug snapshot
                    snapshot_path = self.debug_dir / f"{video_id}_captcha_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                    page.content()
                    with open(snapshot_path, 'w', encoding='utf-8') as f:
                        f.write(page.content())
                    browser.close()
                    return None
                
                # Extract video data
                video_data = self._extract_video_data(page, video_id)
                
                # Extract channel data
                channel_data = self._extract_channel_data(page)
                
                # Visit channel About page for contact info (reuse same page/browser)
                if channel_data.get('channel_url'):
                    contact_data = self._extract_channel_contact(page, channel_data['channel_url'])
                    channel_data.update(contact_data)
                
                browser.close()
                
                # Merge data
                result = {**video_data, **channel_data}
                result['extraction_path'] = 'playwright'
                
                # Mark all scraped fields
                if result.get('view_count'):
                    result['field_source_view_count'] = 'scraped'
                if result.get('like_count'):
                    result['field_source_like_count'] = 'scraped'
                if result.get('comment_count'):
                    result['field_source_comment_count'] = 'scraped'
                
                # Don't include scraped_at and proxy_used in output
                
                return result
                
            except PlaywrightTimeout as e:
                logger.error(f"Timeout scraping {video_id}: {e}")
                if 'browser' in locals():
                    browser.close()
                return None
            except Exception as e:
                logger.error(f"Error scraping {video_id}: {e}")
                if 'browser' in locals():
                    browser.close()
                return None
    
    def _extract_video_data(self, page: Page, video_id: str) -> Dict:
        """Extract video-level data from page"""
        data = {'video_id': video_id}
        
        try:
            # Wait for key elements to load
            try:
                page.wait_for_selector('h1.ytd-watch-metadata', timeout=10000)
            except:
                logger.warning("Title element not found, continuing anyway")
            
            # Title - multiple selectors
            title_selectors = [
                'h1.ytd-watch-metadata',
                'h1 yt-formatted-string.ytd-watch-metadata',
                'h1.style-scope.ytd-video-primary-info-renderer'
            ]
            for selector in title_selectors:
                try:
                    elem = page.locator(selector).first
                    if elem.count() > 0:
                        data['title'] = elem.inner_text().strip()
                        break
                except:
                    continue
            
            # Description
            desc_selectors = [
                'ytd-text-inline-expander#description-inline-expander',
                '#description-inline-expander yt-attributed-string',
                'ytd-video-secondary-info-renderer #description'
            ]
            for selector in desc_selectors:
                try:
                    elem = page.locator(selector).first
                    if elem.count() > 0:
                        data['description'] = elem.inner_text().strip()
                        break
                except:
                    continue
            
            # View count - wait for it to load
            try:
                page.wait_for_selector('#info span.view-count, ytd-video-view-count-renderer', timeout=5000)
            except:
                pass
            
            view_selectors = [
                '#info span.view-count',
                'ytd-video-view-count-renderer span.view-count',
                '#info-container #count span'
            ]
            for selector in view_selectors:
                try:
                    elem = page.locator(selector).first
                    if elem.count() > 0:
                        view_text = elem.inner_text()
                        parsed = self._parse_count(view_text)
                        if parsed:
                            data['view_count'] = parsed
                            break
                except:
                    continue
            
            # Like count - multiple approaches
            like_selectors = [
                'like-button-view-model button[aria-label*="like"]',
                'segmented-like-dislike-button-view-model button[aria-label*="like"]',
                '#top-level-buttons-computed button[aria-label*="like"]',
                'yt-button-shape button[aria-label*="like"]'
            ]
            for selector in like_selectors:
                try:
                    elem = page.locator(selector).first
                    if elem.count() > 0:
                        # Try aria-label first
                        like_text = elem.get_attribute('aria-label')
                        if not like_text:
                            # Fallback to visible text
                            like_text = elem.inner_text()
                        
                        if like_text:
                            parsed = self._parse_count(like_text)
                            if parsed and parsed < 1000000000:  # Sanity check: less than 1 billion
                                data['like_count'] = parsed
                                logger.debug(f"  Like count: {parsed} from '{like_text}'")
                                break
                except Exception as e:
                    logger.debug(f"  Like selector failed: {e}")
                    continue
            
            # Comment count
            try:
                page.wait_for_selector('#count.ytd-comments-header-renderer', timeout=5000)
                comment_elem = page.locator('#count.ytd-comments-header-renderer').first
                if comment_elem.count() > 0:
                    comment_text = comment_elem.inner_text()
                    parsed = self._parse_count(comment_text)
                    if parsed:
                        data['comment_count'] = parsed
            except:
                pass
            
            # Upload date
            date_selectors = [
                '#info-strings yt-formatted-string',
                'ytd-video-primary-info-renderer #info-strings yt-formatted-string'
            ]
            for selector in date_selectors:
                try:
                    elem = page.locator(selector).first
                    if elem.count() > 0:
                        data['upload_date'] = elem.inner_text().strip()
                        break
                except:
                    continue
            
            # Duration from page content
            page_content = page.content()
            duration_match = re.search(r'"lengthSeconds":"(\d+)"', page_content)
            if duration_match:
                data['duration_seconds'] = int(duration_match.group(1))
            
            # Tags (from meta)
            tags_match = re.search(r'"keywords":\s*\[(.*?)\]', page_content)
            if tags_match:
                tags_str = tags_match.group(1)
                tags = [t.strip('"').strip() for t in tags_str.split(',') if t.strip('"').strip()]
                if tags:
                    data['tags'] = tags
            
            # Is live
            is_live_match = re.search(r'"isLiveContent":(true|false)', page_content)
            if is_live_match:
                data['is_live'] = is_live_match.group(1) == 'true'
            
            # Thumbnail
            data['thumbnail_urls'] = [
                f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
                f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
            ]
            
            # Extract emails and links from description
            if data.get('description'):
                desc_text = data['description']
                
                # Find emails in description
                desc_emails = extract_emails_from_text(desc_text)
                if desc_emails:
                    data['description_emails'] = desc_emails
                    logger.info(f"  Found {len(desc_emails)} email(s) in description")
                
                # Find URLs in description
                desc_urls = extract_urls_from_text(desc_text)
                if desc_urls:
                    data['description_urls'] = desc_urls
                    logger.info(f"  Found {len(desc_urls)} URL(s) in description")
            
        except Exception as e:
            logger.error(f"Error extracting video data: {e}")
        
        return data
    
    def _extract_channel_data(self, page: Page) -> Dict:
        """Extract channel-level data from video page"""
        data = {}
        
        try:
            # Channel name
            channel_elem = page.locator('ytd-channel-name a, #channel-name a').first
            if channel_elem.count() > 0:
                data['channel_name'] = channel_elem.inner_text()
                data['channel_url'] = 'https://www.youtube.com' + channel_elem.get_attribute('href')
                
                # Extract channel ID from URL
                channel_url = data['channel_url']
                if '/channel/' in channel_url:
                    data['channel_id'] = channel_url.split('/channel/')[-1].split('/')[0]
                elif '/@' in channel_url:
                    data['channel_handle'] = channel_url.split('/@')[-1].split('/')[0]
            
            # Extract video category from page metadata
            page_content = page.content()
            category_match = re.search(r'"category":"([^"]+)"', page_content)
            if category_match:
                data['video_category'] = category_match.group(1)
            
        except Exception as e:
            logger.error(f"Error extracting channel data: {e}")
        
        return data
    
    def _extract_channel_contact(self, page: Page, channel_url: str) -> Dict:
        """Visit channel About page to extract public contact info - reuses same page"""
        data = {
            'business_email': None,
            'social_links': [],
            'contact_source': []
        }
        
        try:
            about_url = channel_url.rstrip('/') + '/about'
            logger.info(f"  Visiting channel About page...")
            page.goto(about_url, timeout=15000)
            page.wait_for_load_state('networkidle', timeout=10000)
            
            # Wait for about page content
            try:
                page.wait_for_selector('#page-header, ytd-channel-about-metadata-renderer', timeout=5000)
            except:
                pass
            
            # Extract channel description
            try:
                desc_elem = page.locator('#description-container, ytd-channel-about-metadata-renderer #description').first
                if desc_elem.count() > 0:
                    channel_desc = desc_elem.inner_text().strip()
                    if channel_desc:
                        data['channel_description'] = channel_desc
                        logger.info(f"  Found channel description ({len(channel_desc)} chars)")
            except Exception as e:
                logger.debug(f"  Could not extract channel description: {e}")
            
            # Look for "View email address" button and click it
            email_found = False
            try:
                # Wait a bit for page to fully load
                page.wait_for_timeout(1000)
                
                # Multiple possible selectors for the email button
                email_button_selectors = [
                    'button:has-text("View email address")',
                    'button:has-text("View email")',
                    'yt-button-renderer:has-text("View email")',
                    '#link-list-container button:has-text("email")',
                    'ytd-button-renderer:has-text("email")',
                    'a:has-text("View email address")',
                    '[aria-label*="email"]'
                ]
                
                for selector in email_button_selectors:
                    try:
                        button = page.locator(selector).first
                        if button.count() > 0:
                            if button.is_visible():
                                logger.info(f"  Found 'View email address' button, clicking...")
                                button.click()
                                
                                # Wait longer for email to appear
                                page.wait_for_timeout(3000)
                                
                                # Look for email in the page after clicking
                                page_content = page.content()
                                email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
                                emails = re.findall(email_pattern, page_content)
                                
                                # Filter out common non-business emails
                                filtered_emails = [
                                    e for e in emails 
                                    if not any(x in e.lower() for x in ['noreply', 'example', 'test', 'youtube', 'google'])
                                ]
                                
                                if filtered_emails:
                                    data['business_email'] = filtered_emails[0]
                                    data['contact_source'].append('about_page_email_button')
                                    email_found = True
                                    logger.info(f"  Found email: {filtered_emails[0]}")
                                    break
                            else:
                                logger.debug(f"  Email button not visible")
                    except Exception as e:
                        logger.debug(f"  Email button selector '{selector}' failed: {e}")
                        continue
                
                if not email_found:
                    logger.info(f"  No email button found on About page")
            except Exception as e:
                logger.debug(f"  Could not click email button: {e}")
            
            # If no email found via button, try scraping visible text
            if not email_found:
                try:
                    page_content = page.content()
                    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
                    emails = re.findall(email_pattern, page_content)
                    
                    # Filter out common non-business emails
                    filtered_emails = [
                        e for e in emails 
                        if not any(x in e.lower() for x in ['noreply', 'example', 'test', 'youtube', 'google'])
                    ]
                    
                    if filtered_emails:
                        data['business_email'] = filtered_emails[0]
                        data['contact_source'].append('about_page_email_visible')
                        logger.info(f"  Found email in page source: {filtered_emails[0]}")
                except Exception as e:
                    logger.debug(f"  Could not extract email from page: {e}")
            
            # If still no email found, set explicit message
            if not data['business_email']:
                data['business_email'] = None
                logger.info(f"  No email found")
            
            # Look for social links - improved selectors
            social_patterns = [
                'twitter.com',
                'x.com',
                'instagram.com',
                'facebook.com',
                'tiktok.com',
                'linkedin.com',
                'twitch.tv'
            ]
            
            # Get all links on the page
            all_links = page.locator('a[href]').all()
            social_links_found = []
            seen_urls = set()  # Track unique URLs
            
            for link in all_links:
                try:
                    href = link.get_attribute('href')
                    if not href:
                        continue
                    
                    # Decode YouTube redirect URLs
                    actual_url = decode_youtube_redirect(href)
                    if not actual_url:
                        continue
                    
                    # Check if it's a social media link
                    for pattern in social_patterns:
                        if pattern in actual_url.lower():
                            # Clean up the URL
                            if actual_url.startswith('http'):
                                clean_url = actual_url
                            elif actual_url.startswith('//'):
                                clean_url = 'https:' + actual_url
                            else:
                                continue
                            
                            # Remove trailing slashes and query params for deduplication
                            clean_url_base = clean_url.rstrip('/').split('?')[0]
                            
                            # Only add if not already seen
                            if clean_url_base not in seen_urls:
                                social_links_found.append(clean_url.rstrip('/'))
                                seen_urls.add(clean_url_base)
                            break
                except Exception as e:
                    logger.debug(f"Error processing link: {e}")
                    continue
            
            if social_links_found:
                data['social_links'] = social_links_found
                data['contact_source'].append('about_page_social')
                logger.info(f"  Found {len(social_links_found)} social links")
            
        except Exception as e:
            logger.warning(f"  Could not extract channel contact info: {e}")
        
        return data
    
    @staticmethod
    def _parse_count(text: str) -> Optional[int]:
        """Parse count from text like '1.2M views' or '1,234 likes'"""
        if not text:
            return None
        
        # Remove non-numeric except digits, dots, commas, K, M, B
        text = re.sub(r'[^\d.,KMB]', '', text.upper())
        
        multipliers = {'K': 1000, 'M': 1000000, 'B': 1000000000}
        
        for suffix, multiplier in multipliers.items():
            if suffix in text:
                num = text.replace(suffix, '').replace(',', '')
                try:
                    return int(float(num) * multiplier)
                except:
                    return None
        
        try:
            return int(text.replace(',', ''))
        except:
            return None

    def scrape_video(self, video_id: str, video_num: int, total: int) -> Optional[Dict]:
        """Scrape a single video with retry logic and proper proxy rotation"""
        logger.info(f"[{video_num}/{total}] Processing {video_id}")
        
        for attempt in range(self.args.proxy_retries):
            # Always get next proxy (rotates through list)
            proxy = self.proxy_manager.get_next_proxy()
            
            if proxy:
                proxy_display = proxy.split(':')[0]
                logger.info(f"  Attempt {attempt + 1}/{self.args.proxy_retries} with proxy {proxy_display}")
            else:
                logger.info(f"  Attempt {attempt + 1}/{self.args.proxy_retries} without proxy")
            
            result = self.scrape_video_with_playwright(video_id, proxy)
            
            if result:
                logger.info(f"  ✓ Scraped successfully — channel: {result.get('channel_name', 'Unknown')}")
                return result
            else:
                logger.warning(f"  ✗ Failed (CAPTCHA or error)")
                if proxy:
                    self.proxy_manager.report_failure(proxy)
        
        # All retries failed
        logger.error(f"  ✗ Skipped after {self.args.proxy_retries} attempts")
        self.failed_videos.append({
            'video_id': video_id,
            'reason': 'skipped_due_to_captcha',
            'attempts': self.args.proxy_retries
        })
        return None
    
    def enrich_with_api(self, videos: List[Dict]):
        """Enrich scraped data with YouTube API - only fills in missing data"""
        if not self.api.api_key:
            logger.warning("No API key provided, skipping API enrichment")
            return
        
        video_ids = [v['video_id'] for v in videos]
        
        # Check what's missing from scraped data
        needs_video_data = any(
            not v.get('view_count') or 
            not v.get('like_count') or 
            not v.get('title') or
            not v.get('channel_id')
            for v in videos
        )
        
        # Fetch video details only if needed
        if needs_video_data:
            logger.info(f"Fetching API data to fill missing fields for {len(video_ids)} videos")
            api_videos = self.api.get_video_details(video_ids)
            
            for video in videos:
                vid = video['video_id']
                if vid in api_videos:
                    api_data = api_videos[vid]
                    stats = api_data.get('statistics', {})
                    snippet = api_data.get('snippet', {})
                    
                    # Only fill missing data
                    if not video.get('view_count'):
                        video['view_count'] = int(stats.get('viewCount', 0))
                        video['field_source_view_count'] = 'api'
                    else:
                        video['field_source_view_count'] = 'scraped'
                    
                    if not video.get('like_count'):
                        video['like_count'] = int(stats.get('likeCount', 0))
                        video['field_source_like_count'] = 'api'
                    else:
                        video['field_source_like_count'] = 'scraped'
                    
                    if not video.get('comment_count'):
                        video['comment_count'] = int(stats.get('commentCount', 0))
                        video['field_source_comment_count'] = 'api'
                    
                    # Fill missing metadata
                    if not video.get('title'):
                        video['title'] = snippet.get('title')
                    if not video.get('description'):
                        video['description'] = snippet.get('description')
                    if not video.get('tags'):
                        video['tags'] = snippet.get('tags', [])
                    if not video.get('channel_id'):
                        video['channel_id'] = snippet.get('channelId')
        
        # Fetch channel details (subscriber count usually not on page)
        channel_ids = list(set([v.get('channel_id') for v in videos if v.get('channel_id')]))
        if channel_ids:
            logger.info(f"Fetching channel stats for {len(channel_ids)} channels")
            api_channels = self.api.get_channel_details(channel_ids)
            
            for video in videos:
                cid = video.get('channel_id')
                if cid and cid in api_channels:
                    channel_stats = api_channels[cid].get('statistics', {})
                    video['channel_subscriber_count'] = int(channel_stats.get('subscriberCount', 0))
                    video['channel_video_count'] = int(channel_stats.get('videoCount', 0))
                    video['channel_view_count'] = int(channel_stats.get('viewCount', 0))
                    video['field_source_channel_stats'] = 'api'
        
        if self.api.api_calls > 0:
            logger.info(f"Total API calls made: {self.api.api_calls}")
    
    def save_results(self, incremental=False):
        """Save results to CSV and JSON
        
        Args:
            incremental: If True, saves after each video (real-time updates)
        """
        if not hasattr(self, 'output_timestamp'):
            self.output_timestamp = datetime.now().strftime('%Y-%m-%d_%H%M')
        
        timestamp = self.output_timestamp
        
        # Save successful scrapes
        if self.scraped_videos:
            csv_path = self.results_dir / f"{timestamp}_videos.csv"
            json_path = self.results_dir / f"{timestamp}_videos.json"
            
            # Convert to DataFrame
            df = pd.DataFrame(self.scraped_videos)
            
            # Flatten lists for CSV
            df_csv = df.copy()
            for col in df_csv.columns:
                if df_csv[col].apply(lambda x: isinstance(x, (list, dict))).any():
                    df_csv[col] = df_csv[col].apply(lambda x: json.dumps(x) if isinstance(x, (list, dict)) else x)
            
            df_csv.to_csv(csv_path, index=False, encoding='utf-8')
            
            # Save JSON with full structure
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(self.scraped_videos, f, indent=2, ensure_ascii=False)
            
            if incremental:
                logger.info(f"  💾 Saved progress: {len(self.scraped_videos)} video(s) → {csv_path.name}")
            else:
                logger.info(f"CSV saved to {csv_path}")
                logger.info(f"JSON saved to {json_path}")
        
        # Save failed videos
        if self.failed_videos:
            failed_path = self.results_dir / 'failed.csv'
            df_failed = pd.DataFrame(self.failed_videos)
            df_failed.to_csv(failed_path, index=False, encoding='utf-8')
            if not incremental:
                logger.info(f"Failed videos saved to {failed_path}")
    
    def run(self, video_urls: List[str]):
        """Main scraping workflow"""
        # Extract and validate video IDs
        video_ids = []
        
        for url in video_urls:
            url = url.strip()
            if not url:
                continue
            
            # Check if it's a search results URL
            if self.is_search_url(url):
                logger.info(f"\n{'='*60}")
                logger.info("Detected YouTube search results URL")
                logger.info(f"{'='*60}\n")
                
                # Extract videos from search results (up to 30 videos)
                search_video_ids = self.extract_videos_from_search(url, max_videos=30)
                
                if search_video_ids:
                    logger.info(f"Will scrape {len(search_video_ids)} videos from search results\n")
                    video_ids.extend(search_video_ids)
                else:
                    logger.error("Failed to extract videos from search results")
            else:
                # Regular video URL
                video_id = self.extract_video_id(url)
                if video_id:
                    video_ids.append(video_id)
                else:
                    logger.warning(f"Invalid URL, skipping: {url}")
        
        if not video_ids:
            logger.error("No valid video URLs provided")
            return
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Starting scrape for {len(video_ids)} videos")
        logger.info(f"Results will be saved in real-time after each video")
        logger.info(f"{'='*60}\n")
        
        # Initialize output timestamp for consistent filenames
        self.output_timestamp = datetime.now().strftime('%Y-%m-%d_%H%M')
        
        # Scrape each video
        for i, video_id in enumerate(video_ids, 1):
            result = self.scrape_video(video_id, i, len(video_ids))
            if result:
                self.scraped_videos.append(result)
                
                # Save immediately after each successful scrape (real-time updates)
                self.save_results(incremental=True)
        
        # Final API enrichment for all videos at once
        if self.scraped_videos:
            logger.info(f"\n{'='*60}")
            logger.info("Enriching data with YouTube API...")
            logger.info(f"{'='*60}\n")
            self.enrich_with_api(self.scraped_videos)
            
            # Save final enriched results
            self.save_results(incremental=False)
        
        # Summary
        logger.info(f"\n{'='*60}")
        logger.info(f"Processed {len(video_ids)} videos — {len(self.scraped_videos)} scraped, {len(self.failed_videos)} skipped")
        logger.info(f"{'='*60}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='YouTube Video Scraper')
    parser.add_argument('--proxy_retries', type=int, default=3, help='Number of proxy retries per video')
    parser.add_argument('--blacklist_threshold', type=int, default=5, help='Failures before blacklisting proxy')
    
    args = parser.parse_args()
    
    # Get user input
    print("\n" + "="*60)
    print("YouTube Video Scraper")
    print("="*60)
    print("\nSupported URL types:")
    print("  1. Individual video: https://www.youtube.com/watch?v=VIDEO_ID")
    print("  2. Search results: https://www.youtube.com/results?search_query=YOUR_QUERY")
    print("     (Will scrape up to 30 videos from search)")
    print("\nYou can mix both types, separated by commas")
    print("="*60)
    
    urls_input = input("\nEnter YouTube URLs (comma separated): ")
    
    if not urls_input.strip():
        print("No URLs provided. Exiting.")
        return
    
    video_urls = [url.strip() for url in urls_input.split(',')]
    
    # Initialize and run scraper
    scraper = YouTubeScraper(args)
    scraper.run(video_urls)


if __name__ == '__main__':
    main()
