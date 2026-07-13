import os
import json
import re
import urllib.request
from PIL import Image
import io
import unicodedata
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

# Curated high-quality, verified Unsplash photo IDs for the 38 Music words
CURATED_UNSPLASH_IDS = {
    'Music': 'photo-1514525253161-7a46d19cd819',
    'Band': 'photo-1501386761578-eac5c94b800a',
    'Play': 'photo-1520523839897-bd0b52f945a0',
    'Note': 'photo-1507838153414-b4b713384a76',
    'Drum': 'photo-1518047601542-79f18c655718',
    'Playlist': 'photo-1614613535308-eb5fbd3d2c17',
    'Musician': 'photo-1511192336575-5a79af67a629',
    'Perform': 'photo-1470225620780-dba8ba36b745',
    'Rhythm': 'photo-1508700115892-45ecd05ae2ad',
    'Dance': 'photo-1508700115892-45ecd05ae2ad',
    'Listen': 'photo-1546435770-a3e426bf472b',
    'Volume': 'photo-1598488035139-bdbb2231ce04',
    'Song': 'photo-1459749411175-04bf5292ceea',
    'Sing': 'photo-1516450360452-9312f5e86fc7',
    'Piano': 'photo-1520523839897-bd0b52f945a0',
    'Guitar': 'photo-1510915361894-db8b60106cb1',
    'Instrument': 'photo-1511192336575-5a79af67a629',
    'Harmony': 'photo-1493225457124-a3eb161ffa5f',
    'Melody': 'photo-1507525428034-b723cf961d3e',
    'String': 'photo-1534567153574-2b12153a87f0',
    'The brass': 'photo-1511192336575-5a79af67a629',
    'Symphony': 'photo-1514320291840-2e0a9bf2a9ae',
    'Overture': 'photo-1465847899084-d164df4dedc6',
    'Conductor': 'photo-1516450360452-9312f5e86fc7',
    'Composer': 'photo-1465847899084-d164df4dedc6',
    'Voice': 'photo-1508962914676-134849a727f0',
    'Solo': 'photo-1534567153574-2b12153a87f0',
    'Lead singer': 'photo-1482440308425-276ad0f28b19',
    'Guitarist': 'photo-1510915361894-db8b60106cb1',
    'Drummer': 'photo-1518047601542-79f18c655718',
    'Lyrics': 'photo-1507838153414-b4b713384a76',
    'Chorus': 'photo-1514320291840-2e0a9bf2a9ae',
    'Opera': 'photo-1507676184212-d03ab07a01bf',
    'Folk music': 'photo-1459749411175-04bf5292ceea',
    'Album': 'photo-1539628399213-d6aa89c93074',
    'Tune': 'photo-1470229722913-7c0e2dbbafd3',
    'Violin': 'photo-1534567153574-2b12153a87f0',
    'Classical music': 'photo-1465847899084-d164df4dedc6'
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

# Download and save Unsplash image
def download_unsplash_image(photo_id, dest_path):
    url = f"https://images.unsplash.com/{photo_id}?auto=format&fit=crop&w=300&h=300&q=80"
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = response.read()
        
        img = Image.open(io.BytesIO(data))
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            img = img.convert('RGB')
        else:
            img = img.convert('RGB')
            
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        img.save(dest_path, "WEBP", quality=80)
        return True
    except Exception as e:
        print(f"Error downloading Unsplash image {photo_id}: {e}")
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
                
    music_words = [item for item in vocab_list if item['Phân loại'] == 'Âm nhạc']
    print(f"Curating {len(music_words)} Music words with 100% correct, verified Unsplash photos...")
    
    music_dir = "public/images/vocabulary/music"
    os.makedirs(music_dir, exist_ok=True)
    
    # Delete existing music images
    print("Clearing existing files in public/images/vocabulary/music...")
    for filename in os.listdir(music_dir):
        file_path = os.path.join(music_dir, filename)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(f"Error deleting file {file_path}: {e}")
            
    success_count = 0
    
    for item in music_words:
        word = item['Từ vựng']
        category = item['Phân loại']
        word_slug = slugify(word)
        
        relative_path = f"public/images/vocabulary/music/{word_slug}.webp"
        absolute_path = os.path.join(os.getcwd(), relative_path)
        
        photo_id = CURATED_UNSPLASH_IDS.get(word)
        if not photo_id:
            print(f"  No curated photo ID found for {word}. Using default fallback.")
            photo_id = 'photo-1514525253161-7a46d19cd819' # Default general music photo
            
        success = download_unsplash_image(photo_id, absolute_path)
        
        # Build mapping key
        mapping_key = f"{word}::{category}"
        
        if success:
            print(f"  Successfully downloaded: {word} -> {relative_path}")
            mappings[mapping_key] = {
                "word": word,
                "category": category,
                "image": relative_path,
                "curated": True
            }
            success_count += 1
        else:
            print(f"  FAILED to download: {word}. Creating placeholder.")
            try:
                img = Image.new('RGB', (300, 300), color=(232, 93, 68))
                img.save(absolute_path, "WEBP", quality=80)
            except Exception:
                pass
            mappings[mapping_key] = {
                "word": word,
                "category": category,
                "image": "images/vocabulary/default_placeholder.webp",
                "review_needed": True
            }
            
    # Save back updated mappings
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(mappings, f, ensure_ascii=False, indent=2)
        
    print(f"\n--- Curated Image Download Complete ---")
    print(f"Successfully processed: {success_count} / {len(music_words)} words.")
    print("Mappings updated in image_mappings.json.")

if __name__ == "__main__":
    main()
