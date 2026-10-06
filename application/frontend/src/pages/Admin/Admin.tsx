import './Admin.scss';

import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Form, Message, Modal, Header as SUIHeader } from 'semantic-ui-react';

import { useCapabilities, useEnvironment } from '../../hooks';
import { useUser } from '../../hooks/useUser';

type Tab = 'dashboard' | 'config' | 'pipeline' | 'graph' | 'myopencre';

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

export const Admin = () => {
  const { apiUrl } = useEnvironment();
  const { isLoggedIn, loading, login } = useUser();
  const { capabilities, loading: capsLoading } = useCapabilities();
  const [tab, setTab] = useState<Tab>('dashboard');
  const origin = adminOrigin(apiUrl);

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
        <p>Sign in to continue.</p>
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

  return (
    <div className="admin-page">
      <SUIHeader as="h1">Admin</SUIHeader>
      <div className="admin-tabs">
        {(
          [
            ['dashboard', 'Dashboard'],
            ['config', 'Config'],
            ['pipeline', 'Pipeline'],
            ['graph', 'Graph management'],
            ['myopencre', 'MyOpenCRE'],
          ] as [Tab, string][]
        ).map(([id, label]) => (
          <Button key={id} primary={tab === id} onClick={() => setTab(id)}>
            {label}
          </Button>
        ))}
      </div>
      {tab === 'dashboard' && <DashboardTab origin={origin} onOpenJobs={() => setTab('pipeline')} />}
      {tab === 'config' && <ConfigTab origin={origin} />}
      {tab === 'pipeline' && <PipelineTab origin={origin} />}
      {tab === 'graph' && <GraphManagementTab origin={origin} />}
      {tab === 'myopencre' && (
        <Link className="ui primary button" to="/myopencre">
          Open MyOpenCRE
        </Link>
      )}
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

function DashboardTab({ origin, onOpenJobs }: { origin: string; onOpenJobs: () => void }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(`${origin}/admin/dashboard`)
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
  if (error) return <Message negative>{error}</Message>;
  if (!data) return <p>Loading dashboard…</p>;
  const agent = data.agent || {};
  return (
    <div>
      <h3>Jobs</h3>
      <StageStrip steps={data.latest_strip} />
      <p>
        Running: {(data.running || []).length} · Failed: {(data.failed || []).length} · OIE unconsumed:{' '}
        {data.oie_unconsumed ?? 0}{' '}
        <Button size="mini" onClick={onOpenJobs}>
          Job management and logs
        </Button>
      </p>
      {(data.running || []).length === 0 && (data.import_runs || []).length === 0 && <p>No jobs running.</p>}
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
              <td>{r.source}</td>
              <td>{r.staging_status || '—'}</td>
              <td>{r.created_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>OWASP agent</h3>
      <p>
        Enabled: {String(agent.enabled)} · package: {String(agent.package_present)} · writes CRE graph:{' '}
        {String(agent.writes_cre_graph)}
      </p>
      <p>
        Main DB{agent.db_env_key ? ` (${agent.db_env_key})` : ''}: {agent.db_url || '—'}
      </p>
      <Link className="ui mini button" to={agent.demo_path || '/chatbot'}>
        Open chat demo
      </Link>
    </div>
  );
}

function GraphManagementTab({ origin }: { origin: string }) {
  const [runs, setRuns] = useState<any[]>([]);
  const [detail, setDetail] = useState<any>(null);
  const [graph, setGraph] = useState<any>(null);
  const [links, setLinks] = useState<any[]>([]);
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
      const res = await fetch(`${origin}/admin/imports/runs/${runId}/${path}`, { method });
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

  const openRun = async (runId: string) => {
    setError(null);
    setNotice(null);
    try {
      const [csRes, linkRes] = await Promise.all([
        fetch(`${origin}/admin/imports/runs/${runId}/changeset`),
        fetch(`${origin}/admin/imports/runs/${runId}/links`),
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
        headers: { 'Content-Type': 'application/json' },
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
        headers: { 'Content-Type': 'application/json' },
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
        changeset. OIE harvest runs often have an empty CRE changeset (chunks live in harvest_input);
        Accept still marks review status. Apply writes standard node fields; CRE edge apply is
        follow-on.
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
                  <Button
                    size="mini"
                    disabled={!!rowBusy || terminal}
                    onClick={() => act(run.id, 'discard')}
                  >
                    Discard
                  </Button>
                  <Button
                    size="mini"
                    disabled={!!rowBusy || status === 'discarded'}
                    onClick={() => act(run.id, 'apply?dry_run=1')}
                  >
                    Dry-run
                  </Button>
                  <Button
                    size="mini"
                    disabled={!!rowBusy}
                    onClick={() => act(run.id, 'impact', 'GET')}
                  >
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
        <div>
          <h3>Added controls and links</h3>
          {links.length === 0 ? (
            <p>No staged links on this run.</p>
          ) : (
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Added</th>
                  <th>Linked to</th>
                  <th>Decision</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {links.map((row: any) => {
                  const key = `${row.op_index}:${row.link_index}`;
                  const added = row.added || {};
                  const linked = row.linked_to;
                  return (
                    <tr key={key}>
                      <td>
                        {added.op} {added.name} {added.section} {added.sectionID}
                      </td>
                      <td>{linked ? `${linked.id} ${linked.name}`.trim() : '—'}</td>
                      <td>{row.decision}</td>
                      <td>
                        {linked && (
                          <>
                            <Button size="mini" onClick={() => review(detail.run_id, row, 'approve')}>
                              Approve
                            </Button>
                            <Button size="mini" onClick={() => review(detail.run_id, row, 'deny')}>
                              Deny
                            </Button>
                          </>
                        )}
                        <input
                          placeholder="relink CRE id or name"
                          value={relink[key] || ''}
                          onChange={(e) => setRelink({ ...relink, [key]: e.target.value })}
                        />
                        <Button size="mini" onClick={() => review(detail.run_id, row, 'relink')}>
                          Relink
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

function PipelineTab({ origin }: { origin: string }) {
  const [data, setData] = useState<any>(null);
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

  useEffect(() => load(), [load]);

  const startCurrent = async () => {
    setError(null);
    try {
      const res = await fetch(`${origin}/admin/ingest/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ yaml: 'sources: []\n', ...repoSpec(form) }),
      });
      const builtBody = await readJson(built);
      if (!built.ok) {
        setError(builtBody.description || builtBody.error || built.statusText);
        return;
      }
      const res = await fetch(`${origin}/admin/ingest/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
  return (
    <div>
      {error && <Message negative>{error}</Message>}
      {notice && <Message>{notice}</Message>}
      <p>
        <Button primary size="mini" onClick={() => setOpen(true)}>
          New
        </Button>
      </p>
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
      <table className="admin-table">
        <thead>
          <tr>
            <th>Stage</th>
            <th>Status</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {(data.events || []).map((e: any) => (
            <tr key={e.id}>
              <td>{e.stage}</td>
              <td>{e.status}</td>
              <td>{e.detail}</td>
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

  useEffect(() => {
    const cancelYaml = loadYaml();
    let cancelled = false;
    fetch(`${origin}/admin/config`)
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(body.description || body.error || res.statusText);
        if (cancelled) return;
        setRows(body.config || []);
        setInstructions(body.restart_instructions || '');
      })
      .catch(() => {
        if (!cancelled) setMsg('failed to load config');
      });
    return () => {
      cancelYaml();
      cancelled = true;
    };
  }, [origin, loadYaml]);

  const saveYaml = async () => {
    try {
      const res = await fetch(`${origin}/admin/repos.yaml`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ yaml: yamlText, owner: org.trim(), cron: orgCron.trim() }),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(body.description || body.error || res.statusText);
        return;
      }
      const saved = await fetch(`${origin}/admin/repos.yaml`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ yaml: yamlText, ...repoSpec(form) }),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(body.description || body.error || res.statusText);
        return;
      }
      const saved = await fetch(`${origin}/admin/repos.yaml`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
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

  return (
    <div>
      {error && <Message negative>{error}</Message>}
      {notice && <Message>{notice}</Message>}
      {msg && <Message>{msg}</Message>}
      <h3>targets.yaml</h3>
      <p className="admin-help">
        Packaged harvester file (<code>repos.yaml</code>). Each source/repo can set a 5-field cron for how
        often ingest runs. Add org and Add target probe GitHub, then save the packaged file. You can still
        edit the yaml and click Save repos.yaml.
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
    </div>
  );
}
