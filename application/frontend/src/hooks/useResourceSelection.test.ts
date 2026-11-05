import { act, render, waitFor } from '@testing-library/react';
import React from 'react';

import { useResourceSelection } from './useResourceSelection';

jest.mock('./useEnvironment', () => ({
  useEnvironment: () => ({ name: 'test', apiUrl: '/rest/v1' }),
}));

// Render the hook through a tiny probe component (react-testing-library v11 has
// no renderHook) that exposes state to the DOM and a button to trigger save.
type Captured = ReturnType<typeof useResourceSelection>;
let captured: Captured;

function Probe(): React.ReactElement {
  captured = useResourceSelection();
  return React.createElement(
    'div',
    null,
    React.createElement('span', { 'data-testid': 'loading' }, String(captured.loading)),
    React.createElement('span', { 'data-testid': 'selected' }, captured.selected.join(',')),
    React.createElement('span', { 'data-testid': 'error' }, captured.error ?? '')
  );
}

function jsonResponse(body: unknown, status = 200): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  } as unknown as Response;
}

describe('useResourceSelection', () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  it('loads the current selection on mount', async () => {
    const fetchMock = jest.fn().mockResolvedValueOnce(jsonResponse({ selected: ['ASVS', 'CWE'] }));
    (global as any).fetch = fetchMock;

    const { getByTestId } = render(React.createElement(Probe));

    await waitFor(() => expect(getByTestId('loading').textContent).toBe('false'));
    expect(fetchMock).toHaveBeenCalledWith('/rest/v1/user/resources', {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    expect(getByTestId('selected').textContent).toBe('ASVS,CWE');
  });

  it('treats 401 as anonymous / not-available (empty selection, no error)', async () => {
    (global as any).fetch = jest.fn().mockResolvedValueOnce(jsonResponse(null, 401));

    const { getByTestId } = render(React.createElement(Probe));

    await waitFor(() => expect(getByTestId('loading').textContent).toBe('false'));
    expect(getByTestId('selected').textContent).toBe('');
    expect(getByTestId('error').textContent).toBe('');
    expect(captured.loadError).toBe(false); // 401 is not a load failure
  });

  it('flags loadError=true when the initial load fails (non-401)', async () => {
    (global as any).fetch = jest.fn().mockResolvedValueOnce(jsonResponse(null, 500));

    const { getByTestId } = render(React.createElement(Probe));

    await waitFor(() => expect(getByTestId('loading').textContent).toBe('false'));
    expect(captured.loadError).toBe(true);
    expect(getByTestId('error').textContent).toBe('Could not load your saved standards.');
  });

  it('flags loadError=true on a 200 with a malformed body (no selected[])', async () => {
    (global as any).fetch = jest.fn().mockResolvedValueOnce(jsonResponse({ nope: true }, 200));

    const { getByTestId } = render(React.createElement(Probe));

    await waitFor(() => expect(getByTestId('loading').textContent).toBe('false'));
    expect(captured.loadError).toBe(true);
    expect(getByTestId('selected').textContent).toBe(''); // persisted data untouched
  });

  it('save() PUTs the selection with the right headers/body and reflects the stored list', async () => {
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce(jsonResponse({ selected: [] })) // initial GET
      .mockResolvedValueOnce(jsonResponse({ selected: ['ASVS', 'CWE'] })); // PUT echo
    (global as any).fetch = fetchMock;

    const { getByTestId } = render(React.createElement(Probe));
    await waitFor(() => expect(getByTestId('loading').textContent).toBe('false'));

    let returned: string[] | null = null;
    await act(async () => {
      returned = await captured.save(['ASVS', 'CWE']);
    });

    expect(fetchMock).toHaveBeenLastCalledWith('/rest/v1/user/resources', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ selected: ['ASVS', 'CWE'] }),
    });
    expect(returned).toEqual(['ASVS', 'CWE']);
    expect(getByTestId('selected').textContent).toBe('ASVS,CWE');
  });
});
