import urllib.request
import ssl
from PIL import Image
import io

ssl._create_default_https_context = ssl._create_unverified_context

def test_unsplash():
    url = "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?auto=format&fit=crop&w=300&h=300&q=80"
    print(f"Downloading from: {url}")
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = response.read()
            img = Image.open(io.BytesIO(data))
            img.save("test_music.webp", "WEBP", quality=80)
            print("Successfully saved Unsplash image!")
    except Exception as e:
        print(f"Error: {e}")

test_unsplash()
