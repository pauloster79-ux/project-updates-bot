// Example usage of the Notion-like UI builders in your Slack app

import { App } from '@slack/bolt';
import { buildHome, buildCard, DESIGN_TOKENS, HomeTab, CardItem } from '../ui';

const app = new App({
  token: process.env.SLACK_BOT_TOKEN,
  signingSecret: process.env.SLACK_SIGNING_SECRET,
});

// Sample data - replace with your actual data fetching logic
const getSampleUpdates = (): CardItem[] => [
  {
    id: 'update-1',
    title: 'API Integration Complete',
    subtitle: 'Backend services now connected to Slack',
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
  {
    id: 'update-2',
    title: 'Database Migration',
    subtitle: 'Moving from SQLite to PostgreSQL',
    meta: {
      owner: 'Alex Rodriguez',
      date: '2025-09-21',
      status: 'active',
    },
    actions: [
      { id: 'view', text: 'View Details' },
      { id: 'edit', text: 'Edit' },
    ],
  },
  {
    id: 'update-3',
    title: 'UI Redesign',
    subtitle: 'Implementing Notion-like interface',
    meta: {
      owner: 'Emma Wilson',
      date: '2025-09-20',
      status: 'pending',
    },
    actions: [
      { id: 'view', text: 'View Details' },
      { id: 'edit', text: 'Edit' },
    ],
  },
];

// Home tab handler
app.event('app_home_opened', async ({ event, client }) => {
  try {
    const updates = getSampleUpdates();
    const homeConfig: HomeTab = {
      tab: 'overview',
      items: updates,
    };

    const homeView = buildHome(homeConfig);

    await client.views.publish({
      user_id: event.user,
      view: homeView,
    });
  } catch (error) {
    console.error('Error publishing home view:', error);
  }
});

// Tab switching handler
app.action(DESIGN_TOKENS.ACTION_IDS.TAB_OVERVIEW, async ({ ack, body, client }) => {
  await ack();
  
  if (!('user' in body)) return;
  
  const updates = getSampleUpdates();
  const homeConfig: HomeTab = {
    tab: 'overview',
    items: updates,
  };

  const homeView = buildHome(homeConfig);

  await client.views.publish({
    user_id: body.user.id,
    view: homeView,
  });
});

app.action(DESIGN_TOKENS.ACTION_IDS.TAB_MY_UPDATES, async ({ ack, body, client }) => {
  await ack();
  
  if (!('user' in body)) return;
  
  const updates = getSampleUpdates();
  const homeConfig: HomeTab = {
    tab: 'my-updates',
    items: updates,
  };

  const homeView = buildHome(homeConfig);

  await client.views.publish({
    user_id: body.user.id,
    view: homeView,
  });
});

app.action(DESIGN_TOKENS.ACTION_IDS.TAB_ADMIN, async ({ ack, body, client }) => {
  await ack();
  
  if (!('user' in body)) return;
  
  const updates = getSampleUpdates();
  const homeConfig: HomeTab = {
    tab: 'admin',
    items: updates,
  };

  const homeView = buildHome(homeConfig);

  await client.views.publish({
    user_id: body.user.id,
    view: homeView,
  });
});

// Card action handlers
app.action(/^card_action_/, async ({ ack, body, client }) => {
  await ack();
  
  if (!('user' in body) || !('actions' in body)) return;
  
  const action = body.actions[0];
  const actionId = action.action_id;
  const updateId = action.value;
  
  if (actionId.includes('view')) {
    // Handle view action
    console.log(`Viewing update: ${updateId}`);
    // You could open a modal here or navigate to a detailed view
  } else if (actionId.includes('edit')) {
    // Handle edit action
    console.log(`Editing update: ${updateId}`);
    // You could open an edit modal here
  }
});

// Toggle handler
app.action(/^toggle_/, async ({ ack, body, client }) => {
  await ack();
  
  if (!('user' in body) || !('actions' in body)) return;
  
  const action = body.actions[0];
  const toggleId = action.action_id.replace('toggle_', '');
  
  // In a real app, you'd store the toggle state somewhere
  // For this example, we'll just toggle between expanded/collapsed
  const isExpanded = Math.random() > 0.5; // Random for demo
  
  // Rebuild the home view with the new toggle state
  const updates = getSampleUpdates();
  const homeConfig: HomeTab = {
    tab: 'overview',
    items: updates,
  };

  const homeView = buildHome(homeConfig);

  await client.views.publish({
    user_id: body.user.id,
    view: homeView,
  });
});

// Message handler for update notifications
app.message('update created', async ({ message, client }) => {
  // When an update is created, send a notification message
  const update: CardItem = {
    id: 'new-update',
    title: 'New Update Created',
    subtitle: 'Check out the latest progress',
    meta: {
      owner: 'Team Member',
      date: new Date().toISOString().split('T')[0],
      status: 'active',
    },
    actions: [
      { id: 'view', text: 'View in Home' },
    ],
  };

  const cardBlocks = buildCard(update);
  
  await client.chat.postMessage({
    channel: message.channel,
    blocks: [
      {
        type: 'section',
        text: {
          type: 'mrkdwn',
          text: '✅ *Update Created*\nYour progress has been shared with the team',
        },
      },
      { type: 'divider' },
      ...cardBlocks,
    ],
  });
});

export default app;
