import urllib.request
import urllib.parse
import re
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

def scrape_yahoo_images(query):
    print(f"Searching Yahoo Images for: {query}")
    try:
        url = f"https://images.search.yahoo.com/search/images?p={urllib.parse.quote(query)}"
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            print("HTML Length:", len(html))
            
            # Yahoo image tags usually look like: <img data-src="url" ...> or src="url"
            urls = re.findall(r'src="([^"]+\.(?:jpg|jpeg|png|webp))"', html)
            print("Found src URLs:", len(urls))
            for i, u in enumerate(urls[:5]):
                print(f"src {i}: {u}")
                
            data_srcs = re.findall(r'data-src="([^"]+)"', html)
            print("Found data-src URLs:", len(data_srcs))
            for i, u in enumerate(data_srcs[:5]):
                print(f"data-src {i}: {u}")
                
            # Yahoo also stores original image data in metadata attribute: "iurl":"http..."
            iurls = re.findall(r'"iurl":"([^"]+)"', html)
            print("Found iurls:", len(iurls))
            for i, u in enumerate(iurls[:5]):
                print(f"iurl {i}: {u}")
                
    except Exception as e:
        print(f"Error: {e}")

scrape_yahoo_images("piano instrument realistic photo")
