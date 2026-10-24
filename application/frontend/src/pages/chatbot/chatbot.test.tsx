import { fireEvent, render, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

import { Chatbot, linkifyCitations } from './chatbot';

// The syntax highlighter ships ESM only; the thumbs tests do not render code blocks.
jest.mock('react-syntax-highlighter', () => ({ Prism: () => null }));
jest.mock('react-syntax-highlighter/dist/esm/styles/prism', () => ({ oneLight: {} }));
jest.mock('../../hooks/useEnvironment', () => ({
  useEnvironment: () => ({ name: 'test', apiUrl: '/rest/v1' }),
}));

function res(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    statusText: 'OK',
    text: () => Promise.resolve(typeof body === 'string' ? body : JSON.stringify(body)),
    json: () => Promise.resolve(body),
  });
}

function setup(answerId: string | undefined, feedbackStatus = 200) {
  const calls: { url: string; init?: any }[] = [];
  (global as any).fetch = jest.fn((url: string, init?: any) => {
    calls.push({ url: String(url), init });
    if (String(url).endsWith('/auth/user')) return res('someone');
    if (String(url).endsWith('/completion')) {
      return res({
        response: 'SAMM has 3 maturity levels per practice.',
        accurate: true,
        answer_id: answerId,
      });
    }
    if (String(url).endsWith('/answer_feedback')) return res({ rating: 'up' }, feedbackStatus);
    return res({});
  });
  const utils = render(
    <MemoryRouter>
      <Chatbot />
    </MemoryRouter>
  );
  const ask = async () => {
    fireEvent.change(utils.getByPlaceholderText(/Type your infosec question/), {
      target: { value: 'levels in SAMM?' },
    });
    fireEvent.click(utils.getByText('Ask'));
    await utils.findByText(/3 maturity levels/);
  };
  return { ...utils, calls, ask };
}

describe('Chatbot thumbs up/down', () => {
  afterEach(() => jest.clearAllMocks());

  it('sends the rating for the answer and highlights the choice', async () => {
    const { ask, findByLabelText, calls } = setup('ans-1');
    await ask();
    const up = await findByLabelText('Good answer');
    fireEvent.click(up);
    await waitFor(() => expect(up.getAttribute('aria-pressed')).toBe('true'));
    const post = calls.find((c) => c.url.endsWith('/answer_feedback'));
    expect(JSON.parse(post!.init.body)).toEqual({ answer_id: 'ans-1', rating: 'up' });
  });

  it('undoes the highlight when the server rejects the rating', async () => {
    const { ask, findByLabelText } = setup('ans-2', 500);
    await ask();
    const down = await findByLabelText('Bad answer');
    fireEvent.click(down);
    await waitFor(() => expect(down.getAttribute('aria-pressed')).toBe('false'));
  });

  it('shows no thumbs and keeps the privacy paragraph when the answer was not logged', async () => {
    const { ask, queryByLabelText, queryByText } = setup(undefined);
    await ask();
    expect(queryByLabelText('Good answer')).toBeNull();
    expect(queryByText(/Privacy & Security/)).not.toBeNull();
  });

  it('hides the "not stored" privacy paragraph once answers are stored', async () => {
    const { ask, findByText, queryByText } = setup('ans-3');
    expect(queryByText(/Privacy & Security/)).not.toBeNull();
    await ask();
    await findByText(/3 maturity levels/);
    expect(queryByText(/Privacy & Security/)).toBeNull();
  });
});

describe('linkifyCitations', () => {
  const urls = ['https://github.com/OWASP/a.md', 'https://github.com/OWASP/b.md'];

  it('turns [n] markers into links to the n-th source', () => {
    expect(linkifyCitations('Imperfect [1][2].', urls)).toBe(
      'Imperfect [[1]](https://github.com/OWASP/a.md)[[2]](https://github.com/OWASP/b.md).'
    );
  });

  it('leaves markers without a matching source, and unsafe links, alone', () => {
    expect(linkifyCitations('See [3] and [1].', ['https://x.org/a'])).toBe(
      'See [3] and [[1]](https://x.org/a).'
    );
    expect(linkifyCitations('See [1].', ['javascript:alert(1)'])).toBe('See [1].');
  });

  it('returns the text unchanged when there are no sources', () => {
    expect(linkifyCitations('Plain [1] text', undefined)).toBe('Plain [1] text');
    expect(linkifyCitations('Plain [1] text', [])).toBe('Plain [1] text');
  });
});
