#!/usr/bin/env python3
"""
Improved Shahnameh fetcher with better Persian text extraction.
Focuses on extracting only the actual poetry verses and narrative.
"""

import urllib.request
import urllib.error
import time
import sys
import re
from pathlib import Path
from typing import Dict, Optional

class GanjoorFetcher:
    """Fetch Shahnameh with improved Persian text extraction."""

    def __init__(self, rate_limit_delay=0.5):
        self.base_url = "https://ganjoor.net"
        self.rate_limit_delay = rate_limit_delay
        self.session_headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; StudiumCorpus/1.0; +https://ganjoor.net)'
        }
        self.fetched_content = {}

    def fetch_html(self, path: str) -> Optional[str]:
        """Fetch HTML from a ganjoor.net path."""
        url = f"{self.base_url}{path}"
        try:
            req = urllib.request.Request(url, headers=self.session_headers)
            with urllib.request.urlopen(req, timeout=20) as response:
                return response.read().decode('utf-8', errors='replace')
        except Exception:
            return None

    def extract_persian_text(self, html: str) -> str:
        """Extract Persian poetry text from HTML more aggressively."""
        # Remove all script and style tags
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Remove common navigation and UI elements
        html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<form[^>]*>.*?</form>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<button[^>]*>.*?</button>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<img[^>]*>', '', html)

        # Decode common HTML entities BEFORE removing tags
        html = html.replace('&nbsp;', ' ')
        html = html.replace('&lt;', '<')
        html = html.replace('&gt;', '>')
        html = html.replace('&amp;', '&')
        html = html.replace('&quot;', '"')
        html = html.replace('&apos;', "'")
        html = html.replace('&#39;', "'")
        html = html.replace('&times;', '×')
        html = html.replace('&raquo;', '»')
        html = html.replace('&laquo;', '«')

        # Remove all remaining HTML tags
        html = re.sub(r'<[^>]+>', '\n', html)

        # Split by newlines and process each line
        lines = html.split('\n')
        result = []

        for line in lines:
            line = line.strip()

            # Skip empty lines and very short lines
            if not line or len(line) < 3:
                continue

            # Skip common UI text patterns (keywords that are clearly UI, not poetry)
            skip_patterns = [
                r'^(ورود|نام‌نویسی|خروج|ادامه|تاریخچه|کپی|نشان|ویرایش|شعر یا بخش)',
                r'(کاربر|حساب|دوبارهٔ|نوار|ابزار|راهنما)',
                r'^(فردوسی|شاهنامه|گنجور|»)',
                r'شماره‌گذاری|لغزش|فعال|غیرفعال|چسبانی',
                r'اعلان|اطلاعات|قبلی|بعدی|برگردان|نثر|خلاصه'
            ]

            skip = False
            for pattern in skip_patterns:
                if re.search(pattern, line):
                    skip = True
                    break

            if skip:
                continue

            # Count Persian characters in the line
            persian_chars = sum(1 for c in line if '؀' <= c <= 'ۿ')

            # Keep lines with substantial Persian content (>30% of line is Persian)
            if persian_chars > 0 and len(line) > 5 and persian_chars / len(line) > 0.2:
                result.append(line)

        return '\n'.join(result)

    def discover_and_fetch(self) -> Dict[str, str]:
        """Discover and fetch all Shahnameh cycles."""
        print("Discovering Shahnameh cycles...", file=sys.stderr)

        # Fetch main page to discover URLs
        main_html = self.fetch_html("/ferdousi/shahname/")
        if not main_html:
            print("✗ Failed to fetch main page", file=sys.stderr)
            return {}

        # Extract all links to cycles
        pattern = r'href="(/ferdousi/shahname/[^"]+)"'
        urls = set(re.findall(pattern, main_html))

        # Filter out main page and admin paths
        urls = {path.rstrip('/') for path in urls
                if path != '/ferdousi/shahname' and 'admin' not in path.lower()}

        if not urls:
            print("✗ No cycles discovered", file=sys.stderr)
            return {}

        print(f"✓ Discovered {len(urls)} cycles", file=sys.stderr)
        print("Fetching and extracting Persian text...\n", file=sys.stderr)

        # Fetch each cycle
        for idx, path in enumerate(sorted(urls), 1):
            slug = path.split('/')[-1]
            print(f"[{idx:2d}/{len(urls)}] {slug:30s} ... ", end='', flush=True, file=sys.stderr)

            html = self.fetch_html(path)
            if html and len(html) > 1000:
                content = self.extract_persian_text(html)
                if content and len(content) > 500:
                    print(f"✓ ({len(content):6d} chars)", file=sys.stderr)
                    self.fetched_content[slug] = {
                        'title': slug.replace('-', ' ').title(),
                        'text': content,
                        'size': len(content),
                        'url': path
                    }
                else:
                    print("✗ (low content)", file=sys.stderr)
            else:
                print("✗", file=sys.stderr)

            time.sleep(self.rate_limit_delay)

        return self.fetched_content

    def save_to_file(self, output_path: Path) -> bool:
        """Save to UTF-8 text file with clear markers."""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                # Header
                f.write("=" * 80 + "\n")
                f.write("شاهنامه فردوسی\n")
                f.write("Shahnameh of Ferdowsi — Complete Persian Original Text\n")
                f.write("Source: https://ganjoor.net/ferdousi/shahname/\n")
                f.write(f"Fetched: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Cycles: {len(self.fetched_content)}\n")
                f.write(f"Total Characters: {sum(d['size'] for d in self.fetched_content.values()):,}\n")
                f.write("=" * 80 + "\n\n")

                # Cycles
                for idx, (slug, data) in enumerate(sorted(self.fetched_content.items()), 1):
                    f.write(f"\n{'='*80}\n")
                    f.write(f"CYCLE {idx}: {data['title'].upper()}\n")
                    f.write(f"Source: {self.base_url}{data['url']}\n")
                    f.write(f"{'='*80}\n\n")
                    f.write(data['text'])
                    f.write("\n\n")

            return True
        except Exception as e:
            print(f"✗ Error saving: {e}", file=sys.stderr)
            return False

def main():
    fetcher = GanjoorFetcher(rate_limit_delay=0.5)
    content = fetcher.discover_and_fetch()

    print(f"\n{'='*80}", file=sys.stderr)
    print(f"Successfully fetched: {len(content)} cycles", file=sys.stderr)

    if not content:
        print("✗ No content fetched", file=sys.stderr)
        return 1

    output_path = Path("/Users/4jp/Workspace/.limen-worktrees/studium-corpus-shahnameh-2f2f/corpus/arabic-persian/shahnameh/persian_original.txt")

    if fetcher.save_to_file(output_path):
        file_size = output_path.stat().st_size
        total_chars = sum(d['size'] for d in fetcher.fetched_content.values())

        print("\n✓ Successfully saved to:")
        print(f"  {output_path}", file=sys.stderr)
        print("\nStats:", file=sys.stderr)
        print(f"  File size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)", file=sys.stderr)
        print(f"  Total Persian text: {total_chars:,} characters", file=sys.stderr)
        print(f"  Cycles: {len(content)}", file=sys.stderr)

        return 0
    else:
        print("✗ Failed to save", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
