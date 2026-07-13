import urllib.request
import ssl
from PIL import Image
import io

ssl._create_default_https_context = ssl._create_unverified_context

def download_lorem_flickr(keyword, dest_path):
    url = f"https://loremflickr.com/300/300/{urllib.parse.quote(keyword)}"
    print(f"Fetching: {url}")
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            img_data = response.read()
            img = Image.open(io.BytesIO(img_data))
            img.save(dest_path, "WEBP", quality=80)
            print("Successfully saved image to:", dest_path)
            return True
    except Exception as e:
        print(f"Error: {e}")
    return False

download_lorem_flickr("backpack", "test_backpack.webp")
