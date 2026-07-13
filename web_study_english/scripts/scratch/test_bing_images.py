import urllib.request
import urllib.parse
import re
import ssl
import json

ssl._create_default_https_context = ssl._create_unverified_context

def scrape_bing_images(query):
    print(f"Searching Bing Images for: {query}")
    try:
        url = f"https://www.bing.com/images/search?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            print("HTML Length:", len(html))
            
            # Bing stores image info in class="iusc" m="..." attribute
            matches = re.findall(r'm="([^"]+)"', html)
            print("Found m matches:", len(matches))
            
            image_urls = []
            for m in matches:
                try:
                    # Clean escaped HTML chars in JSON string
                    m_clean = m.replace('&quot;', '"').replace('&amp;', '&')
                    data = json.loads(m_clean)
                    murl = data.get("murl")
                    if murl:
                        image_urls.append(murl)
                except Exception as e:
                    pass
                    
            print("Found image URLs:", len(image_urls))
            for i, u in enumerate(image_urls[:5]):
                print(f"{i}: {u}")
                
    except Exception as e:
        print(f"Error: {e}")

scrape_bing_images("piano instrument realistic photo")
