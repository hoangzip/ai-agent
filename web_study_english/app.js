import { Header } from './components/Header.js';
import { Hero } from './components/Hero.js';
import { CategoryGrid } from './components/CategoryGrid.js';
import { WordList } from './components/WordList.js';
import { PlatformFeatures, HowItWorks, AboutSection, ContactSection } from './components/LandingSections.js';
import { getVocabularyImage, CATEGORY_MAP, slugify } from './helpers.js?v=2';

// Application State
const state = {
  currentView: 'home', // 'home' or 'category'
  selectedCategory: '',
  searchQuery: '',
  vocabularyData: [],
  categories: [], // Array of { name, count }
  imageMappings: {} // Mapping of "word::category" -> image path
};

// Select DOM elements
const appEl = document.getElementById('app');

// Fetch and initialize data
async function init() {
  try {
    const [vocabResponse, mappingResponse, familyResponse, examplesResponse, synonymsResponse, antonymsResponse] = await Promise.all([
      fetch('data/vocabulary.json'),
      fetch('data/image_mappings.json').catch(() => null),
      fetch('data/word-families/music.json').catch(() => null),
      fetch('data/examples/music.json').catch(() => null),
      fetch('data/synonyms/music.json').catch(() => null),
      fetch('data/antonyms/music.json').catch(() => null)
    ]);

    if (!vocabResponse.ok) {
      throw new Error(`HTTP error! status: ${vocabResponse.status}`);
    }
    state.vocabularyData = await vocabResponse.json();
    
    if (mappingResponse && mappingResponse.ok) {
      try {
        state.imageMappings = await mappingResponse.json();
      } catch (e) {
        console.warn("Failed to parse image_mappings.json:", e);
        state.imageMappings = {};
      }
    } else {
      state.imageMappings = {};
    }

    if (familyResponse && familyResponse.ok) {
      try {
        state.wordFamilies = await familyResponse.json();
      } catch (e) {
        console.warn("Failed to parse music.json:", e);
        state.wordFamilies = [];
      }
    } else {
      state.wordFamilies = [];
    }

    if (examplesResponse && examplesResponse.ok) {
      try {
        state.examples = await examplesResponse.json();
      } catch (e) {
        console.warn("Failed to parse examples:", e);
        state.examples = [];
      }
    } else {
      state.examples = [];
    }

    if (synonymsResponse && synonymsResponse.ok) {
      try {
        state.synonyms = await synonymsResponse.json();
      } catch (e) {
        console.warn("Failed to parse synonyms:", e);
        state.synonyms = [];
      }
    } else {
      state.synonyms = [];
    }

    if (antonymsResponse && antonymsResponse.ok) {
      try {
        state.antonyms = await antonymsResponse.json();
      } catch (e) {
        console.warn("Failed to parse antonyms:", e);
        state.antonyms = [];
      }
    } else {
      state.antonyms = [];
    }
    
    // Group and count categories
    const counts = {};
    state.vocabularyData.forEach(item => {
      const cat = item['Phân loại'] || 'Khác';
      counts[cat] = (counts[cat] || 0) + 1;
    });

    state.categories = Object.keys(counts).map(name => ({
      name,
      count: counts[name]
    })).sort((a, b) => a.name.localeCompare(b.name, 'vi'));

    // Render initial view
    render();
  } catch (error) {
    console.error("Failed to load vocabulary data:", error);
    appEl.innerHTML = `
      <div class="container" style="padding: 100px 20px; text-align: center;">
        <div style="border: 2px solid var(--color-black); background: #FFF; padding: 40px; border-radius: 16px; box-shadow: var(--shadow-flat); max-width: 600px; margin: 0 auto;">
          <h2 style="font-family: var(--font-title); font-weight: 800; margin-bottom: 16px; color: var(--accent-red);">Cảnh báo CORS / Lỗi kết nối</h2>
          <p style="margin-bottom: 24px; color: #555;">
            Trình duyệt của bạn đang chặn yêu cầu tải file dữ liệu cục bộ do chính sách bảo mật (CORS).
          </p>
          <div style="background: #F0F0F0; padding: 16px; border-radius: 8px; font-family: monospace; font-size: 14px; text-align: left; border: 1px solid #CCC; margin-bottom: 24px;">
            Nhấp chuột vào nút "Start Server" hoặc chạy lệnh sau trong thư mục dự án để xem website:<br><br>
            <strong>python3 -m http.server 8000</strong>
          </div>
          <p style="font-weight: 600; font-size: 14px;">Sau khi chạy server, truy cập vào URL: <a href="http://localhost:8000" style="color: var(--accent-blue);">http://localhost:8000</a></p>
        </div>
      </div>
    `;
  }
}

// Map of loaded category slugs to avoid duplicate fetches
const loadedCategories = new Set(['music']); // music is loaded by default in init()

async function loadCategoryMetadata(categoryName) {
  if (!categoryName) return;
  const slug = CATEGORY_MAP[categoryName] || slugify(categoryName);
  if (!slug || loadedCategories.has(slug)) return;
  
  loadedCategories.add(slug);
  
  try {
    const [familyRes, examplesRes, synonymsRes, antonymsRes] = await Promise.all([
      fetch(`data/word-families/${slug}.json`).catch(() => null),
      fetch(`data/examples/${slug}.json`).catch(() => null),
      fetch(`data/synonyms/${slug}.json`).catch(() => null),
      fetch(`data/antonyms/${slug}.json`).catch(() => null)
    ]);
    
    if (familyRes && familyRes.ok) {
      const data = await familyRes.json().catch(() => []);
      state.wordFamilies = [...(state.wordFamilies || []), ...data];
    }
    if (examplesRes && examplesRes.ok) {
      const data = await examplesRes.json().catch(() => []);
      state.examples = [...(state.examples || []), ...data];
    }
    if (synonymsRes && synonymsRes.ok) {
      const data = await synonymsRes.json().catch(() => []);
      state.synonyms = [...(state.synonyms || []), ...data];
    }
    if (antonymsRes && antonymsRes.ok) {
      const data = await antonymsRes.json().catch(() => []);
      state.antonyms = [...(state.antonyms || []), ...data];
    }
  } catch (e) {
    console.warn(`Failed to load metadata for category ${categoryName} (${slug}):`, e);
  }
}

// Footer Component
function Footer() {
  return `
    <footer style="background-color: var(--color-black); color: var(--color-white); padding: 40px 0; margin-top: 80px; border-top: var(--border-brutal);">
      <div class="container" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 20px;">
        <div style="font-family: var(--font-title); font-weight: 800; font-size: 20px;">ziph.eng</div>
        <div style="font-size: 14px; color: #8A8A93;">&copy; 2026 ZipH English AI. All rights reserved.</div>
      </div>
    </footer>
  `;
}

// Render the page based on current view
function render() {
  if (state.currentView === 'home') {
    appEl.innerHTML = `
      ${Header()}
      ${Hero()}
      <main id="main-content">
        ${PlatformFeatures()}
        ${HowItWorks()}
        ${AboutSection()}
        ${ContactSection()}
      </main>
      ${Footer()}
    `;
  } else if (state.currentView === 'vocabulary') {
    appEl.innerHTML = `
      ${Header()}
      <main id="main-content" style="padding-top: 40px;">
        ${CategoryGrid(state.categories)}
      </main>
      ${Footer()}
    `;
  } else if (state.currentView === 'category-words') {
    const categoryWords = state.vocabularyData.filter(w => w['Phân loại'] === state.selectedCategory);
    appEl.innerHTML = `
      ${Header()}
      <main id="main-content" style="padding-top: 40px;">
        <div id="word-list-container">
          ${WordList(state.selectedCategory, categoryWords, state.searchQuery, state.imageMappings)}
        </div>
      </main>
      ${Footer()}
    `;
  }
  
  // Re-bind the search input event listener if we are in category-words view
  setupSearchInputEvent();
}

// Re-renders only the word list content during search to avoid losing input focus
function renderWordsOnly() {
  const container = document.getElementById('word-list-container');
  if (!container) return;

  const categoryWords = state.vocabularyData.filter(w => w['Phân loại'] === state.selectedCategory);
  
  // Find current active element (input) and cursor position to restore it if needed
  const searchInput = document.getElementById('word-search');
  const selectionStart = searchInput ? searchInput.selectionStart : null;
  const selectionEnd = searchInput ? searchInput.selectionEnd : null;

  container.innerHTML = WordList(state.selectedCategory, categoryWords, state.searchQuery, state.imageMappings);

  // Restore input value, focus and cursor position
  const newSearchInput = document.getElementById('word-search');
  if (newSearchInput) {
    newSearchInput.value = state.searchQuery;
    newSearchInput.focus();
    if (selectionStart !== null && selectionEnd !== null) {
      newSearchInput.setSelectionRange(selectionStart, selectionEnd);
    }
  }

  // Re-bind the search input event listener after DOM replacement
  setupSearchInputEvent();
}

// Bind search input events specifically (since input events don't rely on clicks)
function setupSearchInputEvent() {
  const searchInput = document.getElementById('word-search');
  if (searchInput) {
    // Remove existing listener to prevent duplicates if any, and add new
    searchInput.removeEventListener('input', handleSearchInput);
    searchInput.addEventListener('input', handleSearchInput);
  }
}

function handleSearchInput(e) {
  state.searchQuery = e.target.value;
  renderWordsOnly();
}

// Global Event Delegation for all click events inside #app
function setupGlobalClickEvents() {
  appEl.addEventListener('click', (e) => {
    // 1. Back button click (returns to vocabulary topics page)
    const backBtn = e.target.closest('#btn-back-home');
    if (backBtn) {
      state.currentView = 'vocabulary';
      state.searchQuery = '';
      render();
      window.scrollTo(0, 0);
      return;
    }

    // 2. Logo click (returns to Landing Page)
    const logo = e.target.closest('#logo-home');
    if (logo) {
      e.preventDefault();
      state.currentView = 'home';
      state.searchQuery = '';
      render();
      window.scrollTo(0, 0);
      return;
    }

    // 3. Home nav link click
    const navHome = e.target.closest('#nav-home');
    if (navHome) {
      e.preventDefault();
      state.currentView = 'home';
      state.searchQuery = '';
      render();
      window.scrollTo(0, 0);
      return;
    }

    // 4. About nav link click
    const navAbout = e.target.closest('#nav-about');
    if (navAbout) {
      e.preventDefault();
      if (state.currentView !== 'home') {
        state.currentView = 'home';
        render();
      }
      setTimeout(() => {
        const section = document.getElementById('about-section');
        if (section) {
          section.scrollIntoView({ behavior: 'smooth' });
        }
      }, 50);
      return;
    }

    // 5. Contact nav link click
    const navContact = e.target.closest('#nav-contact');
    if (navContact) {
      e.preventDefault();
      if (state.currentView !== 'home') {
        state.currentView = 'home';
        render();
      }
      setTimeout(() => {
        const section = document.getElementById('contact-section');
        if (section) {
          section.scrollIntoView({ behavior: 'smooth' });
        }
      }, 50);
      return;
    }

    // 6. Vocabulary dropdown item click
    const navVocab = e.target.closest('#nav-vocabulary');
    if (navVocab) {
      e.preventDefault();
      state.currentView = 'vocabulary';
      state.searchQuery = '';
      render();
      window.scrollTo(0, 0);
      return;
    }

    // 7. Category card click
    const categoryCard = e.target.closest('.card-category');
    if (categoryCard) {
      const catName = categoryCard.getAttribute('data-category');
      state.selectedCategory = catName;
      state.currentView = 'category-words';
      state.searchQuery = '';
      loadCategoryMetadata(catName); // Load category metadata in background
      render();
      window.scrollTo(0, 0);
      return;
    }

    // 8. Explore CTA button click
    const exploreBtn = e.target.closest('#btn-explore');
    if (exploreBtn) {
      // Go to 60 categories page
      state.currentView = 'vocabulary';
      state.searchQuery = '';
      render();
      window.scrollTo(0, 0);
      return;
    }

    // 9. Speak button click
    const speakBtn = e.target.closest('.btn-speak');
    if (speakBtn) {
      const word = speakBtn.getAttribute('data-word');
      speakWord(word, speakBtn);
      return;
    }

    // 10. Word card click (excluding speak button)
    const wordCard = e.target.closest('.card-word');
    if (wordCard) {
      const term = wordCard.querySelector('.word-term').innerText.trim();
      openWordDetailsModal(term);
      return;
    }

    // 11. Modal Close (click on close button or backdrop)
    const modalClose = e.target.closest('.modal-close-btn');
    const isOverlay = e.target.classList.contains('modal-overlay');
    if (modalClose || isOverlay) {
      const modal = document.getElementById('word-detail-modal');
      if (modal) {
        modal.classList.remove('active');
      }
      return;
    }

    // 12. Modal Word Family link click
    const familyLink = e.target.closest('.wf-item.is-clickable');
    if (familyLink) {
      const word = familyLink.getAttribute('data-word');
      openWordDetailsModal(word);
      return;
    }

    // 13. Modal Speak click
    const wfSpeak = e.target.closest('.wf-btn-speak');
    if (wfSpeak) {
      const word = wfSpeak.getAttribute('data-word');
      speakWord(word, wfSpeak);
      return;
    }

    // 13b. Example Sentence Speak click
    const exSpeak = e.target.closest('.ex-btn-speak');
    if (exSpeak) {
      const text = exSpeak.getAttribute('data-text');
      speakWord(text, exSpeak);
      return;
    }

    // 14. Popover Speak click
    const popoverSpeak = e.target.closest('.popover-speak-btn');
    if (popoverSpeak) {
      const word = popoverSpeak.getAttribute('data-word');
      speakWord(word, popoverSpeak);
      return;
    }

    // 15. Popover Link/Trigger click to view details
    const trigger = e.target.closest('.popover-trigger');
    const popoverLink = e.target.closest('.popover-link');
    if (trigger || popoverLink) {
      const el = trigger || popoverLink;
      const word = el.getAttribute('data-word');
      const exists = el.getAttribute('data-exists') === 'true' || el.classList.contains('popover-link');
      if (exists && word) {
        e.stopPropagation();
        e.preventDefault();
        const popover = document.getElementById('tag-popover');
        if (popover) popover.classList.remove('active');
        openWordDetailsModal(word);
        return;
      }
    }
  });
}

// Web Speech API Text-to-Speech function
function speakWord(word, btnEl = null) {
  if ('speechSynthesis' in window) {
    // Cancel any ongoing speech
    window.speechSynthesis.cancel();
    
    // Remove active speaking classes from all speak buttons
    document.querySelectorAll('.is-speaking').forEach(el => {
      el.classList.remove('is-speaking');
    });
    
    const utterance = new SpeechSynthesisUtterance(word);
    utterance.lang = 'en-US';
    utterance.rate = 0.9; // Slightly slower for clear learning pronunciation
    
    // Choose an English voice if available
    const voices = window.speechSynthesis.getVoices();
    const enVoice = voices.find(voice => voice.lang.includes('en-US') || voice.lang.includes('en-GB'));
    if (enVoice) {
      utterance.voice = enVoice;
    }
    
    if (btnEl) {
      utterance.onstart = () => {
        btnEl.classList.add('is-speaking');
      };
      utterance.onend = () => {
        btnEl.classList.remove('is-speaking');
      };
      utterance.onerror = () => {
        btnEl.classList.remove('is-speaking');
      };
    }
    
    window.speechSynthesis.speak(utterance);
  } else {
    alert("Trình duyệt của bạn không hỗ trợ chức năng phát âm Web Speech API.");
  }
}

// Register voices update event (needed for Chrome/Safari compatibility)
if ('speechSynthesis' in window) {
  window.speechSynthesis.onvoiceschanged = () => {};
}

// Run on page load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    setupGlobalClickEvents();
    setupPopoverHandlers();
    init();
  });
} else {
  setupGlobalClickEvents();
  setupPopoverHandlers();
  init();
}

/**
 * Opens a modal displaying details of a word and its corresponding Word Family (if available).
 * 
 * @param {string} word - The term to display.
 */
/**
 * Returns a formatted string containing the word, its pronunciation (if found),
 * and its Vietnamese meaning, to be used inside tag tooltips.
 * 
 * @param {string} tagWord - The tag word to lookup.
 * @returns {string} The formatted tooltip string.
 */
async function openWordDetailsModal(word) {
  // Find word in database
  const wordData = state.vocabularyData.find(w => w['Từ vựng'].toLowerCase() === word.toLowerCase());
  if (!wordData) return;
  
  const term = wordData['Từ vựng'];
  const type = wordData['Từ loại'] || '';
  const ipa = wordData['Phiên âm'] || '';
  const meaning = wordData['Ý nghĩa'] || '';
  const category = wordData['Phân loại'] || '';
  
  // Load category metadata dynamically first!
  await loadCategoryMetadata(category);
  
  // Find image
  const imgSrc = getVocabularyImage(category, term, state.imageMappings);
  
  // Get word family
  const family = state.wordFamilies ? state.wordFamilies.find(f => 
    f.rootWord.toLowerCase() === term.toLowerCase() ||
    f.members.some(m => m.word.toLowerCase() === term.toLowerCase())
  ) : null;
  
  let familyHtml = '';
  if (family) {
    // Sort members: Root Word, Noun, Verb, Adjective, Adverb, Person Noun, Related Form
    const order = ["root word", "noun", "verb", "adjective", "adverb", "person noun", "related form"];
    const sortedMembers = [...family.members].sort((a, b) => {
      const relA = a.relation.toLowerCase();
      const relB = b.relation.toLowerCase();
      
      let catA = relA;
      if (relA !== "root word" && relA !== "person noun" && relA !== "related form") {
        catA = a.partOfSpeech.toLowerCase();
      }
      
      let catB = relB;
      if (relB !== "root word" && relB !== "person noun" && relB !== "related form") {
        catB = b.partOfSpeech.toLowerCase();
      }
      
      return order.indexOf(catA) - order.indexOf(catB);
    });
    
    const membersHtml = sortedMembers.map(m => {
      // Check if member exists in database
      const exists = state.vocabularyData.some(w => w['Từ vựng'].toLowerCase() === m.word.toLowerCase());
      const clickableClass = exists ? 'is-clickable' : '';
      const dataAttr = exists ? `data-word="${m.word}"` : '';
      const badgeClass = `badge-${m.relation.replace(/\s+/g, '-').toLowerCase()}`;
      
      return `
        <div class="wf-item ${clickableClass}" ${dataAttr}>
          <div class="wf-word-group">
            <h5 class="wf-word">${m.word}</h5>
            <span class="wf-badge ${badgeClass}">${m.relation}</span>
          </div>
          <div class="wf-details">
            ${m.pronunciation ? `<span class="wf-ipa">${m.pronunciation}</span>` : ''}
            <span class="wf-meaning">${m.meaning}</span>
          </div>
          <button class="wf-btn-speak" data-word="${m.word}" aria-label="Phát âm">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
              <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
            </svg>
          </button>
        </div>
      `;
    }).join('');
    
    familyHtml = `
      <div class="wf-section">
        <h4 class="wf-header-title">👪 Word Family</h4>
        <div class="wf-list">${membersHtml}</div>
      </div>
    `;
  }

  // Get examples, synonyms, and antonyms
  const wordExamples = state.examples ? state.examples.find(e => e.word.toLowerCase() === term.toLowerCase()) : null;
  const wordSynonyms = state.synonyms ? state.synonyms.find(s => s.word.toLowerCase() === term.toLowerCase()) : null;
  const wordAntonyms = state.antonyms ? state.antonyms.find(a => a.word.toLowerCase() === term.toLowerCase()) : null;

  let examplesHtml = '';
  if (wordExamples && wordExamples.examples && wordExamples.examples.length > 0) {
    const listHtml = wordExamples.examples.map(ex => {
      const rawEn = (ex.en || '').replace(/\*\*/g, '');
      return `
        <div class="example-item">
          <div class="example-text-container">
            <div class="example-en">${(ex.en || '').replace(/\*\*(.*?)\*\*/g, '<b>$1</b>').replace(/<b><b>/g, '<b>').replace(/<\/b><\/b>/g, '</b>')}</div>
            <div class="example-vi">${(ex.vi || '').replace(/\*\*(.*?)\*\*/g, '<b>$1</b>').replace(/<b><b>/g, '<b>').replace(/<\/b><\/b>/g, '</b>')}</div>
          </div>
          <button class="ex-btn-speak" data-text="${rawEn.replace(/"/g, '&quot;')}" aria-label="Phát âm câu ví dụ">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
              <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
            </svg>
          </button>
        </div>
      `;
    }).join('');
    examplesHtml = `
      <div class="modal-examples-section">
        <h4 class="examples-header-title">📖 Examples</h4>
        <div class="example-list">${listHtml}</div>
      </div>
    `;
  }

  let tagsHtml = '';
  const synList = wordSynonyms && wordSynonyms.synonyms && wordSynonyms.synonyms.length > 0 ? wordSynonyms.synonyms : [];
  const antList = wordAntonyms && wordAntonyms.antonyms && wordAntonyms.antonyms.length > 0 ? wordAntonyms.antonyms : [];
  
  if (synList.length > 0 || antList.length > 0) {
    tagsHtml = `
      <div class="modal-tags-section">
        ${synList.length > 0 ? `
          <div class="tags-group">
            <h4 class="tags-title">🔗 Synonyms</h4>
            <div class="tags-container">
              ${synList.map(s => {
                const exists = state.vocabularyData.some(w => w['Từ vựng'].toLowerCase() === s.word.toLowerCase());
                return `<span class="tag-synonym popover-trigger" 
                              data-word="${s.word.replace(/"/g, '&quot;')}" 
                              data-pos="${s.partOfSpeech.replace(/"/g, '&quot;')}" 
                              data-ipa="${s.pronunciation.replace(/"/g, '&quot;')}" 
                              data-meaning="${s.meaning.replace(/"/g, '&quot;')}"
                              data-exists="${exists}">${s.word}</span>`;
              }).join('')}
             </div>
          </div>
        ` : ''}
        ${antList.length > 0 ? `
          <div class="tags-group">
            <h4 class="tags-title">🚫 Antonyms</h4>
            <div class="tags-container">
              ${antList.map(a => {
                const exists = state.vocabularyData.some(w => w['Từ vựng'].toLowerCase() === a.word.toLowerCase());
                return `<span class="tag-antonym popover-trigger" 
                              data-word="${a.word.replace(/"/g, '&quot;')}" 
                              data-pos="${a.partOfSpeech.replace(/"/g, '&quot;')}" 
                              data-ipa="${a.pronunciation.replace(/"/g, '&quot;')}" 
                              data-meaning="${a.meaning.replace(/"/g, '&quot;')}"
                              data-exists="${exists}">${a.word}</span>`;
              }).join('')}
            </div>
          </div>
        ` : ''}
      </div>
    `;
  }
  
  // Create or select modal overlay
  let modalOverlay = document.getElementById('word-detail-modal');
  if (!modalOverlay) {
    modalOverlay = document.createElement('div');
    modalOverlay.id = 'word-detail-modal';
    modalOverlay.className = 'modal-overlay';
    appEl.appendChild(modalOverlay);
  }
  
  // Populate content
  modalOverlay.innerHTML = `
    <div class="modal-box">
      <button class="modal-close-btn" aria-label="Đóng">&times;</button>
      
      <div class="modal-main-details">
        <div class="modal-text-wrap">
          <div class="modal-word-header">
            <h3 class="modal-word-title">${term}</h3>
            ${type ? `<span class="wf-badge badge-noun">${type}</span>` : ''}
            <button class="wf-btn-speak" data-word="${term}" aria-label="Phát âm">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
              </svg>
            </button>
          </div>
          ${ipa ? `<div class="modal-ipa">${ipa}</div>` : ''}
          <div class="modal-meaning">${meaning}</div>
          <div style="font-size: 0.9rem; color: #666; font-weight: 700;">Chủ đề: ${category}</div>
        </div>
        
        <div class="modal-image-wrap">
          <img class="modal-image" src="${imgSrc}" alt="${term}">
        </div>
      </div>
      
      ${examplesHtml}
      
      ${tagsHtml}
      
      ${familyHtml}
    </div>
  `;
  
  // Activate modal
  modalOverlay.classList.add('active');
}

let hideTimeout = null;

/**
 * Sets up mouseover and mouseout event handlers on document.body
 * to display/hide the floating Synonym/Antonym Popover card.
 */
function setupPopoverHandlers() {
  document.body.addEventListener('mouseover', (e) => {
    const trigger = e.target.closest('.popover-trigger');
    const popover = e.target.closest('#tag-popover');
    
    if (trigger) {
      if (hideTimeout) {
        clearTimeout(hideTimeout);
        hideTimeout = null;
      }
      showPopover(trigger);
      return;
    }
    
    if (popover) {
      if (hideTimeout) {
        clearTimeout(hideTimeout);
        hideTimeout = null;
      }
      return;
    }
  });
  
  document.body.addEventListener('mouseout', (e) => {
    const trigger = e.target.closest('.popover-trigger');
    const popover = e.target.closest('#tag-popover');
    
    if (trigger || popover) {
      if (!hideTimeout) {
        hideTimeout = setTimeout(() => {
          const pop = document.getElementById('tag-popover');
          if (pop) pop.classList.remove('active');
        }, 250);
      }
    }
  });
}

/**
 * Creates, populates, and positions the floating Popover card relative to the hovered tag trigger.
 * 
 * @param {HTMLElement} trigger - The synonym/antonym tag element.
 */
function showPopover(trigger) {
  let popover = document.getElementById('tag-popover');
  if (!popover) {
    popover = document.createElement('div');
    popover.id = 'tag-popover';
    document.body.appendChild(popover);
    
    // Attach event listener directly to the popover element to prevent event bubbling issues
    popover.addEventListener('click', (e) => {
      const speakBtn = e.target.closest('.popover-speak-btn');
      if (speakBtn) {
        e.stopPropagation();
        e.preventDefault();
        const word = speakBtn.getAttribute('data-word');
        if (word) {
          if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
          }
          speakWord(word, speakBtn);
        }
        return;
      }
      
      const link = e.target.closest('.popover-link');
      if (link) {
        e.stopPropagation();
        e.preventDefault();
        const word = link.getAttribute('data-word');
        if (word) {
          popover.classList.remove('active');
          openWordDetailsModal(word);
        }
        return;
      }
    });
  }
  
  const word = trigger.getAttribute('data-word') || '';
  const pos = trigger.getAttribute('data-pos') || '';
  const ipa = trigger.getAttribute('data-ipa') || '';
  const meaning = trigger.getAttribute('data-meaning') || '';
  const exists = trigger.getAttribute('data-exists') === 'true';
  
  popover.innerHTML = `
    <div class="popover-header">
      <div class="popover-title-wrap">
        <h4 class="popover-title">${word}</h4>
        ${pos ? `<span class="popover-badge badge-${pos}">${pos}</span>` : ''}
      </div>
      <button class="popover-speak-btn" data-word="${word.replace(/"/g, '&quot;')}" aria-label="Phát âm">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
          <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
        </svg>
      </button>
    </div>
    ${ipa ? `<div class="popover-ipa">${ipa}</div>` : ''}
    <div class="popover-meaning">${meaning}</div>
    ${exists ? `
      <div class="popover-footer">
        <span class="popover-link" data-word="${word.replace(/"/g, '&quot;')}">👉 Click để xem chi tiết</span>
      </div>
    ` : ''}
  `;
  
  // Show first to calculate dimensions
  popover.classList.add('active');
  
  const rect = trigger.getBoundingClientRect();
  const popoverWidth = popover.offsetWidth || 250;
  const popoverHeight = popover.offsetHeight || 120;
  
  // Center horizontally above the trigger
  const left = rect.left + rect.width / 2 - popoverWidth / 2 + window.scrollX;
  const top = rect.top - popoverHeight - 12 + window.scrollY;
  
  popover.style.left = `${left}px`;
  popover.style.top = `${top}px`;
}
