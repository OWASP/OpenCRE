import { fireEvent, render, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

import { Chatbot } from './chatbot';

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

  it('shows no thumbs (and no storage notice) when the answer was not logged', async () => {
    const { ask, queryByLabelText, queryByText } = setup(undefined);
    await ask();
    expect(queryByLabelText('Good answer')).toBeNull();
    expect(queryByText(/stored to improve OpenCRE/)).toBeNull();
  });

  it('tells the user answers are stored when thumbs are offered', async () => {
    const { ask, findByText } = setup('ans-3');
    await ask();
    expect(await findByText(/stored\s+to improve OpenCRE/)).toBeTruthy();
  });
});
