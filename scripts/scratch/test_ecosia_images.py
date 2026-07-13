import urllib.request
import urllib.parse
import re
import ssl
import json

ssl._create_default_https_context = ssl._create_unverified_context

def test_ecosia(query):
    print(f"Querying Ecosia Images for: {query}")
    try:
        url = f"https://images.ecosia.org/?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            print("HTML Length:", len(html))
            
            # Find image JSON payload in Ecosia HTML
            # Ecosia often embeds image results in a script or in image tags with src
            # Let's search for image urls
            urls = re.findall(r'"(https://[^"]+\.(?:jpg|jpeg|png|webp))"', html)
            print("Found image URLs:", len(urls))
            for i, u in enumerate(urls[:5]):
                print(f"{i}: {u}")
                
            img_tags = re.findall(r'<img[^>]+src="([^"]+)"', html)
            print("Found img tag srcs:", len(img_tags))
            for i, s in enumerate(img_tags[:5]):
                print(f"{i}: {s}")
    except Exception as e:
        print("Error:", e)

test_ecosia("composer")
