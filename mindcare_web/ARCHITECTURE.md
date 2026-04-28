# MindCare Web — Frontend Architecture

React 19 · CSS Modules · React Router v6 · CRA (react-scripts 5)

---

## Project Structure

```
src/
├── api/
│   └── api.js                          # Centralized fetch client (all /api/* calls)
├── services/
│   └── api.js                          # Legacy alias — prefer api/api.js
├── store/
│   └── store.js                        # Global state stub (not yet wired)
├── styles/
│   ├── variables.css                   # Design tokens (colors, type, layout, motion)
│   ├── global.css                      # Reset, .container, .section-wrap utilities
│   └── theme.js                        # JS token mirror (unused in prod)
├── routes/
│   └── AppRoutes.jsx                   # All <Route> definitions
├── features/
│   └── auth/
│       ├── Login.jsx
│       └── forgot-password/
│           ├── ForgotPasswordModal.jsx
│           ├── ForgotPasswordStepper.jsx
│           ├── hooks/
│           │   └── useForgotPassword.js
│           ├── steps/
│           │   ├── StepEmail.jsx
│           │   ├── StepOTP.jsx
│           │   ├── StepNewPassword.jsx
│           │   └── StepSuccess.jsx
│           ├── components/
│           │   ├── OTPInput.jsx
│           │   └── PasswordStrength.jsx
│           └── styles/
│               └── forgot-password.module.css
├── pages/
│   ├── home/
│   │   ├── Home.jsx
│   │   └── components/
│   │       ├── Hero.jsx + .module.css
│   │       └── QuickActions.jsx + .module.css
│   ├── about/
│   │   ├── About.jsx
│   │   └── components/
│   │       ├── AboutHero.jsx + .module.css
│   │       ├── AboutIntro.jsx + .module.css
│   │       ├── AboutMission.jsx + .module.css
│   │       ├── AboutServicesPreview.jsx + .module.css
│   │       ├── AboutApproach.jsx + .module.css
│   │       ├── AboutTrust.jsx + .module.css
│   │       └── AboutMedia.jsx + .module.css
│   ├── services/
│   │   ├── Services.jsx + .module.css
│   │   └── components/
│   │       ├── ServicesHero.jsx + .module.css
│   │       ├── ServicesSlider.jsx + .module.css
│   │       ├── ServiceCard.jsx + .module.css
│   │       ├── ProcessBlock.jsx + .module.css
│   │       └── PrinciplesBlock.jsx + .module.css
│   ├── news/
│   │   ├── NewsPage.jsx
│   │   ├── NewsItemPage.jsx + .module.css
│   │   └── components/
│   │       ├── NewsGrid.jsx
│   │       ├── NewsPage.module.css
│   │       ├── Pagination.jsx
│   │       └── mockNews.js
│   ├── materials/
│   │   ├── MaterialsPage.jsx + .module.css
│   │   ├── MaterialsItemPage.jsx + .module.css
│   │   └── components/
│   │       ├── SearchBar.jsx + .module.css       # Search + filter toolbar
│   │       ├── FiltersDropdown.jsx + .module.css # Desktop: position:absolute dropdown
│   │       ├── FilterSheet.jsx + .module.css     # Mobile: portal bottom sheet
│   │       ├── FilterDropdown.jsx + .module.css  # Reusable single-select widget
│   │       ├── FiltersPanel.jsx + .module.css    # UNUSED — legacy portal component
│   │       ├── MaterialsGrid.jsx + .module.css
│   │       ├── MaterialCard.jsx + .module.css
│   │       ├── MaterialsToolbar.jsx + .module.css
│   │       ├── MaterialsHero.jsx + .module.css
│   │       └── mockMaterials.js
│   └── not-found/
│       └── NotFound.jsx + .module.css
└── components/                         # Shared across pages
    ├── Navbar/
    │   └── Navbar.jsx + .module.css
    ├── Footer/
    │   └── Footer.jsx + .module.css
    ├── Hero/
    │   └── PageHero.jsx + .module.css  # Reusable gradient hero (eyebrow/title/sub)
    ├── AuthModal/
    │   ├── AuthModal.jsx + .module.css
    │   ├── LoginForm.jsx
    │   └── RegisterForm.jsx
    ├── CookieBanner/
    │   └── CookieBanner.jsx + .module.css
    ├── News/                           # Home page news preview block
    │   ├── NewsSection.jsx + .module.css
    │   ├── FeaturedNews.jsx
    │   ├── NewsCardSmall.jsx
    │   └── NewsListItem.jsx
    ├── UI/
    │   └── MultiSelect/
    │       └── MultiSelect.jsx + multiSelect.module.css
    └── icons/
        └── index.jsx                   # Shared inline SVG icons
```

---

## Pages

| Route           | Component        | Key sections                                                          |
|----------------|------------------|-----------------------------------------------------------------------|
| `/`             | Home             | Hero · QuickActions · News preview                                    |
| `/about`        | About            | Hero · Intro · Mission · Services preview · Approach · Trust · Media  |
| `/services`     | Services         | Hero · Slider (5 cards) · Timeline · Principles                       |
| `/news`         | NewsPage         | Paginated grid (mock data)                                            |
| `/news/:id`     | NewsItemPage     | Single article                                                        |
| `/materials`    | MaterialsPage    | Search/filter toolbar · card grid · load more                         |
| `/materials/:id`| MaterialsItemPage| Single material                                                       |
| `*`             | NotFound         | 404 fallback                                                          |

Auth is a **modal** (`AuthModal`), not a route. Triggered via `onOpenAuth` prop passed to Navbar.

---

## Key Patterns

### Page-module layout
Each page lives in `pages/<domain>/`. Page-specific components go in `pages/<domain>/components/` — never in `components/`. Shared components used by 2+ pages go in `components/`.

### Shared vs local components
- `components/` — layout shells (Navbar, Footer, Hero), auth modal, UI primitives, icons
- `pages/*/components/` — sections, cards, filters, mock data belonging to one page

### API layer
All fetch calls through `src/api/api.js`. Dev proxy: `package.json → "proxy": "http://localhost:8000"`.

### Materials filter architecture
Desktop: `FiltersDropdown` renders `position:absolute` inside a `position:relative` parent — zero JS positioning, scrolls naturally with the page.
Mobile (≤768px): `FilterSheet` uses `ReactDOM.createPortal` to render a fixed bottom sheet at `document.body`. `SearchBar` switches between them via `window.matchMedia`.

### CSS Modules
Every component has a co-located `.module.css`. No inline styles. Design tokens via `variables.css`.

---

## Design Tokens (`variables.css`)

```
Colors:   --cream, --warm-white, --latte, --sand, --fog, --coffee, --espresso, --mocha
Text:     --text-main, --text-light, --text-on-dark
Type:     --fs-h1/h2/h3/h3-sm/body/ui/sub/tag  +  --lh-h1/h2/body
Spacing:  --ls-nav, --ls-tag, --ls-label
Layout:   --container-max, --container-px, --grid-gap, --section-py
Motion:   --ease-card
```

---

## Breakpoints

| Breakpoint | Affected behaviour                              |
|-----------|-------------------------------------------------|
| ≤1024px   | Filter toolbar compact padding                  |
| ≤900px    | Service cards 3→2 per row                       |
| ≤768px    | Burger menu · timeline vertical · filter bottom sheet |
| ≤560px    | Service cards 1 per row · About grid            |
| ≤480px    | Hero padding reduced · filter trigger font      |
