import './Admin.scss';

import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Checkbox, Form, Message, Modal, Header as SUIHeader, Table } from 'semantic-ui-react';

import { useCapabilities, useEnvironment } from '../../hooks';
import { useUser } from '../../hooks/useUser';

type Tab =
  | 'dashboard'
  | 'config'
  | 'pipeline'
  | 'oie'
  | 'schedule'
  | 'authority'
  | 'graph'
  | 'workbench'
  | 'myopencre'
  | 'profile';

const TAB_META: Record<Tab, { label: string; sub: string }> = {
  dashboard: { label: 'Overview', sub: 'Queue health, needs-attention, review pulse.' },
  config: { label: 'Config values', sub: 'Process env vs .env — admin only.' },
  pipeline: { label: 'Pipeline', sub: 'Jobs, stage logs, ingest.' },
  oie: { label: 'OIE queue', sub: 'RQ / OIE worker status.' },
  authority: {
    label: 'Authority',
    sub: 'Feature or soften projects. 1 = neutral; above 1 = always list the closest passage among the references; below 1 = rank lower; 0 = hidden.',
  },
  schedule: { label: 'Schedules', sub: 'How often the ingestion jobs run — change or switch off.' },
  graph: { label: 'Review', sub: 'Staged links — expand section text, accept/reject.' },
  workbench: { label: 'Workbench', sub: 'Accepted targets and re-ingest.' },
  myopencre: { label: 'MyOpenCRE', sub: 'Personal CRE workspace (admin shortcut).' },
  profile: { label: 'Profile', sub: 'Operator account — admin session required.' },
};

type RepoForm = {
  id: string;
  owner: string;
  repo: string;
  branch: string;
  include: string;
  exclude: string;
  strategy: string;
  max_tokens: string;
  overlap_tokens: string;
  mode: string;
  interval_minutes: string;
  cron: string;
};

function emptyRepo(): RepoForm {
  return {
    id: '',
    owner: '',
    repo: '',
    branch: 'main',
    include: '**/*.md',
    exclude: '',
    strategy: 'markdown_heading',
    max_tokens: '1200',
    overlap_tokens: '100',
    mode: 'incremental',
    interval_minutes: '60',
    cron: '0 2 * * *',
  };
}

function repoSpec(form: RepoForm) {
  return {
    id: form.id.trim() || `${form.owner.trim()}-${form.repo.trim()}`.toLowerCase(),
    owner: form.owner.trim(),
    repo: form.repo.trim(),
    branch: form.branch.trim() || 'main',
    include: form.include,
    exclude: form.exclude,
    strategy: form.strategy,
    max_tokens: Number(form.max_tokens),
    overlap_tokens: Number(form.overlap_tokens),
    mode: form.mode,
    interval_minutes: Number(form.interval_minutes),
    cron: form.cron.trim(),
  };
}

function adminOrigin(apiUrl: string): string {
  if (apiUrl.startsWith('http')) {
    return apiUrl.replace(/\/rest\/v1\/?$/, '');
  }
  return '';
}

async function readJson(res: Response) {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    // Flask HTML aborts (legacy) — surface a short line, not the whole page.
    const plain = text
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    const clipped = plain.slice(0, 240);
    return { description: clipped || res.statusText, error: clipped || res.statusText };
  }
}

function apiError(body: any, res: Response): string {
  return body?.description || body?.error || res.statusText || 'Request failed';
}

/** Session CSRF from GET /admin/config (see web_main.admin_imports_enabled_required). */
let _adminCsrf = '';

function setAdminCsrf(token: string) {
  _adminCsrf = (token || '').trim();
}

function mutHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return {
    Accept: 'application/json',
    ...(_adminCsrf ? { 'X-CSRF-Token': _adminCsrf } : {}),
    ...extra,
  };
}

export const Admin = () => {
  const { apiUrl } = useEnvironment();
  const { isLoggedIn, loading, login, user } = useUser();
  const { capabilities, loading: capsLoading } = useCapabilities();
  const [tab, setTab] = useState<Tab>('dashboard');
  const origin = adminOrigin(apiUrl);

  useEffect(() => {
    if (!origin || !isLoggedIn || !capabilities?.admin) return;
    let cancelled = false;
    fetch(`${origin}/admin/config`)
      .then(async (res) => {
        const body = await readJson(res);
        if (!cancelled && typeof body.csrf_token === 'string') {
          setAdminCsrf(body.csrf_token);
        }
      })
      .catch(() => {
        /* ConfigTab will retry; mutations fail closed without token. */
      });
    return () => {
      cancelled = true;
    };
  }, [origin, isLoggedIn, capabilities?.admin]);

  if (loading || capsLoading) {
    return (
      <div className="admin-page">
        <SUIHeader as="h1">Admin</SUIHeader>
        <p>Loading…</p>
      </div>
    );
  }

  if (!isLoggedIn) {
    return (
      <div className="admin-page">
        <SUIHeader as="h1">Admin</SUIHeader>
        <p>Sign in to continue. Admin APIs require login.</p>
        <Button primary onClick={login}>
          Login
        </Button>
      </div>
    );
  }

  if (!capabilities?.admin) {
    return (
      <div className="admin-page">
        <SUIHeader as="h1">Admin</SUIHeader>
        <p>Admin APIs are off. Set CRE_ALLOW_IMPORT and restart the process.</p>
      </div>
    );
  }

  const meta = TAB_META[tab];
  const nav: { id: Tab; label: string; group: string }[] = [
    { id: 'dashboard', label: 'Overview', group: 'Ops' },
    { id: 'config', label: 'Config values', group: 'Ops' },
    { id: 'pipeline', label: 'Pipeline', group: 'Ops' },
    { id: 'oie', label: 'OIE queue', group: 'Ops' },
    { id: 'schedule', label: 'Schedules', group: 'Ops' },
    { id: 'authority', label: 'Authority', group: 'Ops' },
    { id: 'graph', label: 'Review', group: 'Ops' },
    { id: 'workbench', label: 'Workbench', group: 'Ops' },
    { id: 'myopencre', label: 'MyOpenCRE', group: 'Apps' },
    { id: 'profile', label: 'Profile', group: 'Account' },
  ];

  return (
    <div className="admin-shell">
      <aside className="admin-side">
        <div className="admin-side__brand">
          OpenCRE
          <span>Admin · authenticated</span>
        </div>
        {(['Ops', 'Apps', 'Account'] as const).map((group) => (
          <div key={group}>
            <div className="admin-side__label">{group}</div>
            <div className="admin-side__nav">
              {nav
                .filter((n) => n.group === group)
                .map((n) => (
                  <button
                    key={n.id}
                    type="button"
                    className={tab === n.id ? 'is-active' : undefined}
                    onClick={() => setTab(n.id)}
                  >
                    {n.label}
                  </button>
                ))}
            </div>
          </div>
        ))}
        <div className="admin-side__foot">
          Requires login + CRE_ALLOW_IMPORT. Site browse links stay in the main header.
        </div>
      </aside>
      <div className="admin-main">
        <div className="admin-page">
          <h1 className="admin-page__title">{meta.label}</h1>
          <p className="admin-page__sub">{meta.sub}</p>
          {tab === 'dashboard' && (
            <DashboardTab
              origin={origin}
              onOpenJobs={() => setTab('pipeline')}
              onOpenReview={() => setTab('graph')}
              onOpenWorkbench={() => setTab('workbench')}
            />
          )}
          {tab === 'config' && <ConfigTab origin={origin} />}
          {tab === 'pipeline' && <PipelineTab origin={origin} />}
          {tab === 'oie' && <OieQueueTab origin={origin} />}
          {tab === 'schedule' && <ScheduleTab origin={origin} />}
          {tab === 'authority' && <AuthorityTab origin={origin} />}
          {tab === 'graph' && <GraphManagementTab origin={origin} />}
          {tab === 'workbench' && <WorkbenchTab origin={origin} />}
          {tab === 'myopencre' && (
            <div className="admin-card">
              <h3>MyOpenCRE</h3>
              <p className="admin-card__sub">
                Personal workspace (also needs CRE_ENABLE_MYOPENCRE for non-admin users).
              </p>
              <Link className="ui primary button" to="/myopencre">
                Open MyOpenCRE
              </Link>
            </div>
          )}
          {tab === 'profile' && <ProfileTab user={user} />}
        </div>
      </div>
    </div>
  );
};

function StageStrip({ steps }: { steps?: { id: string; label: string; state: string }[] }) {
  if (!steps || !steps.length) return null;
  return (
    <ol className="admin-strip">
      {steps.map((step) => (
        <li key={step.id} className={`admin-strip-step is-${step.state}`}>
          {step.label}
        </li>
      ))}
    </ol>
  );
}

function RepoFormFields({ form, setForm }: { form: RepoForm; setForm: (next: RepoForm) => void }) {
  const set =
    (key: keyof RepoForm) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setForm({ ...form, [key]: e.target.value });
  return (
    <Form>
      <Form.Group widths="equal">
        <Form.Input label="Id" value={form.id} onChange={set('id')} placeholder="owasp-asvs" />
        <Form.Input label="Owner" value={form.owner} onChange={set('owner')} placeholder="OWASP" />
        <Form.Input label="Repo" value={form.repo} onChange={set('repo')} placeholder="ASVS" />
      </Form.Group>
      <Form.Group widths="equal">
        <Form.Input label="Branch" value={form.branch} onChange={set('branch')} />
        <Form.Input label="Cron" value={form.cron} onChange={set('cron')} placeholder="0 2 * * *" />
        <Form.Input
          label="Interval minutes"
          value={form.interval_minutes}
          onChange={set('interval_minutes')}
        />
      </Form.Group>
      <Form.Group widths="equal">
        <Form.Field>
          <label>Chunking</label>
          <select value={form.strategy} onChange={set('strategy')}>
            <option value="markdown_heading">markdown_heading</option>
            <option value="html_readability">html_readability</option>
            <option value="fixed_size">fixed_size</option>
          </select>
        </Form.Field>
        <Form.Input label="Max tokens" value={form.max_tokens} onChange={set('max_tokens')} />
        <Form.Input label="Overlap tokens" value={form.overlap_tokens} onChange={set('overlap_tokens')} />
      </Form.Group>
      <Form.Field>
        <label>Include globs (one per line)</label>
        <textarea aria-label="include globs" value={form.include} onChange={set('include')} />
      </Form.Field>
      <Form.Field>
        <label>Exclude globs</label>
        <textarea aria-label="exclude globs" value={form.exclude} onChange={set('exclude')} />
      </Form.Field>
      <Form.Field>
        <label>Sync mode</label>
        <select value={form.mode} onChange={set('mode')}>
          <option value="incremental">incremental</option>
          <option value="full">full</option>
        </select>
      </Form.Field>
    </Form>
  );
}

function DashboardTab({
  origin,
  onOpenJobs,
  onOpenReview,
  onOpenWorkbench,
}: {
  origin: string;
  onOpenJobs: () => void;
  onOpenReview: () => void;
  onOpenWorkbench: () => void;
}) {
  const [data, setData] = useState<any>(null);
  const [ingest, setIngest] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(`${origin}/admin/dashboard`, { credentials: 'include' })
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(body.description || body.error || res.statusText);
        if (!cancelled) setData(body);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [origin]);
  useEffect(() => {
    let cancelled = false;
    const loadIngest = () => {
      fetch(`${origin}/admin/ingest/status`, { credentials: 'include' })
        .then(async (res) => {
          const body = await readJson(res);
          if (!res.ok) throw new Error(body.description || body.error || res.statusText);
          if (!cancelled) setIngest(body);
        })
        .catch(() => {
          /* strip is optional on Overview */
        });
    };
    loadIngest();
    const t = window.setInterval(loadIngest, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [origin]);
  if (error) return <Message negative>{error}</Message>;
  if (!data) return <p>Loading dashboard…</p>;
  const agent = data.agent || {};
  const attn = data.needs_attention || {};
  const pulse = data.review_pulse || {};
  return (
    <div>
      {ingest && (
        <div className="admin-card admin-ingest-strip">
          <h3>Active ingestions</h3>
          <p className="admin-card__sub">
            {ingest.active_count ?? 0} with remaining work
            {(ingest.stuck_count ?? 0) > 0 ? (
              <span className="admin-badge admin-badge--stuck"> · {ingest.stuck_count} stuck</span>
            ) : null}
            {' · '}
            <button type="button" className="admin-linkish" onClick={onOpenJobs}>
              Open Pipeline
            </button>
          </p>
        </div>
      )}
      <div className="admin-kpi-row">
        <div className="admin-kpi">
          <div className="admin-kpi__label">Running</div>
          <div className="admin-kpi__value">{(data.running || []).length}</div>
        </div>
        <div className="admin-kpi">
          <div className="admin-kpi__label">Failed</div>
          <div className="admin-kpi__value warn">{(data.failed || []).length}</div>
        </div>
        <div className="admin-kpi">
          <div className="admin-kpi__label">OIE unconsumed</div>
          <div className="admin-kpi__value">{data.oie_unconsumed ?? 0}</div>
        </div>
        <div className="admin-kpi">
          <div className="admin-kpi__label">Blocked</div>
          <div className="admin-kpi__value danger">{attn.blocked ?? 0}</div>
        </div>
        <div className="admin-kpi">
          <div className="admin-kpi__label">Staged review</div>
          <div className="admin-kpi__value warn">{attn.staged_review ?? 0}</div>
        </div>
        <div className="admin-kpi">
          <div className="admin-kpi__label">Ingest errors</div>
          <div className="admin-kpi__value danger">{attn.ingest_errors ?? 0}</div>
        </div>
      </div>

      <div className="admin-card">
        <h3>Needs attention</h3>
        <p className="admin-card__sub">Actionable queues — open the panel that owns the backlog.</p>
        <div className="admin-stat-grid">
          <div className="admin-stat">
            <div className="admin-stat__k">Staged review runs</div>
            <div className="admin-stat__v">{attn.staged_review ?? 0}</div>
          </div>
          <div className="admin-stat">
            <div className="admin-stat__k">Failed events</div>
            <div className="admin-stat__v">{attn.failed_24h ?? (data.failed || []).length}</div>
          </div>
          <div className="admin-stat">
            <div className="admin-stat__k">Blocked</div>
            <div className="admin-stat__v">{attn.blocked ?? 0}</div>
          </div>
          <div className="admin-stat">
            <div className="admin-stat__k">Ingest errors</div>
            <div className="admin-stat__v">{attn.ingest_errors ?? 0}</div>
          </div>
        </div>
        <Button primary size="mini" onClick={onOpenReview}>
          Open review
        </Button>{' '}
        <Button size="mini" onClick={onOpenJobs}>
          Pipeline
        </Button>{' '}
        <Button size="mini" onClick={onOpenWorkbench}>
          Workbench
        </Button>
      </div>

      <div className="admin-grid-2">
        <div className="admin-card">
          <h3>Recent import runs</h3>
          {(data.import_runs || []).length === 0 ? (
            <p className="admin-help">No import runs yet.</p>
          ) : (
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {(data.import_runs || []).map((r: any) => (
                  <tr key={r.id}>
                    <td>
                      <code>{r.source}</code>
                    </td>
                    <td>{r.staging_status || '—'}</td>
                    <td>{r.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="admin-card">
          <h3>Review pulse</h3>
          <p className="admin-card__sub">Accept-as-is vs adjust vs reject — prod signal, not a gold set.</p>
          <div className="admin-stat-grid">
            <div className="admin-stat">
              <div className="admin-stat__k">Accepted as-is</div>
              <div className="admin-stat__v">{pulse.accepted_as_is_pct ?? 0}%</div>
            </div>
            <div className="admin-stat">
              <div className="admin-stat__k">Adjusted</div>
              <div className="admin-stat__v">{pulse.adjusted_pct ?? 0}%</div>
            </div>
            <div className="admin-stat">
              <div className="admin-stat__k">Rejected</div>
              <div className="admin-stat__v">{pulse.rejected_pct ?? 0}%</div>
            </div>
            <div className="admin-stat">
              <div className="admin-stat__k">Pending links</div>
              <div className="admin-stat__v">{pulse.pending ?? 0}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="admin-card">
        <h3>OWASP agent</h3>
        <p className="admin-help">
          Enabled: {String(agent.enabled)} · package: {String(agent.package_present)} · writes CRE graph:{' '}
          {String(agent.writes_cre_graph)}
        </p>
        <Link className="ui mini button" to={agent.demo_path || '/chatbot'}>
          Open chat demo
        </Link>
      </div>
    </div>
  );
}

function GraphManagementTab({ origin }: { origin: string }) {
  const [runs, setRuns] = useState<any[]>([]);
  const [detail, setDetail] = useState<any>(null);
  const [graph, setGraph] = useState<any>(null);
  const [links, setLinks] = useState<any[]>([]);
  const [linksTotal, setLinksTotal] = useState(0);
  const [linksPage, setLinksPage] = useState(1);
  const [linksPageSize, setLinksPageSize] = useState(10);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [source, setSource] = useState('');
  const [relink, setRelink] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    fetch(`${origin}/admin/imports/runs`)
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(apiError(body, res));
        if (!cancelled) setRuns(body.runs || []);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [origin]);

  useEffect(() => load(), [load]);

  const act = async (runId: string, path: string, method = 'POST') => {
    setError(null);
    setNotice(null);
    setBusy(`${runId}:${path}`);
    try {
      const res = await fetch(`${origin}/admin/imports/runs/${runId}/${path}`, {
        method,
        headers: mutHeaders(),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(apiError(body, res));
        return;
      }
      const status = body.staging_status || body.status;
      const ops =
        typeof body.applied_ops === 'number'
          ? ` applied_ops=${body.applied_ops} skipped=${body.skipped_ops ?? 0}`
          : typeof body.operation_count === 'number'
          ? ` operations=${body.operation_count}`
          : '';
      setNotice(`${path.split('?')[0]} → ${status || 'ok'}${ops}`);
      setDetail(body);
      load();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(null);
    }
  };

  const openRun = async (runId: string, page = 1, pageSize = linksPageSize) => {
    setError(null);
    setNotice(null);
    setActiveRunId(runId);
    setLinksPage(page);
    setLinksPageSize(pageSize);
    try {
      const [csRes, linkRes] = await Promise.all([
        fetch(`${origin}/admin/imports/runs/${runId}/changeset`, { credentials: 'include' }),
        fetch(`${origin}/admin/imports/runs/${runId}/links?page=${page}&page_size=${pageSize}`, {
          credentials: 'include',
        }),
      ]);
      const csBody = await readJson(csRes);
      const linkBody = await readJson(linkRes);
      if (!csRes.ok) {
        setError(apiError(csBody, csRes));
        return;
      }
      if (!linkRes.ok) {
        setError(apiError(linkBody, linkRes));
        return;
      }
      const ops = Array.isArray(csBody.changeset) ? csBody.changeset.length : 0;
      if (ops === 0) {
        setNotice(
          'This run has an empty CRE import changeset (typical for OIE harvest). Accept/Discard only change review status; there are no controls/links to apply yet.'
        );
      }
      setDetail(csBody);
      setLinks(linkBody.links || []);
      setLinksTotal(typeof linkBody.total === 'number' ? linkBody.total : (linkBody.links || []).length);
      setGraph(null);
    } catch (err) {
      setError(String(err));
    }
  };

  const openGraph = async (runId: string) => {
    setError(null);
    setNotice(null);
    try {
      const res = await fetch(`${origin}/admin/imports/runs/${runId}/changeset/graph`);
      const body = await readJson(res);
      if (!res.ok) setError(apiError(body, res));
      else {
        setGraph(body);
        if (!(body.nodes || []).length) {
          setNotice('No graph nodes — staged CRE import ops are empty for this run.');
        }
      }
    } catch (err) {
      setError(String(err));
    }
  };

  const review = async (runId: string, row: any, action: string) => {
    setError(null);
    setNotice(null);
    const key = `${row.op_index}:${row.link_index}`;
    const payload: any = { op_index: row.op_index, link_index: row.link_index, action };
    if (action === 'relink') {
      const raw = (relink[key] || '').trim();
      if (!raw) {
        setError('Relink requires a CRE id or name');
        return;
      }
      payload.cre = raw.includes(' ') ? { name: raw } : { id: raw, name: raw };
    }
    try {
      const res = await fetch(`${origin}/admin/imports/runs/${runId}/links`, {
        method: 'POST',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(payload),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(apiError(body, res));
        return;
      }
      setLinks(body.links || []);
      setDetail({ ...detail, changeset: body.changeset, run_id: body.run_id });
      setNotice(`Link ${action} saved`);
    } catch (err) {
      setError(String(err));
    }
  };

  const dropLast = async () => {
    if (!source.trim()) {
      setError('source is required');
      return;
    }
    try {
      const res = await fetch(`${origin}/admin/imports/drop-last`, {
        method: 'POST',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ source: source.trim() }),
      });
      const body = await readJson(res);
      if (!res.ok) setError(apiError(body, res));
      else {
        setDetail(body);
        setNotice(`Dropped last staged run for ${source.trim()}`);
        load();
      }
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div>
      {error && <Message negative>{error}</Message>}
      {notice && <Message info>{notice}</Message>}
      {Array.isArray(detail?.warnings) && detail.warnings.length > 0 && (
        <Message warning>{detail.warnings.join(' ')}</Message>
      )}
      <p className="admin-help">
        Approve, deny, or relink each proposed CRE link on a run. Decisions are stored on the staged
        changeset. OIE harvest runs often have an empty CRE changeset (chunks live in harvest_input); Accept
        still marks review status. Apply writes standard node fields; CRE edge apply is follow-on.
      </p>
      <table className="admin-table">
        <thead>
          <tr>
            <th>Source</th>
            <th>Status</th>
            <th>Ops</th>
            <th>Created</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const status = run.staging_status || '—';
            const terminal = status === 'applied' || status === 'discarded';
            const rowBusy = busy?.startsWith(`${run.id}:`);
            return (
              <tr key={run.id}>
                <td>{run.source}</td>
                <td>{status}</td>
                <td>{typeof run.operation_count === 'number' ? run.operation_count : '—'}</td>
                <td>{run.created_at}</td>
                <td>
                  <Button size="mini" disabled={!!rowBusy} onClick={() => openRun(run.id)}>
                    Changeset
                  </Button>
                  <Button size="mini" disabled={!!rowBusy} onClick={() => openGraph(run.id)}>
                    Graph
                  </Button>
                  <Button
                    size="mini"
                    disabled={!!rowBusy || status !== 'pending_review'}
                    onClick={() => act(run.id, 'accept')}
                  >
                    Accept
                  </Button>
                  <Button size="mini" disabled={!!rowBusy || terminal} onClick={() => act(run.id, 'discard')}>
                    Discard
                  </Button>
                  <Button
                    size="mini"
                    disabled={!!rowBusy || status === 'discarded'}
                    onClick={() => act(run.id, 'apply?dry_run=1')}
                  >
                    Dry-run
                  </Button>
                  <Button size="mini" disabled={!!rowBusy} onClick={() => act(run.id, 'impact', 'GET')}>
                    Impact
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p>
        Drop last staged ingestion for source{' '}
        <input value={source} onChange={(e) => setSource(e.target.value)} />{' '}
        <Button size="mini" onClick={dropLast}>
          Drop last
        </Button>
      </p>
      {graph && (
        <div>
          <h3>Changeset graph</h3>
          {!(graph.nodes || []).length ? (
            <p>No graph nodes</p>
          ) : (
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Node</th>
                  <th>Type</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {graph.nodes.map((n: any) => (
                  <tr key={n.id}>
                    <td>{n.label}</td>
                    <td>{n.type}</td>
                    <td>{n.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      {detail && (
        <div className="admin-card">
          <h3>Staged links</h3>
          <p className="admin-card__sub">
            Expand a row for section title and content. Page {linksPage} · {linksTotal} total.
          </p>
          <p>
            <label>
              Page size{' '}
              <select
                value={linksPageSize}
                onChange={(e) => {
                  const size = Number(e.target.value) || 10;
                  if (activeRunId) openRun(activeRunId, 1, size);
                }}
              >
                <option value={5}>5</option>
                <option value={10}>10</option>
                <option value={25}>25</option>
              </select>
            </label>{' '}
            <Button
              size="mini"
              disabled={linksPage <= 1 || !activeRunId}
              onClick={() => activeRunId && openRun(activeRunId, linksPage - 1, linksPageSize)}
            >
              Prev
            </Button>{' '}
            <Button
              size="mini"
              disabled={!activeRunId || linksPage * linksPageSize >= linksTotal}
              onClick={() => activeRunId && openRun(activeRunId, linksPage + 1, linksPageSize)}
            >
              Next
            </Button>
          </p>
          {links.length === 0 ? (
            <p>{linksTotal === 0 ? 'No staged links on this run.' : 'No staged links on this page.'}</p>
          ) : (
            links.map((row: any) => {
              const key = `${row.op_index}:${row.link_index}`;
              const added = row.added || {};
              const linked = row.linked_to;
              const title = added.title || added.name || added.sectionID || 'Section';
              const content = added.content || '';
              return (
                <article className="admin-review-item" key={key}>
                  <div style={{ padding: '0.65rem 0.75rem' }}>
                    <div>
                      <code>{added.sectionID || added.section || added.name}</code>{' '}
                      <span className="admin-pill muted">{row.decision}</span>
                    </div>
                    <div className="admin-help">
                      → {linked ? `${linked.id} ${linked.name}`.trim() : 'no proposal'}
                    </div>
                    <div style={{ marginTop: '0.4rem' }}>
                      {linked && (
                        <>
                          <Button size="mini" primary onClick={() => review(detail.run_id, row, 'approve')}>
                            Accept
                          </Button>{' '}
                          <Button size="mini" onClick={() => review(detail.run_id, row, 'deny')}>
                            Reject
                          </Button>{' '}
                        </>
                      )}
                      <input
                        placeholder="relink CRE id or name"
                        value={relink[key] || ''}
                        onChange={(e) => setRelink({ ...relink, [key]: e.target.value })}
                      />{' '}
                      <Button size="mini" onClick={() => review(detail.run_id, row, 'relink')}>
                        Relink
                      </Button>
                    </div>
                  </div>
                  <details>
                    <summary>Section title &amp; content</summary>
                    <div className="admin-review-item__body">
                      <p>
                        <strong>{title}</strong>
                      </p>
                      <p className="admin-help" style={{ whiteSpace: 'pre-wrap' }}>
                        {content || 'No section body on this staged op.'}
                      </p>
                    </div>
                  </details>
                </article>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

function ExternalSuggestions({ origin }: { origin: string }) {
  const [items, setItems] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState({
    url: '',
    prefixes: '',
    maxPages: '200',
    refreshDays: '30',
    weight: '1',
  });
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    fetch(`${origin}/admin/external`, { credentials: 'include' })
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(apiError(body, res));
        setItems((body.external || []).filter((e: any) => e.status === 'suggested'));
      })
      .catch((err) => setError(String(err)));
  }, [origin]);

  useEffect(() => {
    load();
  }, [load]);

  const startEdit = (e: any) => {
    const spec = e.spec || {};
    setEditing(e.id);
    setForm({
      url:
        e.kind === 'youtube_channel'
          ? spec.channel_id || spec.playlist_id || ''
          : (spec.start_urls || [])[0] || '',
      prefixes: (spec.allow_prefixes || []).join(', '),
      maxPages: String(spec.max_pages ?? 200),
      refreshDays: String(spec.refresh_days ?? 30),
      weight: String(spec.weight ?? 1),
    });
  };

  const send = async (e: any, action: 'accept' | 'reject', overrides: Record<string, unknown> = {}) => {
    setBusy(e.id);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch(`${origin}/admin/external/${encodeURIComponent(e.id)}/${action}`, {
        method: 'POST',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(overrides),
      });
      const body = await readJson(res);
      if (!res.ok) throw new Error(apiError(body, res));
      setNotice(`${e.name}: ${action === 'accept' ? 'accepted' : 'rejected'}`);
      setEditing(null);
      load();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(null);
    }
  };

  const accept = (e: any) => {
    const overrides: Record<string, unknown> = {
      allow_prefixes: form.prefixes
        .split(',')
        .map((p) => p.trim())
        .filter(Boolean),
      max_pages: Number(form.maxPages),
      refresh_days: Number(form.refreshDays),
      weight: Number(form.weight),
    };
    if (e.kind === 'youtube_channel')
      overrides[(form.url || '').startsWith('PL') ? 'playlist_id' : 'channel_id'] = form.url;
    else overrides.start_urls = [form.url.trim()];
    return send(e, 'accept', overrides);
  };

  return (
    <div className="admin-card">
      <h3>Suggested external sources</h3>
      <p className="admin-card__sub">
        Websites and YouTube channels linked from harvested repos. Nothing is crawled until you accept.
      </p>
      {error && <Message negative>{error}</Message>}
      {notice && <Message>{notice}</Message>}
      {!items.length && <p className="admin-help">No suggestions.</p>}
      {items.map((e) => {
        const spec = e.spec || {};
        const found = spec.found_in || [];
        return (
          <article className="admin-review-item" key={e.id} data-testid={`suggestion-${e.id}`}>
            <div
              style={{
                padding: '0.65rem 0.75rem',
                display: 'flex',
                justifyContent: 'space-between',
                gap: '1rem',
              }}
            >
              <div>
                <code>{e.id}</code> <span className="admin-pill muted">{e.kind}</span>{' '}
                <span className="admin-pill muted">score {e.score ?? 0}</span>
                <div className="admin-help">{e.name}</div>
                {found.slice(0, 3).map((f: any, i: number) => (
                  <div className="admin-help" key={i}>
                    <span className="admin-pill muted">
                      {f.source === 'crawl' ? 'crawl' : f.source === 'seed' ? 'seed' : 'GitHub'}
                    </span>{' '}
                    {f.source === 'crawl'
                      ? `found on ${f.page}`
                      : f.source === 'seed'
                      ? `curated list ${f.page}`
                      : `${f.repo} · ${f.file}`}
                    {f.link_text ? ` · "${f.link_text}"` : ''}
                  </div>
                ))}
                {found.length > 3 && <div className="admin-help">+{found.length - 3} more</div>}
              </div>
              <div>
                <Button size="mini" primary disabled={busy === e.id} onClick={() => startEdit(e)}>
                  Accept
                </Button>{' '}
                <Button size="mini" disabled={busy === e.id} onClick={() => send(e, 'reject')}>
                  Reject
                </Button>
              </div>
            </div>
            {editing === e.id && (
              <div className="admin-review-item__body">
                <label>
                  {e.kind === 'youtube_channel' ? 'Channel or playlist id' : 'Start URL'}{' '}
                  <input
                    aria-label="start url"
                    value={form.url}
                    onChange={(ev) => setForm({ ...form, url: ev.target.value })}
                  />
                </label>{' '}
                {e.kind !== 'youtube_channel' && (
                  <label>
                    Allowed prefixes{' '}
                    <input
                      aria-label="allowed prefixes"
                      placeholder="comma separated, default same host"
                      value={form.prefixes}
                      onChange={(ev) => setForm({ ...form, prefixes: ev.target.value })}
                    />
                  </label>
                )}{' '}
                <label>
                  Max pages{' '}
                  <input
                    aria-label="max pages"
                    type="number"
                    value={form.maxPages}
                    onChange={(ev) => setForm({ ...form, maxPages: ev.target.value })}
                  />
                </label>{' '}
                <label>
                  Refresh days{' '}
                  <input
                    aria-label="refresh days"
                    type="number"
                    value={form.refreshDays}
                    onChange={(ev) => setForm({ ...form, refreshDays: ev.target.value })}
                  />
                </label>{' '}
                <label>
                  Weight{' '}
                  <input
                    aria-label="weight"
                    type="number"
                    step={0.05}
                    min={0}
                    max={3}
                    value={form.weight}
                    onChange={(ev) => setForm({ ...form, weight: ev.target.value })}
                  />
                </label>{' '}
                <Button size="mini" primary disabled={busy === e.id} onClick={() => accept(e)}>
                  Confirm accept
                </Button>
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}

function WorkbenchTab({ origin }: { origin: string }) {
  const [targets, setTargets] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lane, setLane] = useState('all');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${origin}/admin/targets`, { credentials: 'include' })
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(apiError(body, res));
        if (!cancelled) setTargets(body.targets || []);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [origin]);

  const filtered = targets.filter((t) => {
    const kind = String(t.kind || '');
    const spec = t.spec || {};
    const repoKind = String(spec.kind || (kind === 'owasp_agent' ? 'project' : 'standard'));
    const L = repoKind === 'standard' || kind === 'oie_repo' ? 'cre_expansion' : 'owasp_agent';
    if (lane !== 'all' && L !== lane) return false;
    const hay = `${t.id} ${t.name} ${spec.owner || ''} ${spec.repo || ''}`.toLowerCase();
    if (q.trim() && !hay.includes(q.trim().toLowerCase())) return false;
    return t.enabled !== false;
  });
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize) || 1);
  const pageSafe = Math.min(page, totalPages);
  const slice = filtered.slice((pageSafe - 1) * pageSize, pageSafe * pageSize);

  const reingest = async (id: string) => {
    setBusy(id);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch(`${origin}/admin/ingest/start`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ packaged: true, name: id }),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(apiError(body, res));
        return;
      }
      setNotice(`Queued re-ingest for ${id} → ${body.source || 'ok'}`);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      {error && <Message negative>{error}</Message>}
      {notice && <Message>{notice}</Message>}
      <div className="admin-card">
        <h3>Accepted targets</h3>
        <p className="admin-card__sub">
          From ingestion targets / repos.yaml. Lane: cre_expansion ≈ standards; owasp_agent ≈
          project/chapter/event.
        </p>
        <p>
          <label>
            Lane{' '}
            <select
              value={lane}
              onChange={(e) => {
                setLane(e.target.value);
                setPage(1);
              }}
            >
              <option value="all">All</option>
              <option value="cre_expansion">CRE expansion</option>
              <option value="owasp_agent">OWASP agent</option>
            </select>
          </label>{' '}
          <input
            placeholder="Search"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
          />{' '}
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value) || 5);
              setPage(1);
            }}
          >
            <option value={5}>5</option>
            <option value={10}>10</option>
            <option value={25}>25</option>
          </select>
        </p>
        <p className="admin-help">
          {filtered.length} match · page {pageSafe}/{totalPages}
        </p>
        {slice.map((t) => {
          const spec = t.spec || {};
          return (
            <article className="admin-review-item" key={t.id}>
              <div
                style={{
                  padding: '0.65rem 0.75rem',
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: '1rem',
                }}
              >
                <div>
                  <code>{t.id}</code> <span className="admin-pill muted">{t.kind}</span>
                  <div className="admin-help">
                    {t.name}
                    {spec.owner ? ` · ${spec.owner}/${spec.repo || ''}` : ''}
                  </div>
                </div>
                <Button size="mini" primary disabled={busy === t.id} onClick={() => reingest(t.id)}>
                  Re-ingest
                </Button>
              </div>
              <details>
                <summary>Target details</summary>
                <div className="admin-review-item__body">
                  <pre className="admin-pre">
                    {JSON.stringify(spec && Object.keys(spec).length ? spec : t, null, 2)}
                  </pre>
                </div>
              </details>
            </article>
          );
        })}
        <p>
          <Button size="mini" disabled={pageSafe <= 1} onClick={() => setPage(pageSafe - 1)}>
            Prev
          </Button>{' '}
          <Button size="mini" disabled={pageSafe >= totalPages} onClick={() => setPage(pageSafe + 1)}>
            Next
          </Button>
        </p>
      </div>
      <ExternalSuggestions origin={origin} />
    </div>
  );
}

function ProfileTab({ user }: { user: string | null }) {
  return (
    <div className="admin-card">
      <h3>Profile</h3>
      <p className="admin-card__sub">Operator session — admin panel is gated by login + CRE_ALLOW_IMPORT.</p>
      <p>
        Signed in as <strong>{user || '—'}</strong>
      </p>
      <p className="admin-help">
        JWT API keys (mint/revoke) ship via <code>/rest/v1/api-keys</code> when that module is enabled on the
        deployment. Use <code>Authorization: Bearer</code> or <code>X-API-Key</code> for automated admin
        calls; browser session cookies remain the primary UI path.
      </p>
    </div>
  );
}

type ScheduleJob = {
  job: string;
  description: string;
  default_interval_minutes: number;
  interval_minutes: number;
  overridden: boolean;
  enabled: boolean;
  next_expected: string | null;
  last_run: { status?: string; started_at?: string } | null;
};

type AuthorityRow = { slug: string; name: string; weight: number };

function AuthorityTab({ origin }: { origin: string }) {
  const [rows, setRows] = useState<AuthorityRow[]>([]);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    fetch(`${origin}/admin/authority`)
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(apiError(body, res));
        const list: AuthorityRow[] = body.projects || [];
        setRows(list);
        setDraft(Object.fromEntries(list.map((r) => [r.slug, String(r.weight)])));
        setError(null);
      })
      .catch((err) => setError(String(err)));
  }, [origin]);

  useEffect(() => {
    load();
  }, [load]);

  const changed = rows.filter((r) => Number(draft[r.slug]) !== r.weight);

  const save = async () => {
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      const weights = Object.fromEntries(changed.map((r) => [r.slug, Number(draft[r.slug])]));
      const res = await fetch(`${origin}/admin/authority`, {
        method: 'PUT',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ weights }),
      });
      const body = await readJson(res);
      if (!res.ok) throw new Error(apiError(body, res));
      setNotice(`${changed.length} project weight(s) saved; effective within 30 seconds`);
      load();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const shown = rows
    .filter((r) => !filter || r.slug.toLowerCase().includes(filter.toLowerCase()))
    .sort((a, b) => Number(b.weight !== 1) - Number(a.weight !== 1) || a.slug.localeCompare(b.slug));

  return (
    <div>
      {error ? <Message negative content={error} /> : null}
      {notice ? <Message positive content={notice} /> : null}
      <p>
        Above 1 never changes the answer itself: the project&apos;s closest passage is added to the references
        when it is reasonably relevant (1.15 is strict, 1.3 is looser). Below 1 pushes a project down in the
        ranking and 0 hides it. Questions that name a project are not affected.
      </p>
      <input
        aria-label="filter projects"
        placeholder="Filter projects"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />{' '}
      <Button primary size="small" disabled={!changed.length || busy} onClick={save}>
        Save {changed.length ? `(${changed.length})` : ''}
      </Button>
      <table className="admin-table" data-testid="authority-table">
        <thead>
          <tr>
            <th>project</th>
            <th>weight</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.slug}>
              <td className="mono">{r.slug}</td>
              <td>
                <input
                  type="number"
                  step={0.05}
                  min={0}
                  max={3}
                  aria-label={`${r.slug} weight`}
                  value={draft[r.slug] ?? ''}
                  onChange={(e) => setDraft({ ...draft, [r.slug]: e.target.value })}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScheduleTab({ origin }: { origin: string }) {
  const [jobs, setJobs] = useState<ScheduleJob[]>([]);
  const [draft, setDraft] = useState<Record<string, { interval: string; enabled: boolean }>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const apply = useCallback((rows: ScheduleJob[]) => {
    setJobs(rows);
    setDraft(
      Object.fromEntries(
        rows.map((r) => [r.job, { interval: String(r.interval_minutes), enabled: r.enabled }])
      )
    );
  }, []);

  const load = useCallback(() => {
    fetch(`${origin}/admin/schedule`)
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(apiError(body, res));
        apply(body.jobs || []);
        setError(null);
      })
      .catch((err) => setError(String(err)));
  }, [origin, apply]);

  useEffect(() => {
    load();
  }, [load]);

  const save = async (job: string) => {
    const d = draft[job];
    if (!d) return;
    setBusy(job);
    setNotice(null);
    setError(null);
    try {
      const res = await fetch(`${origin}/admin/schedule/${encodeURIComponent(job)}`, {
        method: 'PUT',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ interval_minutes: Number(d.interval), enabled: d.enabled }),
      });
      const body = await readJson(res);
      if (!res.ok) throw new Error(apiError(body, res));
      apply(body.jobs || []);
      setNotice(`${job} schedule saved`);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      {error ? <Message negative content={error} /> : null}
      {notice ? <Message positive content={notice} /> : null}
      <p>
        Intervals are in minutes. A change takes effect at the next scheduler tick; it does not interrupt a
        run in progress. A switched-off job is skipped by the scheduler but can still be started by hand.
      </p>
      <table className="admin-table" data-testid="schedule-table">
        <thead>
          <tr>
            <th>job</th>
            <th>what it does</th>
            <th>interval (min)</th>
            <th>default</th>
            <th>on</th>
            <th>next run</th>
            <th>last run</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => {
            const d = draft[j.job] || { interval: String(j.interval_minutes), enabled: j.enabled };
            const dirty = d.interval !== String(j.interval_minutes) || d.enabled !== j.enabled;
            return (
              <tr key={j.job}>
                <td className="mono">{j.job}</td>
                <td>{j.description}</td>
                <td>
                  <input
                    type="number"
                    min={1}
                    aria-label={`${j.job} interval minutes`}
                    value={d.interval}
                    onChange={(e) => setDraft({ ...draft, [j.job]: { ...d, interval: e.target.value } })}
                  />
                </td>
                <td>{j.default_interval_minutes}</td>
                <td>
                  <Checkbox
                    aria-label={`${j.job} enabled`}
                    checked={d.enabled}
                    onChange={(_e, data) =>
                      setDraft({ ...draft, [j.job]: { ...d, enabled: !!data.checked } })
                    }
                  />
                </td>
                <td className="mono">
                  {j.next_expected ? j.next_expected.replace('T', ' ').slice(0, 16) : '—'}
                </td>
                <td>
                  {j.last_run?.status
                    ? `${j.last_run.status} · ${(j.last_run.started_at || '').slice(0, 16)}`
                    : '—'}
                </td>
                <td>
                  <Button size="mini" primary disabled={!dirty || busy === j.job} onClick={() => save(j.job)}>
                    Save
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function OieQueueTab({ origin }: { origin: string }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState('');

  const load = useCallback(() => {
    let cancelled = false;
    const q = runId.trim() ? `?run_id=${encodeURIComponent(runId.trim())}` : '';
    fetch(`${origin}/admin/oie/rq/status${q}`)
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(apiError(body, res));
        if (!cancelled) {
          setData(body);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [origin, runId]);

  useEffect(() => {
    const cancel = load();
    const t = window.setInterval(() => load(), 5000);
    return () => {
      cancel();
      window.clearInterval(t);
    };
  }, [load]);

  const postJobs = async (path: string, jobIds?: string[]) => {
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      const res = await fetch(`${origin}${path}`, {
        method: 'POST',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(jobIds ? { job_ids: jobIds } : {}),
      });
      const body = await readJson(res);
      if (!res.ok) throw new Error(apiError(body, res));
      const n = body.requeued_count ?? body.cancelled_count ?? 0;
      const kind = body.requeued_count != null ? 'requeued' : 'cancelled';
      setNotice(`${kind} ${n} job(s)` + (body.errors?.length ? ` · ${body.errors.length} error(s)` : ''));
      load();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const queues = data?.queues || {};
  const oie = data?.oie || {};
  const failedCount = (oie.failed || []).length;
  const jobTable = (rows: any[] | undefined, actions?: 'failed' | 'active') => (
    <table className="admin-table">
      <thead>
        <tr>
          <th>description</th>
          <th>status</th>
          <th>job id</th>
          {actions ? <th /> : null}
        </tr>
      </thead>
      <tbody>
        {(rows || []).length ? (
          rows!.map((r) => (
            <tr key={r.job_id}>
              <td className="mono">{r.description}</td>
              <td>{r.status}</td>
              <td className="mono">{r.job_id}</td>
              {actions === 'failed' ? (
                <td>
                  <Button
                    size="mini"
                    disabled={busy}
                    onClick={() => postJobs('/admin/oie/rq/requeue-failed', [r.job_id])}
                  >
                    Requeue
                  </Button>
                </td>
              ) : null}
              {actions === 'active' ? (
                <td>
                  <Button
                    size="mini"
                    disabled={busy}
                    onClick={() => postJobs('/admin/oie/rq/cancel', [r.job_id])}
                  >
                    Cancel
                  </Button>
                </td>
              ) : null}
            </tr>
          ))
        ) : (
          <tr>
            <td colSpan={actions ? 4 : 3}>—</td>
          </tr>
        )}
      </tbody>
    </table>
  );

  return (
    <div>
      <p className="admin-help">
        Import-style RQ monitor for the <code>oie</code> queue (auto-refresh 5s). Workers:{' '}
        <code>make start-oie-workers</code> (default 10) or <code>CRE_OIE_WORKER_COUNT</code> via import-all.
      </p>
      <Form onSubmit={(e) => e.preventDefault()}>
        <Form.Input
          label="pipeline_run_id (optional DB counts)"
          value={runId}
          onChange={(_, { value }) => setRunId(String(value || ''))}
          placeholder="uncapped-safety-…"
        />
        <Button type="button" onClick={() => load()} disabled={busy}>
          Refresh
        </Button>
        <Button
          type="button"
          primary
          disabled={busy || !failedCount}
          onClick={() => postJobs('/admin/oie/rq/requeue-failed')}
        >
          Requeue all failed ({failedCount})
        </Button>
      </Form>
      {error && <Message negative>{error}</Message>}
      {notice && <Message positive>{notice}</Message>}
      {data && (
        <>
          <p className="admin-help">
            Updated: {data.timestamp} · queue <code>{data.oie_queue_name}</code>
          </p>
          <table className="admin-table">
            <thead>
              <tr>
                <th>queue</th>
                <th>queued</th>
                <th>started</th>
                <th>failed</th>
                <th>finished</th>
              </tr>
            </thead>
            <tbody>
              {Object.keys(queues).map((qn) => (
                <tr key={qn}>
                  <td>
                    <code>{qn}</code>
                  </td>
                  <td>{queues[qn]?.queued}</td>
                  <td>{queues[qn]?.started}</td>
                  <td>{queues[qn]?.failed}</td>
                  <td>{queues[qn]?.finished}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.run && <pre className="admin-pre">{JSON.stringify(data.run, null, 2)}</pre>}
          <h3>Started</h3>
          {jobTable(oie.started, 'active')}
          <h3>Queued</h3>
          {jobTable(oie.queued, 'active')}
          <h3>Failed</h3>
          {jobTable(oie.failed, 'failed')}
          <h3>Recent finished</h3>
          {jobTable(oie.finished)}
        </>
      )}
    </div>
  );
}

function flagChips(cfg: any): string[] {
  if (!cfg) return [];
  const chips: string[] = [];
  if (cfg.skip_b) chips.push('skip_b');
  if (cfg.skip_c) chips.push('skip_c');
  if (cfg.skip_c1) chips.push('skip_c1');
  if (cfg.dry_run) chips.push('dry_run');
  if (cfg.max_repos != null) chips.push(`max_repos=${cfg.max_repos}`);
  if (cfg.spec?.owner && cfg.spec?.repo) chips.push(`${cfg.spec.owner}/${cfg.spec.repo}`);
  if (cfg.spec?.lane) chips.push(`lane=${cfg.spec.lane}`);
  if (cfg.skip_reason && cfg.skip_reason !== 'none') chips.push(String(cfg.skip_reason));
  return chips;
}

function PipelineTab({ origin }: { origin: string }) {
  const [data, setData] = useState<any>(null);
  const [ingest, setIngest] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<'current' | 'single'>('current');
  const [form, setForm] = useState<RepoForm>(emptyRepo());

  const load = useCallback(() => {
    let cancelled = false;
    fetch(`${origin}/admin/pipeline`)
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(body.description || body.error || res.statusText);
        if (!cancelled) setData(body);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [origin]);

  const loadIngest = useCallback(() => {
    let cancelled = false;
    fetch(`${origin}/admin/ingest/status`)
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(apiError(body, res));
        if (!cancelled) setIngest(body);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [origin]);

  useEffect(() => load(), [load]);
  useEffect(() => {
    const cancel = loadIngest();
    const t = window.setInterval(() => loadIngest(), 5000);
    return () => {
      cancel();
      window.clearInterval(t);
    };
  }, [loadIngest]);

  const startCurrent = async () => {
    setError(null);
    try {
      const res = await fetch(`${origin}/admin/ingest/start`, {
        method: 'POST',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ packaged: true }),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(body.description || body.error || res.statusText);
        return;
      }
      setNotice(`Started ${body.source}`);
      setOpen(false);
      load();
    } catch (err) {
      setError(String(err));
    }
  };

  const startSingle = async () => {
    if (!form.owner.trim() || !form.repo.trim()) {
      setError('owner and repo are required');
      return;
    }
    setError(null);
    try {
      const built = await fetch(`${origin}/admin/repos.yaml/add-repo`, {
        method: 'POST',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ yaml: 'sources: []\n', ...repoSpec(form) }),
      });
      const builtBody = await readJson(built);
      if (!built.ok) {
        setError(builtBody.description || builtBody.error || built.statusText);
        return;
      }
      const res = await fetch(`${origin}/admin/ingest/start`, {
        method: 'POST',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ yaml: builtBody.yaml, name: repoSpec(form).id }),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(body.description || body.error || res.statusText);
        return;
      }
      setNotice(`Started ${body.source}`);
      setOpen(false);
      load();
    } catch (err) {
      setError(String(err));
    }
  };

  if (error && !data) return <Message negative>{error}</Message>;
  if (!data) return <p>Loading pipeline…</p>;
  const empty = !(data.import_runs || []).length && !(data.events || []).length;
  const ingestRows = ingest?.ingestions || [];
  return (
    <div>
      {error && <Message negative>{error}</Message>}
      {notice && <Message>{notice}</Message>}
      <p>
        <Button primary size="mini" onClick={() => setOpen(true)}>
          New
        </Button>
      </p>
      <div className="admin-card">
        <h3>Active ingestions</h3>
        <p className="admin-card__sub">
          Config + live progress + ETA (polls every 5s). Stuck when remaining freezes or jobs age out.
        </p>
        {!ingest ? (
          <p>Loading ingest status…</p>
        ) : ingestRows.length === 0 ? (
          <p>No recent ingestions.</p>
        ) : (
          <div className="admin-ingest-list">
            {ingestRows.map((row: any) => {
              const p = row.progress || {};
              const eta = row.eta || {};
              const chips = flagChips(row.config);
              return (
                <div key={row.run_id} className="admin-ingest-card">
                  <div className="admin-ingest-card__head">
                    <strong>{row.source || row.run_id}</strong>
                    <span className="mono">{(row.run_id || '').slice(0, 8)}</span>
                    <span className="admin-help">{row.phase}</span>
                    {row.stuck ? (
                      <span className="admin-badge admin-badge--stuck" title={row.stuck_reason || ''}>
                        Stuck
                      </span>
                    ) : null}
                  </div>
                  {chips.length > 0 && (
                    <div className="admin-ingest-chips">
                      {chips.map((c) => (
                        <span key={c} className="admin-chip">
                          {c}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="admin-stat-grid admin-ingest-progress">
                    <div className="admin-stat">
                      <div className="admin-stat__k">HI pending / done</div>
                      <div className="admin-stat__v">
                        {p.harvest_pending ?? 0} / {p.harvest_processed ?? 0}
                      </div>
                    </div>
                    <div className="admin-stat">
                      <div className="admin-stat__k">KQ open / done</div>
                      <div className="admin-stat__v">
                        {p.knowledge_unconsumed ?? 0} / {p.knowledge_consumed ?? 0}
                      </div>
                    </div>
                    <div className="admin-stat">
                      <div className="admin-stat__k">RQ q / start / fail</div>
                      <div className="admin-stat__v">
                        {p.rq_queued ?? 0} / {p.rq_started ?? 0} / {p.rq_failed ?? 0}
                      </div>
                    </div>
                    <div className="admin-stat">
                      <div className="admin-stat__k">Remaining</div>
                      <div className="admin-stat__v">{p.remaining ?? 0}</div>
                    </div>
                    <div className="admin-stat">
                      <div className="admin-stat__k">ETA</div>
                      <div className="admin-stat__v">
                        {eta.note || '—'}
                        {eta.eta_utc ? <span className="admin-help"> · {eta.eta_utc}</span> : null}
                      </div>
                    </div>
                  </div>
                  {row.stuck_reason ? (
                    <p className="admin-help admin-ingest-stuck-reason">{row.stuck_reason}</p>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </div>
      <h3>Latest run</h3>
      <StageStrip steps={data.latest_strip} />
      {empty && <p>No pipeline runs yet.</p>}
      <h3>Import runs</h3>
      <ol>
        {(data.import_runs || []).map((r: any) => (
          <li key={r.id}>
            {r.source} — {r.staging_status || 'none'}
            <StageStrip steps={r.strip} />
          </li>
        ))}
      </ol>
      <h3>Stage logs</h3>
      <p className="admin-help">
        Look for <code>oie</code>/<code>started</code> (flags + skip_reason) and <code>oie_trace</code>{' '}
        (engine, graph_path, visited). The admin default runs Module B, C, and C.1 (graph filer). Skipped
        stages mean the run passed the matching <code>skip_*</code> flag true. Module A with chunks=0 usually
        means harvester checkpoints were already at HEAD (no file diffs).
      </p>
      <table className="admin-table">
        <thead>
          <tr>
            <th>Run</th>
            <th>Stage</th>
            <th>Status</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {(data.events || []).map((e: any) => (
            <tr key={e.id}>
              <td title={e.run_id}>{(e.run_id || '').slice(0, 8)}</td>
              <td>{e.stage}</td>
              <td>{e.status}</td>
              <td style={{ whiteSpace: 'pre-wrap', maxWidth: '48rem' }}>{e.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>OIE decisions</h3>
      <p>Unconsumed: {data.oie?.unconsumed ?? 0}</p>
      <pre className="admin-pre">{JSON.stringify(data.oie?.recent || [], null, 2)}</pre>
      <h3>LLM reasoning</h3>
      {(data.oie?.knowledge || []).length === 0 ? (
        <p>No knowledge-queue artifacts.</p>
      ) : (
        <ul>
          {(data.oie.knowledge || []).map((k: any) => (
            <li key={k.id}>
              {k.llm_label}: {k.llm_reasoning || '—'}
            </li>
          ))}
        </ul>
      )}
      <Modal open={open} onClose={() => setOpen(false)}>
        <Modal.Header>New ingest</Modal.Header>
        <Modal.Content>
          <p>
            <label>
              <input type="radio" checked={mode === 'current'} onChange={() => setMode('current')} /> Current
              targets.yaml
            </label>{' '}
            <label>
              <input type="radio" checked={mode === 'single'} onChange={() => setMode('single')} /> Single
              repository
            </label>
          </p>
          {mode === 'single' && <RepoFormFields form={form} setForm={setForm} />}
        </Modal.Content>
        <Modal.Actions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button primary onClick={mode === 'current' ? startCurrent : startSingle}>
            Start
          </Button>
        </Modal.Actions>
      </Modal>
    </div>
  );
}

type ApiKeyRow = {
  jti: string;
  name: string;
  expires_at?: string | null;
  revoked_at?: string | null;
  created_at?: string | null;
  last_used_at?: string | null;
};

function ConfigTab({ origin }: { origin: string }) {
  const [rows, setRows] = useState<any[]>([]);
  const [instructions, setInstructions] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [yamlText, setYamlText] = useState('');
  const [yamlSource, setYamlSource] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [org, setOrg] = useState('');
  const [orgCron, setOrgCron] = useState('0 2 * * *');
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<RepoForm>(emptyRepo());
  const [agent, setAgent] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [filingEnabled, setFilingEnabled] = useState(false);
  const [filingBusy, setFilingBusy] = useState(false);
  const [apiKeys, setApiKeys] = useState<ApiKeyRow[]>([]);
  const [apiKeysOpen, setApiKeysOpen] = useState(false);
  const [apiKeyName, setApiKeyName] = useState('ci');
  const [apiKeyDays, setApiKeyDays] = useState('90');
  const [apiKeyBusy, setApiKeyBusy] = useState(false);
  const [mintedToken, setMintedToken] = useState<string | null>(null);
  const [mintedMeta, setMintedMeta] = useState<{ name: string; expires_at?: string } | null>(null);
  const [diffRows, setDiffRows] = useState<any[]>([]);
  const [diffFilter, setDiffFilter] = useState('all');

  const loadYaml = useCallback(() => {
    let cancelled = false;
    fetch(`${origin}/admin/repos.yaml`)
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(body.description || body.error || res.statusText);
        if (cancelled) return;
        if (typeof body.yaml === 'string') setYamlText(body.yaml);
        if (typeof body.source === 'string') setYamlSource(body.source);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [origin]);

  const loadAgent = useCallback(() => {
    let cancelled = false;
    fetch(`${origin}/admin/agent/status`)
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(body.description || body.error || res.statusText);
        if (!cancelled) setAgent(body);
      })
      .catch(() => {
        if (!cancelled) setAgent(null);
      });
    return () => {
      cancelled = true;
    };
  }, [origin]);

  const loadApiKeys = useCallback(() => {
    let cancelled = false;
    fetch(`${origin}/rest/v1/api-keys`, { credentials: 'include' })
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(apiError(body, res));
        if (!cancelled) setApiKeys(Array.isArray(body.keys) ? body.keys : []);
      })
      .catch(() => {
        // Keep Config usable if the caller is not on LOGIN_ALLOWED_EMAILS.
        if (!cancelled) setApiKeys([]);
      });
    return () => {
      cancelled = true;
    };
  }, [origin]);

  useEffect(() => {
    const cancelYaml = loadYaml();
    const cancelAgent = loadAgent();
    const cancelKeys = loadApiKeys();
    let cancelled = false;
    fetch(`${origin}/admin/config`, { credentials: 'include' })
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(body.description || body.error || res.statusText);
        if (cancelled) return;
        setRows(body.config || []);
        setInstructions(body.restart_instructions || '');
        if (typeof body.csrf_token === 'string') setAdminCsrf(body.csrf_token);
        const filing = (body.config || []).find(
          (row: { key?: string; value?: string | null }) => row.key === 'OIE_GRAPH_FILING_ENABLED'
        );
        const raw = String(filing?.value ?? '0').toLowerCase();
        setFilingEnabled(['1', 'true', 'yes', 'on'].includes(raw));
      })
      .catch(() => {
        if (!cancelled) setMsg('failed to load config');
      });
    fetch(`${origin}/admin/config/diff`, { credentials: 'include' })
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok || cancelled) return;
        setDiffRows(body.diff || []);
      })
      .catch(() => undefined);
    return () => {
      cancelYaml();
      cancelAgent();
      cancelKeys();
      cancelled = true;
    };
  }, [origin, loadYaml, loadAgent, loadApiKeys]);

  const mintApiKey = async () => {
    setError(null);
    setNotice(null);
    setApiKeyBusy(true);
    try {
      const days = Number(apiKeyDays);
      const res = await fetch(`${origin}/rest/v1/api-keys`, {
        method: 'POST',
        credentials: 'include',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          name: apiKeyName.trim() || 'api-key',
          expires_days: Number.isFinite(days) && days > 0 ? days : 90,
        }),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(apiError(body, res));
        return;
      }
      setMintedToken(typeof body.token === 'string' ? body.token : null);
      setMintedMeta({
        name: body.name || apiKeyName,
        expires_at: body.expires_at,
      });
      setNotice('API key minted — copy it now; it will not be shown again.');
      loadApiKeys();
    } catch (err) {
      setError(String(err));
    } finally {
      setApiKeyBusy(false);
    }
  };

  const revokeApiKey = async (jti: string) => {
    setError(null);
    setNotice(null);
    setApiKeyBusy(true);
    try {
      const res = await fetch(`${origin}/rest/v1/api-keys/${encodeURIComponent(jti)}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: mutHeaders(),
      });
      if (res.status !== 204 && !res.ok) {
        const body = await readJson(res);
        setError(apiError(body, res));
        return;
      }
      setNotice(`Revoked key ${jti.slice(0, 8)}…`);
      loadApiKeys();
    } catch (err) {
      setError(String(err));
    } finally {
      setApiKeyBusy(false);
    }
  };

  const copyMintedToken = async () => {
    if (!mintedToken) return;
    try {
      await navigator.clipboard.writeText(mintedToken);
      setMsg('API token copied to clipboard');
    } catch {
      setMsg(mintedToken);
    }
  };

  const setGraphFiling = async (enabled: boolean) => {
    setError(null);
    setNotice(null);
    setFilingBusy(true);
    try {
      const res = await fetch(`${origin}/admin/config`, {
        method: 'PUT',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          updates: { OIE_GRAPH_FILING_ENABLED: enabled ? '1' : '0' },
        }),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(body.description || body.error || res.statusText);
        return;
      }
      setFilingEnabled(enabled);
      if (Array.isArray(body.config)) setRows(body.config);
      setNotice(
        enabled
          ? 'C.1 auto-filing on — high-confidence linked decisions will be added to the graph'
          : 'C.1 auto-filing off — Module C results stay in decision_queue for review'
      );
    } catch (err) {
      setError(String(err));
    } finally {
      setFilingBusy(false);
    }
  };

  const runGoldenHarvest = async () => {
    setError(null);
    setNotice(null);
    setBusy('golden');
    try {
      const res = await fetch(`${origin}/admin/ingest/start`, {
        method: 'POST',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ packaged: true, max_repos: 50 }),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(body.description || body.error || res.statusText);
        return;
      }
      setNotice(
        `Golden-set harvest started (${body.source})${body.async ? ' — watch Pipeline for stage logs' : ''}`
      );
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(null);
    }
  };

  const runUpstreamSyncAndIngest = async () => {
    setError(null);
    setNotice(null);
    setBusy('upstream');
    try {
      const res = await fetch(`${origin}/admin/upstream-sync-and-ingest`, {
        method: 'POST',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ packaged: true, max_repos: 50 }),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(body.description || body.error || res.statusText);
        return;
      }
      setNotice(
        `Upstream CRE sync + harvest started (${body.source})` +
          `${body.async ? ' — watch Pipeline for upstream_sync then oie' : ''}`
      );
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(null);
    }
  };

  const runAgentSync = async () => {
    setError(null);
    setNotice(null);
    setBusy('agent');
    try {
      const res = await fetch(`${origin}/admin/agent/sync`, {
        method: 'POST',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ auto_concepts: true }),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(body.description || body.error || res.statusText);
        return;
      }
      setNotice(
        `OWASP agent sync started (run ${String(body.run_id || '').slice(0, 8)}…)` +
          `${body.async ? ' — watch Pipeline for agent_sync events' : ''}` +
          `${body.skip_nest ? ' (Nest skipped — no NEST_API_KEY)' : ''}`
      );
      loadAgent();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(null);
    }
  };

  const saveYaml = async () => {
    try {
      const res = await fetch(`${origin}/admin/repos.yaml`, {
        method: 'PUT',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ yaml: yamlText }),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(body.description || body.error || res.statusText);
        return;
      }
      setError(null);
      setYamlText(body.yaml ?? yamlText);
      setYamlSource(body.source || '');
      setNotice(`Saved ${body.source}`);
    } catch (err) {
      setError(String(err));
    }
  };

  const addOrg = async () => {
    if (!org.trim()) {
      setError('GitHub org is required');
      return;
    }
    try {
      const res = await fetch(`${origin}/admin/repos.yaml/expand-org`, {
        method: 'POST',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ yaml: yamlText, owner: org.trim(), cron: orgCron.trim() }),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(body.description || body.error || res.statusText);
        return;
      }
      const saved = await fetch(`${origin}/admin/repos.yaml`, {
        method: 'PUT',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ yaml: body.yaml }),
      });
      const savedBody = await readJson(saved);
      if (!saved.ok) {
        setError(savedBody.description || savedBody.error || saved.statusText);
        return;
      }
      setError(null);
      setYamlText(savedBody.yaml ?? body.yaml);
      setYamlSource(savedBody.source || body.source || '');
      const added = Number(body.added || 0);
      setNotice(
        added
          ? `Saved source ${body.source_url || org.trim()}. Indexer expands it on ingest.`
          : `Source ${body.source_url || org.trim()} is already in the yaml`
      );
    } catch (err) {
      setError(String(err));
    }
  };

  const addTarget = async () => {
    if (!form.owner.trim() || !form.repo.trim()) {
      setError('owner and repo are required');
      return;
    }
    try {
      const res = await fetch(`${origin}/admin/repos.yaml/add-repo`, {
        method: 'POST',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ yaml: yamlText, ...repoSpec(form) }),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(body.description || body.error || res.statusText);
        return;
      }
      const saved = await fetch(`${origin}/admin/repos.yaml`, {
        method: 'PUT',
        headers: mutHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ yaml: body.yaml }),
      });
      const savedBody = await readJson(saved);
      if (!saved.ok) {
        setError(savedBody.description || savedBody.error || saved.statusText);
        return;
      }
      setError(null);
      setYamlText(savedBody.yaml ?? body.yaml);
      setYamlSource(savedBody.source || body.source || '');
      setNotice(`Added target ${body.added}`);
      setOpen(false);
      setForm(emptyRepo());
    } catch (err) {
      setError(String(err));
    }
  };

  const copyRow = async (row: any) => {
    const line = `${row.key}=${row.value ?? ''}`;
    try {
      await navigator.clipboard.writeText(line);
      setMsg(`Copied ${row.key}`);
    } catch {
      setMsg(line);
    }
  };

  const counts = agent?.counts || {};
  const filteredDiff = diffFilter === 'all' ? diffRows : diffRows.filter((row) => row.status === diffFilter);
  return (
    <div>
      {error && <Message negative>{error}</Message>}
      {notice && <Message>{notice}</Message>}
      {msg && <Message>{msg}</Message>}
      <h3>Environment vs .env</h3>
      <p className="admin-help">
        Compare process environment to the on-disk <code>.env</code> (secrets redacted). Match means values
        agree; Diff means they disagree; Missing means present in one side only.
      </p>
      <div className="admin-toolbar">
        <select value={diffFilter} onChange={(e) => setDiffFilter(e.target.value)} aria-label="Diff filter">
          <option value="all">All</option>
          <option value="match">Match</option>
          <option value="diff">Diff</option>
          <option value="missing">Missing in process</option>
          <option value="process_only">Process only</option>
        </select>
        <span className="admin-muted">{filteredDiff.length} keys</span>
      </div>
      {filteredDiff.length > 0 && (
        <Table celled compact size="small" className="admin-config-diff">
          <Table.Header>
            <Table.Row>
              <Table.HeaderCell>Key</Table.HeaderCell>
              <Table.HeaderCell>Status</Table.HeaderCell>
              <Table.HeaderCell>Process env</Table.HeaderCell>
              <Table.HeaderCell>.env</Table.HeaderCell>
            </Table.Row>
          </Table.Header>
          <Table.Body>
            {filteredDiff.map((row) => (
              <Table.Row key={row.key} className={`admin-diff-${row.status}`}>
                <Table.Cell>
                  <code>{row.key}</code>
                </Table.Cell>
                <Table.Cell>{row.status}</Table.Cell>
                <Table.Cell>
                  <code>{row.process ?? '—'}</code>
                </Table.Cell>
                <Table.Cell>
                  <code>{row.dotenv ?? '—'}</code>
                </Table.Cell>
              </Table.Row>
            ))}
          </Table.Body>
        </Table>
      )}
      <h3>End-to-end bootstrap</h3>
      <p className="admin-help">
        CRE explorer graph comes from upstream (<code>opencre.org</code>). Use the upstream+harvest button
        below (or <code>make install</code> / <code>make dev</code>; skip with{' '}
        <code>SKIP_UPSTREAM_SYNC=1</code>) to pull the CRE hub then run packaged harvest A → B → C → C.1.
        Golden-set harvest skips the upstream pull. C.1 only auto-files high-confidence links when the toggle
        below is on (default off — review <code>decision_queue</code> first). OWASP agent sync is separate —
        progress shows under Pipeline.
      </p>
      <p>
        <Checkbox
          toggle
          label={
            filingEnabled
              ? 'C.1 auto-file high-confidence links (on)'
              : 'C.1 auto-file high-confidence links (off — review first)'
          }
          checked={filingEnabled}
          disabled={filingBusy}
          onChange={(_e, data) => setGraphFiling(Boolean(data.checked))}
        />
      </p>
      <p>
        OWASP agent: enabled={String(agent?.enabled ?? '…')} · db={agent?.db_url || '—'}
        {agent?.last_sync ? ` · last_sync=${agent.last_sync}` : ''}
        {counts && Object.keys(counts).length ? ` · rows=${JSON.stringify(counts)}` : ''}
      </p>
      <p>
        <Button primary size="mini" disabled={!!busy} onClick={runUpstreamSyncAndIngest}>
          {busy === 'upstream' ? 'Starting…' : 'Import upstream CRE + harvest'}
        </Button>{' '}
        <Button size="mini" disabled={!!busy} onClick={runGoldenHarvest}>
          {busy === 'golden' ? 'Starting…' : 'Run golden-set harvest'}
        </Button>{' '}
        <Button size="mini" disabled={!!busy || agent?.enabled === false} onClick={runAgentSync}>
          {busy === 'agent' ? 'Starting…' : 'Sync OWASP agent'}
        </Button>
      </p>
      <p>
        <Button
          primary
          size="small"
          onClick={() => {
            setApiKeysOpen(true);
            loadApiKeys();
          }}
        >
          Manage API keys
        </Button>
        <span className="admin-help" style={{ marginLeft: '0.75rem' }}>
          Mint, name, and revoke JWT API keys (shows expiration).
        </span>
      </p>
      <h3>targets.yaml</h3>
      <p className="admin-help">
        Packaged harvester file (<code>repos.yaml</code>) — the golden-set list used by Run golden-set
        harvest. Each source/repo can set a 5-field cron. Add org and Add target probe GitHub, then save.
      </p>
      <p>
        Source: <code>{yamlSource || 'repos.yaml:&lt;hash&gt;'}</code>
      </p>
      <p>
        <input placeholder="GitHub org" value={org} onChange={(e) => setOrg(e.target.value)} />
        <input placeholder="cron" value={orgCron} onChange={(e) => setOrgCron(e.target.value)} />
        <Button size="mini" onClick={addOrg}>
          Add org
        </Button>
        <Button size="mini" onClick={() => setOpen(true)}>
          Add target
        </Button>
        <Button size="mini" onClick={saveYaml}>
          Save repos.yaml
        </Button>
      </p>
      <textarea
        className="admin-yaml"
        aria-label="repos.yaml"
        value={yamlText}
        onChange={(e) => setYamlText(e.target.value)}
      />
      <h3>Environment</h3>
      {instructions && <p className="admin-help">{instructions}</p>}
      <table className="admin-table">
        <thead>
          <tr>
            <th>Key</th>
            <th>Value</th>
            <th>Help</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <td>{row.key}</td>
              <td>{row.value ?? '—'}</td>
              <td className="admin-help">
                {row.help_text}{' '}
                <a href={row.help_url} target="_blank" rel="noreferrer">
                  docs
                </a>
              </td>
              <td>
                {!row.secret && (
                  <Button size="mini" onClick={() => copyRow(row)}>
                    Copy
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Modal open={open} onClose={() => setOpen(false)}>
        <Modal.Header>Add target</Modal.Header>
        <Modal.Content>
          <RepoFormFields form={form} setForm={setForm} />
        </Modal.Content>
        <Modal.Actions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button primary onClick={addTarget}>
            Add
          </Button>
        </Modal.Actions>
      </Modal>
      <Modal open={apiKeysOpen} onClose={() => setApiKeysOpen(false)} size="large">
        <Modal.Header>API keys</Modal.Header>
        <Modal.Content scrolling>
          <p className="admin-help">
            JWT Bearer tokens for write routes, Admin APIs, and My OpenCRE. Each key has a name and
            expiration. The secret is shown once at mint — use{' '}
            <code>Authorization: Bearer &lt;token&gt;</code> or <code>X-API-Key</code>. Allowlisted admins
            only.
          </p>
          <Form
            onSubmit={(e) => {
              e.preventDefault();
              mintApiKey();
            }}
          >
            <Form.Group widths="equal">
              <Form.Input
                label="Name"
                aria-label="API key name"
                placeholder="e.g. staging-ci"
                value={apiKeyName}
                onChange={(e) => setApiKeyName(e.target.value)}
              />
              <Form.Input
                label="Expires (days)"
                aria-label="API key expires days"
                placeholder="90"
                value={apiKeyDays}
                onChange={(e) => setApiKeyDays(e.target.value)}
              />
            </Form.Group>
            <Button primary type="submit" disabled={apiKeyBusy} size="small">
              {apiKeyBusy ? 'Working…' : 'Mint API key'}
            </Button>
          </Form>
          <table className="admin-table" style={{ marginTop: '1rem' }}>
            <thead>
              <tr>
                <th>Name</th>
                <th>jti</th>
                <th>Expires</th>
                <th>Last used</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {apiKeys.length === 0 ? (
                <tr>
                  <td colSpan={6} className="admin-help">
                    No API keys yet.
                  </td>
                </tr>
              ) : (
                apiKeys.map((key) => (
                  <tr key={key.jti}>
                    <td>{key.name}</td>
                    <td>
                      <code>{key.jti.slice(0, 8)}…</code>
                    </td>
                    <td>{key.expires_at || '—'}</td>
                    <td>{key.last_used_at || '—'}</td>
                    <td>{key.revoked_at ? 'revoked' : 'active'}</td>
                    <td>
                      {!key.revoked_at && (
                        <Button size="mini" disabled={apiKeyBusy} onClick={() => revokeApiKey(key.jti)}>
                          Revoke
                        </Button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Modal.Content>
        <Modal.Actions>
          <Button onClick={() => setApiKeysOpen(false)}>Close</Button>
        </Modal.Actions>
      </Modal>
      <Modal
        open={!!mintedToken}
        onClose={() => {
          setMintedToken(null);
          setMintedMeta(null);
        }}
      >
        <Modal.Header>API key minted</Modal.Header>
        <Modal.Content>
          <p className="admin-help">
            Copy this token now for {mintedMeta?.name || 'key'}
            {mintedMeta?.expires_at ? ` (expires ${mintedMeta.expires_at})` : ''}. It cannot be retrieved
            again.
          </p>
          <pre className="admin-pre" aria-label="minted API token">
            {mintedToken}
          </pre>
        </Modal.Content>
        <Modal.Actions>
          <Button onClick={copyMintedToken}>Copy token</Button>
          <Button
            primary
            onClick={() => {
              setMintedToken(null);
              setMintedMeta(null);
            }}
          >
            Done
          </Button>
        </Modal.Actions>
      </Modal>
    </div>
  );
}
