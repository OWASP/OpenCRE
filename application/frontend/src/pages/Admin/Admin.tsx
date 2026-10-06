import './Admin.scss';

import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Message, Header as SUIHeader } from 'semantic-ui-react';

import { useCapabilities, useEnvironment } from '../../hooks';
import { useUser } from '../../hooks/useUser';

type Tab = 'imports' | 'pipeline' | 'targets' | 'config' | 'myopencre';

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
            ['imports', 'Import review'],
            ['pipeline', 'Pipeline'],
            ['targets', 'Resources'],
            ['config', 'Config'],
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
      {tab === 'targets' && <ResourcesTab origin={origin} />}
      {tab === 'config' && <ConfigTab origin={origin} />}
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
    try {
      const res = await fetch(`${origin}/admin/imports/runs/${runId}/${path}`, { method });
      const body = await readJson(res);
      if (!res.ok) {
        setError(body.description || body.error || res.statusText);
        return;
      }
      setDetail(body);
      load();
    } catch (err) {
      setError(String(err));
    }
  };

  const openRun = async (runId: string) => {
    setError(null);
    try {
      const res = await fetch(`${origin}/admin/imports/runs/${runId}/changeset`);
      const body = await readJson(res);
      if (!res.ok) {
        setError(body.description || body.error || res.statusText);
        return;
      }
      setDetail(body);
      setGraph(null);
      const next: Record<number, string> = {};
      (body.changeset || []).forEach((op: any, i: number) => {
        next[i] = JSON.stringify(op.after || op.document || {}, null, 2);
      });
      setDrafts(next);
    } catch (err) {
      setError(String(err));
    }
  };

  const openGraph = async (runId: string) => {
    setError(null);
    try {
      const res = await fetch(`${origin}/admin/imports/runs/${runId}/changeset/graph`);
      const body = await readJson(res);
      if (!res.ok) setError(body.description || body.error || res.statusText);
      else setGraph(body);
    } catch (err) {
      setError(String(err));
    }
  };

  const saveMapping = async (runId: string, opIndex: number) => {
    let after: unknown;
    try {
      after = JSON.parse(drafts[opIndex] || '{}');
    } catch {
      setError('Mapping JSON is invalid');
      return;
    }
    try {
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
      if (!res.ok) setError(body.description || body.error || res.statusText);
      else {
        setDetail(body);
        load();
      }
    } catch (err) {
      setError(String(err));
    }
  };

  const ops = Array.isArray(detail?.changeset) ? detail.changeset : [];

  return (
    <div>
      {error && <Message negative>{error}</Message>}
      {Array.isArray(detail?.warnings) && detail.warnings.length > 0 && (
        <Message warning>{detail.warnings.join(' ')}</Message>
      )}
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

function AgentResourceDetail({ spec }: { spec: any }) {
  if (!spec) return null;
  return (
    <div>
      <p>
        Enabled: {String(spec.enabled)} · package: {String(spec.package_present)} · writes CRE graph:{' '}
        {String(spec.writes_cre_graph)}
      </p>
      <p>Agent DB configured: {String(spec.db_configured)}</p>
      <p>DB URL: {spec.db_url || '—'}</p>
      <p>Last sync: {spec.last_sync || '—'}</p>
      <p>Counts: {spec.counts ? JSON.stringify(spec.counts) : '—'}</p>
      {(spec.params || []).map((p: any) => (
        <p key={p.key} className="admin-help" title={p.help_text}>
          {p.key}={p.value || '—'}{' '}
          <a href={p.help_url} target="_blank" rel="noreferrer">
            docs
          </a>
        </p>
      ))}
      <p className="admin-help">
        <a href={spec.help_url} target="_blank" rel="noreferrer">
          Agent README
        </a>
      </p>
      <Link className="ui mini button" to={spec.demo_path || '/chatbot'}>
        Open chat demo
      </Link>
    </div>
  );
}

function ResourcesTab({ origin }: { origin: string }) {
  const [targets, setTargets] = useState<any[]>([]);
  const [id, setId] = useState('');
  const [kind, setKind] = useState('import_source');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [yamlText, setYamlText] = useState('');
  const [yamlSource, setYamlSource] = useState('');
  const [customName, setCustomName] = useState('');
  const [org, setOrg] = useState('');

  const loadTargets = useCallback(() => {
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
    const cancelTargets = loadTargets();
    const cancelYaml = loadYaml();
    return () => {
      cancelTargets();
      cancelYaml();
    };
  }, [loadTargets, loadYaml]);

  const add = async () => {
    if (!id.trim()) {
      setError('id and kind are required');
      return;
    }
    try {
      const res = await fetch(`${origin}/admin/targets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: id.trim(), kind, name: id.trim() }),
      });
      if (!res.ok) {
        const body = await readJson(res);
        setError(body.description || body.error || res.statusText);
        return;
      }
      setError(null);
      setNotice(null);
      setId('');
      loadTargets();
    } catch (err) {
      setError(String(err));
    }
  };

  const start = async (targetId: string) => {
    try {
      const res = await fetch(`${origin}/admin/ingest/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_id: targetId,
          name: customName.trim() || undefined,
        }),
      });
      const body = await readJson(res);
      if (!res.ok) setError(body.description || body.error || res.statusText);
      else {
        setError(null);
        setNotice(`Started import source ${body.source}`);
        loadTargets();
      }
    } catch (err) {
      setError(String(err));
    }
  };

  const del = async (targetId: string) => {
    try {
      const res = await fetch(`${origin}/admin/targets/${encodeURIComponent(targetId)}`, {
        method: 'DELETE',
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(body.description || body.error || res.statusText);
        return;
      }
      setError(null);
      setNotice(null);
      loadTargets();
    } catch (err) {
      setError(String(err));
    }
  };

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

  const startOneOff = async () => {
    try {
      const res = await fetch(`${origin}/admin/ingest/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          yaml: yamlText,
          name: customName.trim() || undefined,
        }),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(body.description || body.error || res.statusText);
        return;
      }
      setError(null);
      setNotice(`Started import source ${body.source}`);
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
        body: JSON.stringify({ yaml: yamlText, owner: org.trim() }),
      });
      const body = await readJson(res);
      if (!res.ok) {
        setError(body.description || body.error || res.statusText);
        return;
      }
      setError(null);
      if (typeof body.yaml === 'string') setYamlText(body.yaml);
      if (typeof body.source === 'string') setYamlSource(body.source);
      const added = Number(body.added || 0);
      setNotice(
        added
          ? `Added source ${body.source_url || org.trim()}. Indexer expands it on ingest.`
          : `Source ${body.source_url || org.trim()} is already in the yaml`
      );
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div>
      {error && <Message negative>{error}</Message>}
      {notice && <Message>{notice}</Message>}
      <h3>repos.yaml</h3>
      <p className="admin-help">
        Save writes the packaged harvester file immediately. Add org appends
        <code>github.com/org/</code> — the indexer expands that later and routes each repo to OpenCRE or the
        OWASP agent. Start one-off uses this editor yaml without overwriting the packaged file. Import review
        source is the optional name, otherwise <code>repos.yaml:&lt;hash&gt;</code>. Start is always dry-run;
        git sync is off.
      </p>
      <p>
        Import review source: <code>{customName.trim() || yamlSource || 'repos.yaml:&lt;hash&gt;'}</code>
      </p>
      <p>
        <input
          placeholder="optional source name"
          value={customName}
          onChange={(e) => setCustomName(e.target.value)}
        />
        <input placeholder="GitHub org" value={org} onChange={(e) => setOrg(e.target.value)} />
        <Button size="mini" onClick={addOrg}>
          Add org
        </Button>
        <Button size="mini" onClick={saveYaml}>
          Save repos.yaml
        </Button>
        <Button size="mini" onClick={startOneOff}>
          Start one-off
        </Button>
      </p>
      <textarea
        className="admin-yaml"
        aria-label="repos.yaml"
        value={yamlText}
        onChange={(e) => setYamlText(e.target.value)}
      />
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
      <table className="admin-table">
        <thead>
          <tr>
            <th>Id</th>
            <th>Kind</th>
            <th>Detail</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {targets.map((t) => (
            <tr key={t.id}>
              <td>{t.id}</td>
              <td>{t.kind}</td>
              <td>{t.kind === 'owasp_agent' ? <AgentResourceDetail spec={t.spec} /> : t.name || '—'}</td>
              <td>
                <Button size="mini" onClick={() => start(t.id)}>
                  Start now
                </Button>
                {!t.built_in && t.kind !== 'owasp_agent' && t.id !== 'owasp-agent' && (
                  <Button size="mini" onClick={() => del(t.id)}>
                    Remove
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
