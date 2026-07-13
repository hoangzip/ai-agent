import urllib.request
import urllib.parse
import re
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

def test_ddg_html(query):
    print(f"Querying DuckDuckGo HTML for: {query}")
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            print("HTML Length:", len(html))
            
            # Print title
            title = re.search(r'<title>([^<]+)</title>', html)
            if title:
                print("Title:", title.group(1))
                
            # DuckDuckGo HTML search returns text results. Can we get images?
            # Wait, html.duckduckgo.com only returns text web results, not image search results!
            # Let's check if there are any image links
            links = re.findall(r'href="([^"]+)"', html)
            print("Links found:", len(links))
            for l in links[:10]:
                if 'image' in l or 'jpg' in l:
                    print("   Img link:", l)
    except Exception as e:
        print("Error:", e)

test_ddg_html("piano")
