import subprocess
import urllib.parse
import re
import json

def test_bing_curl(query):
    print(f"Query: {query}")
    try:
        url = f"https://www.bing.com/images/search?q={urllib.parse.quote(query)}"
        
        # Use curl with browser user agent
        cmd = [
            'curl',
            '-s',
            '-A', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            '-H', 'Accept-Language: en-US,en;q=0.9',
            '-H', 'Referer: https://www.google.com/',
            url
        ]
        
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        html = result.stdout.decode('utf-8', errors='ignore')
        
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

test_bing_curl("violin solo performance stage photo")
