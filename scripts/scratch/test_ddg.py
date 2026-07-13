import urllib.request
import urllib.parse
import re
import json
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

def get_vqd_token(query):
    try:
        url = f"https://duckduckgo.com/?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            html = response.read().decode('utf-8', errors='ignore')
            print("HTML Length:", len(html))
            match = re.search(r"vqd\s*=\s*['\"]([^'\"]+)['\"]", html)
            if match:
                return match.group(1)
            match = re.search(r"vqd=([0-9-]+)", html)
            if match:
                return match.group(1)
    except Exception as e:
        print(f"Error fetching vqd token: {e}")
    return None

def search_ddg_image(query):
    vqd = get_vqd_token(query)
    print("VQD Token:", vqd)
    if not vqd:
        return None
    try:
        url = f"https://duckduckgo.com/d.js?q={urllib.parse.quote(query)}&vqd={vqd}&s=0&o=json&api=d.js"
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            res_content = response.read().decode('utf-8')
            print("Response Length:", len(res_content))
            data = json.loads(res_content)
            results = data.get("results", [])
            print("Number of results:", len(results))
            if results:
                print("First result thumbnail:", results[0].get("thumbnail"))
                return results[0].get("thumbnail")
    except Exception as e:
        print(f"Error in search: {e}")
    return None

search_ddg_image("backpack vocabulary clipart")
