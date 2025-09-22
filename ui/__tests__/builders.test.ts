import { buildHome, buildCard, buildEmptyState, buildToggle } from '../builders';
import { HomeTab, CardItem, EmptyStateConfig, ToggleConfig } from '../types';

describe('UI Builders', () => {
  describe('buildHome', () => {
    it('should build overview tab with sample data', () => {
      const config: HomeTab = {
        tab: 'overview',
        items: [
          {
            id: '1',
            title: 'API Integration',
            subtitle: 'Backend services connected',
            meta: {
              owner: 'Sarah Chen',
              date: '2025-09-22',
              status: 'completed',
            },
            actions: [
              { id: 'view', text: 'View' },
              { id: 'edit', text: 'Edit' },
            ],
          },
        ],
      };

      const result = buildHome(config);
      
      expect(result.type).toBe('home');
      expect(result.blocks).toHaveLength(6); // header + tabs + divider + content + divider + card
      expect(result.blocks[0].type).toBe('section');
      expect(result.blocks[0].text.text).toContain('📌 *Project Updates*');
    });

    it('should build my-updates tab with empty state', () => {
      const config: HomeTab = {
        tab: 'my-updates',
        items: [],
      };

      const result = buildHome(config);
      
      expect(result.type).toBe('home');
      expect(result.blocks).toHaveLength(6); // header + tabs + divider + empty state
      expect(result.blocks[4].text.text).toContain('👤 *No updates from you*');
    });

    it('should build admin tab with stats', () => {
      const config: HomeTab = {
        tab: 'admin',
        items: [
          { id: '1', title: 'Test', meta: { owner: 'User1', status: 'active' } },
          { id: '2', title: 'Test2', meta: { owner: 'User2', status: 'pending' } },
        ],
      };

      const result = buildHome(config);
      
      expect(result.type).toBe('home');
      expect(result.blocks[4].text.text).toContain('*Total Updates:* 2');
      expect(result.blocks[4].text.text).toContain('*Active Users:* 2');
      expect(result.blocks[4].text.text).toContain('*Pending Reviews:* 1');
    });
  });

  describe('buildCard', () => {
    it('should build a complete card with all elements', () => {
      const item: CardItem = {
        id: 'test-1',
        title: 'Test Update',
        subtitle: 'Test subtitle',
        meta: {
          owner: 'John Doe',
          date: '2025-09-22',
          status: 'active',
        },
        actions: [
          { id: 'view', text: 'View Details' },
          { id: 'edit', text: 'Edit', style: 'primary' },
        ],
      };

      const result = buildCard(item);
      
      expect(result).toHaveLength(3); // section + context + actions
      expect(result[0].type).toBe('section');
      expect(result[0].text.text).toContain('*Test Update*');
      expect(result[0].text.text).toContain('_Test subtitle_');
      expect(result[1].type).toBe('context');
      expect(result[1].elements[0].text).toContain('👤 John Doe');
      expect(result[1].elements[0].text).toContain('📅 2025-09-22');
      expect(result[1].elements[0].text).toContain('🟢 active');
      expect(result[2].type).toBe('actions');
      expect(result[2].elements).toHaveLength(2);
    });

    it('should build minimal card without optional elements', () => {
      const item: CardItem = {
        id: 'test-2',
        title: 'Minimal Update',
        meta: {},
      };

      const result = buildCard(item);
      
      expect(result).toHaveLength(1); // only section
      expect(result[0].type).toBe('section');
      expect(result[0].text.text).toBe('*Minimal Update*');
    });
  });

  describe('buildEmptyState', () => {
    it('should build empty state with CTA', () => {
      const config: EmptyStateConfig = {
        icon: '📝',
        title: 'No updates yet',
        hint: 'Create your first update to get started',
        cta: {
          id: 'create',
          text: 'Create Update',
          style: 'primary',
        },
      };

      const result = buildEmptyState(config);
      
      expect(result).toHaveLength(2); // section + actions
      expect(result[0].type).toBe('section');
      expect(result[0].text.text).toContain('📝 *No updates yet*');
      expect(result[0].text.text).toContain('Create your first update to get started');
      expect(result[1].type).toBe('actions');
      expect(result[1].elements[0].style).toBe('primary');
    });
  });

  describe('buildToggle', () => {
    it('should build collapsed toggle', () => {
      const config: ToggleConfig = {
        id: 'test-toggle',
        collapsedView: [
          { type: 'section', text: { type: 'mrkdwn', text: 'Collapsed content' } },
        ],
        expandedView: [
          { type: 'section', text: { type: 'mrkdwn', text: 'Expanded content' } },
          { type: 'section', text: { type: 'mrkdwn', text: 'More details' } },
        ],
        isExpanded: false,
      };

      const result = buildToggle(config);
      
      expect(result).toHaveLength(2); // actions + collapsed view
      expect(result[0].type).toBe('actions');
      expect(result[0].elements[0].text.text).toContain('🔽 Expand');
      expect(result[1].text.text).toBe('Collapsed content');
    });

    it('should build expanded toggle', () => {
      const config: ToggleConfig = {
        id: 'test-toggle',
        collapsedView: [
          { type: 'section', text: { type: 'mrkdwn', text: 'Collapsed content' } },
        ],
        expandedView: [
          { type: 'section', text: { type: 'mrkdwn', text: 'Expanded content' } },
          { type: 'section', text: { type: 'mrkdwn', text: 'More details' } },
        ],
        isExpanded: true,
      };

      const result = buildToggle(config);
      
      expect(result).toHaveLength(3); // actions + expanded view (2 blocks)
      expect(result[0].type).toBe('actions');
      expect(result[0].elements[0].text.text).toContain('🔼 Collapse');
      expect(result[1].text.text).toBe('Expanded content');
      expect(result[2].text.text).toBe('More details');
    });
  });
});
