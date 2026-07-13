export const CATEGORY_MAP = {
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
};

/**
 * Standardizes a text string into a clean URL-friendly slug.
 * Removes Vietnamese accents, converts to lowercase, replaces spaces with hyphens.
 * 
 * @param {string} text - The input text to slugify.
 * @returns {string} The formatted slug.
 */
export function slugify(text) {
  if (!text) return '';
  let str = text.toLowerCase().trim();
  
  // Normalize and remove accents
  str = str.normalize('NFKD').replace(/[\u0300-\u036f]/g, '');
  
  // Replace Vietnamese specific characters
  const map = {
    'đ': 'd', 'â': 'a', 'ă': 'a', 'ê': 'e', 'ô': 'o', 'ơ': 'o', 'ư': 'u',
    'á': 'a', 'à': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
    'ế': 'e', 'ề': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
    'í': 'i', 'ì': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
    'ó': 'o', 'ò': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
    'ú': 'u', 'ù': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
    'ý': 'y', 'ỳ': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y'
  };
  
  for (const [key, val] of Object.entries(map)) {
    str = str.replace(new RegExp(key, 'g'), val);
  }
  
  // Remove special characters, replace spaces/multiple hyphens with single hyphen
  str = str.replace(/[^a-z0-9\s-]/g, '');
  str = str.replace(/[\s-]+/g, '-');
  return str.trim().replace(/^-+|-+$/g, ''); // strip leading/trailing hyphens
}

/**
 * Centrally resolves the absolute URL path of a vocabulary word image.
 * Uses image_mappings if available, standardizes path prefixes, and falls back to a clean slug path.
 * 
 * @param {string} category - The vocabulary category (e.g., 'Âm nhạc').
 * @param {string} word - The vocabulary English word (e.g., 'Guitar').
 * @param {object} imageMappings - The dictionary of image mappings loaded from image_mappings.json.
 * @returns {string} The standardized image path beginning with a leading slash.
 */
export function getVocabularyImage(category, word, imageMappings = {}) {
  const key = `${word}::${category}`;
  const mapping = imageMappings[key];
  let imgPath = '';
  
  if (mapping && mapping.image) {
    imgPath = mapping.image;
  } else {
    // Fallback: build slug path dynamically using English category mapping
    const enCategory = CATEGORY_MAP[category] || category;
    const catSlug = slugify(enCategory);
    const wordSlug = slugify(word);
    imgPath = `images/vocabulary/${catSlug}/${wordSlug}.webp`;
  }
  
  // Standardize path: remove public/ prefix if it exists
  if (imgPath.startsWith('public/')) {
    imgPath = imgPath.substring(7); // strip 'public/'
  }
  if (imgPath.startsWith('public')) {
    imgPath = imgPath.substring(6); // strip 'public'
  }
  
  // Ensure it has a leading slash
  if (!imgPath.startsWith('/')) {
    imgPath = '/' + imgPath;
  }
  
  return imgPath;
}
