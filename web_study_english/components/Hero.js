export function Hero() {
  // Colorful pill blocks matching the reference image
  const staticCapsules = [
    { label: "Talk", color: "var(--accent-red)", rotation: "-10deg" },
    { label: "#", color: "var(--accent-green)", rotation: "5deg" },
    { label: "Motivation", color: "var(--accent-blue)", rotation: "-3deg" },
    { label: "Easy", color: "var(--accent-navy)", rotation: "8deg", textColor: "#FFF" },
    { label: "Studies", color: "var(--accent-pink)", rotation: "-12deg" },
    { label: "Support", color: "var(--accent-red)", rotation: "15deg" },
    { label: "Fun", color: "var(--accent-green)", rotation: "-5deg" },
    { label: "Adventures", color: "var(--accent-navy)", rotation: "2deg", textColor: "#FFF" },
    { label: "Exams", color: "var(--accent-yellow)", rotation: "-8deg" },
    { label: "Effectively", color: "var(--accent-pink)", rotation: "12deg" },
    { label: "Speaking", color: "var(--accent-yellow)", rotation: "-15deg" },
    { label: "Communicate", color: "var(--accent-green)", rotation: "5deg" }
  ];

  const capsulesHtml = staticCapsules.map(cap => `
    <div class="capsule-item" style="background-color: ${cap.color}; color: ${cap.textColor || 'var(--color-black)'}; --rotation: ${cap.rotation};">
      <span>${cap.label}</span>
    </div>
  `).join("");

  return `
    <section class="hero">
      <!-- Background squiggle doodle using SVG -->
      <svg class="doodle-arrow" viewBox="0 0 100 80" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M5 25C25 5 45 45 65 15C75 5 80 15 75 25C70 35 60 25 65 15M65 15L55 18M65 15L68 25" stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      
      <div class="container">
        <h1 class="hero-tagline">
          Speak English without<br>any b<span class="highlight">*<span class="sparkle-icon">✦</span></span>orders
        </h1>
        <p class="hero-subtitle">
          Khám phá kho từ vựng khổng lồ với 60 chủ đề học tiếng Anh thông minh cùng AI. Học nhanh, nhớ lâu, phát âm chuẩn xác.
        </p>
        <div class="hero-ctas">
          <button class="btn-primary" id="btn-explore">Get started</button>
          <button class="btn-secondary">Try for free</button>
        </div>
        
        <div class="capsule-pile">
          ${capsulesHtml}
        </div>
      </div>
    </section>
  `;
}
