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
import sys

ssl._create_default_https_context = ssl._create_unverified_context

# Translate Vietnamese categories to English slugs to avoid font/encoding errors in paths
CATEGORY_MAP = {
    "Bóng đá": "football",
    "Bưu điện": "post-office",
    "Bệnh viện": "hospital",
    "Bộ phận cơ thể": "body-parts",
    "Chế độ ăn uống": "diet",
    "Chỉ đường": "directions",
    "Chủ đề biển": "sea",
    "Các loài hoa": "flowers",
    "Côn trùng": "insects",
    "Công việc nhà": "housework",
    "Cảm xúc, cảm giác": "emotions",
    "Cửa hàng": "shops",
    "Du lịch": "travel",
    "Gia đình": "family",
    "Giao thông": "transportation",
    "Giáng sinh": "christmas",
    "Giáo dục": "education",
    "Giải trí": "entertainment",
    "Hoạt động thường ngày": "daily-activities",
    "Hành động": "actions",
    "Hải sản": "seafood",
    "Học tập": "studying",
    "Mua sắm": "shopping",
    "Màu sắc": "colors",
    "Máy tính": "computers",
    "Môi trường": "environment",
    "Nghề nghiệp": "jobs",
    "Ngân hàng": "banking",
    "Nhà bếp": "kitchen",
    "Nhà hàng, khách sạn": "restaurants-hotels",
    "Năng lượng": "energy",
    "Phim ảnh": "movies",
    "Phòng khách": "living-room",
    "Phòng khách sạn": "hotel-rooms",
    "Phòng ngủ": "bedroom",
    "Quê hương": "hometown",
    "Quần áo": "clothing",
    "Quốc gia": "countries",
    "Rau, củ, quả": "vegetables",
    "Sân bay": "airport",
    "Số": "numbers",
    "Sức khỏe": "health",
    "Thảm họa thiên nhiên": "natural-disasters",
    "Thể thao": "sports",
    "Thời gian": "time",
    "Thời tiết": "weather",
    "Thực vật": "plants",
    "Trái cây": "fruits",
    "Trường học": "schools",
    "Tình bạn": "friendship",
    "Tình yêu": "love",
    "Tính cách": "personality",
    "Tết trung thu": "mid-autumn-festival",
    "Âm nhạc": "music",
    "Đám cưới": "wedding",
    "Đồ dùng học tập": "school-supplies",
    "Đồ trang sức": "jewelry",
    "Đồ uống": "drinks",
    "Đồ ăn": "food",
    "Động vật": "animals"
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

# Download, center crop to 480x320 and save image as WebP using curl
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
            return False
            
        img_data = result.stdout
        img = Image.open(io.BytesIO(img_data))
        
        # Convert transparent/palette images to RGB
        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        # aspect ratio cropping to exactly 480x320 (3:2 aspect ratio)
        target_w, target_h = 480, 320
        target_ratio = target_w / target_h
        
        orig_w, orig_h = img.size
        orig_ratio = orig_w / orig_h
        
        if orig_ratio > target_ratio:
            # Source image is wider, crop the sides
            new_w = int(target_ratio * orig_h)
            offset = (orig_w - new_w) // 2
            img = img.crop((offset, 0, orig_w - offset, orig_h))
        else:
            # Source image is taller, crop top/bottom
            new_h = int(orig_w / target_ratio)
            offset = (orig_h - new_h) // 2
            img = img.crop((0, offset, orig_w, orig_h - offset))
            
        # Resize to standardized dimensions
        img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        img.save(dest_path, "WEBP", quality=80)
        return True
    except Exception:
        pass
    return False

def main():
    force_overwrite = '--force' in sys.argv
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, '..', '..'))
    
    xlsx_file = os.path.join(root_dir, 'data', 'tu_vung_tieng_anh_theo_chu_de.xlsx')
    mapping_file = os.path.join(root_dir, 'data', 'image_mappings.json')
    log_file = os.path.join(root_dir, 'scripts', 'logs', 'all_categories_scraping_log.txt')
    
    print("Reading vocabulary list from excel...")
    vocab_list = parse_xlsx(xlsx_file)
    if not vocab_list:
        print(f"Error: {xlsx_file} not found.")
        return
        
    print(f"Total vocabulary items: {len(vocab_list)}")
    
    # Load existing mappings
    mappings = {}
    if os.path.exists(mapping_file):
        with open(mapping_file, "r", encoding="utf-8") as f:
            try:
                mappings = json.load(f)
            except Exception:
                mappings = {}
                
    success_count = 0
    skip_count = 0
    fail_count = 0
    review_needed_count = 0
    logs = []
    
    for idx, item in enumerate(vocab_list):
        word = item.get('Từ vựng', '').strip()
        meaning = item.get('Ý nghĩa', '').strip()
        category = item.get('Phân loại', '').strip()
        
        if not word or not category:
            continue
            
        # Skip Music category as explicitly requested
        if category == "Âm nhạc":
            continue
            
        # Get English category slug
        en_cat_slug = CATEGORY_MAP.get(category, slugify(category))
        word_slug = slugify(word)
        
        relative_path = f"/images/vocabulary/{en_cat_slug}/{word_slug}.webp"
        absolute_path = os.path.join(root_dir, 'images', 'vocabulary', en_cat_slug, f"{word_slug}.webp")
        
        mapping_key = f"{word}::{category}"
        
        # Check if valid image already exists and skip if --force not passed
        if not force_overwrite and os.path.exists(absolute_path) and os.path.getsize(absolute_path) > 1024:
            mappings[mapping_key] = {
                "category": category,
                "categorySlug": en_cat_slug,
                "word": word,
                "wordSlug": word_slug,
                "image": relative_path,
                "source": "bing",
                "status": "success"
            }
            skip_count += 1
            continue
            
        print(f"[{idx+1}/{len(vocab_list)}] Scrape: {word} ({meaning}) in [{category} -> {en_cat_slug}]...")
        logs.append(f"Processing Category: {category} ({en_cat_slug}) | Word: {word}")
        
        # Clean parentheses and commas from meaning for precise search query
        clean_meaning = re.sub(r'\(.*?\)', '', meaning)
        clean_meaning = re.sub(r'[^a-zA-Z0-9\s\u00C0-\u1EF9]', ' ', clean_meaning)
        clean_meaning = " ".join(clean_meaning.split())
        
        # Construct search queries
        queries = [
            f"{word} {clean_meaning} {en_cat_slug} realistic photo",
            f"{word} {en_cat_slug} isolated object photo",
            f"{word} {clean_meaning} photo",
            f"{word} photo"
        ]
        
        success = False
        download_url = ""
        
        # Try at least 3 queries/results before fallback to placeholder
        for q_idx, query in enumerate(queries):
            logs.append(f"  Query: {query}")
            image_urls = search_bing_images(query)
            if image_urls:
                # Try top 3 image URLs
                for url in image_urls[:3]:
                    success = download_and_save_webp(url, absolute_path)
                    if success:
                        download_url = url
                        break
            if success:
                break
                
        if success:
            print(f"  SUCCESS: Downloaded to {relative_path}")
            success_count += 1
            logs.append(f"  Status: SUCCESS | Source URL: {download_url} | Saved Path: {relative_path}")
            mappings[mapping_key] = {
                "category": category,
                "categorySlug": en_cat_slug,
                "word": word,
                "wordSlug": word_slug,
                "image": relative_path,
                "source": "bing",
                "status": "success"
            }
        else:
            print(f"  WARNING: Failed to download image for {word}. Generating review placeholder.")
            review_needed_count += 1
            logs.append(f"  Status: REVIEW_NEEDED | Used review placeholder")
            
            # Generate placeholder image
            try:
                os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
                img = Image.new('RGB', (480, 320), color=(232, 93, 68))
                from PIL import ImageDraw
                draw = ImageDraw.Draw(img)
                draw.rectangle([10, 10, 470, 310], outline=(10, 10, 10), width=4)
                draw.text((240, 160), f"{word}\n({category})\n(REVIEW)", fill=(10, 10, 10), anchor="mm")
                img.save(absolute_path, "WEBP", quality=80)
            except Exception:
                pass
                
            mappings[mapping_key] = {
                "category": category,
                "categorySlug": en_cat_slug,
                "word": word,
                "wordSlug": word_slug,
                "image": relative_path,
                "source": "placeholder",
                "status": "review"
            }
            
        # Write back mappings periodically (every 10 processed items)
        if (success_count + review_needed_count) % 10 == 0:
            with open(mapping_file, "w", encoding="utf-8") as f:
                json.dump(mappings, f, ensure_ascii=False, indent=2)
                
            # Write partial log file
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("\n".join(logs))
                
        # Sleep to be polite
        time.sleep(0.8)
        
    # Final save
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(mappings, f, ensure_ascii=False, indent=2)
        
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("\n".join(logs))
        
    print("\n--- Scraping Completed ---")
    print(f"Total words: {len(vocab_list)}")
    print(f"Already exists / Skipped: {skip_count}")
    print(f"Newly downloaded: {success_count}")
    print(f"Failed / Review Needed: {review_needed_count}")
    print(f"Log written to: {log_file}")

if __name__ == "__main__":
    main()
