# Styling Guide & Design System Tokens

## 1. Color Palette

```css
:root {
  --background: #F8F7F3;          /* Warm Canvas Background */
  --surface: #FFFFFF;             /* Card / Panel Background */
  --surface-secondary: #EFEAE0;   /* Secondary Surface / Input Background */
  --accent-primary: #A8412C;      /* Terracotta Primary Accent */
  --accent-primary-dark: #8C3523; /* Terracotta Hover State */
  --border-light: #E7E1D4;        /* Card & Divider Border */
  --border-dark: #1C1917;         /* High-contrast Panel Border */
  --text-primary: #231F1C;        /* Charcoal Primary Text (13.5:1 Contrast) */
  --text-secondary: #5C574C;      /* Muted Secondary Text */
  --text-tertiary: #8A8378;       /* Tertiary Label Text */
  --success-bg: #E4EEE1;          /* Positive Alert / Savings */
  --success-text: #3F6B42;
  --warning-bg: #F3E4C9;          /* Fallback Warning Box */
  --warning-text: #8A5A20;
  --error-bg: #FDE8E4;            /* Error Panel / Validation Alert */
  --error-text: #A8412C;
}
```

## 2. Background Radial Grid
```css
body {
  background-color: var(--background);
  background-image: radial-gradient(circle, #E5E0D8 1px, transparent 1px);
  background-size: 24px 24px;
}
```
