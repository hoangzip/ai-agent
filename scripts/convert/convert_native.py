import zipfile
import xml.etree.ElementTree as ET
import json
import os

def parse_xlsx(file_path):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return None

    # Namespaces used in Excel XML
    ns = {
        'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
        'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    }

    try:
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            # 1. Parse shared strings
            shared_strings = []
            if 'xl/sharedStrings.xml' in zip_ref.namelist():
                with zip_ref.open('xl/sharedStrings.xml') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    # Find all 't' elements inside 'si'
                    for si in root.findall('main:si', ns):
                        # Some si might have multiple r (rich text) elements
                        t_elements = si.findall('.//main:t', ns)
                        text = "".join([t.text for t in t_elements if t.text is not None])
                        shared_strings.append(text)
            
            # 2. Parse sheet1.xml
            rows = []
            with zip_ref.open('xl/worksheets/sheet1.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                
                sheet_data = root.find('main:sheetData', ns)
                if sheet_data is None:
                    print("Error: sheetData not found in sheet1.xml")
                    return None
                
                for row_elem in sheet_data.findall('main:row', ns):
                    row_idx = int(row_elem.attrib.get('r', 1))
                    # Parse cells inside this row
                    cells = {}
                    for c_elem in row_elem.findall('main:c', ns):
                        cell_ref = c_elem.attrib.get('r', '')
                        cell_type = c_elem.attrib.get('t', '')
                        
                        # Get column name from ref (e.g. "A12" -> "A")
                        col_name = ''.join([char for char in cell_ref if char.isalpha()])
                        
                        v_elem = c_elem.find('main:v', ns)
                        val = ""
                        if v_elem is not None and v_elem.text is not None:
                            val = v_elem.text
                            if cell_type == 's':  # Shared string reference
                                idx = int(val)
                                if idx < len(shared_strings):
                                    val = shared_strings[idx]
                        cells[col_name] = val
                    rows.append((row_idx, cells))
            
            # Sort rows by row index
            rows.sort(key=lambda x: x[0])
            
            # Identify columns
            if not rows:
                print("Error: No rows found.")
                return None
            
            # Header is the first row
            header_row_idx, header_cells = rows[0]
            # Get sorted column letters present in header
            col_letters = sorted(list(header_cells.keys()))
            
            headers = [header_cells[col].strip() for col in col_letters]
            print("Headers:", headers)
            
            # Parse data rows
            data = []
            for r_idx, r_cells in rows[1:]:
                # Map cell values to headers based on column letter
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
        print("Error unzipping or parsing:", e)
        return None

def convert():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, '..', '..'))
    
    file_path = os.path.join(root_dir, 'data', 'tu_vung_tieng_anh_theo_chu_de.xlsx')
    data = parse_xlsx(file_path)
    if data:
        output_path = os.path.join(root_dir, 'data', 'vocabulary.json')
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Successfully converted {len(data)} items to {output_path} natively!")
    else:
        print("Conversion failed.")

if __name__ == "__main__":
    convert()
