import { act, render, waitFor } from '@testing-library/react';
import React from 'react';

import { useUser } from './useUser';

jest.mock('./useEnvironment', () => ({
  useEnvironment: () => ({ name: 'test', apiUrl: '/rest/v1' }),
}));

// react-testing-library v11 has no renderHook; drive the hook via a probe.
type Captured = ReturnType<typeof useUser>;
let captured: Captured;

function Probe(): React.ReactElement {
  captured = useUser();
  return React.createElement('span', { 'data-testid': 'loading' }, String(captured.loading));
}

function jsonResponse(body: unknown, status = 200): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(typeof body === 'string' ? body : JSON.stringify(body)),
  } as unknown as Response;
}

describe('useUser (auth route migration #963)', () => {
  const originalLocation = window.location;

  beforeEach(() => {
    delete (window as any).location;
    (window as any).location = { href: '' };
  });

  afterEach(() => {
    (window as any).location = originalLocation;
    jest.resetAllMocks();
  });

  it('GETs /rest/v1/auth/user with Accept: application/json (so anon gets 401, not a Google redirect)', async () => {
    const fetchMock = jest.fn().mockResolvedValueOnce(jsonResponse(null, 401));
    (global as any).fetch = fetchMock;

    const { getByTestId } = render(React.createElement(Probe));
    await waitFor(() => expect(getByTestId('loading').textContent).toBe('false'));

    expect(fetchMock).toHaveBeenCalledWith('/rest/v1/auth/user', {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
  });

  it('login() navigates to /auth/login and logout() to /auth/logout', async () => {
    (global as any).fetch = jest.fn().mockResolvedValueOnce(jsonResponse(null, 401));

    const { getByTestId } = render(React.createElement(Probe));
    await waitFor(() => expect(getByTestId('loading').textContent).toBe('false'));

    act(() => captured.login());
    expect((window as any).location.href).toBe('/rest/v1/auth/login');

    act(() => captured.logout());
    expect((window as any).location.href).toBe('/rest/v1/auth/logout');
  });
});
