import urllib.request
import urllib.parse
import re
import ssl
import json

ssl._create_default_https_context = ssl._create_unverified_context

def test_bing_clean(query):
    print(f"Query: {query}")
    try:
        # Let's request the main Bing home page first to get cookies
        cookie_jar = urllib.request.HTTPCookieProcessor()
        opener = urllib.request.build_opener(cookie_jar)
        
        # Add realistic headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.bing.com/',
            'Connection': 'keep-alive'
        }
        
        opener.addheaders = [(k, v) for k, v in headers.items()]
        
        # Load main page first
        opener.open("https://www.bing.com/")
        
        # Now search images
        url = f"https://www.bing.com/images/search?q={urllib.parse.quote(query)}"
        with opener.open(url) as response:
            html = response.read().decode('utf-8', errors='ignore')
            matches = re.findall(r'<a[^>]+class="iusc"[^>]+m="([^"]+)"', html)
            print("Matches found:", len(matches))
            
            image_urls = []
            for m in matches[:5]:
                try:
                    m_clean = m.replace('&quot;', '"').replace('&amp;', '&')
                    data = json.loads(m_clean)
                    murl = data.get("murl")
                    title = data.get("t", "")
                    if murl:
                        image_urls.append((murl, title))
                except Exception as e:
                    pass
            
            for i, (u, t) in enumerate(image_urls):
                print(f"{i}: URL: {u}")
                print(f"   Title: {t}")
    except Exception as e:
        print("Error:", e)

test_bing_clean("grand piano keyboard realistic photo")
