---
name: Enterprise Insight Assistant
description: Evidence-first Chinese enterprise operations workspace
colors:
  primary: "#1767d9"
  primary-ink: "#17365f"
  page-mist: "#eef5ff"
  page-surface: "#f6faff"
  panel: "#ffffff"
  border: "#d8e5f3"
  muted: "#63758e"
  success: "#137047"
  warning: "#916300"
  danger: "#b22828"
typography:
  display:
    fontFamily: "Microsoft YaHei UI, PingFang SC, system-ui, sans-serif"
    fontSize: "clamp(42px, 5vw, 68px)"
    fontWeight: 700
    lineHeight: 1.08
    letterSpacing: "-0.045em"
  body:
    fontFamily: "Microsoft YaHei UI, PingFang SC, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.65
  label:
    fontFamily: "Microsoft YaHei UI, PingFang SC, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 700
    letterSpacing: "0.08em"
rounded:
  control: "10px"
  panel: "16px"
  pill: "999px"
spacing:
  compact: "8px"
  control: "12px"
  section: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.panel}"
    rounded: "{rounded.control}"
    padding: "11px 16px"
  button-secondary:
    backgroundColor: "{colors.panel}"
    textColor: "#24538f"
    rounded: "{rounded.control}"
    padding: "10px 14px"
---

# Design System: Enterprise Insight Assistant

## Overview

**Creative North Star: "Evidence in Daylight"**

This is a bright, operational interface for business users who need to see the boundary of an analysis before trusting its conclusion. It borrows the supplied reference's generous pale-blue atmosphere and calm spacing, then replaces marketing-style calls to action with clear working surfaces and evidence controls.

**Key Characteristics:**

- Low-contrast mist-blue surroundings with high-contrast navy working text.
- One cobalt interaction color, reserved for chosen state and primary action.
- Panels explain function through grouping, not decoration.
- Facts, inferences, recommendations, and limitations remain visibly separate.

## Colors

The palette reads as a daylight operations room: cool, spacious, and precise rather than generically futuristic.

### Primary

- **Cobalt action:** used for the primary action, active navigation, and identity mark.

### Neutral

- **Mist ground:** carries page-scale atmosphere around working surfaces.
- **Navy ink:** provides headings and high-priority reading contrast.
- **White panel:** separates login, configuration, report, and form tasks.
- **Blue-gray border:** marks editable and contained areas without visual heaviness.

**The One Accent Rule.** Cobalt is the only general action accent; semantic status colors only communicate status.

## Typography

**Display Font:** Microsoft YaHei UI, PingFang SC, system-ui, sans-serif.
**Body Font:** Microsoft YaHei UI, PingFang SC, system-ui, sans-serif.

**Character:** Chinese-first, compactly confident sans typography. Large statements establish the product purpose; body copy stays practical and evidence-oriented.

### Hierarchy

- **Display:** used only for the login purpose statement.
- **Headline:** section and page titles make the active task immediately clear.
- **Body:** uses an airy line height for explanatory text and report content.
- **Label:** short blue labels identify scopes, statuses, and form fields.

## Layout

Desktop uses a fixed product navigation rail. The operating workspace is deliberately asymmetric: conversation and result reading occupy the center, while the evidence inspector makes data source, active schema snapshot, and document range persistent on the right. Administrative surfaces switch to a list-detail split.

At 1080px the evidence inspector moves below the conversation. At 760px navigation becomes a horizontal strip, application columns collapse, and the login display is reduced to avoid single-character Chinese line breaks.

## Elevation & Depth

Depth is ambient and limited. Panels use a light border first; only key entry surfaces such as the login card and message composer use a soft, blue-tinted shadow. Backdrop blur belongs only to the fixed application navigation and modal scrim.

**The Proof Surface Rule.** A report or configuration boundary may be elevated, but routine rows remain flat so hierarchy follows task importance.

## Shapes

Working panels use gently curved 16px corners. Inputs and buttons use a tighter 10px corner. Status only uses full pills. This is the only intentional mixed-radius rule.

## Components

### Buttons

- **Primary:** cobalt fill for login, submit, and create actions; it depresses by one pixel when active.
- **Secondary:** white with a blue border for operations that do not advance the main flow.
- **Text:** borderless blue action for destructive or contextual operations only when its nearby label makes the consequence clear.

### Cards / Containers

- **Corner Style:** gently curved panels.
- **Background:** white or translucent white on mist ground.
- **Border:** a single pale blue-gray stroke; no stacked card shadows.

### Inputs / Fields

- **Style:** white background, pale blue border, compact label above.
- **Focus:** visible 3px blue focus ring.
- **Error:** red-tinted inline message with recovery guidance.

### Navigation

- **Style:** left rail on desktop, horizontally scrollable row on mobile.
- **State:** active item has a pale cobalt field and dark cobalt text; hover is lighter than active.

### Evidence Inspector

The signature component of the operating workspace. It presents the data source, active snapshot, and document checkboxes before a message is sent; it is never hidden behind an advanced-settings menu.

## Do's and Don'ts

### Do:

- **Do** keep evidence scope visible beside the analysis task.
- **Do** use Chinese errors that say what failed and what the user can do next.
- **Do** distinguish task status with labels and color together.
- **Do** preserve keyboard focus and reduced-motion behavior.

### Don't:

- **Don't** use DeepSeek branding, copied text, or its logo.
- **Don't** render a generic AI glow, purple gradient, or fake dashboard metric.
- **Don't** represent an inference as a confirmed data fact.
- **Don't** display database passwords or any authentication secret in a page.
