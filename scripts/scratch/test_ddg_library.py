from duckduckgo_search import DDGS
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

def search_ddg_image(query):
    print(f"Searching for: {query}")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=2))
            print("Results:", results)
            if results:
                return results[0].get("thumbnail") or results[0].get("image")
    except Exception as e:
        print(f"Error: {e}")
    return None

search_ddg_image("backpack vocabulary clipart")
