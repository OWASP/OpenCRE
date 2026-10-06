import { fireEvent, render, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

import { useCapabilities } from '../../hooks/useCapabilities';
import { useUser } from '../../hooks/useUser';
import { Admin } from './Admin';

jest.mock('../../hooks/useEnvironment', () => ({
  useEnvironment: () => ({ name: 'test', apiUrl: '/rest/v1' }),
}));
jest.mock('../../hooks/useUser');
jest.mock('../../hooks/useCapabilities');

const mockUser = useUser as jest.Mock;
const mockCaps = useCapabilities as jest.Mock;

function jsonRes(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    statusText: 'OK',
    text: () => Promise.resolve(JSON.stringify(body)),
    json: () => Promise.resolve(body),
  });
}

function loggedIn() {
  mockUser.mockReturnValue({
    user: 'u',
    isLoggedIn: true,
    loading: false,
    login: jest.fn(),
    logout: jest.fn(),
  });
  mockCaps.mockReturnValue({
    capabilities: { myopencre: true, login: true, admin: true },
    loading: false,
  });
}

describe('Admin', () => {
  beforeEach(() => {
    mockCaps.mockReturnValue({
      capabilities: { myopencre: false, login: true, admin: false },
      loading: false,
    });
  });

  afterEach(() => jest.clearAllMocks());

  it('hides admin tabs when import capability is off', () => {
    loggedIn();
    mockCaps.mockReturnValue({
      capabilities: { myopencre: true, login: true, admin: false },
      loading: false,
    });
    const { getByText, queryByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    expect(getByText(/CRE_ALLOW_IMPORT/)).toBeTruthy();
    expect(queryByText('Import review')).toBeNull();
  });

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
    expect(getByText('Sign in to continue.')).toBeTruthy();
  });

  it('loads import runs and links to MyOpenCRE', async () => {
    loggedIn();
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
    loggedIn();
    (global as any).fetch = jest.fn((url: string) => {
      if (String(url).includes('/admin/agent/status')) {
        return jsonRes({
          enabled: true,
          writes_cre_graph: false,
          demo_path: '/chatbot',
          help_url: 'https://example.test',
          counts: { chapters: 2 },
          db_url: 'postgresql://cre:***@127.0.0.1:5432/owasp_agent',
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
    expect(getByText(/DB URL:/)).toBeTruthy();
    expect(getByText(/postgresql:\/\/cre:\*\*\*@127.0.0.1:5432\/owasp_agent/)).toBeTruthy();
    expect(getByText('Open chat demo').closest('a')?.getAttribute('href')).toBe('/chatbot');
  });

  it('loads changeset graph and mapping editor', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/changeset/graph')) {
        return jsonRes({
          nodes: [{ id: 'n1', label: 'ASVS 1.1', type: 'Standard', status: 'updated' }],
          edges: [],
        });
      }
      if (u.endsWith('/mapping') && init?.method === 'POST') {
        return jsonRes({
          run_id: 'r1',
          op_index: 0,
          field: 'after',
          after: { description: 'new' },
          changeset: [{ op: 'modify_control', after: { description: 'new' } }],
        });
      }
      if (u.includes('/changeset')) {
        return jsonRes({
          run_id: 'r1',
          changeset: [{ op: 'modify_control', after: { description: 'old' } }],
        });
      }
      if (u.includes('/admin/imports/runs')) {
        return jsonRes({ runs: [{ id: 'r1', source: 'asvs', staging_status: 'pending_review' }] });
      }
      return jsonRes({});
    });
    const { getByText, findByText, getByDisplayValue } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    await findByText('asvs');
    fireEvent.click(getByText('Graph'));
    expect(await findByText('ASVS 1.1')).toBeTruthy();
    fireEvent.click(getByText('Changeset'));
    expect(await findByText('Edit mapping')).toBeTruthy();
    fireEvent.change(getByDisplayValue(/old/), { target: { value: '{"description":"new"}' } });
    fireEvent.click(getByText('Save mapping'));
    await waitFor(() =>
      expect((global as any).fetch).toHaveBeenCalledWith(
        expect.stringContaining('/mapping'),
        expect.objectContaining({ method: 'POST' })
      )
    );
  });

  it('shows empty pipeline state', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string) => {
      if (String(url).includes('/admin/pipeline')) {
        return jsonRes({
          import_runs: [],
          events: [],
          latest_strip: [
            { id: 'queued', label: 'Queued', state: 'current' },
            { id: 'pending_review', label: 'Review', state: 'idle' },
          ],
          oie: { unconsumed: 0, recent: [], knowledge: [] },
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
    fireEvent.click(getByText('Pipeline'));
    expect(await findByText('No pipeline runs yet.')).toBeTruthy();
    expect(getByText('Queued')).toBeTruthy();
  });

  it('shows config restart instructions', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string) => {
      if (String(url).includes('/admin/config')) {
        return jsonRes({
          writable: false,
          restart_instructions: 'HTTP cannot change process env.',
          config: [
            {
              key: 'CRE_ALLOW_IMPORT',
              value: '1',
              help_text: 'kill',
              help_url: 'https://example.test',
              secret: false,
            },
          ],
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
    fireEvent.click(getByText('Config'));
    expect(await findByText('HTTP cannot change process env.')).toBeTruthy();
    expect(getByText('CRE_ALLOW_IMPORT')).toBeTruthy();
  });

  it('shows agent disabled when the flag is off', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string) => {
      if (String(url).includes('/admin/agent/status')) {
        return jsonRes({
          enabled: false,
          writes_cre_graph: false,
          demo_path: '/chatbot',
          help_url: 'https://example.test',
          db_url: null,
          counts: null,
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
    expect(await findByText(/Enabled: false/)).toBeTruthy();
  });

  it('shows pipeline error state', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string) => {
      if (String(url).includes('/admin/pipeline')) {
        return jsonRes({ description: 'pipeline down' }, 500);
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
    fireEvent.click(getByText('Pipeline'));
    expect(await findByText(/pipeline down/)).toBeTruthy();
  });

  it('accepts and discards a staged run', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.endsWith('/accept') || u.endsWith('/discard') || u.includes('apply?dry_run')) {
        return jsonRes({ run_id: 'r1', staging_status: 'ok' });
      }
      if (u.includes('/impact')) {
        return jsonRes({
          run_id: 'r1',
          operation_count: 1,
          impacted_standard_names: [],
          impacted_cre_external_ids: [],
          warnings: ['Skipped 1 operation(s) with empty standard keys'],
        });
      }
      if (u.includes('/admin/imports/runs')) {
        return jsonRes({ runs: [{ id: 'r1', source: 'asvs', staging_status: 'pending_review' }] });
      }
      return jsonRes({});
    });
    const { getByText, findByText, findAllByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    await findByText('asvs');
    fireEvent.click(getByText('Impact'));
    await waitFor(() =>
      expect((global as any).fetch).toHaveBeenCalledWith(
        expect.stringContaining('/impact'),
        expect.objectContaining({ method: 'GET' })
      )
    );
    expect(await findAllByText(/empty standard keys/)).toBeTruthy();
    fireEvent.click(getByText('Discard'));
    await waitFor(() =>
      expect((global as any).fetch).toHaveBeenCalledWith(
        expect.stringContaining('/discard'),
        expect.objectContaining({ method: 'POST' })
      )
    );
    fireEvent.click(getByText('Dry-run'));
    await waitFor(() =>
      expect((global as any).fetch).toHaveBeenCalledWith(
        expect.stringContaining('apply?dry_run=1'),
        expect.objectContaining({ method: 'POST' })
      )
    );
  });

  it('surfaces a failed target delete', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/admin/targets/') && init?.method === 'DELETE') {
        return jsonRes({ description: 'target not found' }, 404);
      }
      if (u.includes('/admin/targets')) {
        return jsonRes({ targets: [{ id: 'asvs-src', kind: 'import_source' }] });
      }
      if (u.includes('/admin/imports/runs')) {
        return jsonRes({ runs: [] });
      }
      return jsonRes({});
    });
    const { getByText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Targets'));
    await findByText('asvs-src');
    fireEvent.click(getByText('Remove'));
    expect(await findByText(/target not found/)).toBeTruthy();
  });

  it('surfaces a failed changeset load', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string) => {
      const u = String(url);
      if (u.includes('/changeset')) {
        return jsonRes({ description: 'run not found' }, 404);
      }
      if (u.includes('/admin/imports/runs')) {
        return jsonRes({ runs: [{ id: 'r1', source: 'asvs', staging_status: 'pending_review' }] });
      }
      return jsonRes({});
    });
    const { getByText, findByText, queryByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    await findByText('asvs');
    fireEvent.click(getByText('Changeset'));
    expect(await findByText(/run not found/)).toBeTruthy();
    expect(queryByText('Edit mapping')).toBeNull();
  });

  it('saves repos.yaml, expands an org, and starts a named one-off', async () => {
    loggedIn();
    let savedBody: any;
    let expandBody: any;
    let startBody: any;
    (global as any).fetch = jest.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/expand-org') && init?.method === 'POST') {
        expandBody = JSON.parse(String(init.body || '{}'));
        return jsonRes({
          yaml: 'repositories:\n  - id: owasp-juice\n',
          added: 1,
          skipped: 2,
          source: 'repos.yaml:newhash12ab',
        });
      }
      if (u.includes('/admin/repos.yaml') && init?.method === 'PUT') {
        savedBody = JSON.parse(String(init.body || '{}'));
        return jsonRes({
          yaml: savedBody.yaml,
          source: 'repos.yaml:savedhash12',
          saved: true,
        });
      }
      if (u.includes('/admin/repos.yaml')) {
        return jsonRes({
          yaml: 'repositories:\n  - id: owasp-asvs\n',
          source: 'repos.yaml:abc123abc123',
        });
      }
      if (u.includes('/admin/ingest/start') && init?.method === 'POST') {
        startBody = JSON.parse(String(init.body || '{}'));
        return jsonRes({
          run_id: 'r-yaml',
          source: startBody.name || 'repos.yaml:deadbeefdead',
          dry_run: true,
        });
      }
      if (u.includes('/admin/targets')) {
        return jsonRes({ targets: [] });
      }
      if (u.includes('/admin/imports/runs')) {
        return jsonRes({ runs: [] });
      }
      return jsonRes({});
    });
    const { getByText, getByLabelText, getByPlaceholderText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Targets'));
    expect(await findByText('repos.yaml')).toBeTruthy();
    fireEvent.change(getByLabelText('repos.yaml'), {
      target: { value: 'repositories:\n  - id: custom\n' },
    });
    fireEvent.click(getByText('Save repos.yaml'));
    expect(await findByText(/Saved repos.yaml:savedhash12/)).toBeTruthy();
    expect(savedBody.yaml).toContain('custom');
    fireEvent.change(getByPlaceholderText('GitHub org'), { target: { value: 'OWASP' } });
    fireEvent.click(getByText('Add org'));
    expect(await findByText(/Added 1 repos from OWASP/)).toBeTruthy();
    expect(expandBody.owner).toBe('OWASP');
    fireEvent.change(getByPlaceholderText('optional source name'), {
      target: { value: 'nightly-asvs' },
    });
    fireEvent.click(getByText('Start one-off'));
    expect(await findByText(/Started import source nightly-asvs/)).toBeTruthy();
    expect(startBody.name).toBe('nightly-asvs');
    expect(startBody.yaml).toContain('owasp-juice');
  });

  it('surfaces a failed ingest start', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/admin/ingest/start') && init?.method === 'POST') {
        return jsonRes({ description: 'target is disabled' }, 400);
      }
      if (u.includes('/admin/targets')) {
        return jsonRes({ targets: [{ id: 'off-src', kind: 'import_source' }] });
      }
      if (u.includes('/admin/imports/runs')) {
        return jsonRes({ runs: [] });
      }
      return jsonRes({});
    });
    const { getByText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Targets'));
    await findByText('off-src');
    fireEvent.click(getByText('Start now'));
    expect(await findByText(/target is disabled/)).toBeTruthy();
  });

  it('rejects blank target add and empty drop-last', async () => {
    loggedIn();
    const fetchMock = jest.fn((url: string) => {
      const u = String(url);
      if (u.includes('/admin/targets')) {
        return jsonRes({ targets: [] });
      }
      if (u.includes('/admin/imports/runs')) {
        return jsonRes({ runs: [] });
      }
      return jsonRes({});
    });
    (global as any).fetch = fetchMock;
    const { getByText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    expect(await findByText('Drop last')).toBeTruthy();
    fireEvent.click(getByText('Drop last'));
    expect(await findByText(/source is required/)).toBeTruthy();
    fireEvent.click(getByText('Targets'));
    fireEvent.click(getByText('Add'));
    expect(await findByText(/id and kind are required/)).toBeTruthy();
    const posts = fetchMock.mock.calls.filter((call: unknown[]) => {
      const init = call[1] as RequestInit | undefined;
      return init?.method === 'POST';
    });
    expect(posts).toEqual([]);
  });

  it('surfaces invalid mapping JSON', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string) => {
      const u = String(url);
      if (u.includes('/changeset')) {
        return jsonRes({
          run_id: 'r1',
          changeset: [{ op: 'modify_control', after: { description: 'old' } }],
        });
      }
      if (u.includes('/admin/imports/runs')) {
        return jsonRes({ runs: [{ id: 'r1', source: 'asvs', staging_status: 'pending_review' }] });
      }
      return jsonRes({});
    });
    const { getByText, findByText, getByDisplayValue } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    await findByText('asvs');
    fireEvent.click(getByText('Changeset'));
    expect(await findByText('Edit mapping')).toBeTruthy();
    fireEvent.change(getByDisplayValue(/old/), { target: { value: '{not json' } });
    fireEvent.click(getByText('Save mapping'));
    expect(await findByText(/Mapping JSON is invalid/)).toBeTruthy();
  });

  it('surfaces a failed graph load', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string) => {
      const u = String(url);
      if (u.includes('/changeset/graph')) {
        return jsonRes({ description: 'graph unavailable' }, 500);
      }
      if (u.includes('/admin/imports/runs')) {
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
    fireEvent.click(getByText('Graph'));
    expect(await findByText(/graph unavailable/)).toBeTruthy();
  });
});
