import os
import json

def generate_report():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, '..', '..'))
    
    mapping_file = os.path.join(root_dir, 'data', 'image_mappings.json')
    vocab_file = os.path.join(root_dir, 'data', 'vocabulary.json')
    images_dir = os.path.join(root_dir, 'images', 'vocabulary')
    
    if not os.path.exists(vocab_file):
        print(f"Error: {vocab_file} not found.")
        return
        
    with open(vocab_file, "r", encoding="utf-8") as f:
        vocab_list = json.load(f)
        
    mappings = {}
    if os.path.exists(mapping_file):
        with open(mapping_file, "r", encoding="utf-8") as f:
            mappings = json.load(f)
            
    total_words = len(vocab_list)
    mapped_count = 0
    success_count = 0
    review_needed_count = 0
    placeholder_count = 0
    missing_files_count = 0
    invalid_files_count = 0
    
    missing_words = []
    broken_mappings = []
    
    for item in vocab_list:
        word = item.get("Từ vựng", "").strip()
        category = item.get("Phân loại", "").strip()
        if not word or not category:
            continue
            
        key = f"{word}::{category}"
        mapping = mappings.get(key)
        
        if not mapping:
            missing_words.append((word, category))
            continue
            
        mapped_count += 1
        img_path = mapping.get("image", "")
        status = mapping.get("status", "")
        source = mapping.get("source", "")
        
        # Resolve absolute path on disk
        clean_path = img_path
        if clean_path.startswith("/"):
            clean_path = clean_path[1:]
        abs_img_path = os.path.join(root_dir, clean_path)
        
        # Verify file existence and size
        if not os.path.exists(abs_img_path):
            missing_files_count += 1
            broken_mappings.append(f"MISSING FILE: {word} ({category}) -> expected at {abs_img_path}")
        elif os.path.getsize(abs_img_path) < 100:
            invalid_files_count += 1
            broken_mappings.append(f"INVALID/TINY FILE: {word} ({category}) -> {abs_img_path} ({os.path.getsize(abs_img_path)} bytes)")
            
        if status == "success" or source == "bing":
            success_count += 1
        elif status == "review" or mapping.get("review_needed"):
            review_needed_count += 1
        else:
            placeholder_count += 1
            
    print("==================================================")
    print("          VOCABULARY IMAGES AUDIT REPORT          ")
    print("==================================================")
    print(f"Total Words in Excel/JSON database : {total_words}")
    print(f"Total Mapped Words in image_maps   : {mapped_count} ({mapped_count/total_words*100:.1f}%)")
    print(f"Unmapped / Missing Mappings        : {len(missing_words)}")
    print(f"Successfully Scraped Images        : {success_count}")
    print(f"Placeholders / Stubs               : {placeholder_count}")
    print(f"Needs Review (Download Failed)     : {review_needed_count}")
    print(f"Missing Files on Disk              : {missing_files_count}")
    print(f"Invalid / Corrupted Files          : {invalid_files_count}")
    print("==================================================")
    
    if broken_mappings:
        print("\nBroken Mappings Details:")
        for bm in broken_mappings[:20]:
            print(f"  - {bm}")
        if len(broken_mappings) > 20:
            print(f"  ... and {len(broken_mappings)-20} more.")
            
    if missing_words:
        print("\nFirst 10 Missing Mappings:")
        for w, c in missing_words[:10]:
            print(f"  - {w} (Category: {c})")
        if len(missing_words) > 10:
            print(f"  ... and {len(missing_words)-10} more.")
    print("==================================================")

if __name__ == "__main__":
    generate_report()
