import os
import json
import re
import time
import urllib.request
import urllib.parse
from PIL import Image
import io
import unicodedata
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

# Custom queries mapping for high precision
MUSIC_QUERIES = {
    'Music': 'music notes sheet realistic photo',
    'Band': 'musical band group performing on stage photo',
    'Play': 'playing musical instrument hands close up photo',
    'Note': 'single musical note symbol clear photo',
    'Drum': 'drum instrument realistic photo',
    'Playlist': 'music playlist phone screen UI photo',
    'Musician': 'musician playing instrument realistic photo',
    'Perform': 'musicians performing live concert stage photo',
    'Rhythm': 'rhythm sound waves visualizer graphic photo',
    'Dance': 'people dancing realistic photo',
    'Listen': 'person listening with headphones realistic photo',
    'Volume': 'volume control dial knob realistic photo',
    'Song': 'song sheet music notes print photo',
    'Sing': 'singer singing into microphone close up photo',
    'Piano': 'grand piano keyboard realistic photo',
    'Guitar': 'acoustic guitar realistic photo',
    'Instrument': 'various musical instruments group photo',
    'Harmony': 'harmony music notes sheet staff photo',
    'Melody': 'sheet music melody staff line photo',
    'String': 'guitar string close up photo',
    'The brass': 'brass instruments trumpet trombone photo',
    'Symphony': 'symphony orchestra concert hall stage photo',
    'Overture': 'orchestra concert stage performing photo',
    'Conductor': 'orchestra conductor leading with baton photo',
    'Composer': 'music composer writing sheet music paper photo',
    'Voice': 'vocalist singing microphone close up photo',
    'Solo': 'solo musician performing on stage photo',
    'Lead singer': 'lead singer vocal microphone stage photo',
    'Guitarist': 'guitarist playing electric guitar photo',
    'Drummer': 'drummer playing drum kit photo',
    'Lyrics': 'song lyrics text printed page photo',
    'Chorus': 'choir singing chorus group photo',
    'Opera': 'opera singer performing stage costumed photo',
    'Folk music': 'folk music acoustic guitar violin performing photo',
    'Album': 'music vinyl record album cover photo',
    'Tune': 'music tuning fork close up photo',
    'Violin': 'violin instrument and bow photo',
    'Classical music': 'classical music orchestra instruments photo'
}

def slugify(text):
    text = text.lower().strip()
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    vietnamese_map = {
        'đ': 'd', 'â': 'a', 'ă': 'a', 'ê': 'e', 'ô': 'o', 'ơ': 'o', 'ư': 'u',
        'á': 'a', 'à': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
        'ế': 'e', 'ề': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
        'í': 'i', 'ì': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
        'ó': 'o', 'ò': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
        'ú': 'u', 'ù': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
        'ý': 'y', 'ỳ': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y'
    }
    for vn_char, en_char in vietnamese_map.items():
        text = text.replace(vn_char, en_char)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text)
    return text.strip('-')

# Search Bing Images for image URLs list
def search_bing_images(query):
    print(f"Searching Bing Images for: {query}")
    try:
        url = f"https://www.bing.com/images/search?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            matches = re.findall(r'm="([^"]+)"', html)
            image_urls = []
            for m in matches:
                try:
                    m_clean = m.replace('&quot;', '"').replace('&amp;', '&')
                    data = json.loads(m_clean)
                    murl = data.get("murl")
                    if murl:
                        image_urls.append(murl)
                except Exception:
                    pass
            return image_urls
    except Exception as e:
        print(f"Error searching Bing Images: {e}")
    return []

# Download, resize and save image as WebP
def download_and_save_webp(img_url, dest_path):
    try:
        req = urllib.request.Request(
            img_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=6) as response:
            img_data = response.read()
            
        img = Image.open(io.BytesIO(img_data))
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            img = img.convert('RGB')
        else:
            img = img.convert('RGB')
            
        img.thumbnail((300, 300), Image.Resampling.LANCZOS)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        img.save(dest_path, "WEBP", quality=80)
        return True
    except Exception as e:
        print(f"  Fail to download/process {img_url[:60]}: {e}")
    return False

def main():
    vocab_file = "vocabulary.json"
    mapping_file = "image_mappings.json"
    
    if not os.path.exists(vocab_file):
        print(f"Error: {vocab_file} not found.")
        return
        
    with open(vocab_file, "r", encoding="utf-8") as f:
        vocab_list = json.load(f)
        
    # Load existing mappings
    mappings = {}
    if os.path.exists(mapping_file):
        with open(mapping_file, "r", encoding="utf-8") as f:
            try:
                mappings = json.load(f)
            except Exception:
                mappings = {}
                
    # Filter only words in Music (Âm nhạc) category
    music_words = [item for item in vocab_list if item['Phân loại'] == 'Âm nhạc']
    print(f"Found {len(music_words)} words in Âm nhạc (Music) category.")
    
    # Create output directory: public/images/vocabulary/music
    music_dir = "public/images/vocabulary/music"
    os.makedirs(music_dir, exist_ok=True)
    
    # Delete any existing files in public/images/vocabulary/music to ensure clean slate
    print("Cleaning existing files in public/images/vocabulary/music...")
    for filename in os.listdir(music_dir):
        file_path = os.path.join(music_dir, filename)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(f"Error deleting file {file_path}: {e}")
            
    # Scraping each music word
    new_downloads = 0
    errors_count = 0
    
    for item in music_words:
        word = item['Từ vựng']
        category = item['Phân loại']
        word_slug = slugify(word)
        
        relative_path = f"public/images/vocabulary/music/{word_slug}.webp"
        absolute_path = os.path.join(os.getcwd(), relative_path)
        
        mapping_key = f"{word}::{category}"
        
        search_query = MUSIC_QUERIES.get(word, f"{word} music instrument realistic photo")
        image_urls = search_bing_images(search_query)
        
        success = False
        if image_urls:
            # Try top 5 URLs
            for url in image_urls[:5]:
                print(f"  Attempting to download for {word}: {url[:70]}...")
                success = download_and_save_webp(url, absolute_path)
                if success:
                    print(f"  Successfully saved {word} -> {relative_path}")
                    new_downloads += 1
                    break
                    
        if not success:
            print(f"  WARNING: Could not find/download suitable image for {word}. Mark as review placeholder.")
            # Create a simple red/warning placeholder for review
            try:
                img = Image.new('RGB', (300, 300), color=(232, 93, 68)) # red
                from PIL import ImageDraw
                draw = ImageDraw.Draw(img)
                draw.rectangle([10, 10, 290, 290], outline=(10, 10, 10), width=4)
                draw.text((150, 150), f"{word}\n(REVIEW)", fill=(10, 10, 10), anchor="mm")
                img.save(absolute_path, "WEBP", quality=80)
                relative_path = f"public/images/vocabulary/music/{word_slug}.webp"
                success = True
            except Exception:
                relative_path = "images/vocabulary/default_placeholder.webp"
            errors_count += 1
            
        # Update mapping specifically
        mappings[mapping_key] = {
            "word": word,
            "category": category,
            "image": relative_path,
            "review_needed": not success or (word not in MUSIC_QUERIES) or ("Fail" in str(success))
        }
        
        time.sleep(1.0) # Respectful delay
        
    # Write back mappings
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(mappings, f, ensure_ascii=False, indent=2)
        
    print("\n--- Scraper Run Complete for Music ---")
    print(f"Total processed: {len(music_words)}")
    print(f"Downloaded: {new_downloads}")
    print(f"Review placeholders: {errors_count}")

if __name__ == "__main__":
    main()
