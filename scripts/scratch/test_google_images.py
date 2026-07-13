import urllib.request
import urllib.parse
import re
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

def scrape_google_images(query):
    print(f"Searching Google Images for: {query}")
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&tbm=isch"
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            print("HTML Length:", len(html))
            
            # Find URLs starting with https and ending with image extensions in the scripts
            urls = re.findall(r'"(https://[^"]+\.(?:jpg|jpeg|png|webp))"', html)
            print("Found image URLs:", len(urls))
            for i, u in enumerate(urls[:5]):
                print(f"{i}: {u}")
                
            # If no script URLs, find standard img tag src
            if not urls:
                img_srcs = re.findall(r'<img[^>]+src="([^"]+)"', html)
                print("Found img tag srcs:", len(img_srcs))
                for i, s in enumerate(img_srcs[:5]):
                    print(f"{i}: {s}")
                    
    except Exception as e:
        print(f"Error: {e}")

scrape_google_images("piano instrument realistic photo")
