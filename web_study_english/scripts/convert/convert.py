import pandas as pd
import json
import os

def convert():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, '..', '..'))
    
    file_path = os.path.join(root_dir, 'data', 'tu_vung_tieng_anh_theo_chu_de.xlsx')
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return
    
    try:
        # Load the Excel file
        df = pd.read_excel(file_path)
        print("Columns found:", df.columns.tolist())
        
        # Expecting columns: Phân loại, Từ vựng, Từ loại, Phiên âm, Ý nghĩa
        # Let's clean headers to match
        df.columns = [c.strip() for c in df.columns]
        
        # Convert to dictionary list
        data = df.to_dict(orient="records")
        
        # Save as JSON
        output_path = os.path.join(root_dir, 'data', 'vocabulary.json')
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        print(f"Successfully converted {len(data)} items to {output_path}")
    except Exception as e:
        print("Error converting file:", e)

if __name__ == "__main__":
    convert()
