#!/usr/bin/env python3
"""
Malware Hash Scraper

This script scrapes malware hashes from various public sources and updates
the repository with the latest findings in a structured format.
"""

import os
import json
import re
import time
import hashlib
import logging
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import feedparser
from tqdm import tqdm

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('hash_scraper')

# Constants
USER_AGENT = 'NealthaScraper/1.0 (GitHub Action; For research purposes)'
BASE_DIR = os.getcwd()
TODAY = datetime.now().strftime('%Y_%m_%d')
SHA256_PATTERN = re.compile(r'\b[A-Fa-f0-9]{64}\b')

# Ensure directories exist
os.makedirs('hashes/virustotal', exist_ok=True)
os.makedirs('hashes/malwarebazaar', exist_ok=True)
os.makedirs('hashes/urlhaus', exist_ok=True)
os.makedirs('hashes/daily', exist_ok=True)

def save_hash_data(source_name, filename, data):
    """Save hash data to a JSON file"""
    directory = os.path.join('hashes', source_name)
    os.makedirs(directory, exist_ok=True)
    
    filepath = os.path.join(directory, filename)
    
    # If file exists, load and merge data
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                existing_data = json.load(f)
                
            # Update version and last_updated
            existing_data['version'] = data.get('version', '1.0.0')
            existing_data['last_updated'] = datetime.now().isoformat()
            
            # Merge sha256_signatures
            existing_signatures = existing_data.get('sha256_signatures', {})
            for hash_key, hash_data in data.get('sha256_signatures', {}).items():
                if hash_key not in existing_signatures:
                    existing_signatures[hash_key] = hash_data
            
            existing_data['sha256_signatures'] = existing_signatures
            data = existing_data
        except Exception as e:
            logger.error(f"Error merging existing data: {e}")
    
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved data to {filepath}")
    except Exception as e:
        logger.error(f"Error saving data to {filepath}: {e}")

def generate_hash_structure(hash_value, classification, detection_rate, additional_info=None, file_type=None):
    """Generate a standard structure for hash data"""
    return {
        "classification": classification,
        "detection_rate": detection_rate,
        "first_seen": datetime.now().strftime('%Y-%m-%d'),
        "neartha_name": f"{classification.replace(' ', '.')}",
        "additional_info": additional_info or "",
        "file_type": file_type or "Unknown"
    }

def fetch_malwarebazaar_samples():
    """Fetch recent samples from MalwareBazaar"""
    logger.info("Fetching MalwareBazaar samples")
    
    data = {
        "version": "1.0.0",
        "last_updated": datetime.now().isoformat(),
        "description": f"MalwareBazaar malware hashes collected on {datetime.now().strftime('%Y-%m-%d')}",
        "source": "MalwareBazaar",
        "sha256_signatures": {}
    }
    
    try:
        # MalwareBazaar API - get recent samples
        url = "https://mb-api.abuse.ch/api/v1/"
        post_data = {
            "query": "get_recent",
            "selector": "100"  # Get last 100 samples
        }
        
        response = requests.post(
            url,
            data=post_data,
            headers={"User-Agent": USER_AGENT},
            timeout=30
        )
        
        if response.status_code == 200:
            json_data = response.json()
            
            if json_data.get("query_status") == "ok":
                for sample in json_data.get("data", []):
                    sha256 = sample.get("sha256_hash")
                    if not sha256:
                        continue
                    
                    tags = sample.get("tags", [])
                    tag_str = ", ".join(tags) if tags else "Unclassified"
                    
                    data["sha256_signatures"][sha256] = generate_hash_structure(
                        sha256,
                        sample.get("signature", "Malware.Generic"),
                        f"{sample.get('intelligence', {}).get('avdetection', '?')}/100",
                        f"Tags: {tag_str}",
                        sample.get("file_type")
                    )
            
            save_hash_data("malwarebazaar", f"{TODAY}.json", data)
            save_hash_data("daily", f"{TODAY}.json", data)  # Also save to daily
            logger.info(f"Collected {len(data['sha256_signatures'])} hashes from MalwareBazaar")
        else:
            logger.error(f"Error fetching from MalwareBazaar: {response.status_code}")
    
    except Exception as e:
        logger.error(f"Error processing MalwareBazaar data: {e}")

def fetch_urlhaus_samples():
    """Fetch recent samples from URLhaus"""
    logger.info("Fetching URLhaus samples")
    
    data = {
        "version": "1.0.0",
        "last_updated": datetime.now().isoformat(),
        "description": f"URLhaus malware hashes collected on {datetime.now().strftime('%Y-%m-%d')}",
        "source": "URLhaus",
        "sha256_signatures": {}
    }
    
    try:
        # URLhaus CSV feed for payloads
        url = "https://urlhaus.abuse.ch/downloads/payloads/"
        
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=30
        )
        
        if response.status_code == 200:
            lines = response.text.split('\n')
            for line in lines:
                if line.startswith('#') or not line.strip():
                    continue
                
                parts = line.split(',')
                if len(parts) >= 8:
                    sha256 = parts[4].strip().lower()
                    if not sha256 or len(sha256) != 64:
                        continue
                    
                    file_type = parts[5].strip()
                    signature = parts[6].strip() if len(parts) > 6 else "Malware.URLhaus"
                    first_seen = parts[0].strip() if len(parts) > 0 else datetime.now().strftime('%Y-%m-%d')
                    
                    data["sha256_signatures"][sha256] = {
                        "classification": signature if signature else "Malware.URLhaus",
                        "detection_rate": "Unknown",
                        "first_seen": first_seen,
                        "neartha_name": f"Malware.{signature}" if signature else "Malware.URLhaus.Generic",
                        "additional_info": f"Downloaded from malicious URL. File type: {file_type}",
                        "file_type": file_type
                    }
            
            save_hash_data("urlhaus", f"{TODAY}.json", data)
            save_hash_data("daily", f"{TODAY}.json", data)  # Also save to daily
            logger.info(f"Collected {len(data['sha256_signatures'])} hashes from URLhaus")
        else:
            logger.error(f"Error fetching from URLhaus: {response.status_code}")
    
    except Exception as e:
        logger.error(f"Error processing URLhaus data: {e}")

def scrape_vx_underground():
    """Scrape VX-Underground for malware hashes"""
    logger.info("Scraping VX-Underground for malware hashes")
    
    data = {
        "version": "1.0.0",
        "last_updated": datetime.now().isoformat(),
        "description": f"VX-Underground malware hashes collected on {datetime.now().strftime('%Y-%m-%d')}",
        "source": "VX-Underground",
        "sha256_signatures": {}
    }
    
    try:
        # VX-Underground Twitter feed often contains hashes
        url = "https://twitter.com/vxunderground"
        
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=30
        )
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            tweets = soup.find_all('div', {'class': 'tweet'})
            
            for tweet in tweets:
                text = tweet.get_text()
                
                # Extract SHA256 hashes
                hashes = SHA256_PATTERN.findall(text)
                
                for sha256 in hashes:
                    data["sha256_signatures"][sha256] = generate_hash_structure(
                        sha256,
                        "Malware.VXUnderground",
                        "Unknown",
                        "Found in VX-Underground Twitter feed",
                        "Unknown"
                    )
            
            save_hash_data("virustotal", f"vxunderground_{TODAY}.json", data)
            save_hash_data("daily", f"{TODAY}.json", data)  # Also save to daily
            logger.info(f"Collected {len(data['sha256_signatures'])} hashes from VX-Underground")
        else:
            logger.error(f"Error fetching from VX-Underground: {response.status_code}")
    
    except Exception as e:
        logger.error(f"Error processing VX-Underground data: {e}")

def scrape_malpedia():
    """Scrape Malpedia for malware hashes"""
    logger.info("Scraping Malpedia for malware hashes")
    
    data = {
        "version": "1.0.0",
        "last_updated": datetime.now().isoformat(),
        "description": f"Malpedia malware hashes collected on {datetime.now().strftime('%Y-%m-%d')}",
        "source": "Malpedia",
        "sha256_signatures": {}
    }
    
    try:
        # Malpedia public feed
        url = "https://malpedia.caad.fkie.fraunhofer.de/api/get/recent"
        
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=30
        )
        
        if response.status_code == 200:
            json_data = response.json()
            
            for item in json_data:
                if isinstance(item, dict) and 'sha256' in item:
                    sha256 = item['sha256']
                    
                    family = item.get('family', 'Unknown')
                    first_seen = item.get('timestamp', datetime.now().strftime('%Y-%m-%d'))
                    
                    data["sha256_signatures"][sha256] = generate_hash_structure(
                        sha256,
                        f"Malware.{family}",
                        "Unknown",
                        f"Malpedia family: {family}",
                        item.get('fileType', 'Unknown')
                    )
            
            save_hash_data("virustotal", f"malpedia_{TODAY}.json", data)
            save_hash_data("daily", f"{TODAY}.json", data)  # Also save to daily
            logger.info(f"Collected {len(data['sha256_signatures'])} hashes from Malpedia")
        else:
            logger.error(f"Error fetching from Malpedia: {response.status_code}")
    
    except Exception as e:
        logger.error(f"Error processing Malpedia data: {e}")

def scrape_any_run():
    """Scrape ANY.RUN for malware hashes"""
    logger.info("Scraping ANY.RUN for malware hashes")
    
    data = {
        "version": "1.0.0",
        "last_updated": datetime.now().isoformat(),
        "description": f"ANY.RUN malware hashes collected on {datetime.now().strftime('%Y-%m-%d')}",
        "source": "ANY.RUN",
        "sha256_signatures": {}
    }
    
    try:
        # ANY.RUN public submissions
        url = "https://app.any.run/submissions/"
        
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=30
        )
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract hashes from submissions list
            submissions = soup.find_all('div', {'class': 'task-card'})
            
            for submission in submissions:
                # Look for SHA256 attributes or in the text
                sha256_elem = submission.find('div', {'data-hash-type': 'sha256'})
                if sha256_elem:
                    sha256 = sha256_elem.get_text().strip()
                else:
                    # Try to find in text content
                    text = submission.get_text()
                    hashes = SHA256_PATTERN.findall(text)
                    if hashes:
                        sha256 = hashes[0]
                    else:
                        continue
                
                # Try to get verdict and name
                verdict_elem = submission.find('div', {'class': 'verdict'})
                verdict = "Malicious" if verdict_elem and "malicious" in verdict_elem.get_text().lower() else "Unknown"
                
                name_elem = submission.find('div', {'class': 'name'})
                name = name_elem.get_text().strip() if name_elem else "Unknown"
                
                data["sha256_signatures"][sha256] = generate_hash_structure(
                    sha256,
                    f"Malware.{name}",
                    "Unknown",
                    f"ANY.RUN verdict: {verdict}",
                    "Unknown"
                )
            
            save_hash_data("virustotal", f"anyrun_{TODAY}.json", data)
            save_hash_data("daily", f"{TODAY}.json", data)  # Also save to daily
            logger.info(f"Collected {len(data['sha256_signatures'])} hashes from ANY.RUN")
        else:
            logger.error(f"Error fetching from ANY.RUN: {response.status_code}")
    
    except Exception as e:
        logger.error(f"Error processing ANY.RUN data: {e}")

def fetch_popular_malware_blogs():
    """Scrape popular security blogs for malware hashes"""
    logger.info("Scraping security blogs for malware hashes")
    
    blogs = [
        # Security blogs that frequently publish malware analyses
        {
            'name': 'Malware Traffic Analysis',
            'feed': 'https://www.malware-traffic-analysis.net/blog-entries.rss',
            'type': 'rss'
        },
        {
            'name': 'BleepingComputer',
            'feed': 'https://www.bleepingcomputer.com/feed/',
            'type': 'rss'
        },
        {
            'name': 'Krebs on Security',
            'feed': 'https://krebsonsecurity.com/feed/',
            'type': 'rss'
        }
    ]
    
    data = {
        "version": "1.0.0",
        "last_updated": datetime.now().isoformat(),
        "description": f"Security blog malware hashes collected on {datetime.now().strftime('%Y-%m-%d')}",
        "source": "Security Blogs",
        "sha256_signatures": {}
    }
    
    # Process each blog
    for blog in blogs:
        logger.info(f"Processing blog: {blog['name']}")
        try:
            if blog['type'] == 'rss':
                feed = feedparser.parse(blog['feed'])
                
                for entry in feed.entries[:10]:  # Process last 10 entries
                    if 'content' in entry:
                        content = entry.content[0].value
                    elif 'summary' in entry:
                        content = entry.summary
                    else:
                        continue
                    
                    soup = BeautifulSoup(content, 'html.parser')
                    text_content = soup.get_text()
                    
                    # Extract potential SHA256 hashes from the content
                    hashes = SHA256_PATTERN.findall(text_content)
                    
                    for sha256 in hashes:
                        data["sha256_signatures"][sha256] = generate_hash_structure(
                            sha256,
                            "Malware.SecurityBlog",
                            "Unknown",
                            f"Source: {blog['name']} - {entry.title}",
                            "Unknown"
                        )
        
        except Exception as e:
            logger.error(f"Error processing blog {blog['name']}: {e}")
    
    if data["sha256_signatures"]:
        save_hash_data("virustotal", f"blogs_{TODAY}.json", data)
        save_hash_data("daily", f"{TODAY}.json", data)  # Also save to daily
        logger.info(f"Collected {len(data['sha256_signatures'])} hashes from security blogs")

def generate_stats():
    """Generate statistics about the collected data and create a report"""
    logger.info("Generating statistics")
    
    stats = {
        "last_update": datetime.now().isoformat(),
        "sources": {},
        "total_unique_hashes": 0
    }
    
    total_hashes = set()
    
    # Analyze all hash directories
    hash_dirs = ['virustotal', 'malwarebazaar', 'urlhaus', 'daily']
    
    for dir_name in hash_dirs:
        dir_path = os.path.join('hashes', dir_name)
        if not os.path.exists(dir_path):
            continue
        
        stats['sources'][dir_name] = {
            "files": 0,
            "hashes": 0
        }
        
        for file in os.listdir(dir_path):
            if file.endswith('.json'):
                stats['sources'][dir_name]["files"] += 1
                
                try:
                    with open(os.path.join(dir_path, file), 'r') as f:
                        data = json.load(f)
                    
                    signatures = data.get('sha256_signatures', {})
                    stats['sources'][dir_name]["hashes"] += len(signatures)
                    
                    # Add to total unique hashes
                    for hash_key in signatures.keys():
                        total_hashes.add(hash_key)
                
                except Exception as e:
                    logger.error(f"Error processing {file}: {e}")
    
    stats['total_unique_hashes'] = len(total_hashes)
    
    # Save stats to file
    try:
        with open(os.path.join('hashes', 'stats.json'), 'w') as f:
            json.dump(stats, f, indent=2)
        logger.info("Statistics saved to hashes/stats.json")
        
        # Also create a summary file
        with open(os.path.join('hashes', 'SUMMARY.md'), 'w') as f:
            f.write(f"# Neartha Malware Hash Database Summary\n\n")
            f.write(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n")
            f.write(f"## Statistics\n\n")
            f.write(f"- Total unique hashes: **{len(total_hashes):,}**\n\n")
            
            f.write("## Sources\n\n")
            for source, source_stats in stats['sources'].items():
                f.write(f"### {source.capitalize()}\n")
                f.write(f"- Files: {source_stats['files']}\n")
                f.write(f"- Hashes: {source_stats['hashes']:,}\n\n")
            
            f.write("## Today's Collection\n\n")
            try:
                with open(os.path.join('hashes', 'daily', f"{TODAY}.json"), 'r') as daily_file:
                    daily_data = json.load(daily_file)
                    daily_count = len(daily_data.get('sha256_signatures', {}))
                    f.write(f"- New hashes today: **{daily_count:,}**\n\n")
            except:
                f.write("- No new hashes collected today\n\n")
                
            f.write("## Notes\n\n")
            f.write("This database is updated daily through automated collection from various sources.\n")
            f.write("All content is released under CC0 1.0 Universal (CC0 1.0) Public Domain Dedication.\n")
            
        logger.info("Summary created at hashes/SUMMARY.md")
            
    except Exception as e:
        logger.error(f"Error generating stats: {e}")

if __name__ == "__main__":
    logger.info("Starting malware hash scraper")
    
    # Run all scrapers
    fetch_malwarebazaar_samples()
    fetch_urlhaus_samples()
    fetch_popular_malware_blogs()
    scrape_vx_underground()
    scrape_malpedia()
    scrape_any_run()
    
    # Generate stats
    generate_stats()
    
    logger.info("Hash scraping completed")
