import os
import json
import re
import time
import urllib.request
import urllib.parse
from PIL import Image
import io
import zipfile
import xml.etree.ElementTree as ET
import unicodedata
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

# Custom query modifications for high precision
SPECIAL_QUERIES = {
    'Solo': ['violin solo musician performing on stage photo', 'solo pianist close up photo'],
    'Opera': ['opera singer performing stage costumed photo', 'opera house stage interior photo'],
    'The brass': ['brass instruments group trumpet trombone photo', 'marching band brass section photo'],
    'String': ['guitar violin string close up photo', 'violin bow and strings photo'],
    'Note': ['single musical note symbol clear photo', 'sheet music notes close up photo'],
    'Rhythm': ['rhythm sound waves visualizer graphic photo', 'music rhythm beat notes photo'],
    'Play': ['playing piano keyboard hands close up photo', 'playing acoustic guitar hands photo'],
    'Band': ['musical band group performing on stage photo', 'rock band live concert photo'],
    'Tune': ['music tuning fork realistic photo', 'tuning guitar peg close up photo'],
    'Listen': ['person listening with headphones realistic photo', 'listening to music headphones photo'],
    'Volume': ['volume control dial knob realistic photo', 'audio console volume slider photo'],
    'Voice': ['singer vocal microphone close up photo', 'microphone stand recording studio photo']
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

# Parse XLSX file natively
def parse_xlsx(file_path):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return None
    ns = {
        'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
        'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    }
    try:
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            shared_strings = []
            if 'xl/sharedStrings.xml' in zip_ref.namelist():
                with zip_ref.open('xl/sharedStrings.xml') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    for si in root.findall('main:si', ns):
                        t_elements = si.findall('.//main:t', ns)
                        text = "".join([t.text for t in t_elements if t.text is not None])
                        shared_strings.append(text)
            
            rows = []
            with zip_ref.open('xl/worksheets/sheet1.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                sheet_data = root.find('main:sheetData', ns)
                for row_elem in sheet_data.findall('main:row', ns):
                    row_idx = int(row_elem.attrib.get('r', 1))
                    cells = {}
                    for c_elem in row_elem.findall('main:c', ns):
                        cell_ref = c_elem.attrib.get('r', '')
                        cell_type = c_elem.attrib.get('t', '')
                        col_name = ''.join([char for char in cell_ref if char.isalpha()])
                        
                        v_elem = c_elem.find('main:v', ns)
                        val = ""
                        if v_elem is not None and v_elem.text is not None:
                            val = v_elem.text
                            if cell_type == 's':
                                idx = int(val)
                                if idx < len(shared_strings):
                                    val = shared_strings[idx]
                        cells[col_name] = val
                    rows.append((row_idx, cells))
            
            rows.sort(key=lambda x: x[0])
            if not rows:
                return None
            
            header_row_idx, header_cells = rows[0]
            col_letters = sorted(list(header_cells.keys()))
            headers = [header_cells[col].strip() for col in col_letters]
            
            data = []
            for r_idx, r_cells in rows[1:]:
                item = {}
                has_content = False
                for i, col in enumerate(col_letters):
                    val = r_cells.get(col, "").strip()
                    if val:
                        has_content = True
                    item[headers[i]] = val
                if has_content:
                    data.append(item)
            return data
    except Exception as e:
        print("Error parsing XLSX:", e)
        return None

# Search Bing Images using curl to bypass bot verification
def search_bing_images(query):
    try:
        import subprocess
        url = f"https://www.bing.com/images/search?q={urllib.parse.quote(query)}"
        cmd = [
            'curl',
            '-s',
            '-A', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            '-H', 'Accept-Language: en-US,en;q=0.9',
            '-H', 'Referer: https://www.google.com/',
            url
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        html = result.stdout.decode('utf-8', errors='ignore')
        
        matches = re.findall(r'<a[^>]+class="iusc"[^>]+m="([^"]+)"', html)
        if not matches:
            matches = re.findall(r'<a[^>]+m="([^"]+)"[^>]+class="iusc"', html)
            
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
        print(f"    Bing Search error: {e}")
    return []

# Download, resize and save image as WebP using curl to bypass User-Agent blocking
def download_and_save_webp(img_url, dest_path):
    try:
        import subprocess
        cmd = [
            'curl',
            '-s',
            '-L',  # follow redirects
            '--max-time', '8',
            '-A', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            img_url
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0 or not result.stdout:
            print(f"    Curl download failed for: {img_url[:50]}...")
            return False
            
        img_data = result.stdout
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
        print(f"    Fail to download/process: {img_url[:50]}... ({e})")
    return False

def main():
    # Resolve absolute paths relative to this script file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, '..', '..'))
    
    xlsx_file = os.path.join(root_dir, 'data', 'tu_vung_tieng_anh_theo_chu_de.xlsx')
    mapping_file = os.path.join(root_dir, 'data', 'image_mappings.json')
    log_file = os.path.join(root_dir, 'scripts', 'logs', 'music_scraping_log.txt')
    music_dir = os.path.join(root_dir, 'images', 'vocabulary', 'music')
    
    print("Reading vocabulary list from excel...")
    vocab_list = parse_xlsx(xlsx_file)
    if not vocab_list:
        print(f"Error: {xlsx_file} not found.")
        return
        
    music_words = [item for item in vocab_list if item.get('Phân loại') == 'Âm nhạc']
    print(f"Found {len(music_words)} vocabulary words in Âm nhạc (Music) category.")
    
    # Load existing mappings
    mappings = {}
    if os.path.exists(mapping_file):
        with open(mapping_file, "r", encoding="utf-8") as f:
            try:
                mappings = json.load(f)
            except Exception:
                mappings = {}
                
    os.makedirs(music_dir, exist_ok=True)
    
    # Delete existing music images to clean slate for this run
    print("Clearing existing files in public/images/vocabulary/music...")
    for filename in os.listdir(music_dir):
        file_path = os.path.join(music_dir, filename)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(f"Error deleting file {file_path}: {e}")
            
    logs = []
    downloaded_count = 0
    placeholders_count = 0
    
    for idx, item in enumerate(music_words):
        word = item.get('Từ vựng', '').strip()
        meaning = item.get('Ý nghĩa', '').strip()
        category = item.get('Phân loại', '').strip()
        
        if not word:
            continue
            
        word_slug = slugify(word)
        relative_path = f"/images/vocabulary/music/{word_slug}.webp"
        absolute_path = os.path.join(music_dir, f"{word_slug}.webp")
        
        print(f"\n[{idx+1}/{len(music_words)}] Processing: {word} ({meaning})...")
        
        # Clean parentheses and commas from meaning
        clean_meaning = re.sub(r'\(.*?\)', '', meaning)
        clean_meaning = re.sub(r'[^a-zA-Z0-9\s\u00C0-\u1EF9]', ' ', clean_meaning)
        clean_meaning = " ".join(clean_meaning.split())
        
        # Build search queries (Primary and Fallbacks)
        queries = []
        if word in SPECIAL_QUERIES:
            queries.extend(SPECIAL_QUERIES[word])
        else:
            # English word + Clean Vietnamese meaning + Music context
            queries.append(f"{word} {clean_meaning} music performance realistic photo")
            queries.append(f"{word} musical instrument photo")
            queries.append(f"{word} music photo")
            
        success = False
        tried_urls = 0
        download_url = ""
        
        for q_idx, query in enumerate(queries):
            print(f"  Querying: {query}...")
            image_urls = search_bing_images(query)
            if image_urls:
                # Try the top 3 image URLs for this query
                for url in image_urls[:3]:
                    tried_urls += 1
                    print(f"    Trying image {tried_urls}: {url[:70]}...")
                    success = download_and_save_webp(url, absolute_path)
                    if success:
                        download_url = url
                        break
            if success:
                break
                
        mapping_key = f"{word}::{category}"
        
        if success:
            print(f"  SUCCESS: Saved to {relative_path}")
            downloaded_count += 1
            logs.append(f"SUCCESS: {word} ({meaning}) -> Downloaded from {download_url}")
            mappings[mapping_key] = {
                "word": word,
                "category": category,
                "image": relative_path,
                "source_url": download_url
            }
        else:
            print(f"  WARNING: Failed to find image for {word}. Generating placeholder.")
            placeholders_count += 1
            logs.append(f"PLACEHOLDER: {word} ({meaning}) -> No matching image found. Used review placeholder.")
            
            # Generate a nice warning review placeholder
            try:
                img = Image.new('RGB', (300, 300), color=(232, 93, 68))
                from PIL import ImageDraw
                draw = ImageDraw.Draw(img)
                draw.rectangle([10, 10, 290, 290], outline=(10, 10, 10), width=4)
                draw.text((150, 150), f"{word}\n(REVIEW)", fill=(10, 10, 10), anchor="mm")
                img.save(absolute_path, "WEBP", quality=80)
            except Exception:
                pass
                
            mappings[mapping_key] = {
                "word": word,
                "category": category,
                "image": relative_path,
                "review_needed": True
            }
            
        time.sleep(1.2) # Sleep to be polite
        
    # Write back mappings
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(mappings, f, ensure_ascii=False, indent=2)
        
    # Write log file
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("\n".join(logs))
        
    print("\n--- Scraping Completed ---")
    print(f"Total processed: {len(music_words)}")
    print(f"Downloaded: {downloaded_count}")
    print(f"Placeholders: {placeholders_count}")
    print(f"Log written to {log_file}")

if __name__ == "__main__":
    main()
