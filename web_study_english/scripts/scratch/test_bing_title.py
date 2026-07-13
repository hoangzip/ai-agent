import urllib.request
import urllib.parse
import re
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

def check_bing_title():
    url = "https://www.bing.com/images/search?q=composer"
    print("Checking title for:", url)
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            title = re.search(r'<title>([^<]+)</title>', html)
            if title:
                print("Page Title:", title.group(1))
            else:
                print("No title tag found.")
            # Save a snippet
            print("HTML Snippet:", html[:500])
    except Exception as e:
        print("Error:", e)

check_bing_title()
