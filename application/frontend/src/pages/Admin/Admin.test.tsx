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
    expect(queryByText('Overview')).toBeNull();
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
    expect(getByText(/Sign in to continue/)).toBeTruthy();
  });

  it('shows job schedules and saves an edited interval', async () => {
    loggedIn();
    const row = {
      job: 'owasp',
      description: 'OWASP agent sync',
      default_interval_minutes: 10,
      interval_minutes: 10,
      overridden: false,
      enabled: true,
      next_expected: '2026-10-19T12:10:00+00:00',
      last_run: { status: 'ok', started_at: '2026-10-19T12:00:00' },
    };
    const calls: { url: string; init?: any }[] = [];
    (global as any).fetch = jest.fn((url: string, init?: any) => {
      calls.push({ url: String(url), init });
      if (String(url).endsWith('/admin/schedule/owasp') && init?.method === 'PUT') {
        return jsonRes({ jobs: [{ ...row, interval_minutes: 30, overridden: true }] });
      }
      if (String(url).endsWith('/admin/schedule')) {
        return jsonRes({ jobs: [row] });
      }
      return jsonRes({});
    });
    const { getByText, findByLabelText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Schedules'));
    const input = (await findByLabelText('owasp interval minutes')) as HTMLInputElement;
    expect(input.value).toBe('10');
    fireEvent.change(input, { target: { value: '30' } });
    fireEvent.click(getByText('Save'));
    expect(await findByText('owasp schedule saved')).toBeTruthy();
    const put = calls.find((c) => c.init?.method === 'PUT');
    expect(JSON.parse(put!.init.body)).toEqual({ interval_minutes: 30, enabled: true });
  });

  it('edits project authority weights and saves only the changed ones', async () => {
    loggedIn();
    const calls: { url: string; init?: any }[] = [];
    (global as any).fetch = jest.fn((url: string, init?: any) => {
      calls.push({ url: String(url), init });
      if (String(url).endsWith('/admin/authority') && init?.method === 'PUT') {
        return jsonRes({ weights: { 'www-project-ai-exchange': 1.2 } });
      }
      if (String(url).endsWith('/admin/authority')) {
        return jsonRes({
          projects: [
            { slug: 'www-project-ai-exchange', name: 'ai exchange', weight: 1 },
            { slug: 'AISVS', name: 'aisvs', weight: 1 },
          ],
        });
      }
      return jsonRes({});
    });
    const { getByText, findByLabelText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Authority'));
    const input = (await findByLabelText('www-project-ai-exchange weight')) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '1.2' } });
    fireEvent.click(getByText(/^Save/));
    expect(await findByText(/1 project weight\(s\) saved/)).toBeTruthy();
    const put = calls.find((c) => c.init?.method === 'PUT');
    expect(JSON.parse(put!.init.body)).toEqual({ weights: { 'www-project-ai-exchange': 1.2 } });
  });

  it('lists suggested external sources and accepts with edits or rejects', async () => {
    loggedIn();
    const calls: { url: string; init?: any }[] = [];
    (global as any).fetch = jest.fn((url: string, init?: any) => {
      calls.push({ url: String(url), init });
      if (String(url).includes('/admin/external/') && init?.method === 'POST') {
        return jsonRes({ id: 'foo-conf-org', status: 'approved' });
      }
      if (String(url).endsWith('/admin/external')) {
        return jsonRes({
          external: [
            {
              id: 'foo-conf-org',
              kind: 'external_site',
              name: 'Foo Conf',
              status: 'suggested',
              score: 6.5,
              spec: {
                start_urls: ['https://foo-conf.org/'],
                found_in: [{ repo: 'OWASP/foo', file: 'README.md', link_text: 'website' }],
              },
            },
            {
              id: 'yt-bar',
              kind: 'youtube_channel',
              name: 'bar',
              status: 'suggested',
              score: 2,
              spec: { channel_id: '@bar' },
            },
            {
              id: 'appsec-eu',
              kind: 'external_site',
              name: 'AppSec EU',
              status: 'suggested',
              score: 5,
              spec: {
                start_urls: ['https://2026.appsec.eu/'],
                found_in: [{ source: 'crawl', page: 'https://owasp.org/events', link_text: 'AppSec EU' }],
              },
            },
            { id: 'done', kind: 'external_site', name: 'Done', status: 'approved', spec: {} },
          ],
        });
      }
      if (String(url).endsWith('/admin/targets')) return jsonRes({ targets: [] });
      return jsonRes({});
    });
    const { getByText, queryByTestId, findByTestId, getByLabelText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Workbench'));
    const card = await findByTestId('suggestion-foo-conf-org');
    expect(card.textContent).toContain('OWASP/foo');
    expect(card.textContent).toContain('GitHub');
    const crawled = await findByTestId('suggestion-appsec-eu');
    expect(crawled.textContent).toContain('crawl');
    expect(crawled.textContent).toContain('found on https://owasp.org/events');
    expect(card.textContent).toContain('score 6.5');
    expect(queryByTestId('suggestion-done')).toBeNull();
    fireEvent.click(card.querySelector('button')!);
    fireEvent.change(getByLabelText('max pages'), { target: { value: '40' } });
    fireEvent.change(getByLabelText('start url'), { target: { value: 'https://foo-conf.org/schedule' } });
    fireEvent.click(getByText('Confirm accept'));
    expect(await findByText(/Foo Conf: accepted/)).toBeTruthy();
    const post = calls.find((c) => c.init?.method === 'POST' && c.url.endsWith('/foo-conf-org/accept'));
    expect(JSON.parse(post!.init.body)).toMatchObject({
      start_urls: ['https://foo-conf.org/schedule'],
      max_pages: 40,
      refresh_days: 30,
      weight: 1,
    });
    const yt = await findByTestId('suggestion-yt-bar');
    fireEvent.click(yt.querySelectorAll('button')[1]);
    expect(await findByText(/bar: rejected/)).toBeTruthy();
    expect(calls.some((c) => c.url.endsWith('/yt-bar/reject'))).toBe(true);
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
    fireEvent.click(getByText('Review'));
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
          needs_attention: { staged_review: 2, failed_24h: 0, blocked: 1, ingest_errors: 0 },
          review_pulse: {
            accepted_as_is_pct: 40,
            adjusted_pct: 35,
            rejected_pct: 25,
            pending: 3,
          },
          agent: {
            enabled: true,
            writes_cre_graph: false,
            demo_path: '/chatbot',
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
    expect(getByText('Needs attention')).toBeTruthy();
    expect(getByText('Review pulse')).toBeTruthy();
    expect(getByText('40%')).toBeTruthy();
    expect(getByText('Open chat demo').closest('a')?.getAttribute('href')).toBe('/chatbot');
    expect(queryByRole('button', { name: 'OWASP agent' })).toBeNull();
    fireEvent.click(getByText('Open review'));
    expect(await findByText(/Approve, deny, or relink/)).toBeTruthy();
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
      if (u.includes('/links') && init?.method === 'POST') {
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
      if (u.includes('/links') && (!init || !init.method || init.method === 'GET')) {
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
    const { getByText, findByText, getAllByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Review'));
    await findByText('asvs');
    fireEvent.click(getByText('Graph'));
    expect(await findByText('ASVS 1.1')).toBeTruthy();
    fireEvent.click(getByText('Changeset'));
    expect(await findByText('Staged links')).toBeTruthy();
    const accepts = getAllByText('Accept');
    fireEvent.click(accepts[accepts.length - 1]);
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
      const u = String(url);
      if (u.includes('/admin/ingest/status')) {
        return jsonRes({ ingestions: [], active_count: 0, stuck_count: 0 });
      }
      if (u.includes('/admin/pipeline')) {
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

  it('renders active ingestions with config progress and ETA', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string) => {
      const u = String(url);
      if (u.includes('/admin/ingest/status')) {
        return jsonRes({
          active_count: 1,
          stuck_count: 1,
          ingestions: [
            {
              run_id: 'run-abc-123',
              source: 'owasp-asvs',
              phase: 'oie/started',
              stuck: true,
              stuck_reason: 'remaining unchanged for 12m',
              config: {
                skip_c1: true,
                max_repos: 0,
                spec: { owner: 'OWASP', repo: 'ASVS', lane: 'owasp_agent' },
              },
              progress: {
                harvest_pending: 2,
                harvest_processed: 8,
                knowledge_unconsumed: 1,
                knowledge_consumed: 4,
                rq_queued: 3,
                rq_started: 1,
                rq_failed: 0,
                remaining: 6,
              },
              eta: { note: '~40m left', eta_utc: '2026-10-13T12:00:00Z' },
            },
          ],
        });
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
    const { getByText, findByText, getAllByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Pipeline'));
    expect(await findByText('owasp-asvs')).toBeTruthy();
    expect(getByText('skip_c1')).toBeTruthy();
    expect(getByText(/~40m left/)).toBeTruthy();
    expect(getAllByText('Stuck').length).toBeGreaterThan(0);
    expect(getByText(/remaining unchanged/)).toBeTruthy();
  });

  it('shows config restart instructions', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string) => {
      const u = String(url);
      if (u.includes('/admin/config/diff')) {
        return jsonRes({
          diff: [
            {
              key: 'CRE_ALLOW_IMPORT',
              status: 'match',
              process: '1',
              dotenv: '1',
            },
          ],
        });
      }
      if (u.includes('/admin/config')) {
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
      if (u.includes('/admin/repos.yaml')) {
        return jsonRes({ yaml: 'sources: []\n', source: 'repos.yaml:abc' });
      }
      if (String(url).includes('/rest/v1/api-keys')) {
        return jsonRes({ keys: [] });
      }
      return jsonRes({});
    });
    const { getByText, findByText, getAllByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Config values'));
    expect(await findByText('Environment vs .env')).toBeTruthy();
    expect(await findByText('HTTP cannot change process env.')).toBeTruthy();
    expect(getAllByText('CRE_ALLOW_IMPORT').length).toBeGreaterThan(0);
  });

  it('mints an API key from Config Manage API keys dialog', async () => {
    loggedIn();
    let keys: any[] = [];
    (global as any).fetch = jest.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/rest/v1/api-keys') && init?.method === 'POST') {
        const body = JSON.parse(String(init.body || '{}'));
        keys = [
          {
            jti: 'abcd1234-eeee-ffff-0000-111122223333',
            name: body.name || 'ci',
            expires_at: '2026-12-01T00:00:00Z',
            revoked_at: null,
            created_at: '2026-10-11T00:00:00Z',
            last_used_at: null,
          },
        ];
        return jsonRes(
          {
            token: 'eyJhbGciOiJIUzI1NiJ9.test-token',
            jti: keys[0].jti,
            name: keys[0].name,
            expires_at: keys[0].expires_at,
          },
          201
        );
      }
      if (u.includes('/rest/v1/api-keys')) {
        return jsonRes({ keys });
      }
      if (u.includes('/admin/config')) {
        return jsonRes({ config: [], restart_instructions: '' });
      }
      if (u.includes('/admin/repos.yaml')) {
        return jsonRes({ yaml: 'sources: []\n', source: 'repos.yaml:abc' });
      }
      return jsonRes({});
    });
    const { getByText, getByLabelText, findByText, findByLabelText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Config values'));
    fireEvent.click(await findByText('Manage API keys'));
    expect(await findByText('No API keys yet.')).toBeTruthy();
    fireEvent.change(getByLabelText('API key name'), { target: { value: 'staging-ci' } });
    fireEvent.click(getByText('Mint API key'));
    expect(await findByText('API key minted')).toBeTruthy();
    const tokenEl = await findByLabelText('minted API token');
    expect(tokenEl.textContent).toContain('eyJhbGciOiJIUzI1NiJ9.test-token');
    expect(await findByText('staging-ci')).toBeTruthy();
    expect(await findByText('2026-12-01T00:00:00Z')).toBeTruthy();
    expect((global as any).fetch).toHaveBeenCalledWith(
      '/rest/v1/api-keys',
      expect.objectContaining({ method: 'POST', credentials: 'include' })
    );
  });

  it('toggles Module C.1 graph filing from Config', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/admin/config') && init?.method === 'PUT') {
        return jsonRes({
          applied: ['OIE_GRAPH_FILING_ENABLED'],
          rejected: [],
          config: [
            {
              key: 'OIE_GRAPH_FILING_ENABLED',
              value: '1',
              writable: true,
              help_text: 'Module C.1',
              help_url: '#',
              secret: false,
            },
          ],
        });
      }
      if (u.includes('/admin/config')) {
        return jsonRes({
          writable: true,
          config: [
            {
              key: 'OIE_GRAPH_FILING_ENABLED',
              value: '0',
              writable: true,
              help_text: 'Module C.1',
              help_url: '#',
              secret: false,
            },
          ],
        });
      }
      if (u.includes('/admin/repos.yaml')) {
        return jsonRes({ yaml: 'sources: []\n', source: 'repos.yaml:abc' });
      }
      if (u.includes('/admin/agent/status')) {
        return jsonRes({ enabled: true, db_url: null, counts: {} });
      }
      return jsonRes({});
    });
    const { getByText, findByText, findByRole } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Config values'));
    expect(await findByText(/C\.1 auto-file high-confidence links \(off/)).toBeTruthy();
    const toggle = await findByRole('checkbox');
    fireEvent.click(toggle);
    await waitFor(() =>
      expect((global as any).fetch).toHaveBeenCalledWith(
        expect.stringContaining('/admin/config'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ updates: { OIE_GRAPH_FILING_ENABLED: '1' } }),
        })
      )
    );
    expect(await findByText(/C\.1 auto-filing on/)).toBeTruthy();
  });

  it('runs golden-set harvest and OWASP agent sync from Config', async () => {
    loggedIn();
    (global as any).fetch = jest.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/admin/config') && (!init || init.method === 'GET' || !init.method)) {
        return jsonRes({
          restart_instructions: 'HTTP cannot change process env.',
          config: [{ key: 'OIE_GRAPH_FILING_ENABLED', value: '0', writable: true }],
        });
      }
      if (u.includes('/admin/repos.yaml')) {
        return jsonRes({ yaml: 'sources: []\n', source: 'repos.yaml:abc' });
      }
      if (u.includes('/admin/agent/status')) {
        return jsonRes({
          enabled: true,
          db_url: 'postgresql://cre:***@127.0.0.1:5432/cre',
          counts: { projects: 1 },
          last_sync: '2026-01-01T00:00:00+00:00',
        });
      }
      if (u.includes('/admin/upstream-sync-and-ingest')) {
        return jsonRes({
          source: 'repos.yaml:deadbeef',
          async: true,
          run_id: 'u1',
          upstream_sync: true,
        });
      }
      if (u.includes('/admin/ingest/start')) {
        return jsonRes({ source: 'repos.yaml:deadbeef', async: true, run_id: 'g1' });
      }
      if (u.includes('/admin/agent/sync')) {
        return jsonRes({
          run_id: 'a1b2c3d4-eeee',
          async: true,
          skip_nest: true,
          source: 'owasp-agent-sync',
        });
      }
      return jsonRes({});
    });
    const { getByText, findByText } = render(
      <MemoryRouter>
        <Admin />
      </MemoryRouter>
    );
    fireEvent.click(getByText('Config values'));
    expect(await findByText(/End-to-end bootstrap/)).toBeTruthy();
    fireEvent.click(getByText(/^Import upstream CRE \+ harvest$/));
    await waitFor(() =>
      expect((global as any).fetch).toHaveBeenCalledWith(
        expect.stringContaining('/admin/upstream-sync-and-ingest'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ packaged: true, max_repos: 50 }),
        })
      )
    );
    expect(await findByText(/Upstream CRE sync \+ harvest started/)).toBeTruthy();
    fireEvent.click(getByText('Run golden-set harvest'));
    await waitFor(() =>
      expect((global as any).fetch).toHaveBeenCalledWith(
        expect.stringContaining('/admin/ingest/start'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ packaged: true, max_repos: 50 }),
        })
      )
    );
    expect(await findByText(/Golden-set harvest started/)).toBeTruthy();
    fireEvent.click(getByText('Sync OWASP agent'));
    await waitFor(() =>
      expect((global as any).fetch).toHaveBeenCalledWith(
        expect.stringContaining('/admin/agent/sync'),
        expect.objectContaining({ method: 'POST' })
      )
    );
    expect(await findByText(/OWASP agent sync started/)).toBeTruthy();
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
      const u = String(url);
      if (u.includes('/admin/ingest/status')) {
        return jsonRes({ ingestions: [], active_count: 0, stuck_count: 0 });
      }
      if (u.includes('/admin/pipeline')) {
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
    fireEvent.click(getByText('Review'));
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
    fireEvent.click(getByText('Review'));
    await findByText('asvs');
    fireEvent.click(getByText('Changeset'));
    expect(await findByText(/run not found/)).toBeTruthy();
    expect(queryByText('Staged links')).toBeNull();
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
    fireEvent.click(getByText('Config values'));
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
    fireEvent.click(getByText('Config values'));
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
      if (u.includes('/admin/ingest/status')) {
        return jsonRes({ ingestions: [], active_count: 0, stuck_count: 0 });
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
    fireEvent.click(getByText('Review'));
    expect(await findByText('Drop last')).toBeTruthy();
    fireEvent.click(getByText('Drop last'));
    expect(await findByText(/source is required/)).toBeTruthy();
    fireEvent.click(getByText('Config values'));
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
    fireEvent.click(getByText('Review'));
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
    fireEvent.click(getByText('Config values'));
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
      if (u.includes('/admin/ingest/status')) {
        return jsonRes({ ingestions: [], active_count: 0, stuck_count: 0 });
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
      if (u.includes('/links')) {
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
    fireEvent.click(getByText('Review'));
    await findByText('asvs');
    fireEvent.click(getByText('Changeset'));
    expect(await findByText('No staged links on this run.')).toBeTruthy();
  });
});
