import { getVocabularyImage } from '../helpers.js';

function getWordTypeClass(type) {
  const t = (type || "").toLowerCase().trim();
  if (t === 'n' || t.startsWith('n.')) return 'type-n';
  if (t === 'v' || t.startsWith('v.')) return 'type-v';
  if (t === 'adj' || t.startsWith('adj.')) return 'type-adj';
  if (t === 'adv' || t.startsWith('adv.')) return 'type-adv';
  return 'type-other';
}

export function WordList(categoryName, words, searchQuery = "", imageMappings = {}) {
  const filteredWords = words.filter(w => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return true;
    return (
      w['Từ vựng'].toLowerCase().includes(q) ||
      w['Ý nghĩa'].toLowerCase().includes(q) ||
      (w['Phiên âm'] || "").toLowerCase().includes(q)
    );
  });

  const wordsHtml = filteredWords.map(w => {
    const word = w['Từ vựng'];
    const type = w['Từ loại'] || '';
    const ipa = w['Phiên âm'] || '';
    const meaning = w['Ý nghĩa'] || '';
    const typeClass = getWordTypeClass(type);
    
    // Find image mapping using standard helper
    const imgSrc = getVocabularyImage(categoryName, word, imageMappings);
    
    return `
      <div class="card-word">
        <div class="word-image-container">
          <img class="word-image" src="${imgSrc}" alt="${word}" loading="lazy">
        </div>
        <div class="word-header">
          <div class="word-term-wrap">
            <h4 class="word-term">${word}</h4>
            ${type ? `<span class="word-type ${typeClass}">${type}</span>` : ''}
          </div>
          
          <button class="btn-speak" data-word="${word.replace(/"/g, '&quot;')}" aria-label="Phát âm">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
              <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
            </svg>
          </button>
        </div>
        
        <div class="word-ipa">${ipa}</div>
        <hr class="word-divider">
        <div class="word-meaning">${meaning}</div>
      </div>
    `;
  }).join("");

  const contentHtml = filteredWords.length > 0
    ? `<div class="grid-words">${wordsHtml}</div>`
    : `
      <div class="empty-state">
        <h4 class="empty-state-title">Không tìm thấy từ vựng</h4>
        <p class="empty-state-desc">Hãy thử tìm kiếm với từ khóa hoặc phiên âm khác!</p>
      </div>
    `;

  return `
    <div class="container">
      <div class="view-header">
        <button class="btn-back" id="btn-back-home">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
            <line x1="19" y1="12" x2="5" y2="12"></line>
            <polyline points="12 19 5 12 12 5"></polyline>
          </svg>
          Quay lại chủ đề
        </button>
        
        <div class="view-title-wrap">
          <h2 class="view-title">Chủ đề: ${categoryName}</h2>
          <span class="view-count-badge">${words.length} từ vựng</span>
        </div>
      </div>
      
      <div class="search-container">
        <span class="search-icon">🔍</span>
        <input 
          type="text" 
          class="search-input" 
          id="word-search" 
          placeholder="Tìm kiếm từ vựng hoặc nghĩa..." 
          value="${searchQuery.replace(/"/g, '&quot;')}"
          autocomplete="off"
        >
      </div>
      
      ${contentHtml}
    </div>
  `;
}
