import urllib.request
import urllib.parse
import json
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

def test_wikimedia(query):
    print(f"Querying Wikimedia Commons for: {query}")
    try:
        # Search for files
        url = f"https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&srnamespace=6&format=json"
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            search_results = data.get("query", {}).get("search", [])
            print("Found files:", len(search_results))
            
            for i, res in enumerate(search_results[:3]):
                title = res.get("title")
                print(f"{i}: Title: {title}")
                
                # Get the image URL for this file title
                # e.g., File:Beethoven.jpg
                url_info = f"https://commons.wikimedia.org/w/api.php?action=query&titles={urllib.parse.quote(title)}&prop=imageinfo&iiprop=url&format=json"
                req_info = urllib.request.Request(
                    url_info, 
                    headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
                )
                with urllib.request.urlopen(req_info, timeout=10) as res_info:
                    data_info = json.loads(res_info.read().decode('utf-8'))
                    pages = data_info.get("query", {}).get("pages", {})
                    for page_id, page_data in pages.items():
                        imageinfo = page_data.get("imageinfo", [])
                        if imageinfo:
                            print(f"   URL: {imageinfo[0].get('url')}")
                            
    except Exception as e:
        print("Error:", e)

test_wikimedia("composer music portrait")
