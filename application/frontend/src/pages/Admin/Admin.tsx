import './Admin.scss';

import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Message, Header as SUIHeader } from 'semantic-ui-react';

import { useEnvironment } from '../../hooks';
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
  const [tab, setTab] = useState<Tab>('imports');
  const origin = adminOrigin(apiUrl);

  if (loading) {
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

function ImportsTab({ origin }: { origin: string }) {
  const [runs, setRuns] = useState<any[]>([]);
  const [detail, setDetail] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState('');

  const load = useCallback(() => {
    fetch(`${origin}/admin/imports/runs`)
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(body.description || body.error || res.statusText);
        setRuns(body.runs || []);
      })
      .catch((err) => setError(String(err)));
  }, [origin]);

  useEffect(() => {
    load();
  }, [load]);

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
    setDetail(await readJson(res));
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
      {detail && <pre className="admin-pre">{JSON.stringify(detail, null, 2)}</pre>}
    </div>
  );
}

function PipelineTab({ origin }: { origin: string }) {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    fetch(`${origin}/admin/pipeline`)
      .then((res) => res.json())
      .then(setData)
      .catch(() => setData({ error: 'failed to load pipeline' }));
  }, [origin]);
  if (!data) return <p>Loading pipeline…</p>;
  return (
    <div>
      <h3>Import runs</h3>
      <ol>
        {(data.import_runs || []).map((r: any) => (
          <li key={r.id}>
            {r.source} — {r.staging_status || 'none'}
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
    </div>
  );
}

function TargetsTab({ origin }: { origin: string }) {
  const [targets, setTargets] = useState<any[]>([]);
  const [id, setId] = useState('');
  const [kind, setKind] = useState('import_source');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetch(`${origin}/admin/targets`)
      .then((res) => res.json())
      .then((body) => setTargets(body.targets || []))
      .catch((err) => setError(String(err)));
  }, [origin]);

  useEffect(() => {
    load();
  }, [load]);

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
      body: JSON.stringify({ target_id: targetId, dry_run: true }),
    });
    const body = await readJson(res);
    if (!res.ok) setError(body.description || body.error || res.statusText);
    else load();
  };

  const del = async (targetId: string) => {
    await fetch(`${origin}/admin/targets/${encodeURIComponent(targetId)}`, { method: 'DELETE' });
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
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${origin}/admin/config`)
      .then((res) => res.json())
      .then((body) => setRows(body.config || []))
      .catch(() => setMsg('failed to load config'));
  }, [origin]);

  return (
    <div>
      {msg && <Message>{msg}</Message>}
      <table className="admin-table">
        <thead>
          <tr>
            <th>Key</th>
            <th>Value</th>
            <th>Help</th>
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
    fetch(`${origin}/admin/agent/status`)
      .then(async (res) => {
        const body = await readJson(res);
        if (!res.ok) throw new Error(body.description || body.error || res.statusText);
        setStatus(body);
      })
      .catch((err) => setError(String(err)));
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
