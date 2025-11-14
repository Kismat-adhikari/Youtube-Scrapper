#!/usr/bin/env python3
"""
YouTube Channel Finder by Niche & Country
Searches for YouTube channels using API + Playwright scraping
"""

import os
import re
import json
import argparse
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Set
from urllib.parse import urlparse

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


def validate_email(email: str) -> bool:
    """Validate email format and domain"""
    if not email:
        return False
    
    # Basic format check
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False
    
    # Check for suspicious patterns
    suspicious = ['noreply', 'no-reply', 'donotreply', 'example', 'test', 'fake']
    email_lower = email.lower()
    if any(pattern in email_lower for pattern in suspicious):
        return False
    
    # Check domain
    try:
        domain = email.split('@')[1]
        # Filter out common non-business domains
        blocked_domains = ['youtube.com', 'google.com', 'gmail.com', 'yahoo.com', 'hotmail.com']
        if domain.lower() in blocked_domains:
            return False
        return True
    except:
        return False


class ProxyManager:
    """Manages proxy rotation and blacklisting"""
    
    def __init__(self, proxy_file: str = 'proxies.txt', blacklist_threshold: int = 5):
        self.proxies = []
        self.proxy_failures = {}
        self.blacklist_threshold = blacklist_threshold
        self.current_index = 0
        self.successful_uses = 0
        self.rotation_interval = 4
        
        if os.path.exists(proxy_file):
            self._load_proxies(proxy_file)
    
    def _load_proxies(self, proxy_file: str):
        """Load proxies from file"""
        with open(proxy_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    self.proxies.append(line)
        logger.info(f"Loaded {len(self.proxies)} proxies")
    
    def get_next_proxy(self, force_rotate: bool = False) -> Optional[str]:
        """Get next available proxy"""
        if not self.proxies:
            return None
        
        # Force rotation on failure or after 4 successful uses
        if force_rotate or self.successful_uses >= self.rotation_interval:
            self.current_index = (self.current_index + 1) % len(self.proxies)
            self.successful_uses = 0
            if not force_rotate:
                logger.info(f"  🔄 Rotating proxy after {self.rotation_interval} successful channels")
        
        # Find next non-blacklisted proxy
        attempts = 0
        while attempts < len(self.proxies):
            proxy = self.proxies[self.current_index]
            
            if self.proxy_failures.get(proxy, 0) < self.blacklist_threshold:
                return proxy
            
            self.current_index = (self.current_index + 1) % len(self.proxies)
            attempts += 1
        
        return None
    
    def report_success(self):
        """Report successful proxy use"""
        self.successful_uses += 1
    
    def report_failure(self, proxy: str):
        """Report proxy failure"""
        if proxy:
            self.proxy_failures[proxy] = self.proxy_failures.get(proxy, 0) + 1
            if self.proxy_failures[proxy] >= self.blacklist_threshold:
                logger.warning(f"Proxy {proxy} blacklisted after {self.blacklist_threshold} failures")
            self.successful_uses = 0


class YouTubeAPI:
    """YouTube Data API v3 client"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.api_calls = 0
        self.cache = {}
    
    def search_channels(self, query: str, max_results: int = 50, country: Optional[str] = None) -> List[Dict]:
        """Search for channels matching query"""
        results = []
        page_token = None
        
        while len(results) < max_results:
            url = f"{self.base_url}/search"
            params = {
                'part': 'snippet',
                'q': query,
                'type': 'channel,video',
                'maxResults': min(50, max_results - len(results)),
                'key': self.api_key
            }
            
            if country:
                params['regionCode'] = country
            
            if page_token:
                params['pageToken'] = page_token
            
            try:
                response = requests.get(url, params=params)
                response.raise_for_status()
                self.api_calls += 1
                
                data = response.json()
                results.extend(data.get('items', []))
                
                page_token = data.get('nextPageToken')
                if not page_token:
                    break
                
                logger.info(f"API search: fetched {len(results)} results so far")
            except Exception as e:
                logger.error(f"API search failed: {e}")
                break
        
        return results[:max_results]
    
    def get_channel_details(self, channel_ids: List[str]) -> Dict:
        """Fetch channel details for multiple channel IDs"""
        if not channel_ids:
            return {}
        
        results = {}
        for i in range(0, len(channel_ids), 50):
            batch = channel_ids[i:i+50]
            
            # Check cache first
            uncached = [cid for cid in batch if cid not in self.cache]
            
            if uncached:
                url = f"{self.base_url}/channels"
                params = {
                    'part': 'snippet,statistics,contentDetails,brandingSettings',
                    'id': ','.join(uncached),
                    'key': self.api_key
                }
                
                try:
                    response = requests.get(url, params=params)
                    response.raise_for_status()
                    self.api_calls += 1
                    
                    data = response.json()
                    for item in data.get('items', []):
                        self.cache[item['id']] = item
                    
                    logger.info(f"API channels: fetched {len(uncached)} channels")
                except Exception as e:
                    logger.error(f"API channels failed: {e}")
            
            # Get from cache
            for cid in batch:
                if cid in self.cache:
                    results[cid] = self.cache[cid]
        
        return results


class ChannelScraper:
    """Scrapes channel data using Playwright"""
    
    def __init__(self, proxy_manager: ProxyManager):
        self.proxy_manager = proxy_manager
    
    def scrape_channel(self, channel_id: str, channel_url: str, target_location: Optional[str] = None) -> Dict:
        """Scrape channel About page and sample videos"""
        data = {
            'channel_id': channel_id,
            'channel_url': channel_url,
            'about_text': None,
            'social_links': [],
            'websites': [],
            'emails': [],
            'detected_location': {},
            'location_confidence': 0,
            'sample_videos': [],
            'target_location': target_location
        }
        
        proxy = self.proxy_manager.get_next_proxy()
        
        with sync_playwright() as p:
            browser_args = {'headless': True}  # Always headless
            
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
            
            try:
                browser = p.chromium.launch(**browser_args)
                context = browser.new_context()
                page = context.new_page()
                
                # Scrape About page
                about_url = channel_url.rstrip('/') + '/about'
                logger.info(f"  Scraping About page: {about_url}")
                
                page.goto(about_url, timeout=30000)
                page.wait_for_load_state('networkidle', timeout=15000)
                
                # Extract About text
                about_data = self._extract_about_page(page, target_location)
                data.update(about_data)
                
                # Scrape sample videos
                videos_url = channel_url.rstrip('/') + '/videos'
                logger.info(f"  Scraping sample videos...")
                page.goto(videos_url, timeout=30000)
                page.wait_for_load_state('networkidle', timeout=15000)
                
                sample_videos = self._extract_sample_videos(page, target_location)
                data['sample_videos'] = sample_videos
                
                if sample_videos:
                    logger.info(f"  Found {len(sample_videos)} sample video(s)")
                else:
                    logger.info(f"  No sample videos found")
                
                # Aggregate location data from all sources
                location_result = self._aggregate_location_data(data, target_location)
                data['detected_location'] = location_result
                data['location_confidence'] = location_result.get('confidence', 0)
                
                browser.close()
                
            except Exception as e:
                logger.error(f"  Error scraping channel: {e}")
                if 'browser' in locals():
                    browser.close()
        
        return data

    
    def _extract_about_page(self, page: Page, target_location: Optional[str] = None) -> Dict:
        """Extract data from About page"""
        data = {
            'about_text': None,
            'social_links': [],
            'websites': [],
            'emails': [],
            'detected_country': None
        }
        
        try:
            # Wait for content
            page.wait_for_selector('#page-header, ytd-channel-about-metadata-renderer', timeout=5000)
        except:
            pass
        
        # Extract About description
        try:
            desc_elem = page.locator('#description-container, ytd-channel-about-metadata-renderer #description').first
            if desc_elem.count() > 0:
                about_text = desc_elem.inner_text().strip()
                if about_text:
                    data['about_text'] = about_text
                    
                    # Extract emails from About text
                    emails = self._extract_emails(about_text)
                    if emails:
                        data['emails'].extend(emails)
        except Exception as e:
            logger.debug(f"  Could not extract About text: {e}")
        
        # Look for "View email address" button and click it
        email_found = False
        try:
            page.wait_for_timeout(1000)
            
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
                    if button.count() > 0 and button.is_visible():
                        logger.info(f"  Found 'View email address' button, clicking...")
                        button.click()
                        page.wait_for_timeout(3000)
                        
                        page_content = page.content()
                        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
                        emails = re.findall(email_pattern, page_content)
                        
                        valid_emails = [e for e in emails if validate_email(e)]
                        
                        if valid_emails:
                            for email in valid_emails:
                                if email not in data['emails']:
                                    data['emails'].append(email)
                            email_found = True
                            logger.info(f"  Found email: {valid_emails[0]}")
                            break
                except Exception as e:
                    logger.debug(f"  Email button selector '{selector}' failed: {e}")
                    continue
            
            if not email_found:
                logger.info(f"  No email button found on About page")
        except Exception as e:
            logger.debug(f"  Could not click email button: {e}")
        
        # Extract social links and websites
        try:
            all_links = page.locator('a[href]').all()
            
            for link in all_links:
                try:
                    href = link.get_attribute('href')
                    if not href:
                        continue
                    
                    # Decode YouTube redirects
                    actual_url = self._decode_youtube_redirect(href)
                    if not actual_url:
                        continue
                    
                    # Categorize link
                    if self._is_social_link(actual_url):
                        if actual_url not in data['social_links']:
                            data['social_links'].append(actual_url)
                    elif self._is_website(actual_url):
                        if actual_url not in data['websites']:
                            data['websites'].append(actual_url)
                except:
                    continue
        except Exception as e:
            logger.debug(f"  Could not extract links: {e}")
        
        return data
    
    def _extract_sample_videos(self, page: Page, target_location: Optional[str] = None, max_videos: int = 3) -> List[Dict]:
        """Extract sample videos from channel"""
        videos = []
        
        try:
            # Wait for video grid
            page.wait_for_selector('ytd-grid-video-renderer, ytd-rich-item-renderer', timeout=5000)
            
            # Try multiple selectors for video elements
            video_elements = page.locator('ytd-grid-video-renderer').all()
            if not video_elements:
                video_elements = page.locator('ytd-rich-item-renderer').all()
            
            logger.debug(f"  Found {len(video_elements)} video elements")
            
            for i, elem in enumerate(video_elements[:max_videos]):
                try:
                    # Try multiple selectors for video link
                    link_elem = elem.locator('#video-title, #video-title-link').first
                    if link_elem.count() == 0:
                        logger.debug(f"  Video {i}: No link element found")
                        continue
                    
                    video_url = link_elem.get_attribute('href')
                    video_title = link_elem.get_attribute('title')
                    
                    if not video_title:
                        video_title = link_elem.inner_text().strip()
                    
                    if video_url and video_title:
                        # Extract video ID
                        video_id = None
                        if '/watch?v=' in video_url:
                            video_id = video_url.split('/watch?v=')[-1].split('&')[0]
                        elif '/shorts/' in video_url:
                            video_id = video_url.split('/shorts/')[-1].split('?')[0]
                        
                        # Build full URL
                        if video_url.startswith('/'):
                            full_url = f"https://www.youtube.com{video_url}"
                        else:
                            full_url = video_url
                        
                        video_data = {
                            'video_id': video_id,
                            'video_title': video_title,
                            'video_url': full_url
                        }
                        
                        # Check video title for location mentions
                        if target_location and video_title:
                            location_info = self._extract_location_from_text(video_title, target_location)
                            if location_info.get('country') or location_info.get('city'):
                                video_data['location_mention'] = location_info
                        
                        videos.append(video_data)
                        logger.debug(f"  Extracted video: {video_title[:50]}")
                    else:
                        logger.debug(f"  Video {i}: Missing URL or title")
                except Exception as e:
                    logger.debug(f"  Could not extract video {i}: {e}")
                    continue
        except Exception as e:
            logger.warning(f"  Could not extract sample videos: {e}")
        
        return videos
    
    @staticmethod
    def _decode_youtube_redirect(url: str) -> Optional[str]:
        """Decode YouTube redirect URLs"""
        if 'youtube.com/redirect' in url:
            try:
                from urllib.parse import urlparse, parse_qs, unquote
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                if 'q' in params:
                    return unquote(params['q'][0])
            except:
                return None
        return url
    
    @staticmethod
    def _is_social_link(url: str) -> bool:
        """Check if URL is a social media link"""
        social_domains = ['twitter.com', 'x.com', 'instagram.com', 'facebook.com', 
                         'tiktok.com', 'linkedin.com', 'twitch.tv']
        return any(domain in url.lower() for domain in social_domains)
    
    def _aggregate_location_data(self, data: Dict, target_location: Optional[str]) -> Dict:
        """Aggregate location data from all sources"""
        location_result = {
            'country': None,
            'city': None,
            'confidence': 0,
            'sources': []
        }
        
        # Check About text
        if data.get('about_text'):
            about_location = self._extract_location_from_text(data['about_text'], target_location)
            if about_location.get('country'):
                location_result['country'] = about_location['country']
                location_result['confidence'] += about_location.get('confidence', 0)
                location_result['sources'].append('about_page')
            if about_location.get('city'):
                location_result['city'] = about_location['city']
        
        # Check video titles
        for video in data.get('sample_videos', []):
            if video.get('location_mention'):
                loc = video['location_mention']
                if loc.get('country') and not location_result['country']:
                    location_result['country'] = loc['country']
                if loc.get('city') and not location_result['city']:
                    location_result['city'] = loc['city']
                location_result['confidence'] += loc.get('confidence', 0) * 0.5  # Lower weight
                if 'video_titles' not in location_result['sources']:
                    location_result['sources'].append('video_titles')
        
        # Check domain from websites
        for website in data.get('websites', []):
            domain_country = self._infer_country_from_domain(website)
            if domain_country and not location_result['country']:
                location_result['country'] = domain_country
                location_result['confidence'] += 5
                location_result['sources'].append('domain')
        
        # Cap confidence at 20 for location scoring
        location_result['confidence'] = min(20, location_result['confidence'])
        
        return location_result
    
    @staticmethod
    def _infer_country_from_domain(url: str) -> Optional[str]:
        """Infer country from domain TLD"""
        tld_map = {
            '.uk': 'UK',
            '.co.uk': 'UK',
            '.ca': 'Canada',
            '.au': 'Australia',
            '.de': 'Germany',
            '.fr': 'France',
            '.es': 'Spain',
            '.it': 'Italy',
            '.br': 'Brazil',
            '.mx': 'Mexico',
            '.in': 'India',
            '.jp': 'Japan',
            '.kr': 'South Korea',
            '.nl': 'Netherlands',
            '.ph': 'Philippines'
        }
        
        url_lower = url.lower()
        for tld, country in tld_map.items():
            if url_lower.endswith(tld) or tld in url_lower:
                return country
        
        return None
    
    @staticmethod
    def _is_website(url: str) -> bool:
        """Check if URL is a website (not YouTube or social)"""
        if not url.startswith('http'):
            return False
        
        excluded = ['youtube.com', 'youtu.be', 'twitter.com', 'x.com', 'instagram.com', 
                   'facebook.com', 'tiktok.com', 'linkedin.com', 'twitch.tv']
        
        return not any(domain in url.lower() for domain in excluded)
    
    @staticmethod
    def _extract_emails(text: str) -> List[str]:
        """Extract and validate email addresses from text"""
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(email_pattern, text)
        
        # Validate each email
        valid_emails = [e for e in emails if validate_email(e)]
        
        return valid_emails
    
    @staticmethod
    def _extract_location_from_text(text: str, target_location: Optional[str] = None) -> Dict:
        """Extract country and city mentions from text"""
        # Comprehensive location database
        locations = {
            'USA': {
                'keywords': ['USA', 'United States', 'America', 'American', 'US'],
                'cities': ['New York', 'NYC', 'Los Angeles', 'LA', 'Chicago', 'Houston', 
                          'Miami', 'Phoenix', 'Philadelphia', 'San Antonio', 'San Diego',
                          'Dallas', 'San Jose', 'Austin', 'Jacksonville', 'San Francisco',
                          'Seattle', 'Denver', 'Boston', 'Portland', 'Las Vegas', 'Atlanta']
            },
            'UK': {
                'keywords': ['UK', 'United Kingdom', 'Britain', 'British', 'England', 'Scotland', 'Wales'],
                'cities': ['London', 'Manchester', 'Birmingham', 'Liverpool', 'Leeds', 
                          'Glasgow', 'Edinburgh', 'Bristol', 'Cardiff', 'Belfast']
            },
            'Canada': {
                'keywords': ['Canada', 'Canadian'],
                'cities': ['Toronto', 'Vancouver', 'Montreal', 'Calgary', 'Ottawa', 
                          'Edmonton', 'Winnipeg', 'Quebec City']
            },
            'Australia': {
                'keywords': ['Australia', 'Australian', 'Aussie'],
                'cities': ['Sydney', 'Melbourne', 'Brisbane', 'Perth', 'Adelaide', 
                          'Gold Coast', 'Canberra']
            },
            'India': {
                'keywords': ['India', 'Indian'],
                'cities': ['Mumbai', 'Delhi', 'Bangalore', 'Hyderabad', 'Chennai', 
                          'Kolkata', 'Pune', 'Ahmedabad']
            },
            'Germany': {
                'keywords': ['Germany', 'German', 'Deutschland'],
                'cities': ['Berlin', 'Munich', 'Hamburg', 'Frankfurt', 'Cologne', 'Stuttgart']
            },
            'France': {
                'keywords': ['France', 'French'],
                'cities': ['Paris', 'Marseille', 'Lyon', 'Toulouse', 'Nice', 'Bordeaux']
            },
            'Spain': {
                'keywords': ['Spain', 'Spanish', 'España'],
                'cities': ['Madrid', 'Barcelona', 'Valencia', 'Seville', 'Malaga']
            },
            'Brazil': {
                'keywords': ['Brazil', 'Brazilian', 'Brasil'],
                'cities': ['São Paulo', 'Rio de Janeiro', 'Brasília', 'Salvador', 'Fortaleza']
            },
            'Mexico': {
                'keywords': ['Mexico', 'Mexican', 'México'],
                'cities': ['Mexico City', 'Guadalajara', 'Monterrey', 'Cancun', 'Tijuana']
            },
            'Italy': {
                'keywords': ['Italy', 'Italian', 'Italia'],
                'cities': ['Rome', 'Milan', 'Naples', 'Turin', 'Florence', 'Venice']
            },
            'Netherlands': {
                'keywords': ['Netherlands', 'Dutch', 'Holland'],
                'cities': ['Amsterdam', 'Rotterdam', 'The Hague', 'Utrecht']
            },
            'Japan': {
                'keywords': ['Japan', 'Japanese'],
                'cities': ['Tokyo', 'Osaka', 'Kyoto', 'Yokohama', 'Nagoya']
            },
            'South Korea': {
                'keywords': ['Korea', 'Korean', 'South Korea'],
                'cities': ['Seoul', 'Busan', 'Incheon', 'Daegu']
            },
            'Philippines': {
                'keywords': ['Philippines', 'Filipino', 'Pinoy'],
                'cities': ['Manila', 'Quezon City', 'Davao', 'Cebu']
            }
        }
        
        result = {
            'country': None,
            'city': None,
            'confidence': 0
        }
        
        text_lower = text.lower()
        
        # Check for country keywords
        for country, data in locations.items():
            for keyword in data['keywords']:
                if keyword.lower() in text_lower:
                    result['country'] = country
                    result['confidence'] += 10
                    break
            
            # Check for city mentions
            for city in data['cities']:
                if city.lower() in text_lower:
                    if not result['city']:
                        result['city'] = city
                    if not result['country']:
                        result['country'] = country
                    result['confidence'] += 15
                    
                    # If target location matches city, boost confidence
                    if target_location and city.lower() == target_location.lower():
                        result['confidence'] += 20
                    break
        
        # If target location is a country code, check match
        if target_location and result['country']:
            if target_location.upper() in ['US', 'USA'] and result['country'] == 'USA':
                result['confidence'] += 20
            elif target_location.upper() == result['country'].upper():
                result['confidence'] += 20
        
        return result


class ChannelFinder:
    """Main channel finder orchestrator"""
    
    def __init__(self, api_key: str):
        self.api = YouTubeAPI(api_key)
        self.proxy_manager = ProxyManager()
        self.scraper = ChannelScraper(self.proxy_manager)
        self.results_dir = Path('results')
        self.results_dir.mkdir(exist_ok=True)
        self.scraped_channel_ids: Set[str] = set()
        self.start_time = None
        
        # Load previously scraped channel IDs for duplicate detection
        self._load_scraped_history()
    
    def _load_scraped_history(self):
        """Load previously scraped channel IDs from existing CSV files"""
        try:
            csv_files = list(self.results_dir.glob('*_channels.csv'))
            for csv_file in csv_files:
                try:
                    df = pd.read_csv(csv_file)
                    if 'channel_id' in df.columns:
                        self.scraped_channel_ids.update(df['channel_id'].dropna().astype(str).tolist())
                except Exception as e:
                    logger.debug(f"Could not load history from {csv_file}: {e}")
            
            if self.scraped_channel_ids:
                logger.info(f"Loaded {len(self.scraped_channel_ids)} previously scraped channel IDs")
        except Exception as e:
            logger.debug(f"Could not load scraping history: {e}")
    
    def _calculate_eta(self, current: int, total: int) -> str:
        """Calculate estimated time remaining"""
        if not self.start_time or current == 0:
            return "calculating..."
        
        elapsed = time.time() - self.start_time
        avg_time_per_channel = elapsed / current
        remaining_channels = total - current
        eta_seconds = avg_time_per_channel * remaining_channels
        
        # Format ETA
        if eta_seconds < 60:
            return f"{int(eta_seconds)}s"
        elif eta_seconds < 3600:
            return f"{int(eta_seconds / 60)}m {int(eta_seconds % 60)}s"
        else:
            hours = int(eta_seconds / 3600)
            minutes = int((eta_seconds % 3600) / 60)
            return f"{hours}h {minutes}m"
    
    def _print_progress(self, current: int, total: int, channel_name: str):
        """Print progress bar with ETA"""
        percentage = (current / total) * 100
        eta = self._calculate_eta(current, total)
        bar_length = 30
        filled = int(bar_length * current / total)
        bar = '█' * filled + '░' * (bar_length - filled)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Progress: [{bar}] {percentage:.1f}% ({current}/{total})")
        logger.info(f"ETA: {eta} | Current: {channel_name}")
        logger.info(f"{'='*60}\n")
    
    def search_channels(self, niche: str, sub_niche: Optional[str] = None, 
                       location: Optional[str] = None, max_results: int = 50,
                       min_subscribers: Optional[int] = None) -> List[Dict]:
        """Search for channels by niche and country"""
        
        # Build search query
        query = niche
        if sub_niche:
            query += f" {sub_niche}"
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Searching for: {query}")
        if location:
            logger.info(f"Location filter: {location}")
        if min_subscribers:
            logger.info(f"Min subscribers: {min_subscribers:,}")
        logger.info(f"{'='*60}\n")
        
        # Determine if location is country code or city
        country_code = None
        if location and len(location) == 2:
            country_code = location.upper()
        
        # Step 1: Search via API
        logger.info("Step 1: Searching YouTube API...")
        search_results = self.api.search_channels(query, max_results * 2, country_code)
        
        # Extract unique channel IDs
        channel_ids = set()
        video_to_channel = {}
        
        for item in search_results:
            if item['id']['kind'] == 'youtube#channel':
                channel_ids.add(item['id']['channelId'])
            elif item['id']['kind'] == 'youtube#video':
                channel_id = item['snippet']['channelId']
                video_id = item['id']['videoId']
                channel_ids.add(channel_id)
                if channel_id not in video_to_channel:
                    video_to_channel[channel_id] = video_id
        
        logger.info(f"Found {len(channel_ids)} unique channels")
        
        # Step 2: Get channel details from API
        logger.info("\nStep 2: Fetching channel details from API...")
        channel_details = self.api.get_channel_details(list(channel_ids))
        
        # Filter by min subscribers
        if min_subscribers:
            filtered = {}
            for cid, details in channel_details.items():
                subs = int(details.get('statistics', {}).get('subscriberCount', 0))
                if subs >= min_subscribers:
                    filtered[cid] = details
            channel_details = filtered
            logger.info(f"Filtered to {len(channel_details)} channels with {min_subscribers:,}+ subscribers")
        
        # Remove already-scraped channels (duplicate detection)
        original_count = len(channel_details)
        channel_details = {cid: data for cid, data in channel_details.items() if cid not in self.scraped_channel_ids}
        
        if len(channel_details) < original_count:
            skipped = original_count - len(channel_details)
            logger.info(f"Skipped {skipped} already-scraped channel(s)")
        
        if not channel_details:
            logger.info("All channels have already been scraped!")
            return []
        
        # Step 3: Scrape each channel with progress tracking
        logger.info(f"\nStep 3: Scraping {len(channel_details)} channels...")
        logger.info(f"Results will be saved in real-time after each channel")
        enriched_channels = []
        
        # Initialize timestamp for consistent filenames
        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M')
        niche_slug = re.sub(r'[^\w\s-]', '', query).strip().replace(' ', '_')
        self.start_time = time.time()
        
        for i, (channel_id, api_data) in enumerate(channel_details.items(), 1):
            channel_name = api_data['snippet']['title']
            
            # Show progress every 5 channels or on first/last
            if i == 1 or i == len(channel_details) or i % 5 == 0:
                self._print_progress(i, len(channel_details), channel_name)
            
            logger.info(f"\n[{i}/{len(channel_details)}] Processing: {channel_name}")
            
            channel_url = f"https://www.youtube.com/channel/{channel_id}"
            
            # Scrape channel
            scraped_data = self.scraper.scrape_channel(channel_id, channel_url, location)
            
            # Merge API + scraped data
            merged = self._merge_channel_data(api_data, scraped_data, video_to_channel.get(channel_id))
            
            # Calculate confidence score
            merged['confidence_score'] = self._calculate_confidence(merged, query, location)
            
            enriched_channels.append(merged)
            self.scraped_channel_ids.add(channel_id)
            
            # Save immediately after each channel (real-time updates)
            self._save_incremental(enriched_channels, timestamp, niche_slug)
        
        # Step 4: Rank by confidence
        enriched_channels.sort(key=lambda x: x['confidence_score'], reverse=True)
        
        # Final save with sorted results
        self._save_final(enriched_channels[:max_results], timestamp, niche_slug)
        
        return enriched_channels[:max_results]
    
    def _save_incremental(self, channels: List[Dict], timestamp: str, niche_slug: str):
        """Save results incrementally after each channel"""
        if not channels:
            return
        
        csv_path = self.results_dir / f"{timestamp}_{niche_slug}_channels.csv"
        json_path = self.results_dir / f"{timestamp}_{niche_slug}_channels.json"
        
        # Prepare data for CSV
        csv_data = []
        for ch in channels:
            row = ch.copy()
            # Convert lists to JSON strings for CSV
            for key in ['social_links', 'websites', 'all_emails', 'location_sources', 'sample_videos']:
                if key in row and isinstance(row[key], (list, dict)):
                    row[key] = json.dumps(row[key])
            csv_data.append(row)
        
        # Save CSV
        df = pd.DataFrame(csv_data)
        df.to_csv(csv_path, index=False, encoding='utf-8')
        
        # Save JSON
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(channels, f, indent=2, ensure_ascii=False)
        
        logger.info(f"  💾 Saved progress: {len(channels)} channel(s) → {csv_path.name}")
    
    def _save_final(self, channels: List[Dict], timestamp: str, niche_slug: str):
        """Save final sorted results"""
        if not channels:
            return
        
        csv_path = self.results_dir / f"{timestamp}_{niche_slug}_channels.csv"
        json_path = self.results_dir / f"{timestamp}_{niche_slug}_channels.json"
        
        # Prepare data for CSV
        csv_data = []
        for ch in channels:
            row = ch.copy()
            # Convert lists to JSON strings for CSV
            for key in ['social_links', 'websites', 'all_emails', 'location_sources', 'sample_videos']:
                if key in row and isinstance(row[key], (list, dict)):
                    row[key] = json.dumps(row[key])
            csv_data.append(row)
        
        # Save CSV
        df = pd.DataFrame(csv_data)
        df.to_csv(csv_path, index=False, encoding='utf-8')
        
        # Save JSON
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(channels, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\n✅ CSV saved to: {csv_path}")
        logger.info(f"✅ JSON saved to: {json_path}")

    
    def _merge_channel_data(self, api_data: Dict, scraped_data: Dict, sample_video_id: Optional[str]) -> Dict:
        """Merge API and scraped data"""
        snippet = api_data.get('snippet', {})
        stats = api_data.get('statistics', {})
        
        # Get sample video from scraped data
        sample_video = scraped_data['sample_videos'][0] if scraped_data['sample_videos'] else {}
        
        merged = {
            'channel_id': scraped_data['channel_id'],
            'channel_name': snippet.get('title'),
            'channel_url': scraped_data['channel_url'],
            'channel_description': snippet.get('description'),
            'subscriber_count': int(stats.get('subscriberCount', 0)),
            'channel_video_count': int(stats.get('videoCount', 0)),
            'channel_view_count': int(stats.get('viewCount', 0)),
            'sample_video_id': sample_video.get('video_id') or sample_video_id,
            'sample_video_title': sample_video.get('video_title'),
            'sample_video_url': sample_video.get('video_url'),
            'detected_location': scraped_data.get('detected_location', {}),
            'location_sources': scraped_data.get('detected_location', {}).get('sources', []),
            'about_text': scraped_data.get('about_text'),
            'social_links': scraped_data.get('social_links', []),
            'websites': scraped_data.get('websites', []),
            'contact_email_public': scraped_data['emails'][0] if scraped_data.get('emails') else None,
            'all_emails': scraped_data.get('emails', []),
            'extraction_path': 'api+playwright',
            'scraped_at': datetime.now().isoformat()
        }
        
        return merged
    
    def _calculate_confidence(self, channel: Dict, query: str, target_location: Optional[str]) -> float:
        """Calculate confidence score for channel match"""
        score = 0.0
        
        # Keyword match in title/description (0-40 points)
        query_lower = query.lower()
        title_lower = (channel.get('channel_name') or '').lower()
        desc_lower = (channel.get('channel_description') or '').lower()
        about_lower = (channel.get('about_text') or '').lower()
        
        if query_lower in title_lower:
            score += 40
        elif query_lower in desc_lower:
            score += 30
        elif query_lower in about_lower:
            score += 20
        else:
            # Partial match
            query_words = query_lower.split()
            matches = sum(1 for word in query_words if word in title_lower or word in desc_lower)
            score += (matches / len(query_words)) * 20
        
        # Subscriber count (0-30 points, logarithmic)
        subs = channel.get('subscriber_count', 0)
        if subs > 0:
            import math
            score += min(30, math.log10(subs) * 5)
        
        # Location match (0-20 points)
        if target_location:
            detected_loc = channel.get('detected_location', {})
            detected_country = detected_loc.get('country')
            detected_city = detected_loc.get('city')
            
            target_lower = target_location.lower()
            
            # Check if target matches country
            if detected_country:
                if target_location.upper() in ['US', 'USA'] and detected_country == 'USA':
                    score += 20
                elif detected_country.lower() == target_lower or detected_country.upper() == target_location.upper():
                    score += 20
                else:
                    score += 5  # Has country but doesn't match
            
            # Check if target matches city
            if detected_city and detected_city.lower() == target_lower:
                score += 20  # Direct city match
            
            # Use location confidence from scraper
            loc_confidence = detected_loc.get('confidence', 0)
            score += min(20, loc_confidence)  # Cap at 20
        
        # Has contact info (0-10 points)
        if channel.get('contact_email_public'):
            score += 5
        if channel.get('social_links'):
            score += 5
        
        return round(score, 2)



def main():
    """Main entry point"""
    print("\n" + "="*60)
    print("YouTube Channel Finder by Niche & Country")
    print("="*60)
    print("\nFeatures:")
    print("  ✓ Real-time saving after each channel")
    print("  ✓ Duplicate detection (skips already-scraped channels)")
    print("  ✓ Email validation")
    print("  ✓ Progress bar with ETA")
    print("  ✓ Proxy rotation (every 4 successful channels)")
    print("  ✓ Headless mode (runs in background)")
    print("="*60 + "\n")
    
    # Get user input
    niche = input("Enter niche (required): ").strip()
    if not niche:
        print("❌ Niche is required!")
        return
    
    sub_niche = input("Enter sub-niche (optional, press Enter to skip): ").strip() or None
    location = input("Enter location (country code or city, e.g., US, Miami - optional): ").strip() or None
    
    try:
        max_results = int(input("Max results (default 50): ").strip() or "50")
    except:
        max_results = 50
    
    try:
        min_subs_input = input("Min subscribers (optional, press Enter to skip): ").strip()
        min_subscribers = int(min_subs_input) if min_subs_input else None
    except:
        min_subscribers = None
    
    # Get API key
    api_key = os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        print("❌ YOUTUBE_API_KEY not found in .env file!")
        return
    
    # Initialize finder
    finder = ChannelFinder(api_key)
    
    # Search channels
    try:
        channels = finder.search_channels(
            niche=niche,
            sub_niche=sub_niche,
            location=location,
            max_results=max_results,
            min_subscribers=min_subscribers
        )
        
        # Display results
        print("\n" + "="*60)
        print(f"Found {len(channels)} channels")
        print("="*60 + "\n")
        
        for i, ch in enumerate(channels[:10], 1):  # Show top 10
            print(f"{i}. {ch['channel_name']}")
            print(f"   Subscribers: {ch['subscriber_count']:,}")
            
            # Display location
            loc = ch.get('detected_location', {})
            loc_str = []
            if loc.get('city'):
                loc_str.append(loc['city'])
            if loc.get('country'):
                loc_str.append(loc['country'])
            print(f"   Location: {', '.join(loc_str) if loc_str else 'Unknown'}")
            
            print(f"   Confidence: {ch['confidence_score']}/100")
            if ch.get('contact_email_public'):
                print(f"   Email: {ch['contact_email_public']}")
            if ch.get('social_links'):
                print(f"   Social: {len(ch['social_links'])} links")
            print()
        
        # Summary
        elapsed = time.time() - finder.start_time if finder.start_time else 0
        print("\n" + "="*60)
        print("Summary")
        print("="*60)
        print(f"Completed in {int(elapsed/60)}m {int(elapsed%60)}s")
        print(f"Total channels found: {len(channels)}")
        print(f"Total API calls: {finder.api.api_calls}")
        print("="*60 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n❌ Search cancelled by user")
    except Exception as e:
        logger.error(f"Error during search: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
