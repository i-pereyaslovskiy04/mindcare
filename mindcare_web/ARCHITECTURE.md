# MindCare Web — Frontend Architecture

React 19 · CSS Modules · React Router v6 · CRA (react-scripts 5)

---

## Project Structure

```
src/
├── api/
│   └── api.js                       # Centralized fetch client (all /api/* calls)
├── services/
│   └── api.js                       # Legacy alias — prefer api/api.js
├── store/
│   └── store.js                     # Global state stub (not yet wired)
├── styles/
│   ├── variables.css                # Design tokens (colors, type, layout, motion)
│   ├── global.css                   # Reset, .container, .section-wrap utilities
│   └── theme.js                     # JS token mirror (unused in prod)
├── routes/
│   └── AppRoutes.jsx                # All <Route> definitions
├── pages/
│   ├── Home.jsx                     # /
│   ├── About.jsx                    # /about
│   ├── Services.jsx                 # /services
│   ├── NewsPage.jsx                 # /news
│   ├── NewsItemPage.jsx             # /news/:id
│   └── NotFound/
├── features/
│   └── auth/
│       ├── Login.jsx
│       └── forgot-password/
│           ├── ForgotPasswordModal.jsx
│           ├── ForgotPasswordStepper.jsx
│           ├── hooks/useForgotPassword.js
│           ├── steps/               # StepEmail / StepOTP / StepNewPassword / StepSuccess
│           └── components/          # OTPInput, PasswordStrength
└── components/
    ├── Navbar/                      # Burger menu + auth icon trigger
    ├── Hero/                        # Home hero (gradient, min-height, centered)
    ├── QuickActions/                # 3-card row on Home
    ├── News/                        # Home news preview block
    │   ├── NewsSection.jsx
    │   ├── FeaturedNews.jsx
    │   ├── NewsCardSmall.jsx
    │   └── NewsListItem.jsx
    ├── NewsPage/                    # Full /news page
    │   ├── NewsGrid.jsx
    │   ├── Pagination.jsx
    │   └── mockNews.js
    ├── About/                       # /about page blocks
    │   ├── AboutHero.jsx            # Gradient hero (matches Home standard)
    │   ├── AboutIntro.jsx           # 2-col: text + stat cards (2022 / 5+ / 100%)
    │   ├── AboutMission.jsx         # 3 pillar cards
    │   ├── AboutServicesPreview.jsx # 4-col preview grid → links to /services
    │   ├── AboutApproach.jsx        # 2-col: text + numbered step list
    │   ├── AboutTrust.jsx           # 3 guarantee cards with SVG icons
    │   └── AboutMedia.jsx           # Video + photo placeholders grid
    ├── Services/                    # /services page blocks
    │   ├── ServicesHero.jsx         # Gradient hero (matches Home standard)
    │   ├── ServicesSlider.jsx       # Scroll-snap slider, arrow navigation
    │   ├── ServiceCard.jsx          # Card: gradient band, benefits list, CTA
    │   ├── ProcessBlock.jsx         # 4-step horizontal timeline
    │   └── PrinciplesBlock.jsx      # 5 icon cards grid
    ├── AuthModal/                   # Login + Register modal (not a route)
    │   ├── AuthModal.jsx
    │   ├── LoginForm.jsx
    │   └── RegisterForm.jsx
    ├── Footer/
    ├── CookieBanner/
    └── icons/
        └── index.jsx                # Shared inline SVG icons
```

---

## Pages

| Route       | Component    | Key sections                                      |
|------------|--------------|---------------------------------------------------|
| `/`         | Home         | Hero · QuickActions · News preview                |
| `/about`    | About        | Hero · Intro · Mission · Services preview · Approach · Trust · Media |
| `/services` | Services     | Hero · Slider (5 cards) · Timeline · Principles   |
| `/news`     | NewsPage     | Paginated grid (mock data)                        |
| `/news/:id` | NewsItemPage | Single article                                    |
| `*`         | NotFound     | 404 fallback                                      |

Auth is a **modal** (`AuthModal`), not a route. Triggered via `onOpenAuth` prop passed to Navbar.

---

## Key Patterns

### CSS Modules
Every component has a co-located `.module.css`. No inline styles.
Dynamic per-card accent colors via object lookup (avoids inline `style=`):
```jsx
const ACCENTS = ['accent1', 'accent2', 'accent3', 'accent4', 'accent5'];
const cls = styles[ACCENTS[index % ACCENTS.length]];
```

### Design Tokens (`variables.css`)
```
Colors:   --cream, --warm-white, --latte, --sand, --fog, --coffee, --espresso, --mocha
Text:     --text-main, --text-light, --text-on-dark
Type:     --fs-h1/h2/h3/h3-sm/body/ui/sub/tag  +  --lh-h1/h2/body
Spacing:  --ls-nav, --ls-tag, --ls-label
Layout:   --container-max, --container-px, --grid-gap, --section-py
Motion:   --ease-card
```

### Hero Standard (all 3 heroes are identical in structure)
```css
.hero {
  background: linear-gradient(135deg, var(--espresso) 0%, var(--mocha) 50%, #7A5C40 100%);
  min-height: clamp(420px, 50vh, 700px);
  display: flex; align-items: center; justify-content: center;
}
/* inner: max-width min(700px, 90vw), text-align: center */
/* typography: --fs-tag label · --fs-h1 title · --fs-body sub */
```

### Section Layout
```jsx
<section className="section-wrap">      {/* white bg */}
<section className="section-wrap alt">  {/* cream bg */}
  <div className="container">…</div>
</section>
```
Pages alternate white → cream throughout.

### Services Slider
Native scroll — no library. `overflow-x: auto` + `scroll-snap-type: x mandatory` + `scrollBy()`.
Arrow enable/disable state synced via `useCallback` + `useEffect` on resize.

### Forgot Password Flow
Multi-step stepper in `features/auth/forgot-password/`:
- Steps: Email → OTP → New Password → Success
- All logic in `useForgotPassword.js` hook; steps are pure UI

---

## API

All fetch calls via `src/api/api.js`. Dev proxy: `package.json → "proxy": "http://localhost:8000"`.

```
POST /api/login              POST /api/register
POST /api/logout             GET  /api/profile
POST /api/forgot-password    GET  /api/news?page=&limit=
GET  /api/news/:id           GET  /api/psychologists
POST /api/appointments
```

---

## Breakpoints

| Breakpoint | Affected behaviour                         |
|-----------|---------------------------------------------|
| ≤900px    | Service cards 3→2 per row                   |
| ≤768px    | Burger menu, timeline stacks vertically      |
| ≤560px    | Service cards 1 per row (85vw), About grid  |
| ≤480px    | Hero padding reduced                        |
