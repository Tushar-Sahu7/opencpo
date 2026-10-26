# Design System Specification: The Kinetic Terminal

## 1. Overview & Creative North Star

**Creative North Star: The Kinetic Terminal**
This design system moves away from the "softness" of traditional consumer apps and leans into the high-precision world of industrial human-machine interfaces (HMI) and automotive telemetry. It is inspired by the raw utility of a Tesla Supercharger and the focused clarity of an aircraft cockpit. 

The aesthetic is characterized by **Command-Line Precision** mixed with **High-End Editorial Depth**. We break the "template" look by utilizing intentional asymmetry—placing critical data points off-center to mimic real-world instrumentation—and using extreme typography scales to separate "The Machine" (data) from "The User" (interface). This is a PWA designed for the 390px viewport, emphasizing thumb-driven tactical density.

---

## 2. Colors

The palette is rooted in deep obsidian and cold steel, providing a canvas where light (energy) becomes the primary signifier of status.

### Color Strategy & Hierarchy
*   **Primary (`#00daf3`):** The "Electric Blue." Use this exclusively for active charging states, flow animations, and primary actions. It represents energy in motion.
*   **Secondary (`#40e56c`):** The "Availability Green." Reserved for success states and charger availability. High-vibrancy for instant recognition at a distance.
*   **Tertiary (`#ffb950`):** The "Caution Amber." Used for warnings, thermal limits, or restricted access.
*   **Surface Hierarchy:** We utilize `surface-container-lowest` (#0e0e0e) for the base canvas and `surface-container-highest` (#353535) for interactive modules.

### The "No-Line" Rule
Standard 1px borders are strictly prohibited for sectioning. Structural boundaries must be defined through:
1.  **Tonal Shifts:** Placing a `surface-container-low` card against a `surface-container-lowest` background.
2.  **Negative Space:** Using the spacing scale to create "islands" of information.
3.  **Functional Edge:** If a container needs focus, use a `surface-bright` top-edge highlight (0.5px) rather than a full border to simulate light hitting a physical edge.

### Signature Textures
Main CTAs should not be flat. Apply a subtle linear gradient (e.g., `primary` to `primary_container`) to give buttons a "lit" appearance, as if they are hardware-backlit buttons. For overlays, use **Glassmorphism**: `surface_container` at 70% opacity with a `20px` backdrop-blur to maintain context of the underlying "instrumentation."

---

## 3. Typography

The typography strategy is a dual-engine system. It separates human-readable instructions from machine-generated telemetry.

*   **The Editorial Layer (Space Grotesk):** Used for Headlines and Labels. Its geometric, slightly "engineered" look provides an authoritative, modern voice.
    *   *Display-LG (3.5rem):* Reserved for critical charging percentages or time-remaining figures.
*   **The Utility Layer (Inter):** Used for body copy and instructions. It provides neutral, high-legibility support for the more aggressive display faces.
*   **The Telemetry Layer (JetBrains Mono / Roboto Mono):** **Mandatory** for all numerical values, kWh readouts, and voltage data. This monospace choice ensures that numbers don't "jump" when values update rapidly, mimicking a digital multimeter.

**Hierarchy Note:** Use `label-sm` in all-caps with `0.1em` letter-spacing for technical metadata to reinforce the industrial aesthetic.

---

## 4. Elevation & Depth

In this system, depth is "carved" or "stacked," never "shadowed."

*   **The Layering Principle:** Avoid traditional shadows. To elevate a "charging card," place it on `surface-container-highest` while the main app background remains `surface-container-lowest`. This 2-tier jump creates immediate visual priority.
*   **Ambient Glow:** For the "Active Charging" state, replace shadows with an ambient blue glow using the `primary` color at 10% opacity with a `40px` blur. This simulates the light emitted from a charging port.
*   **The Ghost Border Fallback:** Where accessibility requires a container edge, use the `outline_variant` at 15% opacity. This "Ghost Border" should feel like a faint etching on metal rather than a drawn line.

---

## 5. Components

### Buttons (Tactile Triggers)
*   **Primary:** `primary` background with `on_primary` text. No rounded corners (`0.25rem` default). High-contrast.
*   **Secondary:** Ghost style. `outline` border (20% opacity) with `primary` text.
*   **Interaction:** On press, the button should shift to `primary_fixed_dim`, creating a "pressed-in" physical sensation.

### Telemetry Blocks (Data Cards)
Instead of standard cards, use "Instrument Clusters." These are borderless containers using `surface-container-low`. 
*   **Layout:** Place the label (`label-md`) in the top-left and the value (`display-sm` monospace) in the bottom-right. This asymmetrical arrangement leads the eye diagonally across the data point.

### Input Fields
*   **Style:** Minimalist underlines using `outline_variant`.
*   **Active State:** The underline transitions to `primary` (2px thickness). 
*   **Typography:** User-inputted text must use the monospace font to match the telemetry aesthetic.

### Progress & Status
*   **Charging Bar:** A thick, horizontal bar using `primary_container` as the track and a `primary` to `white` gradient for the fill. 
*   **Forbid Dividers:** Never use horizontal rules (`<hr>`). Use a 24px vertical gap or a color-block shift to separate the "Map" from "Station Details."

---

## 6. Do's and Don'ts

### Do:
*   **Embrace Asymmetry:** Align technical labels to the left and data values to the right.
*   **Use High Contrast:** Ensure `on_surface` text sits prominently against `surface` backgrounds for legibility in bright sunlight (common for EV drivers).
*   **Design for Thumbs:** Keep primary actions within the bottom 30% of the 390px width screen.
*   **Support Bilingual Flow:** Ensure that "Charging" (English) and "Opladen" (Dutch) have enough container breathing room to account for character length differences.

### Don't:
*   **Don't use Rounded Shapes:** Avoid `full` roundedness unless it's for a status "pill." Stick to the `DEFAULT (0.25rem)` or `none` for a professional, industrial feel.
*   **Don't use Generic Iconography:** Avoid "soft" or "playful" icons. Use thin-stroke, technical icons that look like architectural symbols.
*   **Don't Blur Information:** Avoid low-contrast grays for secondary text. Use `on_surface_variant` to ensure the "Industrial" clarity is never sacrificed for "vibe."