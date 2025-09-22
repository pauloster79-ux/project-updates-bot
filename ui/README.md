# Notion-like UI for Slack Block Kit

A comprehensive UI system that brings Notion's clean, minimal design to Slack apps using Block Kit constraints.

## 🎨 Design Philosophy

This UI system emulates Notion's design principles within Slack's Block Kit framework:

- **Calm & Minimal**: Clean layouts with generous spacing
- **Monochrome with Accents**: Subtle use of color for emphasis
- **Clear Hierarchy**: Proper typography and visual structure
- **Card-based Layout**: Information organized in digestible chunks
- **Consistent Patterns**: Reusable components across all surfaces

## 🏗️ Architecture

```
ui/
├── types.ts          # TypeScript interfaces and design tokens
├── builders.ts       # Composable UI builder functions
├── index.ts          # Main exports
├── __tests__/        # Unit tests
└── README.md         # This file

examples/
├── home-overview.json        # Home tab example
├── modal-create-update.json  # Modal example
├── message-update-created.json # Message example
└── usage-example.ts          # Integration example
```

## 🚀 Quick Start

```typescript
import { buildHome, buildCard, DESIGN_TOKENS } from './ui';

// Build a home tab
const homeView = buildHome({
  tab: 'overview',
  items: [
    {
      id: 'update-1',
      title: 'API Integration Complete',
      subtitle: 'Backend services connected',
      meta: {
        owner: 'Sarah Chen',
        date: '2025-09-22',
        status: 'completed',
      },
      actions: [
        { id: 'view', text: 'View Details' },
        { id: 'edit', text: 'Edit' },
      ],
    },
  ],
});

// Publish to Slack
await client.views.publish({
  user_id: userId,
  view: homeView,
});
```

## 📱 Components

### Home Tab

The main interface with three tabs: Overview, My Updates, and Admin.

**Features:**
- Notion-style header with icon and actions
- Segmented tab navigation using buttons
- Card-based content layout
- Empty states with friendly messaging
- Responsive design that works on all devices

### Cards

Information units that display updates, tasks, or any content.

**Structure:**
- Bold title with optional subtitle
- Meta information (owner, date, status) in context
- Action buttons for interactions
- Consistent spacing and typography

### Modals

Forms and detailed views with Notion-like styling.

**Features:**
- Clean header with emoji icons
- Proper form hierarchy with labels and hints
- Primary/secondary button styling
- Helpful context and tips

### Messages

Notifications and updates using the same card pattern.

**Features:**
- Consistent with home tab styling
- Action buttons for quick interactions
- Contextual information and tips

## 🎨 Design Tokens

```typescript
export const DESIGN_TOKENS = {
  COLORS: {
    INK_900: '#37352f', // Primary text
    INK_600: '#787774', // Secondary text
    INK_400: '#9b9a97', // Muted text
    ACCENT_600: '#2383e2', // Subtle blue
    ACCENT_400: '#4a9eff', // Hover/active
  },
  ICONS: {
    PIN: '📌',
    CHECK: '✅',
    FOLDER: '🗂️',
    COMPASS: '🧭',
    SETTINGS: '⚙️',
    // ... more icons
  },
};
```

## 🔧 Builder Functions

### `buildHome(config: HomeTab)`

Creates a complete home tab view with header, tabs, and content.

```typescript
const homeView = buildHome({
  tab: 'overview', // 'overview' | 'my-updates' | 'admin'
  items: cardItems,
});
```

### `buildCard(item: CardItem)`

Creates a single card with title, meta, and actions.

```typescript
const cardBlocks = buildCard({
  id: 'update-1',
  title: 'API Integration',
  meta: { owner: 'Sarah', status: 'completed' },
  actions: [{ id: 'view', text: 'View' }],
});
```

### `buildEmptyState(config: EmptyStateConfig)`

Creates friendly empty states with CTAs.

```typescript
const emptyState = buildEmptyState({
  icon: '📝',
  title: 'No updates yet',
  hint: 'Create your first update',
  cta: { id: 'create', text: 'Create Update' },
});
```

### `buildToggle(config: ToggleConfig)`

Creates expandable/collapsible sections.

```typescript
const toggle = buildToggle({
  id: 'details',
  collapsedView: [collapsedBlocks],
  expandedView: [expandedBlocks],
  isExpanded: false,
});
```

## 🧪 Testing

Run the test suite:

```bash
npm test
```

Tests include:
- Snapshot tests for all builder functions
- Edge cases and error handling
- Type safety validation

## 📸 Examples

### Home Tab - Overview
![Home Tab Overview](examples/home-overview.json)
- Clean header with project branding
- Segmented tab navigation
- Card list with meta information
- Consistent spacing and typography

### Modal - Create Update
![Modal Example](examples/modal-create-update.json)
- Form with proper hierarchy
- Helpful hints and placeholders
- Primary/secondary button styling
- Contextual tips

### Message - Update Created
![Message Example](examples/message-update-created.json)
- Notification with card pattern
- Action buttons for quick access
- Consistent with home tab styling

## 🔄 Integration

### With Bolt for JavaScript

```typescript
import { App } from '@slack/bolt';
import { buildHome, DESIGN_TOKENS } from './ui';

const app = new App({
  token: process.env.SLACK_BOT_TOKEN,
  signingSecret: process.env.SLACK_SIGNING_SECRET,
});

// Home tab handler
app.event('app_home_opened', async ({ event, client }) => {
  const homeView = buildHome({
    tab: 'overview',
    items: await getUpdates(),
  });

  await client.views.publish({
    user_id: event.user,
    view: homeView,
  });
});

// Tab switching
app.action(DESIGN_TOKENS.ACTION_IDS.TAB_OVERVIEW, async ({ ack, body, client }) => {
  await ack();
  // Handle tab switch...
});
```

### Action Handling

All interactive elements have consistent action IDs:

```typescript
// Tab actions
DESIGN_TOKENS.ACTION_IDS.TAB_OVERVIEW
DESIGN_TOKENS.ACTION_IDS.TAB_MY_UPDATES
DESIGN_TOKENS.ACTION_IDS.TAB_ADMIN

// Card actions
DESIGN_TOKENS.ACTION_IDS.CARD_ACTION_PREFIX + actionId

// Toggle actions
DESIGN_TOKENS.ACTION_IDS.TOGGLE_PREFIX + toggleId
```

## 🎯 Best Practices

1. **Consistent Styling**: Always use the design tokens for colors and icons
2. **Clear Hierarchy**: Use proper text formatting (bold, italic, code)
3. **Helpful Actions**: Every interactive element should have a clear purpose
4. **Accessibility**: Include confirm dialogs for destructive actions
5. **Empty States**: Provide friendly guidance when there's no content
6. **Error Handling**: Gracefully handle missing or invalid data

## 🔮 Future Enhancements

- [ ] Dark mode support
- [ ] More card variants (compact, detailed, etc.)
- [ ] Advanced form components
- [ ] Animation support (where possible)
- [ ] Accessibility improvements
- [ ] Internationalization support

## 📄 License

MIT License - feel free to use in your projects!

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

---

*Built with ❤️ for the Slack developer community*
