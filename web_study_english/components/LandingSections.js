export function PlatformFeatures() {
  return `
    <section class="platform-features" id="features-section">
      <div class="container">
        <h2 class="section-title">Nền tảng học thông minh</h2>
        
        <div class="grid-features">
          <div class="card-feature feature-blue">
            <div class="feature-icon">🧠</div>
            <h3 class="feature-title">AI Spaced Repetition</h3>
            <p class="feature-desc">Hệ thống ghi nhớ ngắt quãng thông minh tự động lên lịch ôn tập từ vựng dựa trên tần suất ghi nhớ của bạn.</p>
          </div>
          
          <div class="card-feature feature-red">
            <div class="feature-icon">🗣️</div>
            <h3 class="feature-title">Speech Coach</h3>
            <p class="feature-desc">Luyện phát âm chuẩn xác với AI phản hồi ngay lập tức, sử dụng công nghệ nhận diện giọng nói giọng Mỹ chuẩn.</p>
          </div>
          
          <div class="card-feature feature-green">
            <div class="feature-icon">⚡</div>
            <h3 class="feature-title">Contextual Generator</h3>
            <p class="feature-desc">Tạo ngữ cảnh thực tế cho từng từ vựng giúp bạn hiểu rõ cách sử dụng từ trong câu thực tế.</p>
          </div>
        </div>
      </div>
    </section>
  `;
}

export function HowItWorks() {
  return `
    <section class="how-it-works">
      <div class="container">
        <h2 class="section-title">Quy trình 3 bước học nhanh</h2>
        
        <div class="flow-steps">
          <div class="flow-step">
            <div class="step-num">1</div>
            <h3 class="step-title">Chọn chủ đề</h3>
            <p class="step-desc">Khám phá hơn 60 chủ đề từ vựng phong phú từ đời sống đến công việc.</p>
          </div>
          
          <div class="flow-arrow">
            <svg width="40" height="20" viewBox="0 0 40 20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <path d="M5 10H35M35 10L28 3M35 10L28 17"/>
            </svg>
          </div>
          
          <div class="flow-step">
            <div class="step-num">2</div>
            <h3 class="step-title">Luyện phát âm</h3>
            <p class="step-desc">Nghe cách phát âm chuẩn và thực hành nói trực tiếp với sự trợ giúp của AI.</p>
          </div>
          
          <div class="flow-arrow">
            <svg width="40" height="20" viewBox="0 0 40 20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <path d="M5 10H35M35 10L28 3M35 10L28 17"/>
            </svg>
          </div>
          
          <div class="flow-step">
            <div class="step-num">3</div>
            <h3 class="step-title">Làm chủ từ vựng</h3>
            <p class="step-desc">Hoàn thành các bài ôn tập định kỳ để đưa từ vựng vào vùng trí nhớ dài hạn.</p>
          </div>
        </div>
      </div>
    </section>
  `;
}

export function AboutSection() {
  return `
    <section class="about-section" id="about-section">
      <div class="container">
        <h2 class="section-title">Về chúng tôi</h2>
        <div class="about-content">
          <div class="about-text">
            <p><strong>ZipH English AI</strong> được ra đời với sứ mệnh xóa bỏ mọi rào cản ngôn ngữ. Chúng tôi tin rằng học tiếng Anh không chỉ là ghi nhớ các quy tắc ngữ pháp cứng nhắc, mà là sự tương tác chủ động và tự nhiên nhất.</p>
            <p>Bằng cách ứng dụng các mô hình ngôn ngữ lớn (LLM) và trí tuệ nhân tạo thế hệ mới, ZipH mang đến phương pháp học từ vựng trực quan, sinh động qua 60 chủ đề cốt lõi thực tế nhất trong cuộc sống.</p>
          </div>
          <div class="about-card">
            <div class="about-card-title">Học không biên giới</div>
            <div class="about-card-body">✦ 1760+ Từ vựng chọn lọc<br>✦ 60 Chủ đề thông dụng<br>✦ AI Pronunciation tích hợp<br>✦ Giao diện trực quan hiện đại</div>
          </div>
        </div>
      </div>
    </section>
  `;
}

export function ContactSection() {
  return `
    <section class="contact-section" id="contact-section">
      <div class="container">
        <h2 class="section-title">Liên hệ</h2>
        <div class="contact-layout">
          <div class="contact-info">
            <h3>Kết nối với ZipH</h3>
            <p>Bạn có bất kỳ câu hỏi nào về nền tảng học từ vựng ZipH English AI? Hãy liên hệ với chúng tôi, đội ngũ hỗ trợ sẽ phản hồi trong vòng 24 giờ.</p>
            <div class="contact-details">
              <div class="contact-detail-item"><strong>📧 Email:</strong> support@ziph.eng</div>
              <div class="contact-detail-item"><strong>📍 Địa chỉ:</strong> Ho Chi Minh City, Vietnam</div>
              <div class="contact-detail-item"><strong>🌐 Website:</strong> www.ziph-english.ai</div>
            </div>
          </div>
          
          <form class="contact-form" id="contact-form" onsubmit="event.preventDefault(); alert('Cảm ơn bạn đã liên hệ! Chúng tôi đã nhận được tin nhắn.'); this.reset();">
            <div class="form-group">
              <label for="contact-name">Họ & Tên</label>
              <input type="text" id="contact-name" placeholder="Nguyễn Văn A" required>
            </div>
            <div class="form-group">
              <label for="contact-email">Email</label>
              <input type="email" id="contact-email" placeholder="example@mail.com" required>
            </div>
            <div class="form-group">
              <label for="contact-message">Lời nhắn</label>
              <textarea id="contact-message" rows="4" placeholder="Tôi muốn hỏi về..." required></textarea>
            </div>
            <button type="submit" class="btn-primary" style="margin-top: 10px;">Gửi tin nhắn</button>
          </form>
        </div>
      </div>
    </section>
  `;
}
