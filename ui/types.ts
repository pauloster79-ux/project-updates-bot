// TypeScript types for Notion-like Slack Block Kit UI

export interface HomeTab {
  tab: 'overview' | 'my-updates' | 'admin';
  items: CardItem[];
}

export interface CardItem {
  id: string;
  title: string;
  subtitle?: string;
  meta: {
    owner?: string;
    date?: string;
    status?: 'active' | 'paused' | 'completed' | 'pending';
  };
  content?: string;
  actions?: Action[];
}

export interface Action {
  id: string;
  text: string;
  style?: 'primary' | 'danger';
  confirm?: {
    title: string;
    text: string;
  };
}

export interface HeaderConfig {
  icon: string;
  title: string;
  subtitle?: string;
  actions?: Action[];
}

export interface EmptyStateConfig {
  icon: string;
  title: string;
  hint: string;
  cta: Action;
}

export interface ToggleConfig {
  id: string;
  collapsedView: any[];
  expandedView: any[];
  isExpanded: boolean;
}

// Slack Block Kit types
export interface Block {
  type: string;
  block_id?: string;
  [key: string]: any;
}

export interface View {
  type: 'home' | 'modal';
  blocks: Block[];
  [key: string]: any;
}

// Design tokens
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
    USER: '👤',
    CALENDAR: '📅',
    CLOCK: '⏰',
    PLUS: '➕',
    EDIT: '✏️',
    DELETE: '🗑️',
    EXPAND: '🔽',
    COLLAPSE: '🔼',
  },
  ACTION_IDS: {
    TAB_OVERVIEW: 'tab_overview',
    TAB_MY_UPDATES: 'tab_my_updates',
    TAB_ADMIN: 'tab_admin',
    TOGGLE_PREFIX: 'toggle_',
    CARD_ACTION_PREFIX: 'card_action_',
    HEADER_ACTION_PREFIX: 'header_action_',
  },
  BLOCK_IDS: {
    HOME_HEADER: 'home_header',
    HOME_TABS: 'home_tabs',
    HOME_CONTENT: 'home_content',
    CARD_PREFIX: 'card_',
    TOGGLE_PREFIX: 'toggle_',
  },
} as const;
