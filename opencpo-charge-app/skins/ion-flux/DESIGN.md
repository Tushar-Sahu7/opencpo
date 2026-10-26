```markdown
# Design System Specification: High-Voltage Minimalism

## 1. Overview & Creative North Star: "The Kinetic Monolith"
This design system is built upon the concept of **The Kinetic Monolith**. In the world of high-performance EV charging, we reject the soft, "friendly" aesthetic of consumer apps. Instead, we embrace a high-end, technical editorial approach that feels like an advanced cockpit.

The visual identity is defined by a deep, monochromatic foundation interrupted by "electric" strikes of neon cyan. We break the standard "template" look by using intentional asymmetry and a rigid, mathematical approach to spacing. Instead of boxes and borders, we use tonal shifts to create a sense of machined precision. The interface should feel less like a mobile app and more like a high-precision instrument carved out of dark glass.

---

## 2. Colors: Tonal Depth & The Electric Strike
The palette is rooted in an ultra-dark obsidian (`#0c0e12`). We move away from flat UI by utilizing a specific hierarchy of "surfaces" that mimic the layering of carbon fiber and glass.

### Color Tokens
*   **Primary (Electric Strike):** `#81ecff` (Primary) / `#00d4ec` (Primary Dim). Use this for critical path data and energy states.
*   **Surface Foundation:** `#0c0e12` (Background/Surface).
*   **Surface Hierarchy:**
    *   `surface-container-lowest`: `#000000` (Recessed areas, deep wells).
    *   `surface-container-low`: `#111318` (Secondary information).
    *   `surface-container-high`: `#1d2025` (Interactive surfaces).
    *   `surface-container-highest`: `#23262c` (Floating modals or highlighted data).

### The "No-Line" Rule
Prohibit 1px solid borders for sectioning. Boundaries must be defined solely through background color shifts. For example, a `surface-container-low` section should sit against a `surface` background to define its edge. This creates a "machined" look where parts feel fitted together rather than outlined.

### The "Glass & Gradient" Rule
To add soul to the technicality, use Glassmorphism for floating elements (back-drop blur: 12px-20px) using semi-transparent variations of `surface-variant`. Main CTAs should utilize a subtle linear gradient from `primary` (`#81ecff`) to `primary-container` (`#00e3fd`) at a 135-degree angle to simulate the glow of an energized conductor.

---

## 3. Typography: Data-Driven Authority
We use a dual-typeface system to balance technical clarity with editorial impact.

*   **Display & Headlines (Space Grotesk):** This typeface provides a wide, technical stance. Use `display-lg` (3.5rem) for state-of-charge percentages and `headline-md` (1.75rem) for telemetry headers.
*   **Body & Labels (Inter):** Chosen for its exceptional legibility at small sizes. Use `label-md` (0.75rem) for technical units (kW, Amps, Volts) to maintain a "data-sheet" aesthetic.
*   **Hierarchy:** Always pair a high-contrast `on-surface` (`#f6f6fc`) for values with an `on-surface-variant` (`#aaabb0`) for labels to ensure the data is the hero of the composition.

---

## 4. Elevation & Depth: Tonal Layering
Traditional drop shadows are forbidden. We achieve depth through atmospheric physics.

*   **The Layering Principle:** Stacking tiers creates "soft lift." Place a `surface-container-highest` card on top of a `surface-container-low` background. The subtle shift in hex value provides all the separation required for a premium feel.
*   **Ambient Glow:** When a floating element (like a map pin or active charging card) requires a "shadow," use a 20px-40px blur with `primary` (`#81ecff`) at 4-8% opacity. This mimics the light spill of a neon display.
*   **The Ghost Border:** If accessibility requires a stroke, use `outline-variant` (`#46484d`) at 15% opacity. It should be felt, not seen.

---

## 5. Components: Machined Precision

### Buttons
*   **Primary:** Gradient fill (`primary` to `primary_container`), sharp `4px` corners (`DEFAULT`). Text in `on_primary_fixed` (`#003840`).
*   **Secondary:** Ghost style. No fill, `Ghost Border` (`outline-variant` at 20%), text in `primary`.
*   **Interaction:** On press, the `primary_dim` state should be triggered, accompanied by a subtle `primary` outer glow.

### Cards & Telemetry Blocks
*   **Construction:** Forbid the use of divider lines. Separate data points using `0.75rem` (`xl`) vertical spacing or by nesting a `surface-container-highest` block inside a `surface-container` area.
*   **Corners:** Use the `md` (0.375rem / 6px) scale for cards to maintain the "High-Voltage" sharpness.

### Input Fields
*   **States:** Default state uses `surface_container_high`. Focused state transitions the background to `surface_container_highest` and adds a 1px `primary` underline—never a full box stroke.

### Specialized EV Components
*   **The Power Bar:** A linear progress indicator using `primary` for the fill and `surface_container_lowest` for the track. Add a `primary` outer glow to the leading edge of the progress bar to signify "active current."
*   **Live Telemetry Chips:** Use `secondary_container` backgrounds with `label-sm` Inter text for real-time stats (e.g., "800V Architecture").

---

## 6. Do's and Don'ts

### Do
*   **Do** use asymmetrical layouts. A left-aligned headline with a right-aligned telemetry value creates a sophisticated, instrument-cluster feel.
*   **Do** lean into the "High-Voltage" cyan. Use it sparingly but intensely for the most critical data points.
*   **Do** use `0.25rem` (4px) and `0.5rem` (8px) roundness almost exclusively to maintain a professional, technical edge.

### Don't
*   **Don't** use standard "Material" shadows. They look muddy on an obsidian base.
*   **Don't** use 1px solid borders to separate list items. Use the spacing scale (`sm` or `md`) to let the negative space do the work.
*   **Don't** use rounded "pill" buttons unless they are small utility chips. Primary actions must remain sharp and authoritative.
*   **Don't** use pure white (`#ffffff`). Always use `on-surface` (`#f6f6fc`) to prevent eye strain in dark environments.