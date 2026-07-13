import os
import json

def fix_mappings():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, '..', '..'))
    mapping_file = os.path.join(root_dir, 'data', 'image_mappings.json')
    
    if not os.path.exists(mapping_file):
        print(f"Error: {mapping_file} not found.")
        return
        
    with open(mapping_file, "r", encoding="utf-8") as f:
        mappings = json.load(f)
        
    updated_count = 0
    for key, item in mappings.items():
        original_image = item.get("image", "")
        if not original_image:
            continue
            
        cleaned = original_image
        if cleaned.startswith("public/"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("public"):
            cleaned = cleaned[6:]
            
        if not cleaned.startswith("/"):
            cleaned = "/" + cleaned
            
        if cleaned != original_image:
            item["image"] = cleaned
            updated_count += 1
            
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(mappings, f, ensure_ascii=False, indent=2)
        
    print(f"Standardized {updated_count} image path references in {mapping_file} to start with leading slash /images/vocabulary/...")

if __name__ == "__main__":
    fix_mappings()
