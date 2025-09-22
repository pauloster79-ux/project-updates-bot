import { 
  HomeTab, 
  CardItem, 
  HeaderConfig, 
  EmptyStateConfig, 
  ToggleConfig, 
  Block, 
  View,
  DESIGN_TOKENS 
} from './types';

/**
 * Builds a complete Home tab view with Notion-like styling
 */
export function buildHome(config: HomeTab): View {
  const blocks: Block[] = [
    ...buildHeader({
      icon: DESIGN_TOKENS.ICONS.PIN,
      title: 'Project Updates',
      subtitle: 'Track team progress and manage updates',
      actions: [
        {
          id: 'refresh',
          text: 'Refresh',
        }
      ]
    }),
    ...buildTabs(config.tab),
    { type: 'divider' },
    ...buildContent(config),
  ];

  return {
    type: 'home',
    blocks,
  };
}

/**
 * Builds a Notion-style header with icon, title, subtitle, and actions
 */
export function buildHeader(config: HeaderConfig): Block[] {
  const blocks: Block[] = [
    {
      type: 'section',
      block_id: DESIGN_TOKENS.BLOCK_IDS.HOME_HEADER,
      text: {
        type: 'mrkdwn',
        text: `${config.icon} *${config.title}*${config.subtitle ? `\n${config.subtitle}` : ''}`,
      },
    },
  ];

  // Add actions if provided
  if (config.actions && config.actions.length > 0) {
    blocks[0].accessory = {
      type: 'overflow',
      action_id: 'header_actions',
      options: config.actions.map(action => ({
        text: {
          type: 'plain_text',
          text: action.text,
        },
        value: action.id,
      })),
    };
  }

  return blocks;
}

/**
 * Builds segmented tabs using buttons (fake tabs)
 */
export function buildTabs(activeTab: HomeTab['tab']): Block[] {
  const tabs = [
    { id: 'overview', text: 'Overview', icon: DESIGN_TOKENS.ICONS.COMPASS },
    { id: 'my-updates', text: 'My Updates', icon: DESIGN_TOKENS.ICONS.USER },
    { id: 'admin', text: 'Admin', icon: DESIGN_TOKENS.ICONS.SETTINGS },
  ];

  return [
    {
      type: 'actions',
      block_id: DESIGN_TOKENS.BLOCK_IDS.HOME_TABS,
      elements: tabs.map(tab => ({
        type: 'button',
        action_id: DESIGN_TOKENS.ACTION_IDS[`TAB_${tab.id.toUpperCase().replace('-', '_')}` as keyof typeof DESIGN_TOKENS.ACTION_IDS],
        text: {
          type: 'plain_text',
          text: `${tab.icon} ${tab.text}`,
        },
        style: tab.id === activeTab ? 'primary' : undefined,
        value: tab.id,
      })),
    },
  ];
}

/**
 * Builds the main content area based on the active tab
 */
export function buildContent(config: HomeTab): Block[] {
  switch (config.tab) {
    case 'overview':
      return buildOverviewContent(config.items);
    case 'my-updates':
      return buildMyUpdatesContent(config.items);
    case 'admin':
      return buildAdminContent(config.items);
    default:
      return buildEmptyState({
        icon: DESIGN_TOKENS.ICONS.FOLDER,
        title: 'No content available',
        hint: 'Select a different tab to view content',
        cta: {
          id: 'refresh',
          text: 'Refresh',
        },
      });
  }
}

/**
 * Builds overview tab content with team updates
 */
export function buildOverviewContent(items: CardItem[]): Block[] {
  if (items.length === 0) {
    return buildEmptyState({
      icon: DESIGN_TOKENS.ICONS.CHECK,
      title: 'All caught up!',
      hint: 'No pending updates from your team',
      cta: {
        id: 'refresh',
        text: 'Refresh',
      },
    });
  }

  const blocks: Block[] = [
    {
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: `*Recent Updates* (${items.length})`,
      },
    },
    { type: 'divider' },
    ...buildCardList(items.slice(0, 5)), // Show first 5 items
  ];

  if (items.length > 5) {
    blocks.push({
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: `_... and ${items.length - 5} more updates_`,
      },
    });
  }

  return blocks;
}

/**
 * Builds my updates tab content
 */
export function buildMyUpdatesContent(items: CardItem[]): Block[] {
  const myItems = items.filter(item => item.meta.owner === 'me');
  
  if (myItems.length === 0) {
    return buildEmptyState({
      icon: DESIGN_TOKENS.ICONS.USER,
      title: 'No updates from you',
      hint: 'Share your progress with the team',
      cta: {
        id: 'create_update',
        text: 'Create Update',
        style: 'primary',
      },
    });
  }

  return [
    {
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: `*Your Updates* (${myItems.length})`,
      },
    },
    { type: 'divider' },
    ...buildCardList(myItems),
  ];
}

/**
 * Builds admin tab content
 */
export function buildAdminContent(items: CardItem[]): Block[] {
  return [
    {
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: '*Admin Panel*',
      },
    },
    { type: 'divider' },
    {
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: `• *Total Updates:* ${items.length}\n• *Active Users:* ${new Set(items.map(i => i.meta.owner)).size}\n• *Pending Reviews:* ${items.filter(i => i.meta.status === 'pending').length}`,
      },
    },
    { type: 'divider' },
    {
      type: 'actions',
      elements: [
        {
          type: 'button',
          action_id: 'admin_manage_users',
          text: {
            type: 'plain_text',
            text: `${DESIGN_TOKENS.ICONS.USER} Manage Users`,
          },
        },
        {
          type: 'button',
          action_id: 'admin_settings',
          text: {
            type: 'plain_text',
            text: `${DESIGN_TOKENS.ICONS.SETTINGS} Settings`,
          },
        },
      ],
    },
  ];
}

/**
 * Builds a list of cards with Notion-like styling
 */
export function buildCardList(items: CardItem[]): Block[] {
  const blocks: Block[] = [];
  
  items.forEach((item, index) => {
    blocks.push(...buildCard(item));
    if (index < items.length - 1) {
      blocks.push({ type: 'divider' });
    }
  });
  
  return blocks;
}

/**
 * Builds a single card with Notion-like styling
 */
export function buildCard(item: CardItem): Block[] {
  const statusEmoji = getStatusEmoji(item.meta.status);
  const metaText = [
    item.meta.owner && `👤 ${item.meta.owner}`,
    item.meta.date && `📅 ${item.meta.date}`,
    item.meta.status && `${statusEmoji} ${item.meta.status}`,
  ].filter(Boolean).join(' • ');

  const blocks: Block[] = [
    {
      type: 'section',
      block_id: `${DESIGN_TOKENS.BLOCK_IDS.CARD_PREFIX}${item.id}`,
      text: {
        type: 'mrkdwn',
        text: `*${item.title}*${item.subtitle ? `\n_${item.subtitle}_` : ''}`,
      },
    },
  ];

  // Add meta information as context
  if (metaText) {
    blocks.push({
      type: 'context',
      elements: [
        {
          type: 'mrkdwn',
          text: metaText,
        },
      ],
    });
  }

  // Add actions if provided
  if (item.actions && item.actions.length > 0) {
    blocks.push({
      type: 'actions',
      elements: item.actions.map(action => ({
        type: 'button',
        action_id: `${DESIGN_TOKENS.ACTION_IDS.CARD_ACTION_PREFIX}${action.id}`,
        text: {
          type: 'plain_text',
          text: action.text,
        },
        style: action.style,
        value: item.id,
        confirm: action.confirm ? {
          title: {
            type: 'plain_text',
            text: action.confirm.title,
          },
          text: {
            type: 'mrkdwn',
            text: action.confirm.text,
          },
        } : undefined,
      })),
    });
  }

  return blocks;
}

/**
 * Builds an empty state with friendly messaging
 */
export function buildEmptyState(config: EmptyStateConfig): Block[] {
  return [
    {
      type: 'section',
      text: {
        type: 'mrkdwn',
        text: `${config.icon} *${config.title}*\n${config.hint}`,
      },
    },
    {
      type: 'actions',
      elements: [
        {
          type: 'button',
          action_id: config.cta.id,
          text: {
            type: 'plain_text',
            text: config.cta.text,
          },
          style: config.cta.style || 'primary',
        },
      ],
    },
  ];
}

/**
 * Builds a toggle section that can expand/collapse
 */
export function buildToggle(config: ToggleConfig): Block[] {
  const toggleIcon = config.isExpanded ? DESIGN_TOKENS.ICONS.COLLAPSE : DESIGN_TOKENS.ICONS.EXPAND;
  
  return [
    {
      type: 'actions',
      block_id: `${DESIGN_TOKENS.BLOCK_IDS.TOGGLE_PREFIX}${config.id}`,
      elements: [
        {
          type: 'button',
          action_id: `${DESIGN_TOKENS.ACTION_IDS.TOGGLE_PREFIX}${config.id}`,
          text: {
            type: 'plain_text',
            text: `${toggleIcon} ${config.isExpanded ? 'Collapse' : 'Expand'}`,
          },
        },
      ],
    },
    ...(config.isExpanded ? config.expandedView : config.collapsedView),
  ];
}

/**
 * Helper function to get status emoji
 */
function getStatusEmoji(status?: string): string {
  switch (status) {
    case 'active': return '🟢';
    case 'paused': return '🟡';
    case 'completed': return '✅';
    case 'pending': return '⏳';
    default: return '⚪';
  }
}
