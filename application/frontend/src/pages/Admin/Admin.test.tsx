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

function mockRuns() {
  return jsonRes({ runs: [{ id: 'r1', source: 'asvs', staging_status: 'pending_review' }] });
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
    expect(queryByText('Dashboard')).toBeNull();
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
        return mockRuns();
      }
      return jsonRes({});
    });
    const { getByText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Graph management'));
    await findByText('asvs');
    fireEvent.click(getByText('MyOpenCRE'));
    expect(getByText('Open MyOpenCRE').closest('a')?.getAttribute('href')).toBe('/myopencre');
  });

  it('loads agent status on the dashboard', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string) => {
      if (String(url).includes('/admin/dashboard')) {
        return jsonRes({
          running: [],
          failed: [],
          import_runs: [],
          agent: {
            enabled: true,
            writes_cre_graph: false,
            demo_path: '/chatbot',
            db_url: 'postgresql://cre:***@127.0.0.1:5432/opencre',
            db_env_key: 'DEV_DATABASE_URL',
            package_present: false,
          },
        });
      }
      return jsonRes({});
    });
    const { getByText, findByText, queryByRole } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    await findByText(/writes CRE graph: false/);
    expect(getByText(/Main DB \(DEV_DATABASE_URL\):/)).toBeTruthy();
    expect(getByText(/postgresql:\/\/cre:\*\*\*@127.0.0.1:5432\/opencre/)).toBeTruthy();
    expect(getByText('Open chat demo').closest('a')?.getAttribute('href')).toBe('/chatbot');
    expect(queryByRole('button', { name: 'OWASP agent' })).toBeNull();
    fireEvent.click(getByText('Job management and logs'));
    expect(await findByText('New')).toBeTruthy();
  });

  it('reviews links per run and loads the changeset graph', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/changeset/graph')) {
        return jsonRes({
          nodes: [{ id: 'n1', label: 'ASVS 1.1', type: 'Standard', status: 'updated' }],
          edges: [],
        });
      }
      if (u.endsWith('/links') && init?.method === 'POST') {
        return jsonRes({
          run_id: 'r1',
          links: [
            {
              op_index: 0,
              link_index: 0,
              added: { op: 'add_control', name: 'ASVS', section: '1.1' },
              linked_to: { id: '123', name: 'Auth' },
              decision: 'approved',
            },
          ],
        });
      }
      if (u.endsWith('/links')) {
        return jsonRes({
          run_id: 'r1',
          links: [
            {
              op_index: 0,
              link_index: 0,
              added: { op: 'add_control', name: 'ASVS', section: '1.1' },
              linked_to: { id: '123', name: 'Auth' },
              decision: 'pending',
            },
          ],
        });
      }
      if (u.includes('/changeset')) {
        return jsonRes({ run_id: 'r1', changeset: [{ op: 'add_control', document: {} }] });
      }
      if (u.includes('/admin/imports/runs')) {
        return mockRuns();
      }
      return jsonRes({});
    });
    const { getByText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Graph management'));
    await findByText('asvs');
    fireEvent.click(getByText('Graph'));
    expect(await findByText('ASVS 1.1')).toBeTruthy();
    fireEvent.click(getByText('Changeset'));
    expect(await findByText('Added controls and links')).toBeTruthy();
    fireEvent.click(getByText('Approve'));
    await waitFor(() =>
      expect((global as any).fetch).toHaveBeenCalledWith(
        expect.stringContaining('/links'),
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
    expect(getByText('New')).toBeTruthy();
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
      if (String(url).includes('/admin/repos.yaml')) {
        return jsonRes({ yaml: 'sources: []\n', source: 'repos.yaml:abc' });
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
      if (String(url).includes('/admin/dashboard')) {
        return jsonRes({
          running: [],
          failed: [],
          import_runs: [],
          agent: { enabled: false, writes_cre_graph: false, db_url: null },
        });
      }
      return jsonRes({});
    });
    const { findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    expect(await findByText(/Enabled: false/)).toBeTruthy();
  });

  it('shows pipeline error state', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string) => {
      if (String(url).includes('/admin/pipeline')) {
        return jsonRes({ description: 'pipeline down' }, 500);
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
        return mockRuns();
      }
      return jsonRes({});
    });
    const { getByText, findByText, findAllByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Graph management'));
    await findByText('asvs');
    fireEvent.click(getByText('Impact'));
    await waitFor(() =>
      expect((global as any).fetch).toHaveBeenCalledWith(
        expect.stringContaining('/impact'),
        expect.objectContaining({ method: 'GET' })
      )
    );
    expect(await findAllByText(/empty standard keys/)).toBeTruthy();
    fireEvent.click(getByText('Accept'));
    await waitFor(() =>
      expect((global as any).fetch).toHaveBeenCalledWith(
        expect.stringContaining('/accept'),
        expect.objectContaining({ method: 'POST' })
      )
    );
    expect(await findByText(/accept →/i)).toBeTruthy();
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

  it('surfaces a failed changeset load', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string) => {
      const u = String(url);
      if (u.includes('/changeset')) {
        return jsonRes({ description: 'run not found' }, 404);
      }
      if (u.includes('/admin/imports/runs')) {
        return mockRuns();
      }
      return jsonRes({});
    });
    const { getByText, findByText, queryByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Graph management'));
    await findByText('asvs');
    fireEvent.click(getByText('Changeset'));
    expect(await findByText(/run not found/)).toBeTruthy();
    expect(queryByText('Added controls and links')).toBeNull();
  });

  it('saves repos.yaml and expands an org from config', async () => {
    loggedIn();
    let savedBody: any;
    let expandBody: any;
    (global as any).fetch = jest.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/expand-org') && init?.method === 'POST') {
        expandBody = JSON.parse(String(init.body || '{}'));
        return jsonRes({
          yaml: 'sources:\n  - github.com/OWASP/\n',
          added: 1,
          skipped: 0,
          source_url: 'github.com/OWASP/',
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
      if (u.includes('/admin/config')) {
        return jsonRes({ config: [], restart_instructions: '' });
      }
      return jsonRes({});
    });
    const { getByText, getByLabelText, getByPlaceholderText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Config'));
    expect(await findByText('targets.yaml')).toBeTruthy();
    fireEvent.change(getByLabelText('repos.yaml'), {
      target: { value: 'repositories:\n  - id: custom\n' },
    });
    fireEvent.click(getByText('Save repos.yaml'));
    expect(await findByText(/Saved repos.yaml:savedhash12/)).toBeTruthy();
    expect(savedBody.yaml).toContain('custom');
    fireEvent.change(getByPlaceholderText('GitHub org'), { target: { value: 'OWASP' } });
    fireEvent.click(getByText('Add org'));
    expect(await findByText(/Saved source github.com\/OWASP/)).toBeTruthy();
    expect(expandBody.owner).toBe('OWASP');
  });

  it('surfaces an inaccessible GitHub source immediately', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/expand-org') && init?.method === 'POST') {
        return jsonRes({ description: 'GitHub source is not accessible: github.com/NoSuchOrgCcdd/' }, 400);
      }
      if (u.includes('/admin/repos.yaml')) {
        return jsonRes({ yaml: 'sources: []\n', source: 'repos.yaml:abc123abc123' });
      }
      if (u.includes('/admin/config')) {
        return jsonRes({ config: [], restart_instructions: '' });
      }
      return jsonRes({});
    });
    const { getByText, getByPlaceholderText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Config'));
    await findByText('targets.yaml');
    fireEvent.change(getByPlaceholderText('GitHub org'), { target: { value: 'NoSuchOrgCcdd' } });
    fireEvent.click(getByText('Add org'));
    expect(await findByText(/not accessible: github.com\/NoSuchOrgCcdd\//)).toBeTruthy();
  });

  it('starts a packaged ingest from Pipeline New', async () => {
    loggedIn();
    let startBody: any;
    (global as any).fetch = jest.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/admin/ingest/start') && init?.method === 'POST') {
        startBody = JSON.parse(String(init.body || '{}'));
        return jsonRes({ run_id: 'r-new', source: 'repos.yaml:abc', dry_run: true });
      }
      if (u.includes('/admin/pipeline')) {
        return jsonRes({
          import_runs: [],
          events: [],
          latest_strip: [{ id: 'queued', label: 'Queued', state: 'current' }],
          oie: { unconsumed: 0, recent: [], knowledge: [] },
        });
      }
      return jsonRes({});
    });
    const { getByText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Pipeline'));
    await findByText('No pipeline runs yet.');
    fireEvent.click(getByText('New'));
    fireEvent.click(getByText('Start'));
    expect(await findByText(/Started repos.yaml:abc/)).toBeTruthy();
    expect(startBody.packaged).toBe(true);
  });

  it('rejects empty drop-last and empty add-target', async () => {
    loggedIn();
    const fetchMock = jest.fn((url: string) => {
      if (String(url).includes('/admin/imports/runs')) {
        return jsonRes({ runs: [] });
      }
      if (String(url).includes('/admin/repos.yaml')) {
        return jsonRes({ yaml: 'sources: []\n', source: 'repos.yaml:abc' });
      }
      if (String(url).includes('/admin/config')) {
        return jsonRes({ config: [], restart_instructions: '' });
      }
      return jsonRes({});
    });
    (global as any).fetch = fetchMock;
    const { getByText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Graph management'));
    expect(await findByText('Drop last')).toBeTruthy();
    fireEvent.click(getByText('Drop last'));
    expect(await findByText(/source is required/)).toBeTruthy();
    fireEvent.click(getByText('Config'));
    fireEvent.click(getByText('Add target'));
    fireEvent.click(getByText('Add'));
    expect(await findByText(/owner and repo are required/)).toBeTruthy();
    const posts = fetchMock.mock.calls.filter((call: unknown[]) => {
      const init = call[1] as RequestInit | undefined;
      return init?.method === 'POST';
    });
    expect(posts).toEqual([]);
  });

  it('surfaces a failed graph load', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string) => {
      const u = String(url);
      if (u.includes('/changeset/graph')) {
        return jsonRes({ description: 'graph unavailable' }, 500);
      }
      if (u.includes('/admin/imports/runs')) {
        return mockRuns();
      }
      return jsonRes({});
    });
    const { getByText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Graph management'));
    await findByText('asvs');
    fireEvent.click(getByText('Graph'));
    expect(await findByText(/graph unavailable/)).toBeTruthy();
  });

  it('adds a target from the config lightbox', async () => {
    loggedIn();
    let addBody: any;
    let savedYaml: string | undefined;
    (global as any).fetch = jest.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/add-repo') && init?.method === 'POST') {
        addBody = JSON.parse(String(init.body || '{}'));
        return jsonRes({
          yaml: 'repositories:\n  - id: owasp-asvs\n',
          added: 'owasp-asvs',
          source: 'repos.yaml:added12ab',
        });
      }
      if (u.includes('/admin/repos.yaml') && init?.method === 'PUT') {
        savedYaml = JSON.parse(String(init.body || '{}')).yaml;
        return jsonRes({ yaml: savedYaml, source: 'repos.yaml:saved12ab', saved: true });
      }
      if (u.includes('/admin/repos.yaml')) {
        return jsonRes({ yaml: 'sources: []\n', source: 'repos.yaml:abc' });
      }
      if (u.includes('/admin/config')) {
        return jsonRes({ config: [], restart_instructions: '' });
      }
      return jsonRes({});
    });
    const { getByText, getByPlaceholderText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Config'));
    await findByText('targets.yaml');
    fireEvent.click(getByText('Add target'));
    fireEvent.change(getByPlaceholderText('OWASP'), { target: { value: 'OWASP' } });
    fireEvent.change(getByPlaceholderText('ASVS'), { target: { value: 'ASVS' } });
    fireEvent.click(getByText('Add'));
    expect(await findByText(/Added target owasp-asvs/)).toBeTruthy();
    expect(addBody.owner).toBe('OWASP');
    expect(addBody.repo).toBe('ASVS');
    expect(addBody.cron).toBe('0 2 * * *');
    expect(savedYaml).toContain('owasp-asvs');
  });

  it('starts a one-off single repository from Pipeline New', async () => {
    loggedIn();
    let startBody: any;
    (global as any).fetch = jest.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/add-repo') && init?.method === 'POST') {
        return jsonRes({ yaml: 'repositories:\n  - id: one-off\n', added: 'one-off' });
      }
      if (u.includes('/admin/ingest/start') && init?.method === 'POST') {
        startBody = JSON.parse(String(init.body || '{}'));
        return jsonRes({ run_id: 'r-one', source: 'one-off', dry_run: true });
      }
      if (u.includes('/admin/pipeline')) {
        return jsonRes({
          import_runs: [],
          events: [],
          latest_strip: [{ id: 'queued', label: 'Queued', state: 'current' }],
          oie: { unconsumed: 0, recent: [], knowledge: [] },
        });
      }
      return jsonRes({});
    });
    const { getByText, getByPlaceholderText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Pipeline'));
    await findByText('No pipeline runs yet.');
    fireEvent.click(getByText('New'));
    fireEvent.click(getByText('Single repository'));
    fireEvent.change(getByPlaceholderText('OWASP'), { target: { value: 'OWASP' } });
    fireEvent.change(getByPlaceholderText('ASVS'), { target: { value: 'ASVS' } });
    fireEvent.click(getByText('Start'));
    expect(await findByText(/Started one-off/)).toBeTruthy();
    expect(startBody.yaml).toContain('one-off');
    expect(startBody.name).toBe('owasp-asvs');
  });

  it('shows an empty graph-management links table', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string) => {
      const u = String(url);
      if (u.endsWith('/links')) {
        return jsonRes({ run_id: 'r1', links: [] });
      }
      if (u.includes('/changeset')) {
        return jsonRes({ run_id: 'r1', changeset: [] });
      }
      if (u.includes('/admin/imports/runs')) {
        return mockRuns();
      }
      return jsonRes({});
    });
    const { getByText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Graph management'));
    await findByText('asvs');
    fireEvent.click(getByText('Changeset'));
    expect(await findByText('No staged links on this run.')).toBeTruthy();
  });
});
