jest.mock('react-syntax-highlighter/dist/esm/styles/prism', () => ({
  oneLight: {},
}));

import { parseChatbotErrorMessage, renderChatMarkdown } from './chatbot';

describe('renderChatMarkdown', () => {
  it('renders markdown to sanitized html', () => {
    const html = renderChatMarkdown('**bold**');
    expect(html).toContain('<strong>bold</strong>');
  });
});

describe('parseChatbotErrorMessage', () => {
  it('returns authentication required fallback on 401 with empty body', () => {
    const msg = parseChatbotErrorMessage(401, 'Unauthorized', '');
    expect(msg).toBe('Authentication required. Please log in to access this functionality.');
  });

  it('returns authentication required fallback on 401 when body is None', () => {
    const msg = parseChatbotErrorMessage(401, 'Unauthorized', 'None');
    expect(msg).toBe('Authentication required. Please log in to access this functionality.');
  });

  it('preserves parsed JSON message on 401 when body is non-empty', () => {
    const msg = parseChatbotErrorMessage(401, 'Unauthorized', JSON.stringify({ message: 'Token expired' }));
    expect(msg).toBe('Token expired');
  });

  it('preserves parsed JSON error on 401 when body is non-empty', () => {
    const msg = parseChatbotErrorMessage(401, 'Unauthorized', JSON.stringify({ error: 'Invalid session' }));
    expect(msg).toBe('Invalid session');
  });

  it('preserves parsed HTML message on 401 when body is non-empty', () => {
    const msg = parseChatbotErrorMessage(
      401,
      'Unauthorized',
      '<html><body><p>Access Denied</p></body></html>'
    );
    expect(msg).toBe('Access Denied');
  });

  it('falls back to statusText on non-401 empty body', () => {
    const msg = parseChatbotErrorMessage(403, 'Forbidden', '');
    expect(msg).toBe('Forbidden');
  });

  it('falls back to Error status code when statusText is empty on non-401 empty body', () => {
    const msg = parseChatbotErrorMessage(500, '', '');
    expect(msg).toBe('Error 500');
  });
});
