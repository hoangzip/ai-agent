import urllib.request
import urllib.parse
import re
import ssl
import json

ssl._create_default_https_context = ssl._create_unverified_context

def test_bing_regex(query):
    print(f"Query: {query}")
    try:
        url = f"https://www.bing.com/images/search?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
            # Match only <a> tags with class="iusc"
            # Typical tag: <a class="iusc" style="..." href="..." m="{"murl":"...", ...}">
            matches = re.findall(r'<a[^>]+class="iusc"[^>]+m="([^"]+)"', html)
            print("Found class=iusc matches:", len(matches))
            
            if not matches:
                # Try matching class after m
                matches = re.findall(r'<a[^>]+m="([^"]+)"[^>]+class="iusc"', html)
                print("Found class=iusc (alternative order) matches:", len(matches))
                
            image_urls = []
            for m in matches[:3]:
                try:
                    m_clean = m.replace('&quot;', '"').replace('&amp;', '&')
                    data = json.loads(m_clean)
                    print("Parsed JSON data:", data)
                    murl = data.get("murl")
                    if murl:
                        image_urls.append(murl)
                except Exception as e:
                    print("JSON error:", e)
                    
            print("Top 5 image URLs:")
            for i, u in enumerate(image_urls):
                print(f"{i}: {u}")
                
    except Exception as e:
        print("Error:", e)

test_bing_regex("composer writing music")
