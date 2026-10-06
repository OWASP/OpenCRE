import './Admin.scss';

import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Message, Header as SUIHeader } from 'semantic-ui-react';

import { useCapabilities, useEnvironment } from '../../hooks';
import { useUser } from '../../hooks/useUser';

type Tab = 'imports' | 'pipeline' | 'targets' | 'config' | 'agent' | 'myopencre';

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
    return { error: text || res.statusText };
  }
}

export const Admin = () => {
  const { apiUrl } = useEnvironment();
  const { isLoggedIn, loading, login } = useUser();
  const { capabilities, loading: capsLoading } = useCapabilities();
  const [tab, setTab] = useState<Tab>('imports');
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
        <p>Sign in to use the admin showcase.</p>
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
            ['imports', 'Import review'],
            ['pipeline', 'Pipeline'],
            ['targets', 'Targets'],
            ['config', 'Config'],
            ['agent', 'OWASP agent'],
            ['myopencre', 'MyOpenCRE'],
          ] as [Tab, string][]
        ).map(([id, label]) => (
          <Button key={id} primary={tab === id} onClick={() => setTab(id)}>
            {label}
          </Button>
        ))}
      </div>
      {tab === 'imports' && <ImportsTab origin={origin} />}
      {tab === 'pipeline' && <PipelineTab origin={origin} />}
      {tab === 'targets' && <TargetsTab origin={origin} />}
      {tab === 'config' && <ConfigTab origin={origin} />}
      {tab === 'agent' && <AgentTab origin={origin} />}
      {tab === 'myopencre' && (
        <div>
          <p>CSV catalogue upload stays on its own URL.</p>
          <Link className="ui primary button" to="/myopencre">
            Open MyOpenCRE
          </Link>
        </div>
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

function ImportsTab({ origin }: { origin: string }) {
  const [runs, setRuns] = useState<any[]>([]);
  const [detail, setDetail] = useState<any>(null);
  const [graph, setGraph] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState('');
  const [drafts, setDrafts] = useState<Record<number, string>>({});

  const load = useCallback(() => {
    let cancelled = false;
    fetch(`${origin}/admin/imports/runs`)
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(body.description || body.error || res.statusText);
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
    const res = await fetch(`${origin}/admin/imports/runs/${runId}/${path}`, { method });
    const body = await readJson(res);
    if (!res.ok) {
      setError(body.description || body.error || res.statusText);
      return;
    }
    setDetail(body);
    load();
  };

  const openRun = async (runId: string) => {
    const res = await fetch(`${origin}/admin/imports/runs/${runId}/changeset`);
    const body = await readJson(res);
    setDetail(body);
    setGraph(null);
    const next: Record<number, string> = {};
    (body.changeset || []).forEach((op: any, i: number) => {
      next[i] = JSON.stringify(op.after || op.document || {}, null, 2);
    });
    setDrafts(next);
  };

  const openGraph = async (runId: string) => {
    const res = await fetch(`${origin}/admin/imports/runs/${runId}/changeset/graph`);
    const body = await readJson(res);
    if (!res.ok) setError(body.description || body.error || res.statusText);
    else setGraph(body);
  };

  const saveMapping = async (runId: string, opIndex: number) => {
    let after: unknown;
    try {
      after = JSON.parse(drafts[opIndex] || '{}');
    } catch {
      setError('Mapping JSON is invalid');
      return;
    }
    const res = await fetch(`${origin}/admin/imports/runs/${runId}/mapping`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ op_index: opIndex, after }),
    });
    const body = await readJson(res);
    if (!res.ok) setError(body.description || body.error || res.statusText);
    else {
      setDetail(body);
      load();
    }
  };

  const dropLast = async () => {
    if (!source.trim()) return;
    const res = await fetch(`${origin}/admin/imports/drop-last`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: source.trim() }),
    });
    const body = await readJson(res);
    if (!res.ok) setError(body.description || body.error || res.statusText);
    else {
      setDetail(body);
      load();
    }
  };

  const ops = Array.isArray(detail?.changeset) ? detail.changeset : [];

  return (
    <div>
      {error && <Message negative>{error}</Message>}
      <table className="admin-table">
        <thead>
          <tr>
            <th>Source</th>
            <th>Status</th>
            <th>Created</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td>{run.source}</td>
              <td>{run.staging_status || '—'}</td>
              <td>{run.created_at}</td>
              <td>
                <Button size="mini" onClick={() => openRun(run.id)}>
                  Changeset
                </Button>
                <Button size="mini" onClick={() => openGraph(run.id)}>
                  Graph
                </Button>
                <Button size="mini" onClick={() => act(run.id, 'accept')}>
                  Accept
                </Button>
                <Button size="mini" onClick={() => act(run.id, 'discard')}>
                  Discard
                </Button>
                <Button size="mini" onClick={() => act(run.id, 'apply?dry_run=1')}>
                  Dry-run
                </Button>
                <Button size="mini" onClick={() => act(run.id, 'impact', 'GET')}>
                  Impact
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        Drop last staged ingestion for source{' '}
        <input value={source} onChange={(e) => setSource(e.target.value)} />{' '}
        <Button size="mini" onClick={dropLast}>
          Drop last
        </Button>
      </p>
      <p className="admin-help">
        Applied runs return 409 — graph rollback is not implemented. Edit staged mappings before apply.
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
      {ops.length > 0 && (
        <div>
          <h3>Edit mapping</h3>
          {ops.map((op: any, i: number) => (
            <div key={i} className="admin-map-op">
              <p>
                #{i} {op.op || op.__class__ || 'op'}
              </p>
              <textarea
                value={drafts[i] || ''}
                onChange={(e) => setDrafts({ ...drafts, [i]: e.target.value })}
              />
              <Button size="mini" onClick={() => saveMapping(detail.run_id, i)}>
                Save mapping
              </Button>
            </div>
          ))}
        </div>
      )}
      {detail && <pre className="admin-pre">{JSON.stringify(detail, null, 2)}</pre>}
    </div>
  );
}

function PipelineTab({ origin }: { origin: string }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
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
  if (error) return <Message negative>{error}</Message>;
  if (!data) return <p>Loading pipeline…</p>;
  const empty = !(data.import_runs || []).length && !(data.events || []).length;
  return (
    <div>
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
    </div>
  );
}

function TargetsTab({ origin }: { origin: string }) {
  const [targets, setTargets] = useState<any[]>([]);
  const [id, setId] = useState('');
  const [kind, setKind] = useState('import_source');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    fetch(`${origin}/admin/targets`)
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(body.description || body.error || res.statusText);
        if (!cancelled) setTargets(body.targets || []);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [origin]);

  useEffect(() => load(), [load]);

  const add = async () => {
    const res = await fetch(`${origin}/admin/targets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, kind, name: id }),
    });
    if (!res.ok) {
      const body = await readJson(res);
      setError(body.description || body.error || res.statusText);
      return;
    }
    setId('');
    load();
  };

  const start = async (targetId: string) => {
    const res = await fetch(`${origin}/admin/ingest/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_id: targetId }),
    });
    const body = await readJson(res);
    if (!res.ok) setError(body.description || body.error || res.statusText);
    else load();
  };

  const del = async (targetId: string) => {
    const res = await fetch(`${origin}/admin/targets/${encodeURIComponent(targetId)}`, {
      method: 'DELETE',
    });
    const body = await readJson(res);
    if (!res.ok) {
      setError(body.description || body.error || res.statusText);
      return;
    }
    load();
  };

  return (
    <div>
      {error && <Message negative>{error}</Message>}
      <p>
        <input placeholder="id" value={id} onChange={(e) => setId(e.target.value)} />
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="import_source">import_source</option>
          <option value="oie_repo">oie_repo</option>
        </select>
        <Button size="mini" onClick={add}>
          Add
        </Button>
      </p>
      <p className="admin-help">Start is always dry-run; git sync is off.</p>
      <table className="admin-table">
        <thead>
          <tr>
            <th>Id</th>
            <th>Kind</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {targets.map((t) => (
            <tr key={t.id}>
              <td>{t.id}</td>
              <td>{t.kind}</td>
              <td>
                <Button size="mini" onClick={() => start(t.id)}>
                  Start now
                </Button>
                <Button size="mini" onClick={() => del(t.id)}>
                  Remove
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConfigTab({ origin }: { origin: string }) {
  const [rows, setRows] = useState<any[]>([]);
  const [instructions, setInstructions] = useState('');
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
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
      cancelled = true;
    };
  }, [origin]);

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
      {msg && <Message>{msg}</Message>}
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
    </div>
  );
}

function AgentTab({ origin }: { origin: string }) {
  const [status, setStatus] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(`${origin}/admin/agent/status`)
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(body.description || body.error || res.statusText);
        if (!cancelled) setStatus(body);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [origin]);
  if (error) return <Message negative>{error}</Message>;
  if (!status) return <p>Loading agent…</p>;
  return (
    <div>
      <p>
        Enabled: {String(status.enabled)} · package: {String(status.package_present)} · writes CRE graph:{' '}
        {String(status.writes_cre_graph)}
      </p>
      <p>Agent DB configured: {String(status.db_configured)}</p>
      <p>DB path: {status.db_path || '—'}</p>
      <p>Last sync: {status.last_sync || '—'}</p>
      <p>Counts: {status.counts ? JSON.stringify(status.counts) : '—'}</p>
      {(status.params || []).map((p: any) => (
        <p key={p.key} className="admin-help" title={p.help_text}>
          {p.key}={p.value || '—'}{' '}
          <a href={p.help_url} target="_blank" rel="noreferrer">
            docs
          </a>
        </p>
      ))}
      <p className="admin-help">
        <a href={status.help_url} target="_blank" rel="noreferrer">
          Agent README
        </a>
      </p>
      <Link className="ui primary button" to={status.demo_path || '/chatbot'}>
        Open chat demo
      </Link>
    </div>
  );
}
