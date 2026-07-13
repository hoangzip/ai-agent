export function Header() {
  return `
    <header>
      <div class="container header-inner">
        <a href="#" class="logo" id="logo-home">
          <div class="logo-icon"></div>
          <span>ziph.eng</span>
        </a>
        <nav class="nav-links">
          <a href="#" class="nav-link" id="nav-home">Home</a>
          <span class="nav-separator">/</span>
          <div class="dropdown">
            <a href="#" class="nav-link dropdown-toggle" id="nav-courses">Courses</a>
            <div class="dropdown-menu">
              <a href="#" class="dropdown-item" id="nav-vocabulary">Vocabulary</a>
              <div class="dropdown-divider"></div>
              <a href="#" class="dropdown-item disabled">Grammar (Soon)</a>
              <a href="#" class="dropdown-item disabled">Speaking (Soon)</a>
            </div>
          </div>
          <span class="nav-separator">/</span>
          <a href="#about-section" class="nav-link" id="nav-about">About</a>
          <span class="nav-separator">/</span>
          <a href="#contact-section" class="nav-link" id="nav-contact">Contact</a>
          <span class="nav-separator">/</span>
          <button class="btn-login">Log In</button>
        </nav>
      </div>
    </header>
  `;
}
