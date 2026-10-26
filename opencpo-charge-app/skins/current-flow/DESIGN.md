```markdown
# Design System Strategy: The Electric Editorial

This document outlines the visual language for the Stroomlijnen Mobile PWA. Moving beyond the "utility app" aesthetic, this system adopts a high-end, editorial approach to EV charging—blending the precision of Dutch engineering with the fluidity of sustainable energy.

---

## 1. Overview & Creative North Star: "The Fluid Architect"
The Creative North Star for this system is **The Fluid Architect**. We are not building a static interface; we are designing a responsive environment that feels as effortless as electricity flowing through a circuit. 

To break the "template" look, we move away from rigid, centered grids. Instead, we use **Intentional Asymmetry** and **Tonal Depth**. By overlapping high-contrast typography (Manrope) with soft, organic containers, we create a sense of forward motion and premium reliability. The interface should feel like a premium digital magazine: spacious, authoritative, and breathable.

---

## 2. Color Strategy & Tonal Logic
Our palette is rooted in the "Stroomlijnen Cyan" and "Fresh Green," but we apply them with sophisticated restraint to avoid a "cheap" or overly saturated look.

### The "No-Line" Rule
**Strict Mandate:** 1px solid borders for sectioning are prohibited. 
Boundaries must be defined through background color shifts. For example, a `surface-container-low` section should sit directly on a `surface` background. The change in tone is the divider. This creates a seamless, modern flow that feels engineered rather than "boxed in."

### Surface Hierarchy & Nesting
Treat the UI as physical layers of frosted glass.
- **Base Layer:** `surface` (#f8fafb)
- **Secondary Sectioning:** `surface-container-low` (#f2f4f5)
- **Interactive Cards:** `surface-container-lowest` (#ffffff)
- **Elevated Modals:** `surface-bright` (#f8fafb) with Glassmorphism.

### The Glass & Gradient Rule
To achieve "visual soul," use subtle gradients for primary actions. Instead of a flat `#00B0E4`, use a linear gradient from `primary` (#006686) to `primary_container` (#00B0E4) at a 135° angle. This adds a "lithium-ion" glow to buttons and hero elements.

---

## 3. Typography: The Editorial Voice
We use a dual-font pairing to balance character with readability.

- **Display & Headlines (Manrope):** This is our "Editorial" voice. Use `display-lg` and `headline-md` with tight letter-spacing (-0.02em) to create an authoritative, modern Dutch aesthetic.
- **UI & Body (Inter):** Our "Functional" voice. Inter provides maximum legibility at small scales on 390px mobile screens.

**Hierarchy as Identity:**
- **Primary Info (kWh, Price):** Always use `display-sm` or `headline-lg` in `on_surface`. 
- **Supporting Labels:** Use `label-md` in `on_surface_variant` with all-caps and +0.05em tracking for a premium, "technical" feel.

---

## 4. Elevation & Depth
We convey hierarchy through **Tonal Layering** rather than drop shadows.

- **The Layering Principle:** Place a `surface-container-lowest` card on a `surface-container-low` background. The subtle contrast creates a "natural lift."
- **Ambient Shadows:** For floating elements (like a "Start Charging" FAB), use a shadow with a 24px blur, 0% spread, and 6% opacity using a tint of `primary` (#006686). This mimics natural light passing through energy-efficient glass.
- **The Ghost Border:** If a boundary is required for accessibility, use the `outline_variant` at **15% opacity**. This creates a "suggestion" of a border without breaking the editorial flow.
- **Glassmorphism:** Use `backdrop-blur: 12px` on top navigation bars or floating status cards to allow the vibrant charging map or green gradients to bleed through.

---

## 5. Components

### Cards & Lists
*   **The Rule:** No dividers. Use `xl` (1.5rem) rounded corners for cards.
*   **Structure:** Separate list items using `body-md` spacing (16px) of vertical white space.
*   **Visuals:** Use a `tertiary_container` (#7db300) background for "Eco-Impact" cards to distinguish them from standard "Charging" cards.

### Buttons (The "Power" Units)
*   **Primary:** Gradient (Primary to Primary Container), `full` (9999px) rounded corners, `title-sm` typography.
*   **Secondary:** `surface-container-high` background with `on_primary_container` text. No border.
*   **Tertiary:** Transparent background, `on_surface` text, with a `label-md` weight.

### Input Fields
*   **State:** Use `surface-container-highest` for the input track. 
*   **Focus:** Instead of a thick border, use a 2px "glow" using the `primary` color at 30% opacity.
*   **Success State:** When a charger is connected, transition the container background to a soft 10% opacity of `tertiary` (Fresh Green).

### Charging Progress (Signature Component)
*   Instead of a standard bar, use a large `display-lg` percentage text overlapping a soft, pulsating glassmorphic circle. Use the `tertiary` (#476800) color to signify green energy flow.

---

## 6. Do’s and Don’ts

### Do
*   **Do** use Dutch terminology accurately (e.g., "Start Laden" instead of "Start Charging").
*   **Do** embrace white space. If a screen feels "full," increase the `surface` padding.
*   **Do** use asymmetrical layouts for headers—large left-aligned titles with small right-aligned status icons.
*   **Do** use `tertiary` (Fresh Green) as a "reward" color, reserved for environmental savings and successful sessions.

### Don’t
*   **Don’t** use pure black (#000000). Use `on_background` (#191c1d) for all "black" text.
*   **Don’t** use standard 4px or 8px "card shadows." They look dated. Stick to tonal shifts.
*   **Don’t** use icons without labels for primary navigation.
*   **Don’t** use 100% opaque borders. They create visual "noise" that contradicts the clean Dutch aesthetic.

---

## 7. Device Specs (PWA 390px)
*   **Side Margins:** 20px (for an airy, edge-to-edge feel).
*   **Gutter:** 12px.
*   **Safe Area:** Ensure the "Start Laden" action is always within the bottom 30% of the screen for thumb-reachability.