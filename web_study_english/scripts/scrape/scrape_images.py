import os
import json
import re
import time
import urllib.request
import urllib.parse
import ssl

ssl._create_default_https_context = ssl._create_unverified_context
from PIL import Image
import io
import unicodedata
from duckduckgo_search import DDGS

# ----------------- Helper functions -----------------

def slugify(text):
    text = text.lower().strip()
    # Remove accents using unicodedata
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    
    # Custom Vietnamese mapping for characters not handled by normalizer
    vietnamese_map = {
        'đ': 'd', 'đ': 'd',
        'â': 'a', 'ă': 'a', 'ê': 'e', 'ô': 'o', 'ơ': 'o', 'ư': 'u',
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

# Get image URL from Lorem Flickr
def get_image_url(word):
    return f"https://loremflickr.com/300/300/{urllib.parse.quote(word)}"

# Download, resize and save image as WebP
def download_and_save_webp(img_url, dest_path):
    try:
        req = urllib.request.Request(
            img_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            img_data = response.read()
            
        # Parse image using Pillow
        img = Image.open(io.BytesIO(img_data))
        
        # Convert RGBA to RGB (WebP supports alpha, but RGB is safer for output)
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            img = img.convert('RGB')
        else:
            img = img.convert('RGB')
            
        # Resize to max 300px width/height while maintaining aspect ratio
        img.thumbnail((300, 300), Image.Resampling.LANCZOS)
        
        # Create output directory
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        
        # Save as WebP
        img.save(dest_path, "WEBP", quality=80)
        return True
    except Exception as e:
        print(f"Error downloading or processing image {img_url}: {e}")
    return False

# Generate a high-quality category placeholder image with initials/letters
def generate_placeholder_image(word, category_color, dest_path):
    try:
        from PIL import ImageDraw, ImageFont
        # Create a simple colored 300x300 canvas
        img = Image.new('RGB', (300, 300), color=category_color)
        draw = ImageDraw.Draw(img)
        
        # Draw a clean border inside
        draw.rectangle([10, 10, 290, 290], outline=(10, 10, 10), width=4)
        
        # Write first letter
        first_letter = word[0].upper() if word else "A"
        
        # Attempt to load a default font
        try:
            # Try to load a standard system font
            font = ImageFont.truetype("Arial.ttf", 120)
        except IOError:
            font = ImageFont.load_default()
            
        # Draw text centered (simple coordinates since load_default doesn't support size)
        draw.text((150, 150), first_letter, fill=(10, 10, 10), anchor="mm", font=font)
        
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        img.save(dest_path, "WEBP", quality=80)
        return True
    except Exception as e:
        # Fallback to a solid color if PIL drawing fails
        try:
            img = Image.new('RGB', (300, 300), color=category_color)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            img.save(dest_path, "WEBP", quality=80)
            return True
        except Exception as ex:
            print(f"Error generating fallback: {ex}")
    return False

# ----------------- Main runner -----------------

# Distinct colors for fallback placeholders
ACCENT_COLORS = [
    (79, 103, 232),   # Blue: #4F67E8
    (232, 93, 68),    # Red: #E85D44
    (58, 158, 117),   # Green: #3A9E75
    (245, 200, 76),   # Yellow: #F5C84C
    (232, 162, 201),  # Pink: #E8A2C9
]

def main():
    vocab_file = "vocabulary.json"
    mapping_file = "image_mappings.json"
    
    if not os.path.exists(vocab_file):
        print(f"Error: {vocab_file} not found.")
        return
        
    with open(vocab_file, "r", encoding="utf-8") as f:
        vocab_list = json.load(f)
        
    # Load existing mappings if any
    mappings = {}
    if os.path.exists(mapping_file):
        with open(mapping_file, "r", encoding="utf-8") as f:
            try:
                mappings = json.load(f)
            except Exception:
                mappings = {}
                
    print(f"Loaded {len(vocab_list)} vocabulary items.")
    print(f"Existing mappings found: {len(mappings)}")
    
    # Create public/images/vocabulary structure or images/vocabulary
    base_dir = "images/vocabulary"
    os.makedirs(base_dir, exist_ok=True)
    
    # Generate global default placeholder if needed
    default_placeholder_path = os.path.join(base_dir, "default_placeholder.webp")
    if not os.path.exists(default_placeholder_path):
        try:
            img = Image.new('RGB', (300, 300), color=(220, 220, 220))
            img.save(default_placeholder_path, "WEBP", quality=80)
        except Exception as e:
            print("Failed to save default placeholder:", e)
            
    # Process words in vocabulary list
    processed_count = 0
    new_downloads = 0
    errors_count = 0
    
    # Categories set to allocate a distinct fallback color per category
    unique_categories = sorted(list(set(item['Phân loại'] for item in vocab_list)))
    cat_colors = {}
    for i, cat in enumerate(unique_categories):
        cat_colors[cat] = ACCENT_COLORS[i % len(ACCENT_COLORS)]
        
    # We will process a limit of real scrapes,
    # and generate custom placeholders for the rest, allowing the app to run immediately with all images present.
    # The user can run this script repeatedly to download more images over time.
    MAX_SCRAPES = 150  # Download first 150 images as real scrapes, rest get custom placeholders.
    
    for idx, item in enumerate(vocab_list):
        word = item['Từ vựng']
        category = item['Phân loại']
        
        cat_slug = slugify(category)
        word_slug = slugify(word)
        
        # Construct paths
        relative_path = f"images/vocabulary/{cat_slug}/{word_slug}.webp"
        absolute_path = os.path.join(os.getcwd(), relative_path)
        
        mapping_key = f"{word}::{category}"
        
        # Check if already mapped and file exists
        if mapping_key in mappings and os.path.exists(absolute_path):
            processed_count += 1
            continue
            
        # Need to download or generate
        success = False
        
        # If we haven't exceeded MAX_SCRAPES, try to download from Lorem Flickr
        if new_downloads < MAX_SCRAPES:
            print(f"Downloading image for: {word} ({category})...")
            img_url = get_image_url(word)
            success = download_and_save_webp(img_url, absolute_path)
            if success:
                new_downloads += 1
                print(f"Success! Saved to {relative_path}")
                time.sleep(0.2)  # Short delay
            else:
                print("Failed to download image from Lorem Flickr.")
                
        # If download failed or skipped, generate custom colored placeholder
        if not success:
            color = cat_colors.get(category, (200, 200, 200))
            success = generate_placeholder_image(word, color, absolute_path)
            if success:
                print(f"Generated fallback placeholder for: {word} -> {relative_path}")
            else:
                relative_path = "images/vocabulary/default_placeholder.webp"
                errors_count += 1
                
        # Update mapping
        mappings[mapping_key] = {
            "word": word,
            "category": category,
            "image": relative_path
        }
        
        processed_count += 1
        
        # Periodically save mappings file
        if processed_count % 10 == 0:
            with open(mapping_file, "w", encoding="utf-8") as f:
                json.dump(mappings, f, ensure_ascii=False, indent=2)
                
    # Save final mappings
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(mappings, f, ensure_ascii=False, indent=2)
        
    print("\n--- Scraping Complete ---")
    print(f"Total vocabulary items processed: {processed_count}")
    print(f"New downloads: {new_downloads}")
    print(f"Mapping entries in {mapping_file}: {len(mappings)}")
    if errors_count:
        print(f"Errors occurred for {errors_count} items (fallback to default placeholder).")

if __name__ == "__main__":
    main()
