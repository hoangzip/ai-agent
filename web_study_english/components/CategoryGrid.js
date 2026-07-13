const CATEGORY_COLORS = [
  'var(--accent-blue)',
  'var(--accent-red)',
  'var(--accent-green)',
  'var(--accent-yellow)',
  'var(--accent-pink)',
  '#A288E3',
  '#FF9F1C',
  '#4EA8DE',
  '#E07A5F',
  '#81B29A'
];

export function CategoryGrid(categories) {
  const cardsHtml = categories.map((cat, idx) => {
    // Determine a stable color based on index or name
    const color = CATEGORY_COLORS[idx % CATEGORY_COLORS.length];
    
    return `
      <div class="card-category" data-category="${cat.name}">
        <!-- Small background decorative blob matching the card color -->
        <div class="card-category-bg" style="background-color: ${color};"></div>
        
        <h3 class="category-name">${cat.name}</h3>
        
        <div class="category-meta">
          <span class="category-count">${cat.count} từ vựng</span>
          <button class="category-btn" aria-label="Xem từ vựng">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
              <line x1="5" y1="12" x2="19" y2="12"></line>
              <polyline points="12 5 19 12 12 19"></polyline>
            </svg>
          </button>
        </div>
      </div>
    `;
  }).join("");

  return `
    <section class="categories-section" id="categories-section">
      <div class="container">
        <h2 class="section-title">Chủ Đề Học Tập (60 Topics)</h2>
        <div class="grid-categories">
          ${cardsHtml}
        </div>
      </div>
    </section>
  `;
}
