#!/usr/bin/env python3
"""Direct test of Jobspresso fetching without CLI."""

import sys
import yaml
from jobradar.models import Feed
from jobradar.fetchers import Fetcher

def main():
    print("=== Direct Jobspresso Fetch Test ===")
    
    # Load config
    try:
        with open('feeds.yml', 'r') as f:
            config = yaml.safe_load(f)
        print(f"✓ Loaded config with {len(config.get('feeds', []))} feeds")
    except Exception as e:
        print(f"✗ Failed to load config: {e}")
        return
    
    # Find Jobspresso feed
    jobspresso_config = None
    for feed_config in config.get('feeds', []):
        if feed_config.get('name') == 'jobspresso':
            jobspresso_config = feed_config
            break
    
    if not jobspresso_config:
        print("✗ Jobspresso feed not found in config")
        return
    
    print(f"✓ Found Jobspresso config: {jobspresso_config}")
    
    # Create Feed object
    try:
        feed = Feed(**jobspresso_config)
        print(f"✓ Created Feed object: {feed.name} ({feed.fetch_method})")
    except Exception as e:
        print(f"✗ Failed to create Feed object: {e}")
        return
    
    # Create Fetcher and test fetch
    try:
        fetcher = Fetcher()
        print("✓ Created Fetcher instance")
        
        print(f"📥 Attempting to fetch from {feed.url}...")
        jobs = fetcher.fetch(feed)
        
        print(f"✓ Fetch completed! Got {len(jobs)} jobs")
        
        if jobs:
            print("\n📋 Sample jobs:")
            for i, job in enumerate(jobs[:3]):
                print(f"  {i+1}. {job.title} @ {job.company}")
                print(f"     URL: {job.url}")
        else:
            print("⚠️  No jobs returned")
            
        # Check if debug file was created
        import pathlib
        debug_file = pathlib.Path("debug/jobspresso_content.html")
        if debug_file.exists():
            print(f"✓ Debug HTML saved: {debug_file} ({debug_file.stat().st_size} bytes)")
        else:
            print("⚠️  No debug HTML file created")
            
    except Exception as e:
        print(f"✗ Fetch failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 