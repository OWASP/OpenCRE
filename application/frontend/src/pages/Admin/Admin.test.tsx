import { fireEvent, render, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

import { useUser } from '../../hooks/useUser';
import { Admin } from './Admin';

jest.mock('../../hooks/useEnvironment', () => ({
  useEnvironment: () => ({ name: 'test', apiUrl: '/rest/v1' }),
}));
jest.mock('../../hooks/useUser');

const mockUser = useUser as jest.Mock;

function jsonRes(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    statusText: 'OK',
    text: () => Promise.resolve(JSON.stringify(body)),
    json: () => Promise.resolve(body),
  });
}

describe('Admin', () => {
  afterEach(() => jest.clearAllMocks());

  it('asks anonymous users to log in', () => {
    mockUser.mockReturnValue({
      user: null,
      isLoggedIn: false,
      loading: false,
      login: jest.fn(),
      logout: jest.fn(),
    });
    const { getByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    expect(getByText('Sign in to use the admin showcase.')).toBeTruthy();
  });

  it('loads import runs and links to MyOpenCRE', async () => {
    mockUser.mockReturnValue({
      user: 'u',
      isLoggedIn: true,
      loading: false,
      login: jest.fn(),
      logout: jest.fn(),
    });
    (global as any).fetch = jest.fn((url: string) => {
      if (String(url).includes('/admin/imports/runs')) {
        return jsonRes({ runs: [{ id: 'r1', source: 'asvs', staging_status: 'pending_review' }] });
      }
      return jsonRes({});
    });
    const { getByText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    await findByText('asvs');
    fireEvent.click(getByText('MyOpenCRE'));
    expect(getByText('Open MyOpenCRE').closest('a')?.getAttribute('href')).toBe('/myopencre');
  });

  it('loads agent status on the agent tab', async () => {
    mockUser.mockReturnValue({
      user: 'u',
      isLoggedIn: true,
      loading: false,
      login: jest.fn(),
      logout: jest.fn(),
    });
    (global as any).fetch = jest.fn((url: string) => {
      if (String(url).includes('/admin/agent/status')) {
        return jsonRes({
          enabled: true,
          writes_cre_graph: false,
          demo_path: '/chatbot',
          help_url: 'https://example.test',
          counts: { chapters: 2 },
        });
      }
      if (String(url).includes('/admin/imports/runs')) {
        return jsonRes({ runs: [] });
      }
      return jsonRes({});
    });
    const { getByText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('OWASP agent'));
    await findByText(/writes CRE graph: false/);
    expect(getByText('Open chat demo').closest('a')?.getAttribute('href')).toBe('/chatbot');
  });
});
