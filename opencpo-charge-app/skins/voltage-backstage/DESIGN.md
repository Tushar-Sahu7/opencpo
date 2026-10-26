# Design System Document: Stroomlijnen Digital Experience

## 1. Overview & Creative North Star: "The Command Center"
This design system moves away from the "utility app" aesthetic toward a **Command Center** philosophy. Inspired by high-end theater control rooms and the precision of premium automotive telemetry, the interface should feel like a high-stakes backstage environment: dark, focused, and powerful.

### The Creative North Star: "Electric Precision"
The "Electric Precision" concept centers on the idea that the user is not just "charging a car," but orchestrating energy. 
- **Intentional Asymmetry:** Avoid perfectly centered, static layouts. Use weighted typography and off-grid element placement to create a sense of forward motion.
- **Tonal Depth:** Instead of flat cards, we use "light leaks" and "glows" to suggest energy behind the screen.
- **Atmospheric UI:** Elements should appear to emerge from the deep navy void, illuminated by the electric cyan of the grid.

---

## 2. Colors & Surface Philosophy
The palette is built on high-contrast technical precision. We use light as a functional tool, not just decoration.

### The "No-Line" Rule
**Strict Mandate:** Traditional 1px solid borders are prohibited for sectioning. Boundaries must be defined solely through:
1.  **Background Shifts:** Use `surface-container-low` for secondary sections sitting on `surface`.
2.  **Tonal Transitions:** A transition from `surface-container-lowest` to `surface-container-highest` creates a natural ledge without a hard line.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers—like stacked sheets of tinted glass.
*   **Base Level:** `surface` (#051424) – The "backstage" floor.
*   **Primary Containers:** `surface-container` (#122031) – For main content blocks.
*   **Elevated Widgets:** `surface-container-highest` (#283647) – For the most critical interactive elements (e.g., "Start Charging" sliders).

### The "Glass & Gradient" Rule
To capture the "theater lighting" aesthetic, use Glassmorphism for floating elements. Apply a `backdrop-blur` (12px-20px) to `surface-variant` with 60% opacity. 
*   **Signature Glow:** Use a subtle radial gradient for hero backgrounds: `primary-container` (#00B0E4) at 15% opacity fading into the background to simulate a stage spotlight hitting a dark floor.

---

## 3. Typography
The typography system pairs the technical rigidity of **Space Grotesk** with the humanistic clarity of **Manrope**.

| Role | Font Family | Token | Purpose |
| :--- | :--- | :--- | :--- |
| **Display** | Space Grotesk | `display-lg` | Large metrics (e.g., % Battery). |
| **Headline** | Space Grotesk | `headline-md` | Section titles (e.g., "Laadstation Details"). |
| **Title** | Manrope | `title-lg` | Card titles and prominent labels. |
| **Body** | Manrope | `body-md` | General information and descriptions. |
| **Label** | Space Grotesk | `label-md` | Technical metadata (e.g., "kWh", "Volt"). |

**Creative Note:** Use `label-sm` in all-caps with 0.05em letter spacing for a "technical readout" feel. This reinforces the theater-tech aesthetic.

---

## 4. Elevation & Depth
In this system, depth is conveyed through **Tonal Layering** and **Ambient Light**, never through heavy, muddy shadows.

*   **The Layering Principle:** Stack `surface-container-lowest` cards on a `surface-container-low` section to create a soft, natural lift.
*   **Ambient Shadows:** Use a glow-style shadow for active charging states. Shadow color should be `primary` (#6fd2ff) at 8% opacity with a 40px blur. This mimics light emission from the device.
*   **The "Ghost Border" Fallback:** If containment is required for accessibility, use `outline-variant` (#3d484f) at 20% opacity. Never use 100% opaque borders.
*   **Glassmorphism:** Navigation bars and sticky headers must use a semi-transparent `surface` with a 20px blur to ensure the content "flows" beneath the UI chrome.

---

## 5. Components

### Buttons
*   **Primary (Action):** Filled with `primary-container` (#00b0e4). Text in `on-primary` (#003547). High-contrast, sharp 4px (`sm`) corners.
*   **Secondary (Success):** Filled with `secondary-container` (#83bc00). Use for "Charge Complete" or "Payment Success" states.
*   **Ghost Action:** No fill, `primary` text. Used for secondary navigation like "Annuleren".

### Input Fields & Controls
*   **Text Inputs:** No bottom line or full border. Use `surface-container-high` background with a subtle `outline-variant` (20% opacity) top-edge highlight.
*   **Checkboxes/Radios:** Use `secondary` (#9dd82c) for checked states to provide a clear "Go" signal.
*   **The Pulse (Custom Component):** A signature EV component. While charging, the active container should have a subtle breathing animation (opacity 1.0 to 0.8) using the `primary` color.

### Cards & Lists
*   **Strict Rule:** No dividers. Use 24px vertical whitespace (Spacing Scale) or a shift from `surface-container` to `surface-container-low` to separate items.
*   **Interactive Cards:** Should have a "haptic feel"—on press, the card should scale to 98% and shift color to `surface-bright`.

### Charging Progress Gauge
*   A custom circular or linear gauge using a gradient from `primary` (#6fd2ff) to `secondary` (#9dd82c) to represent energy flow.

---

## 6. Do's and Don'ts

### Do
*   **Do** use Dutch terminology with professional precision (e.g., use "Beschikbaarheid" instead of "Status").
*   **Do** lean into the "dark mode" exclusively. There is no light mode for Stroomlijnen; it is a dedicated environment.
*   **Do** use wide margins (24dp+) to give the high-contrast typography room to breathe.
*   **Do** use `secondary` (Lime Green) sparingly—only for final success states or "Available" status.

### Don't
*   **Don't** use standard Material Design drop shadows. They look "dirty" on deep navy backgrounds.
*   **Don't** use rounded corners larger than `lg` (0.5rem). The app must feel "tech-sharp," not "bubble-soft."
*   **Don't** use pure white (#FFFFFF) for text. Use `on-surface` (#d5e4fa) to reduce eye strain and maintain the "theater" atmosphere.
*   **Don't** use dividers to separate list items. Use the "Background Shift" rule instead.