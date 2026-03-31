# GoTale Server Manager - UI/UX Overhaul Design Spec

## Goal

Complete visual redesign of the GoTale Server Manager web panel. Clean & Minimal dark theme with Gold/Amber accents. Slim icon sidebar, tab-based server navigation, modern typography, simplified layouts. All existing features preserved.

## Design Principles

- **Clean & Minimal**: Lots of breathing room, no visual clutter, flat surfaces
- **Dark Theme**: Near-black backgrounds (#08090c, #0c0e14, #0f1118) with subtle borders
- **Gold/Amber Accent**: #eebb4d as primary interactive color (buttons, active states, highlights)
- **Consistent**: One button style system, one card style, one input style - everywhere
- **Information hierarchy**: Most important info largest/brightest, secondary info muted gray

## Color System

```
Background layers:
  --bg-base:     #08090c    (page background)
  --bg-surface:  #0f1118    (cards, panels)
  --bg-elevated: #141720    (hover states, dropdowns)
  --bg-sidebar:  #0c0e14    (sidebar)
  --bg-input:    #0a0b10    (input fields)

Borders:
  --border:        rgba(255,255,255,0.06)
  --border-hover:  rgba(255,255,255,0.12)
  --border-accent: rgba(238,187,77,0.3)

Text:
  --text-primary:   #e2e8f0
  --text-secondary: #94a3b8
  --text-muted:     #64748b
  --text-subtle:    #4a5568

Accent:
  --accent:       #eebb4d   (gold - primary actions)
  --accent-hover: #d4a233   (gold darker - hover)
  --accent-soft:  rgba(238,187,77,0.1)  (gold backgrounds)

Status:
  --success: #22c55e
  --error:   #ef4444
  --warning: #f59e0b
  --info:    #3b82f6
```

## Typography

- **Font**: Inter (sans-serif) for everything. Drop Cinzel serif font.
- **Headings**: Inter 600-700 weight, no uppercase transforms
- **Body**: 14px base, Inter 400
- **Labels**: 12-13px, 500 weight, --text-secondary color
- **Monospace**: JetBrains Mono / Fira Code / Consolas (console only)
- **No text-shadow, no letter-spacing tricks, no decorative fonts**

## Layout Architecture

### Global Sidebar (always visible)

- **Width collapsed**: 64px (icon only)
- **Width expanded**: 220px (on hover, shows icon + label)
- **Position**: Fixed left, full height
- **Content top-to-bottom**:
  1. Logo: Gold "G" square icon + "GoTale" text (text hidden when collapsed)
  2. Nav items grouped with separator lines:
     - **Main**: Dashboard
     - **Server** (when a server is selected): Console, Config, World, Players, Mods, Backup, Startup, Webhooks, Stats, Chat
     - **System**: Admin (users, roles, settings)
  3. Footer: User avatar circle + username + logout

- **Active state**: Gold background tint + gold icon/text
- **Hover state**: Subtle white background tint

### Top Bar (per page)

- **Height**: 56px, sticky top
- **Left**: Page title (or server name + status dot when in server view)
- **Right**: Action buttons (context-dependent)
- **Backdrop blur**: frosted glass effect

### Server Detail View

When viewing a server, additional **tab bar** below the top bar:
- Horizontal tabs: Console | Config | World | Players | Stats | Chat | Backup | Startup | Mods | Installed Mods | Webhooks
- Active tab: Gold underline + gold text
- Replaces the old sidebar navigation within server pages

### Content Area

- **Max-width**: 1200px for form/card pages
- **Full-width**: Console output (no max-width)
- **Padding**: 32px

## Page Designs

### Login Page

- Centered card layout, no split-screen
- Subtle radial gold glow on background
- Logo + "Server Manager" subtitle above card
- Card: username, password, "stay signed in" checkbox, sign-in button
- Version number below card

### Setup Page (first run)

- Same centered layout as login
- Card with: username, email (optional), password, confirm password
- "Create Admin Account" gold button

### Dashboard

- **Stats row**: 4 cards in grid (Servers count, Online count, Java version, Hytale version)
- **Server list**: Cards with status dot, name, port, version, action icon buttons (console, start/stop)
- **Top bar actions**: "Check Updates" ghost button, "+ New Server" gold button
- **Empty state**: Dashed border card with "No servers yet" + CTA button
- **Alerts** (Java missing, update available): Compact banner above stats row, dismissible

### Server Console

- **Top bar**: Status dot + server name + port/version meta + Restart/Stop buttons
- **Tabs**: Below top bar
- **Console output**: Full-width, monospace, color-coded (time gray, INFO blue, WARN gold, ERROR red, player names purple, success green)
- **Input bar**: Bottom-fixed, gold ">" prompt + input field + Send button

### Server Config

- **File selector**: Dropdown grouped by category (Server Config, Gameplay, Environments, Instances)
- **Editor**: JSON editor with monospace font, line numbers optional
- **Form mode**: Toggle between raw JSON and form-based editing
- **Save button**: Fixed bottom bar with "Save" gold button + "Reset" ghost button

### Server World

- Same JSON editor pattern as Config
- File selector for world data files

### Server Players

- **Player list**: Cards with avatar placeholder, display name, UUID, "Edit" button
- **Player detail**: Expandable below the card
- **Inventory grid**: Same layout as current but with cleaner slot styling (dark slots, subtle borders, item images)
- **World data panel**: Position coordinates, death positions, movement states

### Server Mods (Search)

- **Search bar**: Full-width input with search icon
- **Results grid**: Cards with mod icon, name, author, download count, "Install" button
- **File version selector**: Dropdown within install flow

### Installed Mods

- **Mod list**: Cards with icon, name, version, auto-update toggle, "Uninstall" button
- **Update check**: "Check for Updates" button in top bar

### Server Backup

- **Backup settings card**: Schedule toggle, frequency input, Hytale built-in backup toggle
- **Backup list**: Table/cards with date, size, type, "Restore" button
- **Run backup**: "Backup Now" gold button

### Server Startup

- **Settings form**: RAM, port, auth mode, JVM args textarea
- **JVM Options editor**: Monospace textarea for jvm.options file
- **Crash handling**: Auto-restart toggle, crash notification settings
- **Preview**: Command preview showing what will be executed

### Server Webhooks

- **Webhook URL input**: Per event type (connect, disconnect, death, chat)
- **Template editor**: Message template with placeholder tokens
- **Diagnostics**: Sent/failed/dropped counters

### Server Stats

- **Overview cards**: Unique players, total joins, total chats
- **Chart**: Line chart of activity over time (Chart.js)
- **Trend indicators**: Up/down arrows with percentages

### Server Chat

- **Chat log**: Scrollable message list with player names, timestamps, messages
- **Search**: Filter bar at top
- **Live mode**: Auto-scroll with new messages via WebSocket

### Admin Pages

- **Users**: Table with username, email, roles, actions (edit roles, reset password, delete)
- **Roles**: List with permissions checkboxes
- **Settings**: CurseForge API key, mod update interval, Hytale auto-update toggle

### Error Pages (403, 404, 500)

- Centered card with error code, message, "Go to Dashboard" button

## Component Library

### Buttons

```
Primary (gold):    bg #eebb4d, text #0c0e14, hover #d4a233
Ghost:             bg transparent, border rgba(255,255,255,0.08), text #94a3b8, hover border gold
Danger:            bg transparent, border rgba(ef4444,0.2), text #f87171, hover bg rgba(ef4444,0.1)
Icon button:       36x36px, same ghost style, icon centered
```

All buttons: border-radius 8px, font-weight 600, font-size 13px, padding 8px 16px

### Cards

```
Background: --bg-surface (#0f1118)
Border: 1px solid --border
Border-radius: 12px
Padding: 20px
Hover: border-color --border-hover, background --bg-elevated
```

### Inputs

```
Background: --bg-input (#0a0b10)
Border: 1px solid --border
Border-radius: 8px
Padding: 12px 16px
Focus: border-color --border-accent
Font-size: 14px
```

### Chips/Badges

```
Padding: 2px 8px
Border-radius: 4px
Font-size: 11px, weight 500
Variants: green (success), amber (warning), gray (neutral), blue (info), red (error)
```

### Modals

```
Overlay: rgba(0,0,0,0.6) with backdrop-filter blur(4px)
Card: --bg-surface, border, border-radius 16px, padding 32px
Max-width: 480px (small), 640px (medium), 800px (large)
```

### Toasts/Notifications

```
Position: bottom-right, stacked
Background: --bg-elevated
Border-left: 3px solid (color based on type)
Auto-dismiss: 5 seconds
```

## CSS Architecture

- **theme.css**: All CSS custom properties (colors, spacing, radii, shadows)
- **style.css**: Complete rewrite using the new design system
- No external CSS frameworks. Pure custom CSS.

## Files Changed

### Templates (all 24 .html files rewritten):
- login.html, setup.html, change_password.html
- dashboard.html
- navbar.html (becomes sidebar component)
- server_console.html, server_config.html, server_world.html
- server_players.html, server_stats.html, server_chat.html
- server_backup.html, server_startup.html
- server_mods.html, server_mods_installed.html
- server_webhooks.html
- admin_users.html, admin_roles.html, admin_settings.html
- 403.html, 404.html, 500.html
- footer.html, system_restarting.html

### CSS:
- static/css/theme.css - Complete rewrite with new design tokens
- static/css/style.css - Complete rewrite with new component styles

### JavaScript (minimal changes):
- JS files need NO logic changes
- Only update CSS class names if any were renamed
- Console color classes stay the same pattern

### Python routes:
- No changes needed. All endpoints stay the same.
- Templates render the same variables, just with new markup.

## What Does NOT Change

- All Flask routes and API endpoints
- All JavaScript logic and WebSocket handling
- Database schema
- Server management functionality
- Authentication and authorization
- Plugin system (GoTaleManager)
